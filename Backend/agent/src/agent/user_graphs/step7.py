"""Step 7 graph for EvalFlow Pro — 指标分析、扣分原因与得分表.

衔接 Step 5 的 ``score_standards`` 与 Step 4 的 ``scored_tree``，结合 Step 2 项目
核心内容与现场评价数据，逐三级指标产出：

- ``analysis`` —— 文字分析；
- ``obtained_score`` / ``score_rate`` —— 得分与得分率；
- ``deduction_reason`` —— 扣分原因（如未扣分写「无」）；
- ``evidence_points`` —— 现场佐证点（用于回写现场材料）。

最终汇总为：

- ``analysis_rows`` —— 结构化数据；
- ``analysis_draft_markdown`` —— 草稿；
- ``final_score_sheet_markdown`` —— 含总分的定稿；
- ``total_score`` —— 加总后的项目得分；
- ``content_text`` —— 与定稿一致，供持久化。

LLM 调用失败时回退到 ``score * 0.8`` 规则模板。
"""

from __future__ import annotations

import json
import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from ._llm import (
    build_admin_preamble,
    collect_errors,
    filter_configs_by_compare_models,
    first_successful_draft,
    generate_drafts_async,
    now_iso,
    parse_json_object,
    read_admin_kb,
    read_admin_prompt,
    read_model_configs,
)
from .step4 import L1ScoreRow
from .step5 import ScoreStandard, await_in_sync

ReviewMode = Literal["modify", "approve"]


class EvidencePoint(TypedDict, total=False):
    id: str
    prompt: str
    score_note: str
    reason: str


class AnalysisRow(TypedDict, total=False):
    id: str
    l1_name: str
    l2_name: str
    l3_name: str
    score: float
    obtained_score: float
    score_rate: float
    deduction_reason: str
    analysis: str
    evidence_points: list[EvidencePoint]
    model_name: str


class AnalysisDraft(TypedDict, total=False):
    model_name: str
    label: str
    draft: str
    error: str


class Step7State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    scored_tree: list[L1ScoreRow]
    score_standards: list[ScoreStandard]
    field_evidence: str

    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    model_comparisons: list[AnalysisDraft]

    analysis_rows: list[AnalysisRow]
    analysis_draft_markdown: str
    final_score_sheet_markdown: str
    total_score: float
    content_text: str
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
    model_configs: list[dict[str, Any]]
    compare_models: list[str]
    enable_multi_model: bool
    admin_prompt_content: str
    admin_kb_content: str
    output_dir: str


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _flatten_indicators(
    tree: list[L1ScoreRow],
    standards: list[ScoreStandard],
) -> list[dict[str, Any]]:
    rubric_index: dict[str, ScoreStandard] = {
        str(s.get("id", "")): s for s in standards if s.get("id")
    }
    rows: list[dict[str, Any]] = []
    for l1 in tree:
        for l2 in l1.get("level2", []) or []:
            for l3 in l2.get("level3", []) or []:
                row_id = str(l3.get("id", ""))
                rubric = rubric_index.get(row_id, {}).get("rubric") or {}
                rows.append(
                    {
                        "id": row_id,
                        "l1_name": str(l1.get("name", "")),
                        "l2_name": str(l2.get("name", "")),
                        "l3_name": str(l3.get("name", "")),
                        "score": float(l3.get("score", 0)),
                        "tag": str(l3.get("tag", "其他")),
                        "rubric": dict(rubric),
                    }
                )
    return rows


def _make_evidence_points(l3_name: str, rubric: dict[str, str], score: float) -> list[EvidencePoint]:
    sample = next(((rubric.get(t) or "").strip() for t in ("合格", "良好", "优秀") if rubric.get(t)), "")
    return [
        {
            "id": "P1",
            "prompt": f"请描述与「{l3_name}」相关的现场情况、数据或材料证据。",
            "score_note": f"该要点对应满分 {score:.2f} 分中的关键证据。",
            "reason": (f"用于支撑评分标准要求：{sample[:80]}" if sample else "用于支撑该指标得分判断。"),
        },
        {
            "id": "P2",
            "prompt": f"请说明「{l3_name}」存在的扣分点或不足。",
            "score_note": "请写明扣分原因及影响程度。",
            "reason": "用于形成扣分原因列。",
        },
    ]


