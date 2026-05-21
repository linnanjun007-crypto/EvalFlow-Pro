"""Step 1 graph for EvalFlow Pro.

Step 1 implements the client workflow for generating the project document manifest:
1. Accept uploaded source files.
2. Extract metadata and a short summary from each file.
3. Build a draft manifest.
4. Optionally compare multiple model outputs.
5. Allow human review and refinement loops.
6. Mark a final manifest that can later be exported.

This module is intentionally self-contained so you can start developing Step 1
without splitting into extra files yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict
import asyncio
import json
import re
import operator
import zipfile
from xml.etree import ElementTree as ET

import httpx

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

try:
    import pandas as pd  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    pd = None

try:  # pragma: no cover - optional dependency
    from docx import Document as DocxDocument  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    DocxDocument = None

try:  # pragma: no cover - optional dependency
    from pypdf import PdfReader  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    PdfReader = None


class DocumentItem(TypedDict):
    """A single source file summary for Step 1."""

    name: str
    type: str
    page_count: int
    content_summary: str
    source_path: str


class ModelComparison(TypedDict, total=False):
    """One model's draft for the manifest."""

    model_name: str
    label: str
    provider: str
    temperature: float
    draft: str
    error: str


class ModelConfig(TypedDict, total=False):
    id: str
    label: str
    provider: str
    model_name: str
    base_url: str
    api_key: str
    temperature: float
    enabled: bool


class Step1State(TypedDict, total=False):
    """LangGraph state for Step 1."""

    project_name: str
    file_paths: list[str]
    doc_metadata: list[DocumentItem]
    draft_manifest: str
    final_manifest: str
    model_comparisons: list[ModelComparison]
    review_round: int
    review_mode: Literal["modify", "approve"]
    review_feedback: str
    export_format: Literal["docx", "pdf", "both"]
    export_style: Literal["classic", "custom"]
    export_filename: str
    export_payload: str
    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    chat_intent: ChatIntent
    created_at: str
    updated_at: str


ChatIntent = Literal["small_talk", "qa", "manifest_refine", "manifest_generate"]


class Step1Context(TypedDict, total=False):
    """Runtime context for Step 1."""

    project_id: str
    user_id: str
    model_name: str
    model_provider: str
    base_url: str
    api_key: str
    temperature: float
    active_model_name: str
    active_model_provider: str
    active_base_url: str
    active_api_key: str
    active_temperature: float
    active_model_configs: list[ModelConfig]
    model_configs: list[ModelConfig]
    compare_models: list[str]
    enable_multi_model: bool
    output_dir: str
    chat_mode: bool


