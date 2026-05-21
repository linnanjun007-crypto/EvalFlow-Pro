"""Step 5 graph for EvalFlow Pro — 生成评分标准.

本模块承接 ``step4`` 的分值定稿结果，基于第二步项目核心内容、第三/四步指标体系与分值，
为每个三级指标逐个生成评分标准，并支持：

- 按三级指标逐项生成/审核评分标准
- 人工直接编辑评分标准
- 多轮对话式修改反馈
- 多模型对比草稿
- 最终一键导入并定稿

这与 ``doc/_docx_extract.txt`` 中“第五步：生成评分标准”的要求对齐。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .step4 import L1ScoreRow

ScoreStyle = Literal["中立", "尖锐", "委婉"]
ReviewMode = Literal["modify", "approve"]


class RubricRow(TypedDict, total=False):
    id: str
    l1_name: str
    l2_name: str
    l3_name: str
    score: float
    explanation: str
    rubric: str
    approved: bool
    model_name: str


class RubricDraft(TypedDict):
    model_name: str
    draft: str


class ModelDraft(TypedDict):
    model_name: str
    draft: str


class Step5State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    scored_tree: list[L1ScoreRow]
    rubric_tree: list[RubricRow]

    generation_style: ScoreStyle
    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    manual_rubric_overrides: dict[str, str]
    rubric_source_json: str

    model_comparisons: list[RubricDraft]
    draft_rubrics_markdown: str
    final_rubrics_markdown: str
    export_filename: str
    export_payload: str

    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step5Context(TypedDict, total=False):
    project_id: str
    user_id: str
    model_name: str
    compare_models: list[str]
    enable_multi_model: bool
    system_prompt_stub: str
    knowledge_stub: str
    output_dir: str


EPS = 0.02


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _flatten_scored_tree(tree: list[L1ScoreRow]) -> list[RubricRow]:
    rows: list[RubricRow] = []
    for l1 in tree:
        for l2 in l1.get("level2", []) or []:
            for l3 in l2.get("level3", []) or []:
                rows.append(
                    {
                        "id": str(l3.get("id", "")),
                        "l1_name": str(l1.get("name", "")),
                        "l2_name": str(l2.get("name", "")),
                        "l3_name": str(l3.get("name", "")),
                        "score": float(l3.get("score", 0)),
                        "explanation": f"围绕三级指标「{l3.get('name', '')}」设置评分标准与判定口径。",
                        "rubric": "",
                        "approved": False,
                        "model_name": "",
                    }
                )
    return rows


def _infer_style_text(style: ScoreStyle, l1: str, l2: str, l3: str, score: float) -> str:
    if style == "尖锐":
        lead = "若未达到要求，则视为明显扣分点"
    elif style == "委婉":
        lead = "如有不足，可酌情扣分"
    else:
        lead = "根据实际完成情况进行评分"
    return (
        f"{lead}。评价对象为「{l1} / {l2} / {l3}」，该项满分 {score:.2f} 分。"
        f"评分时重点关注证据完整性、逻辑一致性、与项目核心内容的匹配程度。"
    )


def _render_rubric_markdown(project_name: str, rows: list[RubricRow]) -> str:
    lines = [f"《{project_name} — 评分标准定稿》", "", f"- 生成时间：{_now_iso()}", "", "## 评分标准明细"]
    current_l1 = current_l2 = None
    for row in rows:
        if row.get("l1_name") != current_l1:
            current_l1 = row.get("l1_name")
            lines.append(f"### 一级：{current_l1}")
            current_l2 = None
        if row.get("l2_name") != current_l2:
            current_l2 = row.get("l2_name")
            lines.append(f"- 二级：**{current_l2}**")
        lines.append(
            f"  - 三级：{row.get('l3_name')} ｜ 分值：{row.get('score', 0):.2f} ｜ "
            f"状态：{'已确认' if row.get('approved') else '待确认'}"
        )
        lines.append(f"    - 评分标准：{row.get('rubric', '')}")
    return "\n".join(lines)


def _simulate_model_drafts(project_name: str, rows: list[RubricRow], models: list[str], style: ScoreStyle) -> list[RubricDraft]:
    out: list[RubricDraft] = []
    for m in models:
        drafts = []
        for row in rows:
            rubric = _infer_style_text(style, row["l1_name"], row["l2_name"], row["l3_name"], float(row.get("score", 0)))
            drafts.append(f"- {row['l3_name']}：{rubric}（模型：{m}）")
        out.append({"model_name": m, "draft": f"《{project_name} — {m} 评分标准草稿》\n" + "\n".join(drafts)})
    return out


def validate_step4_basis(state: Step5State) -> Step5State:
    tree = list(state.get("scored_tree") or [])
    if not tree:
        return {
            "status": "failed",
            "error": "缺少第四步定稿分值结构：请传入 scored_tree 后再生成评分标准。",
            "messages": [AIMessage(content="第五步需基于第四步已确认的 scored_tree 生成评分标准。")],
            "updated_at": _now_iso(),
        }

    name = (state.get("project_name") or "未命名项目").strip() or "未命名项目"
    rows = _flatten_scored_tree(tree)
    return {
        "project_name": name,
        "rubric_tree": rows,
        "created_at": state.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
        "status": "basis_ok",
        "messages": [AIMessage(content=f"已接收第四步分值结构，项目：{name}。开始逐个生成评分标准。")],
    }


def route_after_basis(state: Step5State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


def generate_rubrics(state: Step5State, runtime: Any = None) -> Step5State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    rows = json.loads(json.dumps(state.get("rubric_tree") or []))
    style: ScoreStyle = state.get("generation_style") or "中立"
    project_name = state.get("project_name", "未命名项目")
    manual = dict(state.get("manual_rubric_overrides") or {})

    for row in rows:
        row_id = str(row.get("id", ""))
        rubric = manual.get(row_id) or _infer_style_text(style, row["l1_name"], row["l2_name"], row["l3_name"], float(row.get("score", 0)))
        row["rubric"] = rubric
        row["approved"] = bool(manual.get(row_id))
        row["model_name"] = context.get("model_name") or "默认模型"

    multi = bool(context.get("enable_multi_model", False))
    models = list(context.get("compare_models", [])) or [context.get("model_name") or "默认模型"]
    if multi:
        comps = _simulate_model_drafts(project_name, rows, models, style)
        first_model = comps[0]["model_name"] if comps else (context.get("model_name") or "默认模型")
        for row in rows:
            if not row.get("approved"):
                row["rubric"] = _infer_style_text(style, row["l1_name"], row["l2_name"], row["l3_name"], float(row.get("score", 0)))
                row["model_name"] = first_model
        md = comps[0]["draft"] if comps else ""
        return {
            "rubric_tree": rows,
            "model_comparisons": comps,
            "draft_rubrics_markdown": md,
            "status": "rubrics_generated",
            "updated_at": _now_iso(),
            "messages": [AIMessage(content=f"已生成 {len(comps)} 套评分标准草稿，供多模型对比后择优定稿。")],
        }

    md = _render_rubric_markdown(project_name, rows)
    return {
        "rubric_tree": rows,
        "model_comparisons": [],
        "draft_rubrics_markdown": md,
        "status": "rubrics_generated",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="已完成评分标准逐项生成，请逐条确认或提交修改意见。")],
    }


def review_rubrics(state: Step5State) -> Step5State:
    fb = (state.get("review_feedback") or "").strip()
    rnd = int(state.get("review_round", 0)) + 1
    return {
        "review_round": rnd,
        "status": "reviewed",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content=f"已记录第 {rnd} 轮评分标准修改意见：{fb or '（无具体内容）'}")],
    }


def finalize_rubrics(state: Step5State) -> Step5State:
    rows = json.loads(json.dumps(state.get("rubric_tree") or []))
    project_name = state.get("project_name", "未命名项目")
    if not rows:
        return {
            "status": "blocked",
            "error": "没有可定稿的评分标准。",
            "messages": [AIMessage(content="请先生成评分标准草稿后再定稿。")],
            "updated_at": _now_iso(),
        }
    for row in rows:
        row["approved"] = True
    md = _render_rubric_markdown(project_name, rows)
    payload = md + "\n\n## 机器可读快照（JSON）\n```json\n" + json.dumps(rows, ensure_ascii=False, indent=2) + "\n```\n"
    return {
        "rubric_tree": rows,
        "final_rubrics_markdown": md,
        "export_payload": payload,
        "export_filename": f"{project_name}评分标准_定稿",
        "status": "completed",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="评分标准已定稿，可用于后续绩效评价指标体系分析部分生成。")],
    }


def build_graph() -> Any:
    graph = StateGraph(Step5State, context_schema=Step5Context)
    graph.add_node("validate_step4_basis", validate_step4_basis)
    graph.add_node("generate_rubrics", generate_rubrics)
    graph.add_node("review_rubrics", review_rubrics)
    graph.add_node("finalize_rubrics", finalize_rubrics)

    graph.add_edge(START, "validate_step4_basis")
    graph.add_conditional_edges(
        "validate_step4_basis",
        route_after_basis,
        {"continue": "generate_rubrics", "end": END},
    )
    graph.add_edge("generate_rubrics", "review_rubrics")
    graph.add_edge("review_rubrics", "finalize_rubrics")
    graph.add_edge("finalize_rubrics", END)

    memory = MemorySaver()
    return graph.compile(checkpointer=memory, name="evalflow-pro-step5")


graph = build_graph()