def _build_analysis_prompt(
    *,
    project_name: str,
    project_core_content: str,
    field_evidence: str,
    rows: list[dict[str, Any]],
    admin_prompt: str,
    admin_kb: str,
    review_feedback: str = "",
) -> str:
    preamble = build_admin_preamble(admin_prompt, admin_kb)
    indicator_blocks: list[str] = []
    for row in rows:
        rubric = row.get("rubric") or {}
        rubric_lines = "\n".join(
            f"      - {tier}：{(rubric.get(tier) or '').strip() or '（待补充）'}"
            for tier in ("优秀", "良好", "合格", "不合格")
        )
        indicator_blocks.append(
            "\n".join(
                [
                    f"- id={row['id']}",
                    f"  一级={row['l1_name']} / 二级={row['l2_name']} / 三级={row['l3_name']}",
                    f"  满分={row['score']:.2f}，维度={row.get('tag', '其他')}",
                    "    评分标准：",
                    rubric_lines,
                ]
            )
        )
    indicators = "\n".join(indicator_blocks) or "（空）"

    feedback_block = (
        f"\n【人工反馈意见（请按此调整本次输出）】\n{review_feedback.strip()}\n"
        if review_feedback.strip()
        else ""
    )

    instructions = [
        "请基于以上素材，逐个三级指标输出：",
        "1. analysis —— 中文 2~4 句分析，须结合项目核心内容与现场证据；",
        "2. obtained_score —— 在 [0, 满分] 内的实际得分（两位小数）；",
        "3. deduction_reason —— 若得分未达满分需写明扣分原因；满分则写「无」；",
        "4. 严禁出现 '同上' '略' 等占位说明；",
        "",
        "输出格式（严格 JSON，不要任何额外文字）：",
        "{",
        '  "rows": [',
        '    {"id": "L3-…", "obtained_score": 8.5, "deduction_reason": "…", "analysis": "…"}',
        "  ]",
        "}",
    ]

    return "\n".join(
        [
            preamble.strip(),
            f"项目名称：{project_name}",
            "项目核心内容：",
            (project_core_content or "（未提供）").strip(),
            "",
            "现场评价证据：",
            (field_evidence or "（未提供，请基于评分标准与核心内容审慎判断）").strip(),
            "",
            "待分析三级指标列表：",
            indicators,
            feedback_block,
            "",
            *instructions,
        ]
    )


def _fallback_analysis_row(row: dict[str, Any]) -> AnalysisRow:
    score = float(row.get("score", 0) or 0)
    obtained = round(score * 0.8, 2)
    deduction = "证据不足，按评分标准酌情扣分。" if obtained < score else "无"
    rubric = row.get("rubric") or {}
    return {
        "id": str(row.get("id", "")),
        "l1_name": str(row.get("l1_name", "")),
        "l2_name": str(row.get("l2_name", "")),
        "l3_name": str(row.get("l3_name", "")),
        "score": score,
        "obtained_score": obtained,
        "score_rate": (obtained / score) if score else 0.0,
        "deduction_reason": deduction,
        "analysis": (
            f"基于项目核心内容与评分标准对「{row.get('l3_name', '')}」进行规则模板估算，"
            f"按 80% 给分；详细分析请重试模型或人工补充。"
        ),
        "evidence_points": _make_evidence_points(str(row.get("l3_name", "")), rubric, score),
        "model_name": "fallback",
    }


def _apply_llm_analysis(
    rows: list[dict[str, Any]],
    raw_text: str,
    model_name: str,
) -> list[AnalysisRow]:
    parsed = parse_json_object(raw_text) or {}
    items = parsed.get("rows") if isinstance(parsed, dict) else None
    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            row_id = str(item.get("id") or "").strip()
            if row_id:
                by_id[row_id] = item

    out: list[AnalysisRow] = []
    for row in rows:
        score = float(row.get("score", 0) or 0)
        rubric = row.get("rubric") or {}
        item = by_id.get(str(row.get("id")))
        if item:
            try:
                obtained = float(item.get("obtained_score", 0))
            except (TypeError, ValueError):
                obtained = round(score * 0.8, 2)
            obtained = max(0.0, min(score, round(obtained, 2)))
            deduction = str(item.get("deduction_reason") or "").strip() or (
                "无" if obtained == score else "证据不足，按评分标准扣分。"
            )
            analysis = str(item.get("analysis") or "").strip()
            if not analysis:
                analysis = (
                    f"模型未返回 {row.get('l3_name')} 的分析，已回退到规则模板。"
                )
                source_model = f"{model_name}+fallback"
            else:
                source_model = model_name
            out.append(
                {
                    "id": str(row.get("id", "")),
                    "l1_name": str(row.get("l1_name", "")),
                    "l2_name": str(row.get("l2_name", "")),
                    "l3_name": str(row.get("l3_name", "")),
                    "score": score,
                    "obtained_score": obtained,
                    "score_rate": (obtained / score) if score else 0.0,
                    "deduction_reason": deduction,
                    "analysis": analysis,
                    "evidence_points": _make_evidence_points(
                        str(row.get("l3_name", "")), rubric, score
                    ),
                    "model_name": source_model,
                }
            )
        else:
            out.append(_fallback_analysis_row(row))
    return out


