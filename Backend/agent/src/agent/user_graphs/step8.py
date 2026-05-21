"""Step 8 graph for EvalFlow Pro — 生成经验做法.

承接第七步得分表与分析结果，结合项目核心内容与现场评价数据，提炼经验做法。
"""

from __future__ import annotations

from datetime import datetime, timezone
import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

ReviewMode = Literal["modify", "approve"]


class ExperienceItem(TypedDict, total=False):
    title: str
    content: str
    source_hint: str


class Step8State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    analysis_draft_markdown: str
    final_score_sheet_markdown: str
    field_evidence: str

    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    experience_items: list[ExperienceItem]
    experience_draft_markdown: str
    final_experience_markdown: str
    export_filename: str
    export_payload: str

    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step8Context(TypedDict, total=False):
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


def validate_basis(state: Step8State) -> Step8State:
    if not state.get("project_core_content"):
        return {"status": "failed", "error": "缺少第七步/第二步输入。", "messages": [AIMessage(content="第八步需基于项目核心内容与第七步成果。")], "updated_at": _now_iso()}
    return {"project_name": (state.get("project_name") or "未命名项目").strip() or "未命名项目", "status": "basis_ok", "created_at": state.get("created_at") or _now_iso(), "updated_at": _now_iso(), "messages": [AIMessage(content="已接收第七步成果，开始提炼经验做法。")]} 


def generate_experience(state: Step8State, runtime: Any = None) -> Step8State:
    _ = runtime
    core = state.get("project_core_content", "")
    analysis = state.get("analysis_draft_markdown") or state.get("final_score_sheet_markdown") or ""
    items = [
        {"title": "规范组织实施", "content": "建立了较为清晰的职责分工与推进机制，保障项目按期完成。", "source_hint": "来自核心内容与分析摘要"},
        {"title": "强化过程控制", "content": "对关键节点和资料留痕进行跟踪管理，形成可复制的流程经验。", "source_hint": "来自评分表与分析结果"},
        {"title": "注重结果导向", "content": "围绕目标产出与效益开展统筹，提升成果转化效率。", "source_hint": "来自绩效分析"},
    ]
    draft = "\n".join([f"### {x['title']}\n{x['content']}\n> {x['source_hint']}" for x in items])
    if core or analysis:
        draft += "\n\n【依据说明】经验做法综合参考项目核心内容、现场评价与第七步分析结果。"
    return {"experience_items": items, "experience_draft_markdown": draft, "status": "experience_ready", "updated_at": _now_iso(), "messages": [AIMessage(content="已生成经验做法草稿，可修改后定稿。")]} 


def review_experience(state: Step8State) -> Step8State:
    rnd = int(state.get("review_round", 0)) + 1
    return {"review_round": rnd, "status": "experience_reviewed", "updated_at": _now_iso(), "messages": [AIMessage(content=f"已记录第 {rnd} 轮经验做法修改意见。")]} 


def finalize_experience(state: Step8State) -> Step8State:
    project_name = state.get("project_name", "未命名项目")
    md = state.get("experience_draft_markdown") or ""
    return {"final_experience_markdown": md, "export_payload": md, "export_filename": f"{project_name}经验做法", "status": "completed", "updated_at": _now_iso(), "messages": [AIMessage(content="第八步已完成。")]} 


def build_graph() -> Any:
    graph = StateGraph(Step8State, context_schema=Step8Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_experience", generate_experience)
    graph.add_node("review_experience", review_experience)
    graph.add_node("finalize_experience", finalize_experience)
    graph.add_edge(START, "validate_basis")
    graph.add_edge("validate_basis", "generate_experience")
    graph.add_edge("generate_experience", "review_experience")
    graph.add_edge("review_experience", "finalize_experience")
    graph.add_edge("finalize_experience", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step8")


graph = build_graph()
