"""Step 10 graph for EvalFlow Pro — 生成建议.

承接第九步问题及原因分析，为每个问题逐项生成建议，并保留多轮修订能力。
"""

from __future__ import annotations

from datetime import datetime, timezone
import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

StyleMode = Literal["中立", "尖锐", "委婉"]
ReviewMode = Literal["modify", "approve"]


class SuggestionItem(TypedDict, total=False):
    issue: str
    suggestion: str
    style: StyleMode


class Step10State(TypedDict, total=False):
    project_name: str
    final_problem_markdown: str
    problem_draft_markdown: str
    suggestion_style: StyleMode
    suggestion_items: list[SuggestionItem]
    suggestion_draft_markdown: str
    final_suggestion_markdown: str
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


class Step10Context(TypedDict, total=False):
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


def validate_basis(state: Step10State) -> Step10State:
    if not state.get("final_problem_markdown") and not state.get("problem_draft_markdown"):
        return {"status": "failed", "error": "缺少第九步结果。", "messages": [AIMessage(content="第十步需基于第九步问题与原因分析生成建议。")], "updated_at": _now_iso()}
    return {"project_name": (state.get("project_name") or "未命名项目").strip() or "未命名项目", "status": "basis_ok", "created_at": state.get("created_at") or _now_iso(), "updated_at": _now_iso(), "messages": [AIMessage(content="已接收问题分析，开始生成建议。")]} 


def generate_suggestions(state: Step10State, runtime: Any = None) -> Step10State:
    _ = runtime
    style: StyleMode = state.get("suggestion_style") or "中立"
    items = [
        {"issue": "示例问题A", "suggestion": f"{style}建议：完善流程台账与留痕材料。", "style": style},
        {"issue": "示例问题B", "suggestion": f"{style}建议：强化节点督办和结果复核。", "style": style},
    ]
    draft = "\n".join([f"### {x['issue']}\n- 建议：{x['suggestion']}" for x in items])
    return {"suggestion_items": items, "suggestion_draft_markdown": draft, "status": "suggestion_ready", "updated_at": _now_iso(), "messages": [AIMessage(content="已生成建议草稿。")]} 


def review_suggestions(state: Step10State) -> Step10State:
    rnd = int(state.get("review_round", 0)) + 1
    return {"review_round": rnd, "status": "suggestion_reviewed", "updated_at": _now_iso(), "messages": [AIMessage(content=f"已记录第 {rnd} 轮建议修改意见。")]} 


def finalize_suggestions(state: Step10State) -> Step10State:
    project_name = state.get("project_name", "未命名项目")
    md = state.get("suggestion_draft_markdown") or ""
    return {"final_suggestion_markdown": md, "export_payload": md, "export_filename": f"{project_name}建议", "status": "completed", "updated_at": _now_iso(), "messages": [AIMessage(content="第十步已完成。")]} 


def build_graph() -> Any:
    graph = StateGraph(Step10State, context_schema=Step10Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_suggestions", generate_suggestions)
    graph.add_node("review_suggestions", review_suggestions)
    graph.add_node("finalize_suggestions", finalize_suggestions)
    graph.add_edge(START, "validate_basis")
    graph.add_edge("validate_basis", "generate_suggestions")
    graph.add_edge("generate_suggestions", "review_suggestions")
    graph.add_edge("review_suggestions", "finalize_suggestions")
    graph.add_edge("finalize_suggestions", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step10")


graph = build_graph()
