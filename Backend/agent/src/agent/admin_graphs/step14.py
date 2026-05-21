from __future__ import annotations

from datetime import datetime, timezone
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph


class AdminStep14State(TypedDict, total=False):
    project_name: str
    prompt_text: str
    knowledge_text: str
    module_order_locked: bool
    editable_report_order: list[str]
    section_notes: list[str]
    draft_markdown: str
    final_markdown: str
    export_filename: str
    export_payload: str
    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class AdminStep14Context(TypedDict, total=False):
    project_id: str
    user_id: str
    model_name: str
    output_dir: str


DEFAULT_REPORT_ORDER = [
    "基本情况",
    "绩效评价工作开展情况",
    "绩效评价指标体系",
    "绩效评价指标体系得分表",
    "经验做法",
    "问题及原因分析",
    "建议",
    "综合评价分析及评价结论",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_basis(state: AdminStep14State) -> AdminStep14State:
    return {
        "project_name": (state.get("project_name") or "管理端配置").strip() or "管理端配置",
        "editable_report_order": list(state.get("editable_report_order") or DEFAULT_REPORT_ORDER),
        "section_notes": list(state.get("section_notes") or []),
        "module_order_locked": bool(state.get("module_order_locked", False)),
        "status": "basis_ok",
        "created_at": state.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="已进入管理端第14步：最终报告模块顺序配置。")],
    }


def draft_report_policy(state: AdminStep14State, runtime: Any = None) -> AdminStep14State:
    _ = runtime
    order = list(state.get("editable_report_order") or DEFAULT_REPORT_ORDER)
    notes = list(state.get("section_notes") or [])
    if not notes:
        notes = ["客户端可查看/调整顺序，但模块名称保持固定。", "支持按项目需要自定义组合顺序。"]
    md = ["## 第14步：最终评价报告模块顺序配置", f"- 顺序锁定：{'是' if state.get('module_order_locked') else '否'}", "", "### 报告模块顺序"]
    for i, name in enumerate(order, start=1):
        md.append(f"{i}. {name}")
    md.extend(["", "### 配置说明"])
    md.extend([f"- {n}" for n in notes])
    md.extend(["", "### 输出规则", "- 支持固定顺序或自定义顺序。", "- 支持导出前预览与人工复核。"])
    return {
        "draft_markdown": "\n".join(md),
        "status": "draft_ready",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="已生成第14步最终报告顺序配置草稿。")],
    }


def finalize_report_policy(state: AdminStep14State) -> AdminStep14State:
    md = state.get("draft_markdown") or ""
    return {
        "final_markdown": md,
        "export_payload": md,
        "export_filename": f"{state.get('project_name', '管理端配置')}Step14配置",
        "status": "completed",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="管理端第14步已完成。")],
    }


def build_graph() -> Any:
    graph = StateGraph(AdminStep14State, context_schema=AdminStep14Context)
    graph.add_node("validate", validate_basis)
    graph.add_node("draft", draft_report_policy)
    graph.add_node("finalize", finalize_report_policy)
    graph.add_edge(START, "validate")
    graph.add_edge("validate", "draft")
    graph.add_edge("draft", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-admin-step14")


graph = build_graph()
