"""Admin Step 1 graph — 生成资料清单：Prompt / 知识库配置与变更日志。"""

from __future__ import annotations

from datetime import datetime, timezone
import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

STEP_CODE = "step1"
STEP_NAME = "生成资料清单配置"
MIN_PROMPT_LEN = 32
MIN_KB_LEN = 16
MAX_FIELD_LEN = 120_000


class ChangeEntry(TypedDict, total=False):
    target_type: Literal["prompt", "kb"]
    action: Literal["create", "update", "unchanged"]
    field: str
    summary: str
    before_excerpt: str
    after_excerpt: str


class AdminStep1State(TypedDict, total=False):
    step_code: str
    action: Literal["save", "preview"]
    project_name: str
    actor_user_id: str
    prompt_title: str
    prompt_text: str
    kb_name: str
    knowledge_text: str
    previous_prompt_title: str
    previous_prompt_text: str
    previous_kb_name: str
    previous_knowledge_text: str
    change_entries: list[ChangeEntry]
    change_log: str
    draft_markdown: str
    final_markdown: str
    export_filename: str
    export_payload: str
    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class AdminStep1Context(TypedDict, total=False):
    project_id: str
    user_id: str
    model_name: str
    output_dir: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _excerpt(text: str, limit: int = 180) -> str:
    cleaned = (text or "").strip().replace("\r\n", "\n")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def _normalize_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").strip()


def _diff_field(
    *,
    target_type: Literal["prompt", "kb"],
    field: str,
    label: str,
    before: str,
    after: str,
) -> ChangeEntry | None:
    if before == after:
        return {
            "target_type": target_type,
            "action": "unchanged",
            "field": field,
            "summary": f"{label}未变更",
            "before_excerpt": _excerpt(before),
            "after_excerpt": _excerpt(after),
        }
    action: Literal["create", "update"] = "create" if not before else "update"
    return {
        "target_type": target_type,
        "action": action,
        "field": field,
        "summary": f"{label}{'新增' if action == 'create' else '已修改'}（{len(before)} → {len(after)} 字）",
        "before_excerpt": _excerpt(before),
        "after_excerpt": _excerpt(after),
    }


def load_context(state: AdminStep1State, runtime: Any = None) -> AdminStep1State:
    _ = runtime
    return {
        "step_code": state.get("step_code") or STEP_CODE,
        "action": state.get("action") or "preview",
        "project_name": _normalize_text(state.get("project_name")) or STEP_NAME,
        "prompt_title": _normalize_text(state.get("prompt_title")) or "资料清单生成 Prompt",
        "prompt_text": _normalize_text(state.get("prompt_text")),
        "kb_name": _normalize_text(state.get("kb_name")) or "资料清单知识库",
        "knowledge_text": _normalize_text(state.get("knowledge_text")),
        "previous_prompt_title": _normalize_text(state.get("previous_prompt_title")),
        "previous_prompt_text": _normalize_text(state.get("previous_prompt_text")),
        "previous_kb_name": _normalize_text(state.get("previous_kb_name")),
        "previous_knowledge_text": _normalize_text(state.get("previous_knowledge_text")),
        "status": "loaded",
        "created_at": state.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
        "messages": [AIMessage(content=f"已加载 {STEP_NAME} 当前配置，可进行预览或保存。")],
    }


def compute_changes(state: AdminStep1State) -> AdminStep1State:
    entries: list[ChangeEntry] = []
    prompt_title_entry = _diff_field(
        target_type="prompt",
        field="title",
        label="Prompt 标题",
        before=state.get("previous_prompt_title") or "",
        after=state.get("prompt_title") or "",
    )
    prompt_content_entry = _diff_field(
        target_type="prompt",
        field="content",
        label="Prompt 正文",
        before=state.get("previous_prompt_text") or "",
        after=state.get("prompt_text") or "",
    )
    kb_name_entry = _diff_field(
        target_type="kb",
        field="name",
        label="知识库名称",
        before=state.get("previous_kb_name") or "",
        after=state.get("kb_name") or "",
    )
    kb_content_entry = _diff_field(
        target_type="kb",
        field="storage_ref",
        label="知识库内容",
        before=state.get("previous_knowledge_text") or "",
        after=state.get("knowledge_text") or "",
    )
    for entry in (prompt_title_entry, prompt_content_entry, kb_name_entry, kb_content_entry):
        if entry:
            entries.append(entry)

    meaningful = [e for e in entries if e.get("action") != "unchanged"]
    lines = []
    for entry in meaningful:
        lines.append(f"- [{entry.get('target_type')}] {entry.get('summary')}")
        if entry.get("before_excerpt"):
            lines.append(f"  改前：{entry.get('before_excerpt')}")
        if entry.get("after_excerpt"):
            lines.append(f"  改后：{entry.get('after_excerpt')}")
    change_log = "\n".join(lines) if lines else "本次未检测到 Prompt 或知识库内容变更。"

    return {
        "change_entries": entries,
        "change_log": change_log,
        "status": "diff_ready",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content=f"已分析变更：{len(meaningful)} 项有效修改。")],
    }