@dataclass(slots=True)
class DocumentProcessor:
    """Extract a lightweight manifest summary from source files."""

    max_preview_chars: int = 900

    def parse(self, file_path: str) -> DocumentItem:
        path = Path(file_path)
        ext = path.suffix.lower()
        name = path.name
        pages = 1
        summary = ""

        try:
            if ext == ".pdf":
                summary, pages = self._parse_pdf(path)
            elif ext in {".docx", ".doc"}:
                summary, pages = self._parse_docx(path)
            elif ext in {".xlsx", ".xls"}:
                summary, pages = self._parse_excel(path)
            elif ext in {".md", ".txt", ".csv"}:
                summary = self._read_text_file(path)
                pages = max(1, len(summary) // 1500 + 1)
            elif ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
                summary = f"图片文件：{name}。当前仅记录文件名与路径，后续可接 OCR。"
                pages = 1
            else:
                summary = self._read_binary_preview(path)
        except Exception as exc:  # pragma: no cover - defensive fallback
            summary = f"解析失败：{exc}"

        return {
            "name": name,
            "type": ext or path.name,
            "page_count": pages,
            "content_summary": self._normalize_summary(summary),
            "source_path": str(path),
        }

    def _normalize_summary(self, summary: str) -> str:
        compact = re.sub(r"\s+", " ", summary).strip()
        return compact[: self.max_preview_chars] if compact else "未提取到可用文本。"

    def _read_text_file(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="ignore")[: self.max_preview_chars]

    def _read_binary_preview(self, path: Path) -> str:
        data = path.read_bytes()[:256]
        return f"未知格式文件：{path.name}。二进制预览：{data.hex()[:120]}"

    def _parse_pdf(self, path: Path) -> tuple[str, int]:
        if PdfReader is not None:
            reader = PdfReader(str(path))
            texts: list[str] = []
            for page in reader.pages[:3]:
                try:
                    texts.append(page.extract_text() or "")
                except Exception:
                    texts.append("")
            summary = "\n".join(texts).strip()
            return summary[: self.max_preview_chars], len(reader.pages)

        return self._fallback_zip_or_text(path, default_label="PDF")

    def _parse_docx(self, path: Path) -> tuple[str, int]:
        if DocxDocument is not None:
            doc = DocxDocument(str(path))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            summary = "\n".join(paragraphs[:20])
            return summary[: self.max_preview_chars], max(1, len(paragraphs) // 20 + 1)

        return self._fallback_zip_or_text(path, default_label="Word")

    def _parse_excel(self, path: Path) -> tuple[str, int]:
        if pd is not None:
            xls = pd.ExcelFile(path)
            sheet_names = xls.sheet_names
            preview: list[str] = [f"工作表：{', '.join(sheet_names)}"]
            for sheet in sheet_names[:2]:
                df = pd.read_excel(path, sheet_name=sheet)
                preview.append(f"[{sheet}] 行数={len(df)} 列名={list(df.columns)}")
            pages = max(1, sum(len(pd.read_excel(path, sheet_name=s)) for s in sheet_names[:2]) // 50 + 1)
            return "\n".join(preview)[: self.max_preview_chars], pages

        return self._fallback_zip_or_text(path, default_label="Excel")

    def _fallback_zip_or_text(self, path: Path, default_label: str) -> tuple[str, int]:
        suffix = path.suffix.lower()
        if suffix == ".docx":
            try:
                with zipfile.ZipFile(path) as zf:
                    xml = zf.read("word/document.xml")
                    root = ET.fromstring(xml)
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    texts = [node.text for node in root.findall(".//w:t", ns) if node.text]
                    summary = "".join(texts)
                    return summary[: self.max_preview_chars], max(1, len(texts) // 20 + 1)
            except Exception:
                pass

        return f"{default_label} 文件：{path.name}。当前环境缺少专用解析库，建议后续安装对应依赖。", 1


processor = DocumentProcessor()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace('+00:00', 'Z')


def _detect_project_name(metadata: list[DocumentItem], fallback: str = "未命名项目") -> str:
    if not metadata:
        return fallback

    first = metadata[0]["name"]
    stem = Path(first).stem
    # 尝试去掉一些常见后缀词，让命名更像“***项目资料清单”
    stem = re.sub(r"(资料|清单|项目|报告|评价|材料|文档|附件)+$", "", stem).strip("-_ 。.\t\n\r")
    return stem or fallback


def _build_manifest_title(project_name: str) -> str:
    return f"{project_name}项目资料清单"


def _render_manifest(metadata: list[DocumentItem], project_name: str) -> str:
    lines = [
        f"《{_build_manifest_title(project_name)}》",
        "",
        f"项目名称：{project_name}",
        f"生成时间：{_now_iso()}",
        "",
        "一、资料清单",
    ]
    for idx, item in enumerate(metadata, start=1):
        lines.append(
            f"{idx}. {item['name']} | 类型：{item['type']} | 规模：{item['page_count']} | 摘要：{item['content_summary']}"
        )
    lines.extend(
        [
            "",
            "二、备注",
            "本清单由系统自动解析资料并整理，用户可在成品区直接编辑或继续与大模型对话完善。",
        ]
    )
    return "\n".join(lines)


def _build_llm_prompt(
    project_name: str,
    metadata: list[DocumentItem],
    *,
    admin_system_prompt: str = "",
    admin_knowledge_base: str = "",
) -> str:
    task_lines = [
        "请根据用户上传的资料元数据生成《项目资料清单》。",
        "要求：",
        "1. 输出中文；",
        "2. 按资料编号、文件名、类型、页数/规模、内容摘要、用途建议整理；",
        "3. 标注需要人工复核的资料；",
        "4. 末尾给出后续 Step2 生成有效项目资料时的资料使用建议；",
        "5. 不要编造不存在的文件。",
    ]
    parts: list[str] = []
    if admin_system_prompt.strip():
        parts.extend(["【管理端 Prompt 配置】", admin_system_prompt.strip(), ""])
    if admin_knowledge_base.strip():
        parts.extend(["【管理端知识库】", admin_knowledge_base.strip(), ""])
    parts.extend(task_lines)
    parts.extend(
        [
            "",
            f"项目名称：{project_name}",
            "资料元数据 JSON：",
            json.dumps(metadata, ensure_ascii=False, indent=2),
        ]
    )
    return "\n".join(parts)


def _normalize_temperature(value: Any, default: float = 0.2) -> float:
    try:
        temperature = float(value)
    except (TypeError, ValueError):
        temperature = default
    return min(2.0, max(0.0, temperature))


def _read_model_config(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "primary",
        "label": str(context.get("active_model_name") or context.get("model_name") or "默认模型").strip(),
        "provider": str(context.get("active_model_provider") or context.get("model_provider") or "openai-compatible").strip(),
        "model_name": str(context.get("active_model_name") or context.get("model_name") or "").strip(),
        "base_url": str(context.get("active_base_url") or context.get("base_url") or "").strip(),
        "api_key": str(context.get("active_api_key") or context.get("api_key") or "").strip(),
        "temperature": _normalize_temperature(context.get("active_temperature") if "active_temperature" in context else context.get("temperature")),
        "enabled": True,
    }


def _read_model_configs(context: dict[str, Any]) -> list[dict[str, Any]]:
    raw_configs = context.get("active_model_configs") or context.get("model_configs") or []
    configs: list[dict[str, Any]] = []
    if isinstance(raw_configs, list):
        for index, item in enumerate(raw_configs):
            if not isinstance(item, dict):
                continue
            model_name = str(item.get("model_name") or "").strip()
            base_url = str(item.get("base_url") or "").strip()
            api_key = str(item.get("api_key") or "").strip()
            if not (model_name and base_url and api_key) or item.get("enabled") is False:
                continue
            configs.append(
                {
                    "id": str(item.get("id") or f"model-{index + 1}"),
                    "label": str(item.get("label") or model_name).strip(),
                    "provider": str(item.get("provider") or "openai-compatible").strip(),
                    "model_name": model_name,
                    "base_url": base_url,
                    "api_key": api_key,
                    "temperature": _normalize_temperature(item.get("temperature")),
                    "enabled": True,
                }
            )
    if configs:
        return configs
    primary = _read_model_config(context)
    return [primary] if primary["model_name"] and primary["base_url"] and primary["api_key"] else []


def _extract_openai_compatible_content(data: Any) -> str:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices:
        raise RuntimeError("模型接口未返回 choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("模型接口未返回有效 content")
    return content.strip()


def _build_openai_compatible_request(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    prompt: str,
    temperature: float = 0.2,
    system_prompt: str = "",
) -> tuple[str, dict[str, str], dict[str, Any]]:
    base = base_url.rstrip("/")
    endpoint = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    system_content = system_prompt.strip() or "你是严谨的政务/财政绩效评价文档生成助手。"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ],
        "temperature": _normalize_temperature(temperature),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    return endpoint, headers, payload


def _call_openai_compatible_model(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    prompt: str,
    temperature: float = 0.2,
    timeout_seconds: float = 60.0,
    system_prompt: str = "",
) -> str:
    endpoint, headers, payload = _build_openai_compatible_request(
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        prompt=prompt,
        temperature=temperature,
        system_prompt=system_prompt,
    )
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    return _extract_openai_compatible_content(data)


async def _call_openai_compatible_model_async(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    prompt: str,
    temperature: float = 0.2,
    timeout_seconds: float = 60.0,
    system_prompt: str = "",
) -> str:
    endpoint, headers, payload = _build_openai_compatible_request(
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        prompt=prompt,
        temperature=temperature,
        system_prompt=system_prompt,
    )
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    return _extract_openai_compatible_content(data)


async def _generate_model_drafts_async(
    project_name: str,
    metadata: list[DocumentItem],
    models: list[str],
    context: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> list[ModelComparison]:
    state = state or {}
    admin_system_prompt = str(state.get("admin_system_prompt") or context.get("admin_system_prompt") or "")
    admin_knowledge_base = str(state.get("admin_knowledge_base") or context.get("admin_knowledge_base") or "")
    prompt = _build_llm_prompt(
        project_name,
        metadata,
        admin_system_prompt=admin_system_prompt,
        admin_knowledge_base=admin_knowledge_base,
    )
    system_prompt = admin_system_prompt or "你是严谨的政务/财政绩效评价文档生成助手。"
    configured_models = _read_model_configs(context)
    if models:
        requested = {str(model).strip() for model in models if str(model).strip()}
        configured_models = [item for item in configured_models if item["model_name"] in requested] or configured_models

    if not configured_models:
        raise RuntimeError("缺少客户端模型配置：model_configs/base_url/api_key/model_name 必填")

    async def generate_one(config: dict[str, Any]) -> ModelComparison:
        model_name = str(config["model_name"])
        base_result: ModelComparison = {
            "model_name": model_name,
            "label": str(config.get("label") or model_name),
            "provider": str(config.get("provider") or "openai-compatible"),
            "temperature": float(config["temperature"]),
        }
        try:
            draft = await _call_openai_compatible_model_async(
                base_url=str(config["base_url"]),
                api_key=str(config["api_key"]),
                model_name=model_name,
                prompt=prompt,
                temperature=float(config["temperature"]),
                system_prompt=system_prompt,
            )
            return {**base_result, "draft": draft}
        except Exception as exc:
            return {**base_result, "draft": "", "error": str(exc)}

    drafts = await asyncio.gather(*(generate_one(config) for config in configured_models))
    successful = [item for item in drafts if item.get("draft")]
    if not successful:
        errors = "; ".join(f"{item.get('model_name')}: {item.get('error')}" for item in drafts)
        raise RuntimeError(f"所有模型调用均失败：{errors}")
    return drafts


def _generate_model_drafts(
    project_name: str,
    metadata: list[DocumentItem],
    models: list[str],
    context: dict[str, Any],
    state: dict[str, Any] | None = None,
) -> list[ModelComparison]:
    return asyncio.run(_generate_model_drafts_async(project_name, metadata, models, context, state))


def _merge_review_feedback(draft: str, feedback: str, round_no: int) -> str:
    feedback = feedback.strip()
    if not feedback:
        return draft

    return (
        f"{draft}\n\n"
        f"【第 {round_no} 轮人工/对话优化意见】\n"
        f"{feedback}\n\n"
        f"【系统更新说明】\n"
        f"已根据反馈优化资料清单结构，保留原有资料条目，并增强对重点资料的分类与说明。"
    )


def _refine_manifest_with_llm(current_manifest: str, feedback: str, context: dict[str, Any]) -> str:
    model_config = _read_model_config(context)
    base_url = str(model_config["base_url"])
    api_key = str(model_config["api_key"])
    model_name = str(model_config["model_name"])
    temperature = float(model_config["temperature"])
    if not (base_url and api_key and model_name):
        raise RuntimeError("缺少模型配置，无法执行 LLM 重写")

    prompt = "\n".join(
        [
            "你是财政绩效评价项目资料整理专家。",
            "请根据用户反馈对当前《项目资料清单》进行重写优化。",
            "要求：",
            "1. 保留事实，不编造文件；",
            "2. 强化层次结构与分类可读性；",
            "3. 输出完整新版本清单正文（不要只给修改建议）。",
            "",
            "用户反馈：",
            feedback,
            "",
            "当前清单：",
            current_manifest,
        ]
    )
    return _call_openai_compatible_model(
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        prompt=prompt,
        temperature=temperature,
    )


def _build_export_filename(project_name: str, export_style: str) -> str:
    style_suffix = "经典排版" if export_style == "classic" else "自定义排版"
    return f"{project_name}项目资料清单_{style_suffix}"


def _extract_latest_user_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message.content.strip()
    return ""


def _detect_chat_intent_with_llm(user_text: str, state: Step1State, context: Step1Context) -> ChatIntent:
    model_config = _read_model_config(context if isinstance(context, dict) else {})
    if not (model_config["base_url"] and model_config["api_key"] and model_config["model_name"]):
        return "qa"

    workflow_state = dict(context.get("workflow_state") or {}) if isinstance(context, dict) else {}
    draft = state.get("final_manifest") or state.get("draft_manifest") or ""
    prompt = "\n".join(
        [
            "你是工作流对话意图分类器。请只根据用户消息和上下文判断意图。",
            "只能返回 JSON，不要输出解释。",
            "JSON 格式：{\"intent\":\"small_talk|qa|manifest_refine\",\"reason\":\"简短原因\"}",
            "分类规则：",
            "- small_talk：问候、寒暄、感谢、自我介绍等普通闲聊；",
            "- qa：询问当前项目、步骤、资料状态、流程说明、一般问题；",
            "- manifest_refine：用户明确要求生成、重写、细化、优化、修改、替换资料清单草稿；",
            "不要因为当前存在资料清单，就把普通问候误判为 manifest_refine。",
            "",
            f"当前步骤：{workflow_state.get('step_title') or context.get('step_code', 'step1')}",
            f"当前是否有资料清单：{bool(draft)}",
            "用户消息：",
            user_text,
        ]
    )
    try:
        raw = _call_openai_compatible_model(
            base_url=str(model_config["base_url"]),
            api_key=str(model_config["api_key"]),
            model_name=str(model_config["model_name"]),
            prompt=prompt,
            temperature=0.0,
            timeout_seconds=30.0,
        )
        match = re.search(r"\{[\s\S]*\}", raw)
        parsed = json.loads(match.group(0) if match else raw)
        intent = str(parsed.get("intent") or "qa").strip()
        if intent in {"small_talk", "qa", "manifest_refine"}:
            return intent  # type: ignore[return-value]
    except Exception:
        return "qa"
    return "qa"


def _call_chat_llm(messages: list[BaseMessage], state: Step1State, context: Step1Context) -> str:
    user_text = _extract_latest_user_text(messages)
    workflow_state = dict(context.get("workflow_state") or {}) if isinstance(context, dict) else {}
    project_name = state.get("project_name") or workflow_state.get("project_name") or context.get("project_id", "未命名项目")
    current_step = workflow_state.get("step_title") or context.get("step_code", "step1") if isinstance(context, dict) else "step1"
    draft = state.get("draft_manifest") or ""
    final_manifest = state.get("final_manifest") or draft
    model_config = _read_model_config(context if isinstance(context, dict) else {})
    if not (model_config["base_url"] and model_config["api_key"] and model_config["model_name"]):
        raise RuntimeError("缺少模型配置，无法执行 AI 对话")

    prompt = "\n".join(
        [
            "你是一个工作流 AI 助手。请自然、简洁地回答用户问题。",
            "重要约束：",
            "1. 用户只是问候、闲聊、介绍自己或普通提问时，只回答对话内容，不要生成或改写资料清单；",
            "2. 只有用户明确要求生成、优化、修改资料清单时，才输出可替换的资料清单正文；",
            "3. 回答中可以结合当前项目、当前 Step 和文件状态；",
            "4. 不要声称已经提交、批准或落库。",
            "",
            f"项目：{project_name}",
            f"当前步骤：{current_step}",
            f"文件数量：{workflow_state.get('file_count', '-')}",
            f"图片/PDF：{workflow_state.get('media_count', '-')}",
            f"文档数量：{workflow_state.get('document_count', '-')}",
            "",
            "当前资料清单摘要：",
            final_manifest[:1500] if final_manifest else "暂无资料清单正文。",
            "",
            "用户消息：",
            user_text,
        ]
    )
    return _call_openai_compatible_model(
        base_url=str(model_config["base_url"]),
        api_key=str(model_config["api_key"]),
        model_name=str(model_config["model_name"]),
        prompt=prompt,
        temperature=float(model_config["temperature"]),
    )


def _compose_small_talk_reply(user_text: str, context: Step1Context, messages: list[BaseMessage] | None = None, state: Step1State | None = None) -> str:
    return _call_chat_llm(messages or [HumanMessage(content=user_text)], state or {}, context)


def _compose_chat_reply(messages: list[BaseMessage], state: Step1State, context: Step1Context) -> str:
    return _call_chat_llm(messages, state, context)


def initialize_project(state: Step1State) -> Step1State:
    """Parse uploaded files and infer the project name."""

    if state.get("status") == "chat":
        return {
            "status": "chat",
            "updated_at": _now_iso(),
        }

    file_paths = state.get("file_paths", [])
    if not file_paths:
        return {
            "status": "failed",
            "error": "未提供任何资料文件。",
            "messages": [AIMessage(content="请先上传至少一个 Word / Excel / PDF / 图片文件。")],
            "updated_at": _now_iso(),
        }

    metadata = [processor.parse(path) for path in file_paths]
    project_name = state.get("project_name") or _detect_project_name(metadata)
    fresh_manifest = _render_manifest(metadata, project_name)

    return {
        "project_name": project_name,
        "doc_metadata": metadata,
        "draft_manifest": fresh_manifest,
        "final_manifest": fresh_manifest,
        "review_round": 0,
        "review_feedback": "",
        "status": "initialized",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已解析 {len(metadata)} 个资料文件，系统自动识别项目名称为：{project_name}。"
                )
            )
        ],
    }


def build_manifest_draft(state: Step1State, runtime: Any) -> Step1State:
    """Build one or more manifest drafts."""

    metadata = state.get("doc_metadata", [])
    project_name = state.get("project_name", "未命名项目")
    context = getattr(runtime, "context", {}) or {}

    multi_model_enabled = bool(context.get("enable_multi_model", False))
    models = list(context.get("compare_models", [])) or [context.get("model_name", "默认模型") or "默认模型"]

    try:
        selected_models = models if multi_model_enabled else models[:1]
        comparisons = _generate_model_drafts(project_name, metadata, selected_models, context, dict(state))
        successful_comparisons = [item for item in comparisons if item.get("draft")]
        draft_manifest = successful_comparisons[0]["draft"] if successful_comparisons else _render_manifest(metadata, project_name)
        failed_count = len(comparisons) - len(successful_comparisons)
        message = f"已调用真实模型生成 {len(successful_comparisons)} 份资料清单草稿，可进入成品区对比与筛选。"
        if failed_count:
            message += f"另有 {failed_count} 个模型调用失败，已在对比结果中保留错误信息。"
    except Exception as exc:
        fallback = _render_manifest(metadata, project_name)
        return {
            "draft_manifest": fallback,
            "model_comparisons": [],
            "export_filename": _build_export_filename(project_name, state.get("export_style", "classic")),
            "export_payload": fallback,
            "status": "model_failed_fallback_ready",
            "error": f"真实模型调用失败，已回退到规则模板：{exc}",
            "updated_at": _now_iso(),
            "messages": [AIMessage(content=f"真实模型调用失败，已回退到规则模板：{exc}")],
        }

    export_style = state.get("export_style", "classic")

    return {
        "draft_manifest": draft_manifest,
        "final_manifest": draft_manifest,
        "model_comparisons": comparisons,
        "export_filename": _build_export_filename(project_name, export_style),
        "export_payload": draft_manifest,
        "status": "draft_ready",
        "error": "",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content=message)],
    }


