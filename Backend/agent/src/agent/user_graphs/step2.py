"""Step 2 graph for EvalFlow Pro.

Step 2 implements the client workflow for generating valid project core materials
(生成有效项目资料), aligned with the product specification:

1. Two upload channels: media (images / PDF) vs office documents (Word / Excel
   etc.), each with its own configurable model in runtime context.
2. Warn when the media-channel model may not support PDF / image understanding;
   emit a verification digest so humans can compare against originals.
3. Call LLM (real OpenAI-compatible API) to distill project-related core content,
   drop noise, keep logic consistent, with source index mapping back to excerpts.
4. Default categories: 资金管理类、预算管理类、制度文件类、项目实施类; extra
   categories can be supplied via state (e.g. from dialogue).
5. Required narrative dimensions: background, implementation, organization,
   funds in/out, performance targets, outputs, benefits, etc.
6. Human-in-the-loop: direct edit is represented by carrying ``final_core_content``;
   conversational refinement uses ``review_feedback`` / ``review_mode`` like Step 1.
7. Multi-model comparison and classic / custom export naming for PDF / Word.

This module reuses :class:`DocumentProcessor` from Step 1 to avoid duplicating
file parsers, and reuses the openai-compatible API helpers from Step 1.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict
import operator
import re

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from .step1 import (
    DocumentItem,
    ModelConfig,
    _call_openai_compatible_model,
    _call_openai_compatible_model_async,
    _normalize_temperature,
    _read_model_config,
    _read_model_configs,
    processor,
)


class ModelComparison(TypedDict, total=False):
    """One model's draft for the core content."""

    model_name: str
    label: str
    provider: str
    temperature: float
    channel: Literal["media", "documents", "combined"]
    draft: str
    error: str


class SourceIndexEntry(TypedDict, total=False):
    """Maps distilled statements back to original material snippets."""

    ref_id: str
    source_name: str
    channel: Literal["media", "documents", "kb"]
    excerpt: str
    chunk_index: int


class Step2State(TypedDict, total=False):
    """LangGraph state for Step 2."""

    project_name: str
    # Two upload windows (optional; see ``_collect_paths``).
    media_file_paths: list[str]
    text_doc_file_paths: list[str]
    # Back-compat: if the two lists are empty, ``file_paths`` is split by type.
    file_paths: list[str]
    project_files: list[dict[str, Any]]

    media_metadata: list[DocumentItem]
    text_doc_metadata: list[DocumentItem]
    parse_warnings: list[str]
    verification_digest: str
    verification_acknowledged: bool
    source_index: list[SourceIndexEntry]

    default_categories: list[str]
    extra_categories: list[str]

    core_content_draft: str
    final_core_content: str
    model_comparisons: list[ModelComparison]

    review_round: int
    review_mode: Literal["modify", "approve"]
    review_feedback: str

    export_format: Literal["docx", "pdf", "both"]
    export_style: Literal["classic", "custom"]
    export_options: dict[str, Any]
    export_filename: str
    export_payload: str

    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step2Context(TypedDict, total=False):
    """Runtime context for Step 2."""

    project_id: str
    user_id: str
    model_name_media: str
    model_name_documents: str
    media_model_supports_pdf_image: bool
    compare_models: list[str]
    enable_multi_model: bool
    output_dir: str
    active_model_configs: list[ModelConfig]
    media_model_config_id: str
    documents_model_config_id: str


DEFAULT_CATEGORIES = ["资金管理类", "预算管理类", "制度文件类", "项目实施类"]

MEDIA_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".pdf"}

