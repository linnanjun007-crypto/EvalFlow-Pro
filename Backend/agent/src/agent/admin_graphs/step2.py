"""Admin Step 2 graph for EvalFlow Pro — 核心内容 Prompt / 知识库管理。"""

from __future__ import annotations

from datetime import datetime, timezone
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph


class AdminStep2State(TypedDict, total=False):
    project_name: str
    prompt_text: str
    knowledge_text: str
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


class AdminStep2Context(TypedDict, total=False):
    project_id: str
    user_id: str
    model_name: str
    output_dir: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_graph() -> Any:
    graph = StateGraph(AdminStep2State, context_schema=AdminStep2Context)

    def validate_basis(state: AdminStep2State) -> AdminStep2State:
        return {"project_name": (state.get("project_name") or "管理端配置").strip() or "管理端配置", "status": "basis_ok", "created_at": state.get("created_at") or _now_iso(), "updated_at": _now_iso(), "messages": [AIMessage(content="已进入管理端第2步：核心内容 Prompt 与知识库配置。")]} 

    def generate_config(state: AdminStep2State, runtime: Any = None) -> AdminStep2State:
        _ = runtime
        md = f"## 第2步配置\n- Prompt：{state.get('prompt_text', '（待填写）')}\n- 知识库：{state.get('knowledge_text', '（待填写）')}"
        return {"draft_markdown": md, "status": "draft_ready", "updated_at": _now_iso(), "messages": [AIMessage(content="已生成第2步配置草稿。")]} 

    def finalize_config(state: AdminStep2State) -> AdminStep2State:
        md = state.get("draft_markdown") or ""
        return {"final_markdown": md, "export_payload": md, "export_filename": f"{state.get('project_name', '管理端配置')}Step2配置", "status": "completed", "updated_at": _now_iso(), "messages": [AIMessage(content="管理端第2步已完成。")]} 

    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_config", generate_config)
    graph.add_node("finalize_config", finalize_config)
    graph.add_edge(START, "validate_basis")
    graph.add_edge("validate_basis", "generate_config")
    graph.add_edge("generate_config", "finalize_config")
    graph.add_edge("finalize_config", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-admin-step2")


graph = build_graph()
