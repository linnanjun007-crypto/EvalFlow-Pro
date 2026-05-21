"""Step 12 graph for EvalFlow Pro — 生成基本情况.

承接前序成果，生成项目背景、项目内容、组织管理、资金投入、绩效目标等基本情况模块。
"""

from __future__ import annotations

from datetime import datetime, timezone
import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

ReviewMode = Literal["modify", "approve"]


class BaseSection(TypedDict, total=False):
    title: str
    content: str


class Step12State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    final_comprehensive_analysis: str
    base_sections: list[BaseSection]
    base_draft_markdown: str
    final_base_markdown: str
    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    export_filename: str
    export_payload: str
    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step12Context(TypedDict, total=False):
    project_id: str
    user_id: str
    model_name: str
    compare_models: list[str]
    enable_multi_model: bool
    system_prompt_stub: str
    knowledge_stub: str
    output_dir: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_basis(state: Step12State) -> Step12State:
    if not state.get("project_core_content"):
        return {"status": "failed", "error": "缺少第二步核心内容。", "messages": [AIMessage(content="第十二步需基于第二步核心内容生成基本情况。")], "updated_at": _now_iso()}
    return {"project_name": (state.get("project_name") or "未命名项目").strip() or "未命名项目", "status": "basis_ok", "created_at": state.get("created_at") or _now_iso(), "updated_at": _now_iso(), "messages": [AIMessage(content="已接收核心内容，开始生成基本情况。")]} 


def generate_base(state: Step12State, runtime: Any = None) -> Step12State:
    _ = runtime
    sections = [
        {"title": "项目背景", "content": "结合项目核心内容，概述项目设立背景、政策依据与现实需求。"},
        {"title": "项目内容", "content": "概述项目主要实施内容与任务安排。"},
        {"title": "项目组织管理情况", "content": "概述组织架构、职责分工、过程管理与监督机制。"},
        {"title": "项目资金投入情况", "content": "概述预算安排、资金来源、拨付与使用情况。"},
        {"title": "项目绩效目标", "content": "概述产出、效益和满意度等目标。"},
    ]
    md = "\n".join([f"### {x['title']}\n{x['content']}" for x in sections])
    return {"base_sections": sections, "base_draft_markdown": md, "status": "base_ready", "updated_at": _now_iso(), "messages": [AIMessage(content="已生成基本情况草稿。")]} 


def review_base(state: Step12State) -> Step12State:
    rnd = int(state.get("review_round", 0)) + 1
    return {"review_round": rnd, "status": "base_reviewed", "updated_at": _now_iso(), "messages": [AIMessage(content=f"已记录第 {rnd} 轮基本情况修改意见。")]} 


def finalize_base(state: Step12State) -> Step12State:
    project_name = state.get("project_name", "未命名项目")
    md = state.get("base_draft_markdown") or ""
    return {"final_base_markdown": md, "export_payload": md, "export_filename": f"{project_name}基本情况", "status": "completed", "updated_at": _now_iso(), "messages": [AIMessage(content="第十二步已完成。")]} 


def build_graph() -> Any:
    graph = StateGraph(Step12State, context_schema=Step12Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_base", generate_base)
    graph.add_node("review_base", review_base)
    graph.add_node("finalize_base", finalize_base)
    graph.add_edge(START, "validate_basis")
    graph.add_edge("validate_basis", "generate_base")
    graph.add_edge("generate_base", "review_base")
    graph.add_edge("review_base", "finalize_base")
    graph.add_edge("finalize_base", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step12")


graph = build_graph()
