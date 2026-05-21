"""Step 11 graph for EvalFlow Pro — 生成综合评价分析及评价结论.

承接前面步骤的结构化成果，汇总得分、亮点、问题与建议，形成综合评价。
"""

from __future__ import annotations

from datetime import datetime, timezone
import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

ReviewMode = Literal["modify", "approve"]


class Step11State(TypedDict, total=False):
    project_name: str
    final_score_sheet_markdown: str
    final_experience_markdown: str
    final_problem_markdown: str
    final_suggestion_markdown: str
    comprehensive_analysis_draft: str
    final_comprehensive_analysis: str
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


class Step11Context(TypedDict, total=False):
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


def validate_basis(state: Step11State) -> Step11State:
    if not state.get("final_score_sheet_markdown"):
        return {"status": "failed", "error": "缺少第七步成果。", "messages": [AIMessage(content="第十一步需基于第七步至第十步成果生成综合评价。")], "updated_at": _now_iso()}
    return {"project_name": (state.get("project_name") or "未命名项目").strip() or "未命名项目", "status": "basis_ok", "created_at": state.get("created_at") or _now_iso(), "updated_at": _now_iso(), "messages": [AIMessage(content="已接收前序成果，开始生成综合评价分析。")]} 


def generate_comprehensive(state: Step11State, runtime: Any = None) -> Step11State:
    _ = runtime
    score = state.get("final_score_sheet_markdown", "")
    experience = state.get("final_experience_markdown", "")
    problem = state.get("final_problem_markdown", "")
    suggestion = state.get("final_suggestion_markdown", "")
    draft = (
        f"### 总体绩效概况\n基于评分结果，项目总体绩效情况已形成闭环。\n\n"
        f"### 绩效亮点\n{experience[:500] or '结合经验做法提炼亮点。'}\n\n"
        f"### 核心问题\n{problem[:500] or '结合问题及原因分析聚焦核心症结。'}\n\n"
        f"### 后续建议\n{suggestion[:500] or '结合建议形成优化方向。'}\n\n"
        f"### 评价结论\n综合判断项目实施达到预期，建议根据得分结果确定等级。"
    )
    if score:
        draft += "\n\n【说明】结论已引用第七步得分表口径。"
    return {"comprehensive_analysis_draft": draft, "status": "comprehensive_ready", "updated_at": _now_iso(), "messages": [AIMessage(content="已生成综合评价分析及结论草稿。")]} 


def review_comprehensive(state: Step11State) -> Step11State:
    rnd = int(state.get("review_round", 0)) + 1
    return {"review_round": rnd, "status": "comprehensive_reviewed", "updated_at": _now_iso(), "messages": [AIMessage(content=f"已记录第 {rnd} 轮综合评价修改意见。")]} 


def finalize_comprehensive(state: Step11State) -> Step11State:
    project_name = state.get("project_name", "未命名项目")
    md = state.get("comprehensive_analysis_draft") or ""
    return {"final_comprehensive_analysis": md, "export_payload": md, "export_filename": f"{project_name}综合评价分析", "status": "completed", "updated_at": _now_iso(), "messages": [AIMessage(content="第十一步已完成。")]} 


def build_graph() -> Any:
    graph = StateGraph(Step11State, context_schema=Step11Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_comprehensive", generate_comprehensive)
    graph.add_node("review_comprehensive", review_comprehensive)
    graph.add_node("finalize_comprehensive", finalize_comprehensive)
    graph.add_edge(START, "validate_basis")
    graph.add_edge("validate_basis", "generate_comprehensive")
    graph.add_edge("generate_comprehensive", "review_comprehensive")
    graph.add_edge("review_comprehensive", "finalize_comprehensive")
    graph.add_edge("finalize_comprehensive", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step11")


graph = build_graph()
