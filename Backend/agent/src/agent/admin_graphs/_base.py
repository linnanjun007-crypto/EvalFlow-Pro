"""Admin graph factory for EvalFlow Pro.

Most admin steps share the same shape:

1. ``validate_inputs``  — sanity-check prompt/kb fields and load previous values.
2. ``apply_changes``    — diff previous vs new fields, build ``change_entries``
                          (no DB write — the FastAPI service layer does that).
3. ``generate_preview`` — render a markdown preview of the new config.
4. ``audit_log``        — write a human-readable log line that points at the
                          actor/operation; reflected in ``messages``.
5. ``finalize``         — set ``status`` and ``content_text`` so the front end
                          can persist the result via ``/steps/{step}/save``.

Steps 1, 2, 3, 4… 14 (admin variant) all reuse this factory.  Step 1 has a
slightly richer flow (it deals with the资料清单 wizard's title/excerpts), so it
keeps its own ``step1.py`` and is *not* migrated to the factory.

State shape
-----------

The state dict tries to be tolerant about field names:

- ``prompt_content`` / ``prompt_text``    — same Prompt body, both accepted.
- ``kb_content``     / ``knowledge_text`` — same KB body, both accepted.

Reads always look at the new names first, falling back to the old aliases.
Writes populate **both** so legacy consumers (e.g. the existing admin step1
graph) continue to see ``prompt_text`` / ``knowledge_text``.

Outputs
-------

``status`` is one of:

- ``"success"``       — ``action == "save"`` finished.
- ``"preview_ready"`` — ``action == "preview"`` finished.
- ``"validation_failed"`` — inputs rejected.

``change_entries`` is a list of ``ChangeEntry`` describing per-field diffs.
``content_text`` mirrors the markdown preview so the FastAPI layer can store
it as the step's text payload.
"""

from __future__ import annotations

from datetime import datetime, timezone
import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

DEFAULT_MIN_PROMPT_LEN = 16
DEFAULT_MIN_KB_LEN = 8
MAX_FIELD_LEN = 120_000


class ChangeEntry(TypedDict, total=False):
    target_type: Literal["prompt", "kb"]
    action: Literal["create", "update", "unchanged"]
    field: str
    summary: str
    before_excerpt: str
    after_excerpt: str


class AdminState(TypedDict, total=False):
    step_code: str
    action: Literal["save", "preview"]
    project_name: str
    actor_user_id: str

    prompt_title: str
    prompt_content: str
    prompt_text: str
    kb_name: str
    kb_content: str
    knowledge_text: str

    previous_prompt_title: str
    previous_prompt_content: str
    previous_prompt_text: str
    previous_kb_name: str
    previous_kb_content: str
    previous_knowledge_text: str

    change_entries: list[ChangeEntry]
    change_log: str
    audit_log: str
    draft_markdown: str
    final_markdown: str
    content_text: str
    export_filename: str
    export_payload: str

    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class AdminContext(TypedDict, total=False):
    project_id: str
    user_id: str
    model_name: str
    output_dir: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _normalize_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").strip()


def _excerpt(text: str, limit: int = 180) -> str:
    cleaned = (text or "").strip().replace("\r\n", "\n")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def _pick_prompt_content(state: AdminState) -> str:
    return _normalize_text(state.get("prompt_content") or state.get("prompt_text"))


def _pick_kb_content(state: AdminState) -> str:
    return _normalize_text(state.get("kb_content") or state.get("knowledge_text"))


def _pick_previous_prompt_content(state: AdminState) -> str:
    return _normalize_text(state.get("previous_prompt_content") or state.get("previous_prompt_text"))


def _pick_previous_kb_content(state: AdminState) -> str:
    return _normalize_text(state.get("previous_kb_content") or state.get("previous_knowledge_text"))


def _diff_field(
    *,
    target_type: Literal["prompt", "kb"],
    field: str,
    label: str,
    before: str,
    after: str,
) -> ChangeEntry:
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


