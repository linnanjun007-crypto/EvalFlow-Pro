from __future__ import annotations

from datetime import datetime, timezone
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph


class AdminStep5State(TypedDict, total=False):
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


class AdminStep5Context(TypedDict, total=False):
    project_id: str
    user_id: str
    model_name: str
    output_dir: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_graph() -> Any:
    graph = StateGraph(AdminStep5State, context_schema=AdminStep5Context)

    def validate(s: AdminStep5State) -> AdminStep5State:
        return {"project_name": (s.get("project_name") or "管理端配置").strip() or "管理端配置", "status": "basis_ok", "created_at": s.get("created_at") or _now_iso(), "updated_at": _now_iso(), "messages": [AIMessage(content="已进入管理端第5步：评分标准 Prompt / 知识库配置。")]} 

    def draft(s: AdminStep5State, runtime: Any = None) -> AdminStep5State:
        _ = runtime
        md = f"## 第5步\n- 用于评分标准生成的 Prompt：{s.get('prompt_text', '（待填写）')}\n- 参考知识库：{s.get('knowledge_text', '（待填写）')}"
        return {"draft_markdown": md, "status": "draft_ready", "updated_at": _now_iso(), "messages": [AIMessage(content="已生成第5步草稿。")]} 

    def finalize(s: AdminStep5State) -> AdminStep5State:
        md = s.get("draft_markdown", "")
        return {"final_markdown": md, "export_payload": md, "export_filename": f"{s.get('project_name', '管理端配置')}Step5配置", "status": "completed", "updated_at": _now_iso(), "messages": [AIMessage(content="管理端第5步已完成。")]} 

    graph.add_node("validate", validate)
    graph.add_node("draft", draft)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "validate")
    graph.add_edge("validate", "draft")
    graph.add_edge("draft", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-admin-step5")


graph = build_graph()
