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
    structured_analysis: dict[str, Any]
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
    cancel_event: Any


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


def _ensure_not_cancelled(context: dict[str, Any]) -> None:
    event = context.get("cancel_event")
    if event is not None and hasattr(event, "is_set") and event.is_set():
        raise RuntimeError("agent run cancelled")


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


# Step 联动映射：文件类型/关键词 → 后续步骤用途
STEP_LINKAGE_MAP: dict[str, list[str]] = {
    "预算": ["Step 4（预算对比分析）", "Step 6（资金绩效评分）"],
    "决算": ["Step 4（预算对比分析）", "Step 6（资金绩效评分）"],
    "资金": ["Step 4（预算对比分析）", "Step 6（资金绩效评分）"],
    "合同": ["Step 5（合规性审查）", "Step 7（项目管理评分）"],
    "招标": ["Step 5（合规性审查）"],
    "采购": ["Step 5（合规性审查）"],
    "验收": ["Step 8（产出评分）", "Step 10（效果评分）"],
    "审计": ["Step 5（合规性审查）", "Step 9（综合评分汇总）"],
    "绩效": ["Step 3（指标体系构建）", "Step 9（综合评分汇总）"],
    "指标": ["Step 3（指标体系构建）"],
    "方案": ["Step 2（核心内容提取）", "Step 7（项目管理评分）"],
    "实施": ["Step 2（核心内容提取）", "Step 7（项目管理评分）"],
    "报告": ["Step 2（核心内容提取）", "Step 14（终稿报告生成）"],
    "通知": ["Step 2（核心内容提取）"],
    "制度": ["Step 5（合规性审查）", "Step 7（项目管理评分）"],
    "政策": ["Step 2（核心内容提取）", "Step 5（合规性审查）"],
    "照片": ["Step 8（产出评分）", "Step 10（效果评分）"],
    "图片": ["Step 8（产出评分）", "Step 10（效果评分）"],
    "发票": ["Step 4（预算对比分析）", "Step 6（资金绩效评分）"],
    "支出": ["Step 4（预算对比分析）", "Step 6（资金绩效评分）"],
}

# 审计/评价常见必备材料清单（用于 Gap Analysis）
# 每条 = (材料名称, [识别关键词列表])
REQUIRED_MATERIALS: list[tuple[str, list[str]]] = [
    ("项目立项文件（批复/通知）", ["立项", "批复", "通知", "批文"]),
    ("项目实施方案", ["实施方案", "工作方案", "建设方案"]),
    ("预算批复/资金拨付文件", ["预算", "拨付", "资金计划"]),
    ("资金支出明细（含发票/凭证）", ["支出", "发票", "凭证", "决算"]),
    ("合同/协议", ["合同", "协议"]),
    ("验收报告/完工证明", ["验收", "完工", "竣工"]),
    ("绩效目标申报表", ["绩效目标", "目标申报", "申报表"]),
    ("绩效自评报告", ["自评", "绩效报告", "评价报告"]),
    ("审计报告", ["审计"]),
    ("受益群体反馈/调查数据", ["反馈", "问卷", "调查", "受益", "满意度"]),
]


def _extract_key_numbers(summary: str) -> list[tuple[str, str]]:
    """从文本摘要中提取数字型关键信息（金额、人数、面积等）。"""
    patterns = [
        (r"(\d[\d,]*\.?\d*)\s*万?元", "金额"),
        (r"(\d[\d,]*\.?\d*)\s*亿", "金额（亿）"),
        (r"(\d[\d,]*)\s*人", "人数"),
        (r"(\d[\d,]*\.?\d*)\s*(?:平方米|㎡|平米|亩|公顷|万亩)", "面积"),
        (r"(\d[\d,]*\.?\d*)\s*(?:公里|km|千米)", "距离"),
        (r"(\d[\d,]*)\s*(?:个|项|件|批|台|套|座|栋|处|条)", "数量"),
        (r"(\d{4})\s*年", "年份"),
    ]
    results: list[tuple[str, str]] = []
    seen_values: set[str] = set()
    for pattern, label in patterns:
        for match in re.finditer(pattern, summary):
            full_match = match.group(0).strip()
            if full_match not in seen_values:
                seen_values.add(full_match)
                results.append((label, full_match))
    return results