def route_review_mode(state: Step1State) -> str:
    """Route to refinement or finish based on review mode."""

    if state.get("review_mode") == "approve":
        return "approve"
    return "modify"


def refine_manifest(state: Step1State) -> Step1State:
    """Refine the draft manifest from human feedback."""

    feedback = state.get("review_feedback", "").strip()
    round_no = int(state.get("review_round", 0)) + 1
    current = state.get("final_manifest") or state.get("draft_manifest") or ""
    refined = _merge_review_feedback(current, feedback, round_no)

    return {
        "review_round": round_no,
        "draft_manifest": refined,
        "final_manifest": refined,
        "status": "refined",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content=f"已完成第 {round_no} 轮优化。请继续确认是否满意。")],
    }


def approve_manifest(state: Step1State) -> Step1State:
    """Mark the current manifest as final."""

    final_manifest = state.get("draft_manifest") or state.get("final_manifest") or ""
    project_name = state.get("project_name", "未命名项目")

    if not final_manifest:
        final_manifest = _render_manifest(state.get("doc_metadata", []), project_name)

    return {
        "final_manifest": final_manifest,
        "export_payload": final_manifest,
        "export_filename": state.get("export_filename") or _build_export_filename(project_name, state.get("export_style", "classic")),
        "status": "approved",
        "error": "",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="资料清单已确认，可以导入成品区并执行导出。")],
    }