REQUIRED_DIMENSIONS = [
    "项目背景",
    "项目实施内容",
    "项目组织管理情况",
    "项目资金投入与支出情况",
    "项目绩效目标",
    "项目实际产出情况",
    "效益情况",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _detect_project_name(
    media_meta: list[DocumentItem],
    text_meta: list[DocumentItem],
    fallback: str = "未命名项目",
) -> str:
    combined = media_meta + text_meta
    if not combined:
        return fallback
    first = combined[0]["name"]
    stem = Path(first).stem
    stem = re.sub(r"(资料|清单|项目|报告|评价|材料|文档|附件|核心)+$", "", stem).strip("-_ 。.\t\n\r")
    return stem or fallback


def _collect_paths(state: Step2State) -> tuple[list[str], list[str]]:
    media = list(state.get("media_file_paths", []))
    text_docs = list(state.get("text_doc_file_paths", []))
    if media or text_docs:
        return media, text_docs

    legacy = list(state.get("file_paths", []))
    for path in legacy:
        ext = Path(path).suffix.lower()
        if ext in MEDIA_EXTENSIONS:
            media.append(path)
        else:
            text_docs.append(path)

    project_files = state.get("project_files", []) or []
    if project_files and not media and not text_docs:
        for item in project_files:
            key = str(item.get("storage_key") or "")
            ext = Path(key).suffix.lower()
            if ext in MEDIA_EXTENSIONS:
                media.append(key)
            elif key:
                text_docs.append(key)
    return media, text_docs


def _media_parse_warnings(
    items: list[DocumentItem],
    model_label: str,
    supports_media: bool,
) -> list[str]:
    warnings: list[str] = []
    if not items:
        return warnings
    if not supports_media:
        warnings.append(
            f"通道「图片/PDF」当前绑定模型「{model_label}」标记为不支持图片或 PDF 语义理解，"
            "识别结果可能不完整，请务必在资料识别结束后进行人工校验与原文对比。"
        )
    for item in items:
        ext = (item.get("type") or "").lower()
        if ext in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"} and not supports_media:
            warnings.append(f"图片「{item['name']}」需人工核对或更换支持视觉的模型。")
        if ext == ".pdf" and not supports_media:
            warnings.append(f"PDF「{item['name']}」需人工核对或更换支持 PDF 解析/视觉的模型。")
    return warnings


def _build_source_index(
    media_meta: list[DocumentItem],
    text_meta: list[DocumentItem],
) -> list[SourceIndexEntry]:
    entries: list[SourceIndexEntry] = []
    idx = 1
    for item in media_meta:
        ref = f"S{idx}"
        idx += 1
        entries.append(
            {
                "ref_id": ref,
                "source_name": item["name"],
                "channel": "media",
                "excerpt": item.get("content_summary", ""),
            }
        )
    for item in text_meta:
        ref = f"S{idx}"
        idx += 1
        entries.append(
            {
                "ref_id": ref,
                "source_name": item["name"],
                "channel": "documents",
                "excerpt": item.get("content_summary", ""),
            }
        )
    return entries


def _render_verification_digest(
    project_name: str,
    media_meta: list[DocumentItem],
    text_meta: list[DocumentItem],
    warnings: list[str],
) -> str:
    lines = [
        f"项目：{project_name}",
        f"生成时间：{_now_iso()}",
        "",
        "【资料识别结果 — 供人工校验与原文对比】",
        "",
        "一、图片 / PDF 通道",
    ]
    if not media_meta:
        lines.append("（本通道未上传文件）")
    else:
        for item in media_meta:
            lines.append(
                f"- {item['name']} | {item['type']} | 页/规模：{item['page_count']} | "
                f"摘录：{item['content_summary']}"
            )
    lines.extend(["", "二、Word / Excel 等文档通道"])
    if not text_meta:
        lines.append("（本通道未上传文件）")
    else:
        for item in text_meta:
            lines.append(
                f"- {item['name']} | {item['type']} | 页/规模：{item['page_count']} | "
                f"摘录：{item['content_summary']}"
            )
    if warnings:
        lines.extend(["", "三、风险提示"])
        for w in warnings:
            lines.append(f"- {w}")
    lines.extend(
        [
            "",
            "请在客户端确认上述识别内容与原件一致后，再继续生成核心内容；"
            "若不一致，请调整上传文件或更换模型后重新解析。",
        ]
    )
    return "\n".join(lines)


def _build_export_filename(project_name: str, export_style: str) -> str:
    style_suffix = "经典排版" if export_style == "classic" else "自定义排版"
    return f"{project_name}项目核心内容_{style_suffix}"


def _citation_block(index: list[SourceIndexEntry]) -> str:
    if not index:
        return "（暂无可用索引；请补充资料后重试。）"
    parts: list[str] = []
    for e in index:
        channel = e.get("channel", "")
        excerpt = (e.get("excerpt") or "")[:300]
        if channel == "kb":
            chunk_idx = e.get("chunk_index", 0)
            parts.append(
                f"[{e['ref_id']}]《{e['source_name']}》（知识库 · 第{chunk_idx}段）摘录：{excerpt}"
            )
        else:
            parts.append(
                f"[{e['ref_id']}]《{e['source_name']}》（通道：{channel}）摘录：{excerpt}"
            )
    return "\n".join(parts)


def _build_core_prompt(
    project_name: str,
    media_meta: list[DocumentItem],
    text_meta: list[DocumentItem],
    index: list[SourceIndexEntry],
    categories: list[str],
    *,
    admin_system_prompt: str = "",
    admin_knowledge_base: str = "",
    review_feedback: str = "",
    user_kb_context: str = "",
) -> str:
    file_count = sum(1 for e in index if e.get("channel") in ("media", "documents"))
    kb_count = sum(1 for e in index if e.get("channel") == "kb")

    task_lines = [
        "请根据下方双通道资料元数据 + 知识库检索结果生成《项目核心内容》。要求：",
        "1. 输出中文 Markdown；",
        "2. 严格围绕本项目展开，剔除与项目无关或重复冗余表述；",
        "3. 按以下分类组织内容（每个分类一个 ### 二级标题）：",
        f"   {'、'.join(categories)}；",
        "4. 必备维度（每个一个 ### 二级标题，与分类章节并列或交叉覆盖，避免遗漏）：",
        f"   {'、'.join(REQUIRED_DIMENSIONS)}；",
        "5. 每条核心结论必须在末尾附带索引引用（例如 [S1]、[S2]），引用编号必须取自“索引清单”，不得编造；",
        f"   - [S1] 至 [S{file_count}] 为本项目上传文件来源；",
        (
            f"   - [S{file_count + 1}] 至 [S{file_count + kb_count}] 为知识库精准检索来源（同一文件可能出现多个段，按 chunk 区分），"
            "若可证实结论，请优先引用知识库来源以提高准确度；"
        ) if kb_count > 0 else "   - 当前未命中知识库段落，请基于上传文件来源给出引用；",
        "6. 不得编造未在资料 / 知识库中出现的事实、数据、政策依据；",
        "7. 内容应条理清晰、逻辑严谨、无自相矛盾；",
        "8. 在末尾输出『## 索引与原文摘录』章节，列出所有引用过的索引条目与原文摘录原文。",
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
            "",
            "图片 / PDF 通道资料元数据（JSON）：",
            json.dumps(media_meta, ensure_ascii=False, indent=2),
            "",
            "Word / Excel 等文档通道资料元数据（JSON）：",
            json.dumps(text_meta, ensure_ascii=False, indent=2),
            "",
            "索引清单（ref_id → 文件 / 知识库段 / 摘录）：",
            _citation_block(index),
        ]
    )
    if review_feedback.strip():
        parts.extend(
            [
                "",
                "【人工 / 多轮对话修订意见 — 必须吸收】",
                review_feedback.strip(),
            ]
        )
    return "\n".join(parts)


