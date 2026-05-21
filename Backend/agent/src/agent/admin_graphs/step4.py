from __future__ import annotations

from datetime import datetime, timezone
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph


class AdminStep4State(TypedDict, total=False):
    project_name: str
    prompt_text: str
    knowledge_text: str
    draft_markdown: str
    final_markdown: str
    export_filename: str
    export_payload: str
    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    created_at: str
    updated_at: str


class AdminStep4Context(TypedDict, total=False):
    project_id: str
    user_id: str
    model_name: str
    output_dir: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_graph() -> Any:
    graph = StateGraph(AdminStep4State, context_schema=AdminStep4Context)

    def validate(s: AdminStep4State) -> AdminStep4State:
        return {"project_name": (s.get("project_name") or "管理端配置").strip() or "管理端配置", "status": "basis_ok", "created_at": s.get("created_at") or _now_iso(), "updated_at": _now_iso(), "messages": [AIMessage(content="已进入管理端第4步。")]} 

    def draft(s: AdminStep4State, runtime: Any = None) -> AdminStep4State:
        _ = runtime
        return {"draft_markdown": f"## 第4步\n- Prompt：{s.get('prompt_text', '（待填写）')}\n- 知识库：{s.get('knowledge_text', '（待填写）')}", "status": "draft_ready", "updated_at": _now_iso(), "messages": [AIMessage(content="已生成第4步草稿。")]} 

    def finalize(s: AdminStep4State) -> AdminStep4State:
        md = s.get("draft_markdown", "")
        return {"final_markdown": md, "export_payload": md, "export_filename": f"{s.get('project_name', '管理端配置')}Step4配置", "status": "completed", "updated_at": _now_iso(), "messages": [AIMessage(content="管理端第4步已完成。")]} 

    graph.add_node("validate", validate)
    graph.add_node("draft", draft)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "validate")
    graph.add_edge("validate", "draft")
    graph.add_edge("draft", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-admin-step4")


graph = build_graph()
