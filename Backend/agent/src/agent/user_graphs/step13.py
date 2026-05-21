"""Step 13 graph for EvalFlow Pro — 绩效评价工作开展情况.

承接前序成果，生成评价目的、对象、范围、原则、指标、方法、标准与工作过程。
"""

from __future__ import annotations

from datetime import datetime, timezone
import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

ReviewMode = Literal["modify", "approve"]


class WorkSection(TypedDict, total=False):
    title: str
    content: str


class Step13State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    final_base_markdown: str
    work_sections: list[WorkSection]
    work_draft_markdown: str
    final_work_markdown: str
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


class Step13Context(TypedDict, total=False):
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


def validate_basis(state: Step13State) -> Step13State:
    if not state.get("project_core_content"):
        return {"status": "failed", "error": "缺少第二步核心内容。", "messages": [AIMessage(content="第十三步需基于核心内容生成工作开展情况。")], "updated_at": _now_iso()}
    return {"project_name": (state.get("project_name") or "未命名项目").strip() or "未命名项目", "status": "basis_ok", "created_at": state.get("created_at") or _now_iso(), "updated_at": _now_iso(), "messages": [AIMessage(content="已接收核心内容，开始生成工作开展情况。")]} 


def generate_work(state: Step13State, runtime: Any = None) -> Step13State:
    _ = runtime
    sections = [
        {"title": "绩效评价目的", "content": "说明开展绩效评价的目标与意义。"},
        {"title": "评价对象", "content": "说明评价范围所覆盖的项目、资金或业务单元。"},
        {"title": "评价范围", "content": "说明时间范围、业务范围与资料范围。"},
        {"title": "评价原则", "content": "说明客观、公正、独立、规范等原则。"},
        {"title": "评价指标", "content": "说明指标体系来源与构成。"},
        {"title": "评价方法", "content": "说明资料核查、现场访谈、数据比对等方法。"},
        {"title": "评价标准", "content": "说明评分标准与依据文件。"},
        {"title": "工作过程", "content": "说明资料收集、分析、复核与成稿过程。"},
    ]
    md = "\n".join([f"### {x['title']}\n{x['content']}" for x in sections])
    return {"work_sections": sections, "work_draft_markdown": md, "status": "work_ready", "updated_at": _now_iso(), "messages": [AIMessage(content="已生成绩效评价工作开展情况草稿。")]} 


def review_work(state: Step13State) -> Step13State:
    rnd = int(state.get("review_round", 0)) + 1
    return {"review_round": rnd, "status": "work_reviewed", "updated_at": _now_iso(), "messages": [AIMessage(content=f"已记录第 {rnd} 轮工作开展情况修改意见。")]} 


def finalize_work(state: Step13State) -> Step13State:
    project_name = state.get("project_name", "未命名项目")
    md = state.get("work_draft_markdown") or ""
    return {"final_work_markdown": md, "export_payload": md, "export_filename": f"{project_name}绩效评价工作开展情况", "status": "completed", "updated_at": _now_iso(), "messages": [AIMessage(content="第十三步已完成。")]} 


def build_graph() -> Any:
    graph = StateGraph(Step13State, context_schema=Step13Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_work", generate_work)
    graph.add_node("review_work", review_work)
    graph.add_node("finalize_work", finalize_work)
    graph.add_edge(START, "validate_basis")
    graph.add_edge("validate_basis", "generate_work")
    graph.add_edge("generate_work", "review_work")
    graph.add_edge("review_work", "finalize_work")
    graph.add_edge("finalize_work", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step13")


graph = build_graph()