def _build_refine_prompt(
    project_name: str,
    current_core_content: str,
    feedback: str,
    index: list[SourceIndexEntry],
    categories: list[str],
) -> str:
    return "\n".join(
        [
            "你是财政绩效评价项目核心内容整理专家。",
            "请根据用户的修订意见，对当前《项目核心内容》进行重写优化。",
            "硬性要求：",
            "1. 保留事实，不编造新数据或新政策；",
            "2. 保持分类章节和必备维度不缺失；",
            f"   分类：{'、'.join(categories)}",
            f"   必备维度：{'、'.join(REQUIRED_DIMENSIONS)}",
            "3. 保留 [S?] 索引引用结构，不得删除或重新编号；",
            "4. 输出完整新版本核心内容正文（不要只给修改建议）；",
            "5. 输出中文 Markdown。",
            "",
            f"项目名称：{project_name}",
            "",
            "用户修订意见：",
            feedback,
            "",
            "可用索引清单：",
            _citation_block(index),
            "",
            "当前版本核心内容：",
            current_core_content,
        ]
    )


def _select_models_for_channel(
    configs: list[ModelConfig],
    channel: Literal["media", "documents"],
    media_model_id: str = "",
    docs_model_id: str = "",
    require_vision: bool = False,
) -> list[ModelConfig]:
    """Pick the model config(s) for a given channel.

    If a specific config id was bound to the channel, prefer it; otherwise
    fall back to filtering by vision capability (where the registry says
    ``supports_vision``), otherwise return the whole list.
    """
    target_id = media_model_id if channel == "media" else docs_model_id
    if target_id:
        bound = [c for c in configs if c.get("id") == target_id]
        if bound:
            return bound
    if channel == "media" and require_vision:
        vision = [c for c in configs if bool(c.get("supports_vision"))]
        if vision:
            return vision
    return configs


def _media_supports(config: ModelConfig) -> bool:
    if "supports_vision" in config:
        return bool(config.get("supports_vision"))
    name = str(config.get("model_name") or "").lower()
    label = str(config.get("label") or "").lower()
    keywords = ("vision", "vl", "omni", "multimodal", "gpt-4o", "gpt-4.1", "claude-3", "gemini", "qwen-vl", "yi-vl")
    return any(k in name or k in label for k in keywords)