def _intent_node(state: Step1State, runtime: Any) -> Step1State:
    context = getattr(runtime, "context", {}) or {}
    messages = list(state.get("messages", []))
    user_text = str(context.get("latest_user_message") or "").strip() or _extract_latest_user_text(messages)
    intent = _detect_chat_intent_with_llm(user_text, state, context)
    return {
        "chat_intent": intent,
        "status": f"chat_intent_{intent}",
        "updated_at": _now_iso(),
    }


def route_chat_intent(state: Step1State) -> str:
    intent = state.get("chat_intent", "qa")
    if intent in {"manifest_refine", "manifest_generate"}:
        return "manifest_refine"
    if intent == "small_talk":
        return "small_talk"
    return "qa"


def _chat_small_talk_node(state: Step1State, runtime: Any) -> Step1State:
    messages = list(state.get("messages", []))
    context = getattr(runtime, "context", {}) or {}
    user_text = str(context.get("latest_user_message") or "").strip() or _extract_latest_user_text(messages)
    try:
        reply = _compose_small_talk_reply(user_text, context, messages, state)
        status = "chat_small_talk"
        error = ""
    except Exception as exc:
        reply = f"AI 对话模型调用失败：{exc}。请检查当前生效模型的 Base URL、API Key 和模型名是否正确。"
        status = "chat_model_failed"
        error = str(exc)
    return {
        "status": status,
        "error": error,
        "updated_at": _now_iso(),
        "answer": reply,
        "messages": [AIMessage(content=reply)],
    }


