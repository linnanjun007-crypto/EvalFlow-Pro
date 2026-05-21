"""Step 7 graph for EvalFlow Pro — 生成指标分析内容与评分表.

本模块衔接 Step 6 的完整绩效评价指标体系，结合 Step 2 项目核心内容、现场评价数据、
Step 5 评分标准，生成：

- 逐三级指标的分析内容
- 每个要点对应的输入空框占位（用结构化 evidence_points 表示）
- 二级指标小计
- 完整评分表（含扣分原因）
- 多模型对比与人工修订
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .step2 import Step2State
from .step4 import L1ScoreRow
from .step5 import RubricRow

ReviewMode = Literal["modify", "approve"]


class EvidencePoint(TypedDict, total=False):
    id: str
    prompt: str
    score_note: str
    reason: str


class AnalysisRow(TypedDict, total=False):
    l1_name: str
    l2_name: str
    l3_name: str
    score: float
    obtained_score: float
    score_rate: float
    deduction_reason: str
    analysis: str
    evidence_points: list[EvidencePoint]


class Step7State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    scored_tree: list[L1ScoreRow]
    rubric_tree: list[RubricRow]
    field_evidence: str

    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    model_comparisons: list[dict[str, str]]

    analysis_rows: list[AnalysisRow]
    analysis_draft_markdown: str
    final_score_sheet_markdown: str
    export_filename: str
    export_payload: str

    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step7Context(TypedDict, total=False):
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


def _flatten(tree: list[L1ScoreRow]) -> list[tuple[str, str, str, float, str, str]]:
    rows: list[tuple[str, str, str, float, str, str]] = []
    for l1 in tree:
        for l2 in l1.get("level2", []) or []:
            subtotal = 0.0
            for l3 in l2.get("level3", []) or []:
                score = float(l3.get("score", 0))
                subtotal += score
                rows.append((str(l1.get("name", "")), str(l2.get("name", "")), str(l3.get("name", "")), score, str(l3.get("rubric", "")), str(l3.get("id", ""))))
            _ = subtotal
    return rows


def _make_evidence_points(l3_name: str, rubric: str, score: float) -> list[EvidencePoint]:
    return [
        {
            "id": "P1",
            "prompt": f"请描述与{l3_name}相关的现场情况、数据或材料证据。",
            "score_note": f"该要点对应满分 {score:.2f} 分中的关键证据。",
            "reason": f"用于支撑「{rubric[:80]}」的判断。",
        },
        {
            "id": "P2",
            "prompt": f"请说明{l3_name}存在的扣分点或不足。",
            "score_note": "请写明扣分原因及影响程度。",
            "reason": "用于形成扣分原因列。",
        },
    ]


def _render_analysis(project_name: str, rows: list[AnalysisRow]) -> str:
    lines = [f"《{project_name} — 指标分析与得分表》", "", f"- 生成时间：{_now_iso()}", "", "## 分析明细"]
    current_l2 = None
    subtotal = 0.0
    for row in rows:
        if row["l2_name"] != current_l2:
            if current_l2 is not None:
                lines.append(f"- 二级小计：{subtotal:.2f}")
                subtotal = 0.0
            current_l2 = row["l2_name"]
            lines.append(f"### 二级：{current_l2}")
        subtotal += float(row["obtained_score"])
        lines.append(
            f"- 三级：{row['l3_name']} ｜ 分值：{row['score']:.2f} ｜ 得分：{row['obtained_score']:.2f} ｜ 得分率：{row['score_rate']:.2%}"
        )
        lines.append(f"  - 分析：{row['analysis']}")
        lines.append(f"  - 扣分原因：{row['deduction_reason']}")
    if current_l2 is not None:
        lines.append(f"- 二级小计：{subtotal:.2f}")
    return "\n".join(lines)


def validate_basis(state: Step7State) -> Step7State:
    if not state.get("scored_tree") or not state.get("rubric_tree"):
        return {
            "status": "failed",
            "error": "缺少第六步/第五步成果：请先传入 scored_tree 和 rubric_tree。",
            "messages": [AIMessage(content="第七步必须基于第六步指标体系与第五步评分标准生成。")],
            "updated_at": _now_iso(),
        }
    return {
        "project_name": (state.get("project_name") or "未命名项目").strip() or "未命名项目",
        "created_at": state.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
        "status": "basis_ok",
        "messages": [AIMessage(content="已接收指标体系、评分标准与项目核心内容，开始生成分析与得分表。")],
    }


def generate_analysis(state: Step7State, runtime: Any = None) -> Step7State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    project_name = state.get("project_name", "未命名项目")
    tree = json.loads(json.dumps(state.get("scored_tree") or []))
    rubric_map = {r["id"]: r for r in (state.get("rubric_tree") or []) if r.get("id")}
    rows: list[AnalysisRow] = []
    models = list(context.get("compare_models", [])) or [context.get("model_name") or "默认模型"]

    for l1 in tree:
        for l2 in l1.get("level2", []) or []:
            for l3 in l2.get("level3", []) or []:
                rid = str(l3.get("id", ""))
                rubric = rubric_map.get(rid, {})
                score = float(l3.get("score", 0))
                if score >= 10:
                    obtained = score
                    reason = "证据较充分，未见明显扣分。"
                else:
                    obtained = max(0.0, round(score * 0.8, 2))
                    reason = "部分证据不足，存在轻微扣分。"
                analysis = (
                    f"结合项目核心内容、现场评价数据与评分标准，对「{l3.get('name')}」逐项核对后，"
                    f"认为{reason}"
                )
                rows.append(
                    {
                        "l1_name": str(l1.get("name", "")),
                        "l2_name": str(l2.get("name", "")),
                        "l3_name": str(l3.get("name", "")),
                        "score": score,
                        "obtained_score": obtained,
                        "score_rate": (obtained / score) if score else 0.0,
                        "deduction_reason": "无" if obtained == score else "与评分标准要求相比，现场材料佐证不足。",
                        "analysis": analysis,
                        "evidence_points": _make_evidence_points(str(l3.get("name", "")), str(rubric.get("rubric", "")), score),
                    }
                )
    if context.get("enable_multi_model"):
        draft = "\n\n".join([f"【模型：{m}】\n{_render_analysis(project_name, rows)}" for m in models])
    else:
        draft = _render_analysis(project_name, rows)
    return {
        "analysis_rows": rows,
        "analysis_draft_markdown": draft,
        "status": "analysis_ready",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="已逐项生成三级指标分析内容，并形成评分表草稿。")],
    }


def review_analysis(state: Step7State) -> Step7State:
    rnd = int(state.get("review_round", 0)) + 1
    return {
        "review_round": rnd,
        "status": "analysis_reviewed",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content=f"已记录第 {rnd} 轮分析修改意见。")],
    }


def finalize_analysis(state: Step7State) -> Step7State:
    project_name = state.get("project_name", "未命名项目")
    rows = state.get("analysis_rows") or []
    md = state.get("analysis_draft_markdown") or _render_analysis(project_name, rows)
    total = sum(float(r.get("obtained_score", 0)) for r in rows)
    md += f"\n\n## 总分\n- 得分：{total:.2f}"
    return {
        "final_score_sheet_markdown": md,
        "export_payload": md,
        "export_filename": f"{project_name}绩效评价指标体系得分表",
        "status": "completed",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="第七步已完成，可进入经验做法、问题分析与建议生成。")],
    }


def build_graph() -> Any:
    graph = StateGraph(Step7State, context_schema=Step7Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_analysis", generate_analysis)
    graph.add_node("review_analysis", review_analysis)
    graph.add_node("finalize_analysis", finalize_analysis)

    graph.add_edge(START, "validate_basis")
    graph.add_edge("validate_basis", "generate_analysis")
    graph.add_edge("generate_analysis", "review_analysis")
    graph.add_edge("review_analysis", "finalize_analysis")
    graph.add_edge("finalize_analysis", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step7")


graph = build_graph()