async def _call_model_async(
    config: ModelConfig,
    prompt: str,
    *,
    channel: Literal["media", "documents", "combined"],
    system_prompt: str = "",
) -> ModelComparison:
    base_result: ModelComparison = {
        "model_name": str(config.get("model_name") or ""),
        "label": str(config.get("label") or config.get("model_name") or "未命名模型"),
        "provider": str(config.get("provider") or "openai-compatible"),
        "temperature": _normalize_temperature(config.get("temperature")),
        "channel": channel,
    }
    if not (config.get("base_url") and config.get("api_key") and config.get("model_name")):
        return {**base_result, "draft": "", "error": "模型缺少 base_url / api_key / model_name"}
    try:
        draft = await _call_openai_compatible_model_async(
            base_url=str(config["base_url"]),
            api_key=str(config["api_key"]),
            model_name=str(config["model_name"]),
            prompt=prompt,
            temperature=_normalize_temperature(config.get("temperature")),
            system_prompt=system_prompt or "你是严谨的政务/财政绩效评价文档生成助手。",
        )
        return {**base_result, "draft": draft}
    except Exception as exc:  # pragma: no cover - network errors
        return {**base_result, "draft": "", "error": str(exc)}


async def _generate_core_drafts_async(
    *,
    project_name: str,
    media_meta: list[DocumentItem],
    text_meta: list[DocumentItem],
    index: list[SourceIndexEntry],
    categories: list[str],
    media_configs: list[ModelConfig],
    docs_configs: list[ModelConfig],
    all_configs: list[ModelConfig],
    multi_model: bool,
    admin_system_prompt: str,
    admin_knowledge_base: str,
    review_feedback: str,
    user_kb_context: str = "",
) -> list[ModelComparison]:
    prompt = _build_core_prompt(
        project_name,
        media_meta,
        text_meta,
        index,
        categories,
        admin_system_prompt=admin_system_prompt,
        admin_knowledge_base=admin_knowledge_base,
        review_feedback=review_feedback,
        user_kb_context=user_kb_context,
    )
    system_prompt = admin_system_prompt.strip() or "你是严谨的政务/财政绩效评价文档生成助手。"

    if multi_model and all_configs:
        coros = [_call_model_async(cfg, prompt, channel="combined", system_prompt=system_prompt) for cfg in all_configs]
        return list(await asyncio.gather(*coros))

    # Single-model run: prefer the documents channel model (or media if no docs).
    if not all_configs:
        return []
    primary = (docs_configs or media_configs or all_configs)[:1]
    coros = [_call_model_async(cfg, prompt, channel="combined", system_prompt=system_prompt) for cfg in primary]
    return list(await asyncio.gather(*coros))


def _generate_core_drafts(
    *,
    project_name: str,
    media_meta: list[DocumentItem],
    text_meta: list[DocumentItem],
    index: list[SourceIndexEntry],
    categories: list[str],
    media_configs: list[ModelConfig],
    docs_configs: list[ModelConfig],
    all_configs: list[ModelConfig],
    multi_model: bool,
    admin_system_prompt: str,
    admin_knowledge_base: str,
    review_feedback: str,
    user_kb_context: str = "",
) -> list[ModelComparison]:
    return asyncio.run(
        _generate_core_drafts_async(
            project_name=project_name,
            media_meta=media_meta,
            text_meta=text_meta,
            index=index,
            categories=categories,
            media_configs=media_configs,
            docs_configs=docs_configs,
            all_configs=all_configs,
            multi_model=multi_model,
            admin_system_prompt=admin_system_prompt,
            admin_knowledge_base=admin_knowledge_base,
            review_feedback=review_feedback,
            user_kb_context=user_kb_context,
        )
    )


def _refine_core_with_llm(
    project_name: str,
    current: str,
    feedback: str,
    index: list[SourceIndexEntry],
    categories: list[str],
    context: dict[str, Any],
) -> str:
    model_config = _read_model_config(context)
    base_url = str(model_config.get("base_url") or "")
    api_key = str(model_config.get("api_key") or "")
    model_name = str(model_config.get("model_name") or "")
    if not (base_url and api_key and model_name):
        raise RuntimeError("缺少客户端模型配置，无法执行核心内容重写")

    prompt = _build_refine_prompt(project_name, current, feedback, index, categories)
    return _call_openai_compatible_model(
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        prompt=prompt,
        temperature=_normalize_temperature(model_config.get("temperature")),
        system_prompt="你是严谨的政务/财政绩效评价文档生成助手，擅长基于反馈优化核心内容。",
    )