def _chat_qa_node(state: Step1State, runtime: Any) -> Step1State:
    messages = list(state.get("messages", []))
    context = getattr(runtime, "context", {}) or {}
    try:
        reply = _compose_chat_reply(messages, state, context)
        status = "chat_qa"
        error = ""
    except Exception as exc:
        reply = f"AI 对话模型调用失败：{exc}。请检查当前生效模型的 Base URL、API Key 和模型名是否正确。"
        status = "chat_model_failed"
        error = str(exc)
    return {
        "status": status,
        "error": error,
        "updated_at": _now_iso(),
        "answer": reply,
        "messages": [AIMessage(content=reply)],
    }


def _chat_manifest_node(state: Step1State, runtime: Any) -> Step1State:
    messages = list(state.get("messages", []))
    context = getattr(runtime, "context", {}) or {}
    user_text = str(context.get("latest_user_message") or "").strip() or _extract_latest_user_text(messages)

    should_execute_refine = bool(user_text)
    if should_execute_refine:
        round_no = int(state.get("review_round", 0)) + 1
        workflow_state = dict(context.get("workflow_state") or {}) if isinstance(context, dict) else {}
        workflow_result = workflow_state.get("current_result") if isinstance(workflow_state.get("current_result"), dict) else {}
        workflow_text = ""
        if workflow_result:
            maybe_text = workflow_result.get("content_text") or workflow_result.get("final_manifest") or workflow_result.get("draft_manifest")
            workflow_text = str(maybe_text).strip() if maybe_text is not None else ""

        current = (
            state.get("final_manifest")
            or state.get("draft_manifest")
            or workflow_text
            or _render_manifest(state.get("doc_metadata", []), state.get("project_name", "未命名项目"))
        )
        context_dict = context if isinstance(context, dict) else {}
        status = "chat_executed_refine_fallback"
        try:
            refined = _refine_manifest_with_llm(current, user_text, context_dict)
            status = "chat_executed_refine_llm"
        except Exception:
            refined = _merge_review_feedback(current, user_text, round_no)
            status = "chat_executed_refine_fallback"

        return {
            "review_round": round_no,
            "review_feedback": user_text,
            "draft_manifest": refined,
            "final_manifest": refined,
            "status": status,
            "updated_at": _now_iso(),
            "answer": refined,
            "messages": [AIMessage(content=refined)],
        }

    reply = _compose_chat_reply(messages, state, context)
    return {
        "status": "chat_reply",
        "updated_at": _now_iso(),
        "answer": reply,
        "messages": [AIMessage(content=reply)],
    }


