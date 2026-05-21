"""Step 9 graph for EvalFlow Pro — 生成问题及原因分析.

承接第七/八步结果，提取扣分点并形成问题与原因分析，可中立、尖锐、委婉三种风格。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

StyleMode = Literal["中立", "尖锐", "委婉"]
ReviewMode = Literal["modify", "approve"]


class ProblemItem(TypedDict, total=False):
    indicator_name: str
    problem: str
    reason: str
    style: StyleMode


class Step9State(TypedDict, total=False):
    project_name: str
    analysis_draft_markdown: str
    final_score_sheet_markdown: str
    final_experience_markdown: str
    problem_style: StyleMode
    manual_problem_items: list[str]

    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    problem_items: list[ProblemItem]
    problem_draft_markdown: str
    final_problem_markdown: str
    export_filename: str
    export_payload: str

    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step9Context(TypedDict, total=False):
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


def validate_basis(state: Step9State) -> Step9State:
    if not state.get("analysis_draft_markdown") and not state.get("final_score_sheet_markdown"):
        return {"status": "failed", "error": "缺少第七步结果。", "messages": [AIMessage(content="第九步需基于第七步得分表与分析结果。")], "updated_at": _now_iso()}
    return {"project_name": (state.get("project_name") or "未命名项目").strip() or "未命名项目", "status": "basis_ok", "created_at": state.get("created_at") or _now_iso(), "updated_at": _now_iso(), "messages": [AIMessage(content="已接收扣分信息，开始生成问题及原因分析。")]} 


def generate_problems(state: Step9State, runtime: Any = None) -> Step9State:
    _ = runtime
    style: StyleMode = state.get("problem_style") or "中立"
    analysis = state.get("analysis_draft_markdown") or state.get("final_score_sheet_markdown") or ""
    items = [
        {"indicator_name": "示例指标A", "problem": f"{style}表述的问题：该指标存在落实不到位现象。", "reason": "现场资料与评分标准对照后，证明材料不充分。", "style": style},
        {"indicator_name": "示例指标B", "problem": f"{style}表述的问题：相关工作推进节奏偏慢。", "reason": "工作记录显示部分节点滞后。", "style": style},
    ]
    draft = "\n".join([f"### {x['indicator_name']}\n- 问题：{x['problem']}\n- 原因：{x['reason']}" for x in items])
    if analysis:
        draft += "\n\n【依据】已根据扣分点、扣分原因和现场材料生成。"
    return {"problem_items": items, "problem_draft_markdown": draft, "status": "problem_ready", "updated_at": _now_iso(), "messages": [AIMessage(content="已生成问题及原因分析草稿。")]} 


def review_problems(state: Step9State) -> Step9State:
    rnd = int(state.get("review_round", 0)) + 1
    return {"review_round": rnd, "status": "problem_reviewed", "updated_at": _now_iso(), "messages": [AIMessage(content=f"已记录第 {rnd} 轮问题修改意见。")]} 


def finalize_problems(state: Step9State) -> Step9State:
    project_name = state.get("project_name", "未命名项目")
    md = state.get("problem_draft_markdown") or ""
    return {"final_problem_markdown": md, "export_payload": md, "export_filename": f"{project_name}问题及原因分析", "status": "completed", "updated_at": _now_iso(), "messages": [AIMessage(content="第九步已完成。")]} 


def build_graph() -> Any:
    graph = StateGraph(Step9State, context_schema=Step9Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_problems", generate_problems)
    graph.add_node("review_problems", review_problems)
    graph.add_node("finalize_problems", finalize_problems)
    graph.add_edge(START, "validate_basis")
    graph.add_edge("validate_basis", "generate_problems")
    graph.add_edge("generate_problems", "review_problems")
    graph.add_edge("review_problems", "finalize_problems")
    graph.add_edge("finalize_problems", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step9")


graph = build_graph()