def initialize_materials(state: Step2State, runtime: Any = None) -> Step2State:
    """Parse both upload channels and build verification artifacts."""

    if state.get("status") == "chat":
        return {"status": "chat", "updated_at": _now_iso()}

    media_paths, text_paths = _collect_paths(state)
    if not media_paths and not text_paths:
        return {
            "status": "failed",
            "error": "未提供任何资料文件（图片/PDF 通道或 Word 等文档通道均为空）。",
            "messages": [AIMessage(content="请至少在任一个上传窗口中添加资料后再继续。")],
            "updated_at": _now_iso(),
        }

    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    configs = _read_model_configs(context)
    media_model_id = str(context.get("media_model_config_id") or "")
    docs_model_id = str(context.get("documents_model_config_id") or "")

    media_configs = _select_models_for_channel(
        configs,
        "media",
        media_model_id=media_model_id,
        docs_model_id=docs_model_id,
        require_vision=True,
    ) if configs else []
    docs_configs = _select_models_for_channel(
        configs,
        "documents",
        media_model_id=media_model_id,
        docs_model_id=docs_model_id,
    ) if configs else []

    if media_configs:
        primary_media_label = str(media_configs[0].get("label") or media_configs[0].get("model_name") or "默认模型-媒体通道")
    else:
        primary_media_label = str(context.get("model_name_media") or context.get("model_name") or "默认模型-媒体通道")

    if docs_configs:
        primary_docs_label = str(docs_configs[0].get("label") or docs_configs[0].get("model_name") or "默认模型-文档通道")
    else:
        primary_docs_label = str(context.get("model_name_documents") or context.get("model_name") or "默认模型-文档通道")

    media_supports = False
    if media_configs:
        media_supports = any(_media_supports(c) for c in media_configs)
    else:
        media_supports = bool(context.get("media_model_supports_pdf_image", False))

    project_files = list(state.get("project_files", []))
    media_meta = [processor.parse(p) for p in media_paths]
    text_meta = [processor.parse(p) for p in text_paths]

    warnings: list[str] = []
    warnings.extend(_media_parse_warnings(media_meta, primary_media_label, media_supports))
    if media_paths and not media_supports:
        warnings.append(
            f"图片/PDF 通道当前指向「{primary_media_label}」；若该模型不支持多模态，"
            f"Word 等通道仍由「{primary_docs_label}」处理文本资料，请在客户端确认后再继续。"
        )

    project_name = state.get("project_name") or _detect_project_name(media_meta, text_meta)
    index = _build_source_index(media_meta, text_meta)
    digest = _render_verification_digest(project_name, media_meta, text_meta, warnings)

    default_cats = list(state.get("default_categories") or DEFAULT_CATEGORIES)
    extra = list(state.get("extra_categories") or [])

    upload_summary = {
        "total": len(project_files) or (len(media_meta) + len(text_meta)),
        "media": len(media_meta),
        "documents": len(text_meta),
    }

    return {
        "project_name": project_name,
        "project_files": project_files,
        "media_metadata": media_meta,
        "text_doc_metadata": text_meta,
        "parse_warnings": warnings,
        "verification_digest": digest,
        "verification_acknowledged": bool(state.get("verification_acknowledged", False)),
        "source_index": index,
        "default_categories": default_cats,
        "extra_categories": extra,
        "final_core_content": state.get("final_core_content", ""),
        "review_round": int(state.get("review_round", 0)),
        "status": "initialized",
        "created_at": state.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已完成双通道解析：图片/PDF {len(media_meta)} 个，Word 等文档 {len(text_meta)} 个。"
                    f"项目资料总数 {upload_summary['total']} 份；已生成「资料识别结果」供人工校验。"
                    "确认无误后可继续生成核心内容。"
                )
            )
        ],
    }


def _merged_categories(state: Step2State) -> list[str]:
    default_cats = list(state.get("default_categories") or DEFAULT_CATEGORIES)
    extra = list(state.get("extra_categories") or [])
    merged: list[str] = []
    for c in default_cats + extra:
        c = (c or "").strip()
        if c and c not in merged:
            merged.append(c)
    return merged