def build_graph() -> Any:
    """Build the Step 1 graph."""

    graph = StateGraph(Step1State, context_schema=Step1Context)
    graph.add_node("initialize_project", initialize_project)
    graph.add_node("build_manifest_draft", build_manifest_draft)
    graph.add_node("refine_manifest", refine_manifest)
    graph.add_node("approve_manifest", approve_manifest)
    graph.add_node("detect_chat_intent", _intent_node)
    graph.add_node("chat_small_talk", _chat_small_talk_node)
    graph.add_node("chat_qa", _chat_qa_node)
    graph.add_node("chat_manifest", _chat_manifest_node)

    graph.add_edge(START, "initialize_project")
    graph.add_conditional_edges(
        "initialize_project",
        lambda state: "detect_chat_intent" if state.get("status") == "chat" else "build_manifest_draft",
        {
            "detect_chat_intent": "detect_chat_intent",
            "build_manifest_draft": "build_manifest_draft",
        },
    )

    graph.add_conditional_edges(
        "build_manifest_draft",
        route_review_mode,
        {
            "modify": "refine_manifest",
            "approve": "approve_manifest",
        },
    )

    graph.add_conditional_edges(
        "detect_chat_intent",
        route_chat_intent,
        {
            "small_talk": "chat_small_talk",
            "qa": "chat_qa",
            "manifest_refine": "chat_manifest",
        },
    )

    graph.add_edge("refine_manifest", "build_manifest_draft")
    graph.add_edge("approve_manifest", END)
    graph.add_edge("chat_small_talk", END)
    graph.add_edge("chat_qa", END)
    graph.add_edge("chat_manifest", END)

    memory = MemorySaver()
    return graph.compile(checkpointer=memory, name="evalflow-pro-step1")


# LangGraph CLI entrypoint
graph = build_graph()