def build_admin_graph(
    *,
    step_code: str,
    step_name: str,
    default_prompt_title: str = "",
    default_kb_name: str = "",
    min_prompt_len: int = DEFAULT_MIN_PROMPT_LEN,
    min_kb_len: int = DEFAULT_MIN_KB_LEN,
) -> Any:
    """Build a reusable admin StateGraph.

    Parameters
    ----------
    step_code:
        ``"step2"``, ``"step3"`` ... — used in graph name + status messages.
    step_name:
        Human-readable label, e.g. ``"核心内容 Prompt 配置"``.
    default_prompt_title / default_kb_name:
        Used as fallbacks when the caller doesn't pass values.
    min_prompt_len / min_kb_len:
        Soft validation limits.  Setting either to ``0`` disables that check.
    """

    fallback_prompt_title = default_prompt_title or f"{step_name} Prompt"
    fallback_kb_name = default_kb_name or f"{step_name}知识库"

    def validate_inputs(state: AdminState, runtime: Any = None) -> AdminState:
        _ = runtime
        prompt_content = _pick_prompt_content(state)
        kb_content = _pick_kb_content(state)
        errors: list[str] = []
        if min_prompt_len and len(prompt_content) < min_prompt_len:
            errors.append(f"Prompt 正文不少于 {min_prompt_len} 个字符")
        if min_kb_len and len(kb_content) < min_kb_len:
            errors.append(f"知识库内容不少于 {min_kb_len} 个字符")
        if len(prompt_content) > MAX_FIELD_LEN or len(kb_content) > MAX_FIELD_LEN:
            errors.append("单字段长度超出上限")

        normalized = {
            "step_code": state.get("step_code") or step_code,
            "action": state.get("action") or "preview",
            "project_name": _normalize_text(state.get("project_name")) or step_name,
            "prompt_title": _normalize_text(state.get("prompt_title")) or fallback_prompt_title,
            "prompt_content": prompt_content,
            "prompt_text": prompt_content,
            "kb_name": _normalize_text(state.get("kb_name")) or fallback_kb_name,
            "kb_content": kb_content,
            "knowledge_text": kb_content,
            "previous_prompt_title": _normalize_text(state.get("previous_prompt_title")),
            "previous_prompt_content": _pick_previous_prompt_content(state),
            "previous_prompt_text": _pick_previous_prompt_content(state),
            "previous_kb_name": _normalize_text(state.get("previous_kb_name")),
            "previous_kb_content": _pick_previous_kb_content(state),
            "previous_knowledge_text": _pick_previous_kb_content(state),
            "created_at": state.get("created_at") or _now_iso(),
            "updated_at": _now_iso(),
        }

        if errors:
            return {
                **normalized,
                "status": "validation_failed",
                "error": "；".join(errors),
                "messages": [AIMessage(content=f"{step_name}校验未通过：" + "；".join(errors))],
            }
        return {
            **normalized,
            "status": "validated",
            "error": "",
            "messages": [AIMessage(content=f"已加载{step_name}当前配置，可进行预览或保存。")],
        }

    def route_after_validate(state: AdminState) -> str:
        return "failed" if state.get("status") == "validation_failed" else "ok"

    def apply_changes(state: AdminState) -> AdminState:
        prompt_title = state.get("prompt_title") or ""
        prev_prompt_title = state.get("previous_prompt_title") or ""
        prompt_content = _pick_prompt_content(state)
        prev_prompt_content = _pick_previous_prompt_content(state)
        kb_name = state.get("kb_name") or ""
        prev_kb_name = state.get("previous_kb_name") or ""
        kb_content = _pick_kb_content(state)
        prev_kb_content = _pick_previous_kb_content(state)

        entries: list[ChangeEntry] = [
            _diff_field(target_type="prompt", field="title", label="Prompt 标题", before=prev_prompt_title, after=prompt_title),
            _diff_field(target_type="prompt", field="content", label="Prompt 正文", before=prev_prompt_content, after=prompt_content),
            _diff_field(target_type="kb", field="name", label="知识库名称", before=prev_kb_name, after=kb_name),
            _diff_field(target_type="kb", field="storage_ref", label="知识库内容", before=prev_kb_content, after=kb_content),
        ]
        meaningful = [e for e in entries if e.get("action") != "unchanged"]
        lines: list[str] = []
        for entry in meaningful:
            lines.append(f"- [{entry.get('target_type')}] {entry.get('summary')}")
            if entry.get("before_excerpt"):
                lines.append(f"  改前：{entry.get('before_excerpt')}")
            if entry.get("after_excerpt"):
                lines.append(f"  改后：{entry.get('after_excerpt')}")
        change_log = "\n".join(lines) if lines else f"本次未检测到{step_name}的有效变更。"
        return {
            "change_entries": entries,
            "change_log": change_log,
            "status": "diff_ready",
            "updated_at": _now_iso(),
            "messages": [AIMessage(content=f"已分析{step_name}变更：{len(meaningful)} 项有效修改。")],
        }

    def generate_preview(state: AdminState) -> AdminState:
        prompt_content = _pick_prompt_content(state)
        kb_content = _pick_kb_content(state)
        action_text = "保存并发布新版本" if state.get("action") == "save" else "仅预览"
        md = "\n".join(
            [
                f"# {state.get('project_name') or step_name}",
                "",
                "## 启用 Prompt",
                f"**标题**：{state.get('prompt_title') or '（未命名）'}",
                "",
                "```text",
                prompt_content,
                "```",
                "",
                "## 启用知识库",
                f"**名称**：{state.get('kb_name') or '（未命名）'}",
                "",
                "```markdown",
                kb_content,
                "```",
                "",
                "## 变更摘要",
                state.get("change_log") or "无变更",
                "",
                f"> 操作模式：{action_text}",
            ]
        )
        return {
            "draft_markdown": md,
            "status": "draft_ready",
            "updated_at": _now_iso(),
            "messages": [AIMessage(content=f"已生成{step_name}配置预览。")],
        }

    def audit_log(state: AdminState) -> AdminState:
        actor = state.get("actor_user_id") or "未知用户"
        action = state.get("action") or "preview"
        action_text = "保存" if action == "save" else "预览"
        meaningful = [e for e in (state.get("change_entries") or []) if e.get("action") != "unchanged"]
        log = f"[{_now_iso()}] {actor} 对 {step_code} 执行 {action_text}：{len(meaningful)} 项有效变更。"
        return {
            "audit_log": log,
            "status": "audited",
            "updated_at": _now_iso(),
            "messages": [AIMessage(content=log)],
        }

    def finalize(state: AdminState) -> AdminState:
        md = state.get("draft_markdown") or ""
        action = state.get("action") or "preview"
        export_name = f"{state.get('project_name') or step_name}_{step_code}"
        persist_entries = [
            e for e in (state.get("change_entries") or [])
            if e.get("action") in {"create", "update"}
            and e.get("field") in {"content", "storage_ref"}
        ]
        if action == "save":
            status = "success"
            tail = f"管理端{step_code}配置已保存。"
        else:
            status = "preview_ready"
            tail = f"管理端{step_code}配置预览完成（未写入数据库）。"
        return {
            "final_markdown": md,
            "content_text": md,
            "export_payload": md,
            "export_filename": export_name,
            "change_entries": persist_entries,
            "status": status,
            "updated_at": _now_iso(),
            "messages": [AIMessage(content=tail)],
        }

    graph = StateGraph(AdminState, context_schema=AdminContext)
    graph.add_node("validate_inputs", validate_inputs)
    graph.add_node("apply_changes", apply_changes)
    graph.add_node("generate_preview", generate_preview)
    graph.add_node("audit_log", audit_log)
    graph.add_node("finalize", finalize)

    graph.add_edge(START, "validate_inputs")
    graph.add_conditional_edges(
        "validate_inputs",
        route_after_validate,
        {"ok": "apply_changes", "failed": END},
    )
    graph.add_edge("apply_changes", "generate_preview")
    graph.add_edge("generate_preview", "audit_log")
    graph.add_edge("audit_log", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=MemorySaver(), name=f"evalflow-pro-admin-{step_code}")


__all__ = [
    "AdminState",
    "AdminContext",
    "ChangeEntry",
    "build_admin_graph",
]