def build_core_draft(state: Step2State, runtime: Any = None) -> Step2State:
    """Build one or more core-content drafts via real LLM calls.

    Falls back to a structural template if no model is configured or all
    real calls fail, so the workflow stays usable in offline / smoke tests.
    """

    index = state.get("source_index", [])
    media_meta = state.get("media_metadata", [])
    text_meta = state.get("text_doc_metadata", [])
    project_name = state.get("project_name", "未命名项目")
    categories = _merged_categories(state)
    context_obj = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    context = context_obj if isinstance(context_obj, dict) else {}

    configs = _read_model_configs(context)
    media_model_id = str(context.get("media_model_config_id") or "")
    docs_model_id = str(context.get("documents_model_config_id") or "")
    media_configs = _select_models_for_channel(configs, "media", media_model_id, docs_model_id, require_vision=True)
    docs_configs = _select_models_for_channel(configs, "documents", media_model_id, docs_model_id)

    multi_model_enabled = bool(context.get("enable_multi_model", False)) and len(configs) > 1
    admin_system_prompt = str(state.get("admin_system_prompt") or context.get("admin_system_prompt") or "")
    admin_knowledge_base = str(state.get("admin_knowledge_base") or context.get("admin_knowledge_base") or "")
    review_feedback = str(state.get("review_feedback") or "").strip()

    project_id = str(context.get("project_id") or "")

    from ._llm import fetch_kb_chunks_for_step2, fetch_user_kb_context_sync

    kb_queries: list[str] = []
    for cat in categories:
        kb_queries.append(f"{project_name} {cat}")
    for dim in REQUIRED_DIMENSIONS:
        kb_queries.append(f"{project_name} {dim}")

    kb_chunks = fetch_kb_chunks_for_step2(
        project_id=project_id,
        queries=kb_queries,
        top_k_per_query=3,
    )

    if kb_chunks:
        start_idx = len(index) + 1
        kb_entries: list[SourceIndexEntry] = []
        for i, chunk in enumerate(kb_chunks):
            kb_entries.append({
                "ref_id": f"S{start_idx + i}",
                "source_name": str(chunk.get("file_name") or "知识库文档"),
                "channel": "kb",
                "excerpt": str(chunk.get("content") or "")[:500],
                "chunk_index": int(chunk.get("chunk_index") or 0),
            })
        index = list(index) + kb_entries
        user_kb_context = ""
    else:
        user_kb_context = fetch_user_kb_context_sync(
            project_id=project_id,
            query=f"{project_name} 核心内容 关键信息",
            step_code="step2",
        )

    fallback = _fallback_core_content(project_name, index, categories, "默认模型")
    export_style = state.get("export_style", "classic")
    export_format = state.get("export_format", "both")

    if not configs:
        return {
            "core_content_draft": fallback,
            "final_core_content": state.get("final_core_content") or fallback,
            "model_comparisons": [],
            "source_index": index,
            "export_filename": _build_export_filename(project_name, export_style),
            "export_payload": fallback,
            "export_format": export_format,
            "status": "draft_ready_fallback",
            "error": "未配置可用客户端模型，已使用结构化模板生成核心内容草案。",
            "updated_at": _now_iso(),
            "messages": [
                AIMessage(content="未检测到可用模型配置，已回退到结构化模板。请在客户端绑定模型后重新生成。")
            ],
        }

    try:
        comparisons = _generate_core_drafts(
            project_name=project_name,
            media_meta=media_meta,
            text_meta=text_meta,
            index=index,
            categories=categories,
            media_configs=media_configs,
            docs_configs=docs_configs,
            all_configs=configs,
            multi_model=multi_model_enabled,
            admin_system_prompt=admin_system_prompt,
            admin_knowledge_base=admin_knowledge_base,
            review_feedback=review_feedback,
            user_kb_context=user_kb_context,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return {
            "core_content_draft": fallback,
            "final_core_content": state.get("final_core_content") or fallback,
            "model_comparisons": [],
            "source_index": index,
            "export_filename": _build_export_filename(project_name, export_style),
            "export_payload": fallback,
            "export_format": export_format,
            "status": "draft_ready_fallback",
            "error": f"真实模型调用失败，已回退到结构化模板：{exc}",
            "updated_at": _now_iso(),
            "messages": [AIMessage(content=f"真实模型调用失败，已回退到结构化模板：{exc}")],
        }

    successful = [c for c in comparisons if c.get("draft")]
    if not successful:
        errors = "; ".join(f"{c.get('label') or c.get('model_name')}: {c.get('error') or '空响应'}" for c in comparisons)
        return {
            "core_content_draft": fallback,
            "final_core_content": state.get("final_core_content") or fallback,
            "model_comparisons": comparisons,
            "source_index": index,
            "export_filename": _build_export_filename(project_name, export_style),
            "export_payload": fallback,
            "export_format": export_format,
            "status": "draft_ready_fallback",
            "error": f"所有模型调用均失败：{errors}",
            "updated_at": _now_iso(),
            "messages": [AIMessage(content=f"所有模型调用均失败：{errors}。已回退到结构化模板。")],
        }

    primary = successful[0]["draft"]
    failed_count = len(comparisons) - len(successful)
    if multi_model_enabled:
        message = (
            f"已调用 {len(successful)} 份核心内容草案（共 {len(comparisons)} 个模型），"
            "可在多模型对比区切换查看、粘贴整合后再保存。"
        )
    else:
        message = "已调用真实模型生成核心内容草案，可直接编辑或通过多轮对话优化。"
    if failed_count:
        message += f"另有 {failed_count} 个模型调用失败，已保留错误信息以供排查。"

    return {
        "core_content_draft": primary,
        "final_core_content": state.get("final_core_content") or primary,
        "model_comparisons": comparisons,
        "source_index": index,
        "export_filename": _build_export_filename(project_name, export_style),
        "export_payload": primary,
        "export_format": export_format,
        "status": "draft_ready",
        "error": "",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content=message)],
    }