def _render_analysis(project_name: str, rows: list[AnalysisRow]) -> str:
    lines = [
        f"# 《{project_name} — 指标分析与得分表》",
        "",
        f"- 生成时间：{now_iso()}",
        f"- 指标数：{len(rows)}",
        "",
        "## 分析明细",
    ]
    current_l1: str | None = None
    current_l2: str | None = None
    subtotal = 0.0
    full_subtotal = 0.0
    for row in rows:
        if row.get("l1_name") != current_l1:
            current_l1 = str(row.get("l1_name") or "")
            lines.append(f"### 一级：{current_l1}")
            current_l2 = None
        if row.get("l2_name") != current_l2:
            if current_l2 is not None:
                lines.append(
                    f"- **二级小计**：{subtotal:.2f} / {full_subtotal:.2f}"
                )
                subtotal = 0.0
                full_subtotal = 0.0
            current_l2 = str(row.get("l2_name") or "")
            lines.append(f"- **二级：{current_l2}**")
        score = float(row.get("score", 0) or 0)
        obtained = float(row.get("obtained_score", 0) or 0)
        subtotal += obtained
        full_subtotal += score
        rate = float(row.get("score_rate", 0) or 0)
        lines.append(
            f"  - 三级：{row.get('l3_name')} ｜ 满分：{score:.2f} ｜ 得分：{obtained:.2f} ｜ 得分率：{rate:.2%}"
        )
        lines.append(f"    - 分析：{row.get('analysis')}")
        lines.append(f"    - 扣分原因：{row.get('deduction_reason')}")
    if current_l2 is not None:
        lines.append(f"- **二级小计**：{subtotal:.2f} / {full_subtotal:.2f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------


def validate_basis(state: Step7State) -> Step7State:
    if not state.get("scored_tree"):
        return {
            "status": "failed",
            "error": "缺少第四步成果：请先传入 scored_tree。",
            "messages": [AIMessage(content="第七步必须基于第四步定稿分值结构。")],
            "updated_at": now_iso(),
        }
    if not state.get("score_standards"):
        return {
            "status": "failed",
            "error": "缺少第五步成果：请先传入 score_standards。",
            "messages": [AIMessage(content="第七步必须基于第五步评分标准生成。")],
            "updated_at": now_iso(),
        }
    return {
        "project_name": (state.get("project_name") or "未命名项目").strip() or "未命名项目",
        "created_at": state.get("created_at") or now_iso(),
        "updated_at": now_iso(),
        "status": "basis_ok",
        "messages": [
            AIMessage(content="已接收指标体系、评分标准与项目核心内容，开始生成分析与得分表。")
        ],
    }


def route_after_basis(state: Step7State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


def generate_analysis(state: Step7State, runtime: Any = None) -> Step7State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    project_name = state.get("project_name", "未命名项目")
    rows = _flatten_indicators(
        state.get("scored_tree") or [],
        state.get("score_standards") or [],
    )
    if not rows:
        return {
            "analysis_rows": [],
            "analysis_draft_markdown": "（指标列表为空，无法生成分析。）",
            "status": "failed",
            "error": "无可分析的三级指标。",
            "updated_at": now_iso(),
            "messages": [AIMessage(content="未发现可分析的三级指标。")],
        }

    project_core = str(state.get("project_core_content") or "")
    field_evidence = str(state.get("field_evidence") or "")
    admin_prompt = read_admin_prompt(context, dict(state))
    admin_kb = read_admin_kb(context, dict(state))
    review_feedback = (state.get("review_feedback") or "").strip()

    prompt = _build_analysis_prompt(
        project_name=project_name,
        project_core_content=project_core,
        field_evidence=field_evidence,
        rows=rows,
        admin_prompt=admin_prompt,
        admin_kb=admin_kb,
        review_feedback=review_feedback,
    )

    configs = filter_configs_by_compare_models(
        read_model_configs(context),
        list(context.get("compare_models") or []),
        bool(context.get("enable_multi_model", False)),
    )

    error_message = ""
    comparisons: list[AnalysisDraft] = []
    analysis_rows: list[AnalysisRow]
    chosen_model = ""

    try:
        drafts = await_in_sync(
            generate_drafts_async(
                prompt=prompt,
                system_prompt=admin_prompt
                or "你是绩效评价指标分析专家，输出严格符合 JSON 格式。",
                configs=configs,
            )
        )
        comparisons = [
            {
                "model_name": d.get("model_name", ""),
                "label": d.get("label", d.get("model_name", "")),
                "draft": d.get("draft", ""),
                "error": d.get("error", ""),
            }
            for d in drafts
        ]
        winner = first_successful_draft(drafts)
        if winner is None:
            raise RuntimeError(collect_errors(drafts) or "所有模型调用均失败")
        chosen_model = winner.get("model_name", "")
        analysis_rows = _apply_llm_analysis(rows, winner.get("draft", ""), chosen_model)
    except Exception as exc:  # noqa: BLE001
        error_message = f"模型调用失败，已回退到规则模板：{exc}"
        analysis_rows = [_fallback_analysis_row(row) for row in rows]

    md = _render_analysis(project_name, analysis_rows)
    total = round(sum(float(r.get("obtained_score", 0) or 0) for r in analysis_rows), 2)
    return {
        "analysis_rows": analysis_rows,
        "analysis_draft_markdown": md,
        "total_score": total,
        "model_comparisons": comparisons,
        "status": "analysis_ready" if not error_message else "analysis_ready_with_fallback",
        "error": error_message,
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已逐项生成 {len(analysis_rows)} 个三级指标分析"
                    + (f"（采用模型：{chosen_model}）" if chosen_model else "")
                    + ("，已回退到规则模板。" if error_message else "，可逐项核对修订。")
                )
            )
        ],
    }