def validate_config(state: AdminStep1State) -> AdminStep1State:
    prompt_text = state.get("prompt_text") or ""
    knowledge_text = state.get("knowledge_text") or ""
    errors: list[str] = []
    if len(prompt_text) < MIN_PROMPT_LEN:
        errors.append(f"Prompt 正文不少于 {MIN_PROMPT_LEN} 个字符")
    if len(knowledge_text) < MIN_KB_LEN:
        errors.append(f"知识库内容不少于 {MIN_KB_LEN} 个字符")
    if len(prompt_text) > MAX_FIELD_LEN or len(knowledge_text) > MAX_FIELD_LEN:
        errors.append("单字段长度超出上限")
    if errors:
        return {
            "status": "validation_failed",
            "error": "；".join(errors),
            "updated_at": _now_iso(),
            "messages": [AIMessage(content="配置校验未通过：" + "；".join(errors))],
        }
    return {
        "status": "validated",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="配置校验通过。")],
    }


def route_after_validate(state: AdminStep1State) -> str:
    if state.get("status") == "validation_failed":
        return "failed"
    return "ok"


def build_preview(state: AdminStep1State) -> AdminStep1State:
    prompt_text = state.get("prompt_text") or ""
    knowledge_text = state.get("knowledge_text") or ""
    md = "\n".join(
        [
            f"# {state.get('project_name') or STEP_NAME}",
            "",
            "## 启用 Prompt",
            f"**标题**：{state.get('prompt_title') or '（未命名）'}",
            "",
            "```text",
            prompt_text,
            "```",
            "",
            "## 启用知识库",
            f"**名称**：{state.get('kb_name') or '（未命名）'}",
            "",
            "```markdown",
            knowledge_text,
            "```",
            "",
            "## 变更摘要",
            state.get("change_log") or "无变更",
            "",
            f"> 操作模式：{'保存并发布新版本' if state.get('action') == 'save' else '仅预览'}",
        ]
    )
    return {
        "draft_markdown": md,
        "status": "draft_ready",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="已生成配置预览。")],
    }


def finalize_config(state: AdminStep1State) -> AdminStep1State:
    md = state.get("draft_markdown") or ""
    export_name = f"{state.get('project_name') or '管理端配置'}_{STEP_CODE}"
    persist_entries = [
        e for e in (state.get("change_entries") or [])
        if e.get("action") in {"create", "update"}
        and e.get("field") in {"content", "storage_ref"}
    ]
    return {
        "final_markdown": md,
        "export_payload": md,
        "export_filename": export_name,
        "change_entries": persist_entries,
        "status": "completed" if state.get("action") == "save" else "preview_completed",
        "updated_at": _now_iso(),
        "messages": [
            AIMessage(
                content=(
                    "管理端第1步配置已保存。"
                    if state.get("action") == "save"
                    else "管理端第1步配置预览完成（未写入数据库）。"
                )
            )
        ],
    }


def build_graph() -> Any:
    graph = StateGraph(AdminStep1State, context_schema=AdminStep1Context)
    graph.add_node("load_context", load_context)
    graph.add_node("compute_changes", compute_changes)
    graph.add_node("validate_config", validate_config)
    graph.add_node("build_preview", build_preview)
    graph.add_node("finalize_config", finalize_config)

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "compute_changes")
    graph.add_edge("compute_changes", "validate_config")
    graph.add_conditional_edges(
        "validate_config",
        route_after_validate,
        {"ok": "build_preview", "failed": END},
    )
    graph.add_edge("build_preview", "finalize_config")
    graph.add_edge("finalize_config", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-admin-step1")


graph = build_graph()