def _fallback_core_content(
    project_name: str,
    index: list[SourceIndexEntry],
    categories: list[str],
    model_label: str,
) -> str:
    cat_block = []
    for cat in categories:
        cat_block.append(
            f"### {cat}\n"
            f"- 与项目直接相关的要点已自洽归纳；剔除与项目无关或重复冗余表述。\n"
            f"- 关键结论均应在下方「索引与原文摘录」中找到对应出处（示例引用 [S1]、[S2]）。\n"
        )
    categories_md = "\n".join(cat_block)
    dims_md = "\n\n".join(
        f"### {dim}\n- 待补充与 {dim} 相关的事实、数据与索引引用。" for dim in REQUIRED_DIMENSIONS
    )
    return "\n".join(
        [
            f"《{project_name}项目核心内容》",
            "",
            f"生成模型：{model_label}（回退模板）",
            f"生成时间：{_now_iso()}",
            "",
            "## 分类核心内容",
            categories_md,
            "",
            "## 必备维度",
            dims_md,
            "",
            "## 索引与原文摘录",
            _citation_block(index),
            "",
            "## 说明",
            "本稿为结构化模板回退结果，请在客户端编辑或通过对话完善后再保存。",
        ]
    )


def route_review_mode(state: Step2State) -> str:
    if state.get("review_mode") == "approve":
        return "approve"
    return "modify"


def refine_core_content(state: Step2State, runtime: Any = None) -> Step2State:
    feedback = state.get("review_feedback", "").strip()
    round_no = int(state.get("review_round", 0)) + 1
    current = state.get("final_core_content") or state.get("core_content_draft") or ""
    if not feedback:
        return {
            "review_round": round_no,
            "core_content_draft": current,
            "final_core_content": current,
            "status": "refined_no_feedback",
            "updated_at": _now_iso(),
            "messages": [AIMessage(content=f"第 {round_no} 轮未提供修订意见，保持当前版本不变。")],
        }

    index = state.get("source_index", [])
    categories = _merged_categories(state)
    project_name = state.get("project_name", "未命名项目")
    context_obj = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    context = context_obj if isinstance(context_obj, dict) else {}

    try:
        refined = _refine_core_with_llm(project_name, current, feedback, index, categories, context)
        status = "refined_llm"
    except Exception as exc:
        # Fallback to deterministic concatenation so the workflow keeps progressing.
        refined = (
            f"{current}\n\n"
            f"【第 {round_no} 轮人工 / 对话优化意见】\n{feedback}\n\n"
            f"【系统更新说明（回退模板）】\n"
            f"未能调用真实模型重写：{exc}。已保留索引引用结构，请在客户端继续手工调整。"
        )
        status = "refined_fallback"

    return {
        "review_round": round_no,
        "core_content_draft": refined,
        "final_core_content": refined,
        "status": status,
        "updated_at": _now_iso(),
        "messages": [AIMessage(content=f"已完成第 {round_no} 轮核心内容优化，请继续确认是否满意。")],
    }


def approve_core_content(state: Step2State) -> Step2State:
    final_body = state.get("final_core_content") or state.get("core_content_draft") or ""
    project_name = state.get("project_name", "未命名项目")

    if not final_body:
        index = state.get("source_index", [])
        cats = _merged_categories(state)
        final_body = _fallback_core_content(project_name, index, cats, "默认模型")

    return {
        "final_core_content": final_body,
        "export_filename": state.get("export_filename")
        or _build_export_filename(project_name, state.get("export_style", "classic")),
        "export_payload": final_body,
        "status": "approved",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="核心内容已确认，可一键导入成品区并导出 PDF / Word（文件名含「项目核心内容」）。")],
    }


