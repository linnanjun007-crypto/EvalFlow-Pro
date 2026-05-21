from __future__ import annotations

from datetime import datetime, timezone
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph


class AdminStep13State(TypedDict, total=False):
    project_name: str
    prompt_text: str
    knowledge_text: str
    module_order_locked: bool
    editable_module_order: list[str]
    module_notes: list[str]
    draft_markdown: str
    final_markdown: str
    export_filename: str
    export_payload: str
    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class AdminStep13Context(TypedDict, total=False):
    project_id: str
    user_id: str
    model_name: str
    output_dir: str


DEFAULT_MODULE_ORDER = [
    "绩效评价目的",
    "绩效评价对象",
    "绩效评价范围",
    "绩效评价原则",
    "绩效评价指标",
    "绩效评价方法",
    "绩效评价标准",
    "绩效评价工作过程",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_basis(state: AdminStep13State) -> AdminStep13State:
    return {
        "project_name": (state.get("project_name") or "管理端配置").strip() or "管理端配置",
        "editable_module_order": list(state.get("editable_module_order") or DEFAULT_MODULE_ORDER),
        "module_notes": list(state.get("module_notes") or []),
        "module_order_locked": bool(state.get("module_order_locked", False)),
        "status": "basis_ok",
        "created_at": state.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="已进入管理端第13步：工作开展情况模块顺序与提示词配置。")],
    }


def draft_module_policy(state: AdminStep13State, runtime: Any = None) -> AdminStep13State:
    _ = runtime
    order = list(state.get("editable_module_order") or DEFAULT_MODULE_ORDER)
    locked = bool(state.get("module_order_locked", False))
    notes = list(state.get("module_notes") or [])
    if not notes:
        notes = ["模块顺序可在客户端查看并调整，但模块名称保持不变。"]
    md = ["## 第13步：绩效评价工作开展情况配置", f"- 顺序锁定：{'是' if locked else '否'}", "", "### 模块顺序"]
    for i, name in enumerate(order, start=1):
        md.append(f"{i}. {name}")
    md.extend(["", "### 配置说明"])
    md.extend([f"- {n}" for n in notes])
    return {
        "draft_markdown": "\n".join(md),
        "status": "draft_ready",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="已生成第13步工作开展情况模块顺序草稿。")],
    }


def finalize_module_policy(state: AdminStep13State) -> AdminStep13State:
    md = state.get("draft_markdown") or ""
    return {
        "final_markdown": md,
        "export_payload": md,
        "export_filename": f"{state.get('project_name', '管理端配置')}Step13配置",
        "status": "completed",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="管理端第13步已完成，可配置客户端可见顺序规则。")],
    }


def build_graph() -> Any:
    graph = StateGraph(AdminStep13State, context_schema=AdminStep13Context)
    graph.add_node("validate", validate_basis)
    graph.add_node("draft", draft_module_policy)
    graph.add_node("finalize", finalize_module_policy)
    graph.add_edge(START, "validate")
    graph.add_edge("validate", "draft")
    graph.add_edge("draft", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-admin-step13")


graph = build_graph()
