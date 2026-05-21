"""Step 14 graph for EvalFlow Pro — 生成评价报告.

汇总第六步到第十三步的全部结构化成果，按顺序组合为最终绩效评价报告。
"""

from __future__ import annotations

from datetime import datetime, timezone
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph


class Step14State(TypedDict, total=False):
    project_name: str
    final_indicator_framework_markdown: str
    final_score_sheet_markdown: str
    final_experience_markdown: str
    final_problem_markdown: str
    final_suggestion_markdown: str
    final_comprehensive_analysis: str
    final_base_markdown: str
    final_work_markdown: str
    report_order: list[str]
    final_report_markdown: str
    export_filename: str
    export_payload: str
    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step14Context(TypedDict, total=False):
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


def validate_basis(state: Step14State) -> Step14State:
    if not state.get("final_indicator_framework_markdown"):
        return {"status": "failed", "error": "缺少第六步成果。", "messages": [AIMessage(content="第十四步需汇总第六步至第十三步成果。")], "updated_at": _now_iso()}
    return {"project_name": (state.get("project_name") or "未命名项目").strip() or "未命名项目", "status": "basis_ok", "created_at": state.get("created_at") or _now_iso(), "updated_at": _now_iso(), "messages": [AIMessage(content="已接收前序成果，开始生成最终评价报告。")]} 


def generate_report(state: Step14State, runtime: Any = None) -> Step14State:
    _ = runtime
    order = state.get("report_order") or ["final_base_markdown", "final_work_markdown", "final_indicator_framework_markdown", "final_score_sheet_markdown", "final_experience_markdown", "final_problem_markdown", "final_suggestion_markdown", "final_comprehensive_analysis"]
    parts: list[str] = [f"《{state.get('project_name', '未命名项目')}绩效评价报告》", "", f"- 生成时间：{_now_iso()}"]
    mapping = {
        "final_indicator_framework_markdown": "## 绩效评价指标体系",
        "final_score_sheet_markdown": "## 指标分析与得分表",
        "final_experience_markdown": "## 经验做法",
        "final_problem_markdown": "## 问题及原因分析",
        "final_suggestion_markdown": "## 建议",
        "final_comprehensive_analysis": "## 综合评价分析及评价结论",
        "final_base_markdown": "## 基本情况",
        "final_work_markdown": "## 绩效评价工作开展情况",
    }
    for key in order:
        body = state.get(key, "")
        if body:
            parts.append(mapping.get(key, f"## {key}") )
            parts.append(body)
            parts.append("")
    report = "\n".join(parts)
    return {"final_report_markdown": report, "export_payload": report, "export_filename": f"{state.get('project_name', '未命名项目')}绩效评价报告", "status": "report_ready", "updated_at": _now_iso(), "messages": [AIMessage(content="已完成报告整合，可预览、调整顺序并导出。")]} 


def finalize_report(state: Step14State) -> Step14State:
    return {"status": "completed", "updated_at": _now_iso(), "messages": [AIMessage(content="第十四步已完成，报告可导出。")]} 


def build_graph() -> Any:
    graph = StateGraph(Step14State, context_schema=Step14Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_report", generate_report)
    graph.add_node("finalize_report", finalize_report)
    graph.add_edge(START, "validate_basis")
    graph.add_edge("validate_basis", "generate_report")
    graph.add_edge("generate_report", "finalize_report")
    graph.add_edge("finalize_report", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step14")


graph = build_graph()