def _extract_latest_user_text(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = message.content
            if isinstance(content, str):
                return content.strip()
    return ""


def _chat_node(state: Step2State, runtime: Any = None) -> Step2State:
    context_obj = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    context = context_obj if isinstance(context_obj, dict) else {}
    workflow_state = dict(context.get("workflow_state") or {}) if isinstance(context.get("workflow_state"), dict) else {}
    project_name = state.get("project_name") or str(workflow_state.get("project_name") or context.get("project_id") or "未命名项目")
    step_code = str(workflow_state.get("step_code") or context.get("step_code") or "step2")
    messages = list(state.get("messages", []))
    user_text = str(context.get("latest_user_message") or "").strip() or _extract_latest_user_text(messages)

    if not user_text:
        return {
            "status": "chat_reply",
            "updated_at": _now_iso(),
            "answer": "请在输入框中描述你希望修改的内容（例如：增加资金审计要点，或替换为更紧凑的语气）。",
            "messages": [AIMessage(content="请在输入框中描述你希望修改的内容。")],
        }

    refine_keywords = ("重写", "改写", "优化核心", "再生成", "再写", "生成核心", "生成新版本", "刷新核心", "替换核心")
    intent_refine = any(k in user_text for k in refine_keywords)

    if intent_refine:
        index = state.get("source_index", [])
        categories = _merged_categories(state)
        current = state.get("final_core_content") or state.get("core_content_draft") or ""
        try:
            refined = _refine_core_with_llm(project_name, current, user_text, index, categories, context)
            status = "chat_executed_refine_llm"
            answer = refined
            new_round = int(state.get("review_round", 0)) + 1
            return {
                "review_round": new_round,
                "review_feedback": user_text,
                "core_content_draft": refined,
                "final_core_content": refined,
                "export_payload": refined,
                "status": status,
                "updated_at": _now_iso(),
                "answer": answer,
                "messages": [AIMessage(content=refined)],
            }
        except Exception as exc:
            answer = f"AI 改写失败：{exc}。请检查当前模型配置或重试。"
            return {
                "status": "chat_model_failed",
                "error": str(exc),
                "updated_at": _now_iso(),
                "answer": answer,
                "messages": [AIMessage(content=answer)],
            }

    # General Q&A using whichever model is currently bound to documents channel.
    model_config = _read_model_config(context)
    if not (model_config.get("base_url") and model_config.get("api_key") and model_config.get("model_name")):
        answer = (
            "AI 对话模型未配置 base_url / api_key / model_name，"
            "请先在 Step1 模型配置卡片中绑定并保存后再发起对话。"
        )
        return {
            "status": "chat_model_failed",
            "updated_at": _now_iso(),
            "answer": answer,
            "messages": [AIMessage(content=answer)],
        }

    draft = state.get("final_core_content") or state.get("core_content_draft") or ""
    chat_prompt = "\n".join(
        [
            "你是 Step2 工作流助手，负责帮助用户理解、确认或优化《项目核心内容》。",
            "约束：",
            "1. 只针对用户问题作答；",
            "2. 在涉及内容修改时引用 [S?] 索引；",
            "3. 不要捏造未在资料中出现的数据。",
            "",
            f"项目：{project_name} / 步骤：{step_code}",
            "当前核心内容摘要（截断）：",
            draft[:1800] if draft else "（暂无核心内容草案）",
            "",
            "用户提问：",
            user_text,
        ]
    )
    try:
        answer = _call_openai_compatible_model(
            base_url=str(model_config["base_url"]),
            api_key=str(model_config["api_key"]),
            model_name=str(model_config["model_name"]),
            prompt=chat_prompt,
            temperature=_normalize_temperature(model_config.get("temperature")),
            system_prompt="你是严谨的政务/财政绩效评价文档生成助手。",
        )
        status = "chat_reply"
        error = ""
    except Exception as exc:
        answer = f"AI 对话模型调用失败：{exc}。请检查当前模型配置。"
        status = "chat_model_failed"
        error = str(exc)
    return {
        "status": status,
        "error": error,
        "updated_at": _now_iso(),
        "answer": answer,
        "messages": [AIMessage(content=answer)],
    }


def build_graph() -> Any:
    graph = StateGraph(Step2State, context_schema=Step2Context)
    graph.add_node("initialize_materials", initialize_materials)
    graph.add_node("build_core_draft", build_core_draft)
    graph.add_node("refine_core_content", refine_core_content)
    graph.add_node("approve_core_content", approve_core_content)
    graph.add_node("chat", _chat_node)

    graph.add_edge(START, "initialize_materials")
    graph.add_conditional_edges(
        "initialize_materials",
        lambda state: "chat" if state.get("status") == "chat" else "build_core_draft",
        {
            "chat": "chat",
            "build_core_draft": "build_core_draft",
        },
    )

    graph.add_conditional_edges(
        "build_core_draft",
        route_review_mode,
        {
            "modify": "refine_core_content",
            "approve": "approve_core_content",
        },
    )

    graph.add_edge("refine_core_content", "build_core_draft")
    graph.add_edge("approve_core_content", END)
    graph.add_edge("chat", END)

    memory = MemorySaver()
    return graph.compile(checkpointer=memory, name="evalflow-pro-step2")


graph = build_graph()