def _infer_step_linkage(file_name: str, summary: str) -> list[str]:
    """根据文件名和摘要推断该文件将用于哪些后续步骤。"""
    combined = f"{file_name} {summary}".lower()
    linked_steps: set[str] = set()
    for keyword, steps in STEP_LINKAGE_MAP.items():
        if keyword in combined:
            linked_steps.update(steps)
    if not linked_steps:
        linked_steps.add("Step 2（核心内容提取）")
    return sorted(linked_steps)


def _build_gap_analysis(metadata: list[DocumentItem]) -> list[str]:
    """基于已有文件，分析还缺哪些必备材料。"""
    all_text = " ".join(f"{item['name']} {item['content_summary']}" for item in metadata)
    missing: list[str] = []
    for material, keywords in REQUIRED_MATERIALS:
        if not any(kw in all_text for kw in keywords):
            missing.append(material)
    return missing


def _render_manifest(metadata: list[DocumentItem], project_name: str) -> str:
    lines = [
        f"《{_build_manifest_title(project_name)}》",
        "",
        f"项目名称：{project_name}",
        f"生成时间：{_now_iso()}",
        "",
        "一、资料清单（含关键数字与 Step 联动）",
        "",
        "| 编号 | 文件名 | 类型 | 规模 | 内容摘要 | 关键数字 KV | Step 联动 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for idx, item in enumerate(metadata, start=1):
        summary = item.get("content_summary", "")
        kv_pairs = _extract_key_numbers(summary)
        kv_text = "；".join(f"{label}={value}" for label, value in kv_pairs[:6]) or "（未提取到数字）"
        linkage = "、".join(_infer_step_linkage(item.get("name", ""), summary))
        clean_summary = summary.replace("|", "／").replace("\n", " ")[:120]
        lines.append(
            f"| {idx} | {item['name']} | {item['type']} | {item['page_count']} | {clean_summary} | {kv_text} | {linkage} |"
        )

    lines.extend(["", "二、关键数字汇总（Key-Value）"])
    aggregated: list[tuple[str, str, str]] = []
    for item in metadata:
        for label, value in _extract_key_numbers(item.get("content_summary", "")):
            aggregated.append((item.get("name", ""), label, value))
    if aggregated:
        for source, label, value in aggregated:
            lines.append(f"- {label}：{value}（来源：{source}）")
    else:
        lines.append("- 未从已上传资料中提取到可量化的金额、人数、面积等数字。")

    lines.extend(["", "三、Gap Analysis（差距分析）"])
    missing = _build_gap_analysis(metadata)
    if missing:
        lines.append("以下必备材料尚未在已上传资料中识别到，建议补齐以满足审核要求：")
        for material in missing:
            lines.append(f"- [缺] {material}")
    else:
        lines.append("- 已覆盖常见必备材料类别，无明显缺口。")

    lines.extend(
        [
            "",
            "四、备注",
            "本清单由系统自动解析资料并整理，关键数字基于正则提取，Step 联动基于关键词匹配。",
            "用户可在成品区直接编辑或继续与大模型对话完善。",
        ]
    )
    return "\n".join(lines)


def _build_llm_prompt(
    project_name: str,
    metadata: list[DocumentItem],
    *,
    admin_system_prompt: str = "",
    admin_knowledge_base: str = "",
    user_kb_context: str = "",
) -> str:
    pre_extracted_numbers: list[str] = []
    for item in metadata:
        kv = _extract_key_numbers(item.get("content_summary", ""))
        if kv:
            pre_extracted_numbers.append(
                f"- {item.get('name', '')}: " + "; ".join(f"{label}={value}" for label, value in kv)
            )
    pre_extracted_text = "\n".join(pre_extracted_numbers) if pre_extracted_numbers else "（未自动识别到数字，请你从原文摘要中再次扫描）"

    rule_based_gap = _build_gap_analysis(metadata)
    gap_hint = "、".join(rule_based_gap) if rule_based_gap else "（系统初判未发现明显缺口，请你结合通知/政策原文复核）"

    task_lines = [
        "请根据用户上传的资料元数据生成《项目资料清单》。",
        "",
        "【硬性输出结构（必须按本结构输出，不允许只写摘要）】",
        "",
        "一、资料清单（Markdown 表格）",
        "  表头固定为：| 编号 | 文件名 | 类型 | 规模 | 内容摘要 | 关键数字 KV | 用于 Step |",
        "  - 「关键数字 KV」列：把该文件中提到的金额、人数、面积、时间节点等关键数字单独列成 Key-Value 对，",
        "    例如：经费=100万元；受益学生=5000人；覆盖面积=200亩；起止时间=2024-01~2024-12。多个 KV 用「；」分隔。",
        "  - 「用于 Step」列：必须明确标注该文件将用于后续的哪些步骤（用 Step 2 ~ Step 14 中的具体编号）。",
        "    可选示例：Step 2（核心内容提取）、Step 3（指标体系构建）、Step 4（预算对比分析）、Step 5（合规性审查）、",
        "    Step 6（资金绩效评分）、Step 7（项目管理评分）、Step 8（产出评分）、Step 9（综合评分汇总）、",
        "    Step 10（效果评分）、Step 14（终稿报告生成）。",
        "    例如「本文件将用于 Step 4 的预算-决算自动比对」「本文件将用于 Step 5 的合规性审查」。",
        "",
        "二、关键数字汇总（Key-Value 列表）",
        "  把所有文件中的数字按类别（金额 / 人数 / 面积 / 时间 / 数量 / 距离）汇总，每条标注来源文件名。",
        "  格式：- 金额：100 万元（来源：xxx 通知.docx）",
        "  禁止只写「金额若干」之类模糊表述，必须保留原文具体数值。",
        "",
        "三、Gap Analysis（差距分析）",
        "  基于本批资料，明确指出还缺哪些证明材料才能通过绩效评价/审计审核。",
        "  每条缺口写成：- [缺] 材料名称 —— 用途说明（为什么需要补这份材料）。",
        "  必须覆盖以下维度：立项依据、实施方案、资金/预算、合同/招投标、验收/产出、绩效目标与自评、审计、受益群体反馈。",
        "  系统初判可能缺失：" + gap_hint,
        "",
        "四、Step 联动建议",
        "  汇总说明本批资料将驱动后续哪几个 Step 的自动比对/评分，并标注对应文件。",
        "",
        "【硬性约束】",
        "1. 全文中文；",
        "2. 数字必须从摘要中真实提取，禁止编造；如摘要中没有，写「（原文未提及）」；",
        "3. 不要省略表格列；不要把「关键数字 KV」「用于 Step」合并成一句话散文；",
        "4. 不要复述输入 JSON，要做结构化重写；",
        "5. 不要编造不存在的文件。",
        "",
        "【系统已自动预提取的数字（供你校验/补充）】",
        pre_extracted_text,
    ]
    parts: list[str] = []
    if admin_system_prompt.strip():
        parts.extend(["【管理端 Prompt 配置】", admin_system_prompt.strip(), ""])
    if admin_knowledge_base.strip():
        parts.extend(["【管理端知识库】", admin_knowledge_base.strip(), ""])
    if user_kb_context.strip():
        parts.extend([user_kb_context.strip(), ""])
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

    user_kb_ctx = ""
    project_id = str(context.get("project_id") or "")
    if project_id:
        try:
            from agent.user_graphs._kb_retrieval import retrieve_kb_context
            user_kb_ctx = await retrieve_kb_context(
                project_id=project_id,
                query=f"{project_name} 项目资料清单 文件列表",
                top_k=5,
                step_code="step1",
            )
        except Exception:
            user_kb_ctx = ""

    prompt = _build_llm_prompt(
        project_name,
        metadata,
        admin_system_prompt=admin_system_prompt,
        admin_knowledge_base=admin_knowledge_base,
        user_kb_context=user_kb_ctx,
    )
    system_prompt = admin_system_prompt or "你是严谨的政务/财政绩效评价文档生成助手。"
    configured_models = _read_model_configs(context)
    if models:
        requested = {str(model).strip() for model in models if str(model).strip()}
        configured_models = [item for item in configured_models if item["model_name"] in requested] or configured_models

    if not configured_models:
        raise RuntimeError("缺少客户端模型配置：model_configs/base_url/api_key/model_name 必填")

    _ensure_not_cancelled(context)

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


def _build_structured_analysis(metadata: list[DocumentItem]) -> dict[str, Any]:
    """Build structured analysis data for frontend three-table rendering."""
    key_metrics: list[dict[str, str]] = []
    for item in metadata:
        for label, value in _extract_key_numbers(item.get("content_summary", "")):
            key_metrics.append({"label": label, "value": value, "source": item.get("name", "")})

    gap_items: list[dict[str, str]] = []
    all_text = " ".join(f"{item['name']} {item['content_summary']}" for item in metadata)
    for material, keywords in REQUIRED_MATERIALS:
        found = any(kw in all_text for kw in keywords)
        gap_items.append({
            "material": material,
            "status": "success" if found else "error",
            "note": "已识别到相关资料" if found else "未在已上传资料中识别到，建议补齐",
        })

    data_flow: list[dict[str, Any]] = []
    for item in metadata:
        linked = _infer_step_linkage(item.get("name", ""), item.get("content_summary", ""))
        data_flow.append({
            "file_name": item.get("name", ""),
            "file_type": item.get("type", ""),
            "target_steps": linked,
        })

    return {"key_metrics": key_metrics, "gap_analysis": gap_items, "data_flow": data_flow}


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
    structured = _build_structured_analysis(metadata)

    return {
        "project_name": project_name,
        "doc_metadata": metadata,
        "draft_manifest": fresh_manifest,
        "final_manifest": fresh_manifest,
        "structured_analysis": structured,
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
    _ensure_not_cancelled(context)

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
            "structured_analysis": _build_structured_analysis(metadata),
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
        "structured_analysis": _build_structured_analysis(metadata),
        "export_filename": _build_export_filename(project_name, export_style),
        "export_payload": draft_manifest,
        "status": "draft_ready",
        "error": "",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content=message)],
    }


def route_review_mode(state: Step1State) -> str:
    """Route to refinement or finish based on review mode."""

    if state.get("review_mode") == "modify" and state.get("review_feedback", "").strip():
        return "modify"
    return "approve"


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

    previous_status = str(state.get("status") or "")
    previous_error = str(state.get("error") or "")
    fallback_failed = previous_status.startswith("model_failed") or "模型调用失败" in previous_error or "Unauthorized" in previous_error

    if fallback_failed:
        return {
            "final_manifest": final_manifest,
            "export_payload": final_manifest,
            "export_filename": state.get("export_filename") or _build_export_filename(project_name, state.get("export_style", "classic")),
            "status": "model_failed_fallback_ready",
            "error": previous_error or "模型调用失败，已回退到规则模板。请检查 API Key / Base URL / 模型名是否正确。",
            "updated_at": _now_iso(),
            "messages": [AIMessage(content=f"模型调用失败，当前展示的是规则模板回退结果，并非 LLM 真实输出。错误：{previous_error}")],
        }

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