def review_analysis(state: Step7State) -> Step7State:
    rnd = int(state.get("review_round", 0)) + 1
    fb = (state.get("review_feedback") or "").strip()
    return {
        "review_round": rnd,
        "status": "analysis_reviewed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"已记录第 {rnd} 轮分析修改意见：{fb or '（无具体内容）'}")
        ],
    }


def finalize_analysis(state: Step7State) -> Step7State:
    project_name = state.get("project_name", "未命名项目")
    rows: list[AnalysisRow] = json.loads(json.dumps(state.get("analysis_rows") or []))
    if not rows:
        return {
            "status": "blocked",
            "error": "没有可定稿的分析行。",
            "messages": [AIMessage(content="请先生成分析草稿后再定稿。")],
            "updated_at": now_iso(),
        }
    md = _render_analysis(project_name, rows)
    total = round(sum(float(r.get("obtained_score", 0) or 0) for r in rows), 2)
    full = round(sum(float(r.get("score", 0) or 0) for r in rows), 2)
    md += f"\n\n## 总分汇总\n- 项目得分：{total:.2f} / {full:.2f}\n- 总得分率：{(total / full):.2%}" if full else f"\n\n## 总分汇总\n- 项目得分：{total:.2f}"
    payload = (
        md
        + "\n\n## 机器可读快照（JSON）\n```json\n"
        + json.dumps(rows, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    return {
        "analysis_rows": rows,
        "final_score_sheet_markdown": md,
        "total_score": total,
        "content_text": md,
        "export_payload": payload,
        "export_filename": f"{project_name}指标分析与得分表_定稿",
        "status": "completed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"第七步已完成，项目得分 {total:.2f} / {full:.2f}，可进入后续步骤。")
        ],
    }


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    graph = StateGraph(Step7State, context_schema=Step7Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_analysis", generate_analysis)
    graph.add_node("review_analysis", review_analysis)
    graph.add_node("finalize_analysis", finalize_analysis)

    graph.add_edge(START, "validate_basis")
    graph.add_conditional_edges(
        "validate_basis",
        route_after_basis,
        {"continue": "generate_analysis", "end": END},
    )
    graph.add_edge("generate_analysis", "review_analysis")
    graph.add_edge("review_analysis", "finalize_analysis")
    graph.add_edge("finalize_analysis", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step7")


graph = build_graph()
