"""Step 11 graph for EvalFlow Pro — 综合评价分析及评价结论.

承接 Step 7 ~ Step 10 的成果，生成综合评价分析与结论：

- 总体绩效概况（含总分、得分率、等级）；
- 绩效亮点（链接 Step 8 经验做法）；
- 核心问题（链接 Step 9 问题及原因）；
- 后续建议（链接 Step 10 整改建议）；
- 评价结论与等级建议。

状态字段
~~~~~~~~

- ``comprehensive_sections: dict[str, str]`` —— 各小节正文（结构化）；
- ``rating: str`` —— 评价等级（优 / 良 / 中 / 差）；
- ``comprehensive_analysis_draft`` —— 草稿正文；
- ``final_comprehensive_analysis`` —— 定稿正文；
- ``content_text`` —— 与定稿一致，供工作流持久化使用。
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
from .step5 import await_in_sync

ReviewMode = Literal["modify", "approve"]
Rating = Literal["优", "良", "中", "差"]

SECTION_KEYS: tuple[str, ...] = (
    "overall",
    "highlights",
    "issues",
    "suggestions",
    "conclusion",
)


class ComprehensiveDraft(TypedDict, total=False):
    model_name: str
    label: str
    draft: str
    error: str


class Step11State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    total_score: float
    full_score: float
    final_score_sheet_markdown: str
    final_experience_markdown: str
    final_problem_markdown: str
    final_suggestion_markdown: str
    analysis_rows: list[dict[str, Any]]
    experience_items: list[dict[str, Any]]
    problem_items: list[dict[str, Any]]
    suggestion_items: list[dict[str, Any]]

    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    model_comparisons: list[ComprehensiveDraft]

    comprehensive_sections: dict[str, str]
    rating: Rating
    comprehensive_analysis_draft: str
    final_comprehensive_analysis: str
    content_text: str
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
    model_configs: list[dict[str, Any]]
    compare_models: list[str]
    enable_multi_model: bool
    admin_prompt_content: str
    admin_kb_content: str
    output_dir: str


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _rating_from_rate(rate: float) -> Rating:
    if rate >= 0.9:
        return "优"
    if rate >= 0.8:
        return "良"
    if rate >= 0.6:
        return "中"
    return "差"


def _compute_score_summary(
    total: float,
    full: float,
    rows: list[dict[str, Any]],
) -> tuple[float, float, float, Rating]:
    full_value = float(full or 0)
    total_value = float(total or 0)
    if not full_value and rows:
        full_value = round(sum(float(r.get("score", 0) or 0) for r in rows), 2)
    if not total_value and rows:
        total_value = round(sum(float(r.get("obtained_score", 0) or 0) for r in rows), 2)
    rate = (total_value / full_value) if full_value else 0.0
    return total_value, full_value, rate, _rating_from_rate(rate)


def _summarize_top_bottom(
    rows: list[dict[str, Any]],
    *,
    bottom_n: int = 5,
    top_n: int = 5,
) -> tuple[str, str]:
    if not rows:
        empty = "（暂未提供结构化数据）"
        return empty, empty
    sorted_asc = sorted(rows, key=lambda r: float(r.get("score_rate", 1) or 1))
    sorted_desc = list(reversed(sorted_asc))
    bottom_lines = [
        f"- {r.get('l3_name', '')} ｜ 得分率 {float(r.get('score_rate', 0) or 0):.2%}"
        f" ｜ 扣分原因：{(r.get('deduction_reason') or '').strip() or '未提供'}"
        for r in sorted_asc[:bottom_n]
    ]
    top_lines = [
        f"- {r.get('l3_name', '')} ｜ 得分率 {float(r.get('score_rate', 0) or 0):.2%}"
        for r in sorted_desc[:top_n]
    ]
    return "\n".join(top_lines) or "（无）", "\n".join(bottom_lines) or "（无）"


def _summarize_items(
    items: list[dict[str, Any]],
    *,
    title_key: str = "title",
    detail_key: str | None = None,
    max_items: int = 8,
) -> str:
    if not items:
        return "（无）"
    head = items[:max_items]
    lines = []
    for it in head:
        line = f"- {it.get(title_key, '')}"
        if detail_key and it.get(detail_key):
            line += f" — {it.get(detail_key)}"
        lines.append(line)
    if len(items) > max_items:
        lines.append(f"…（共 {len(items)} 条，仅展示前 {max_items} 条）")
    return "\n".join(lines)


def _build_comprehensive_prompt(
    *,
    project_name: str,
    project_core_content: str,
    total: float,
    full: float,
    rate: float,
    rating: Rating,
    top_md: str,
    bottom_md: str,
    experience_md: str,
    problem_md: str,
    suggestion_md: str,
    admin_prompt: str,
    admin_kb: str,
    user_kb_context: str = "",
    review_feedback: str = "",
) -> str:
    preamble = build_admin_preamble(admin_prompt, admin_kb, user_kb_context)
    feedback_block = (
        f"\n【人工反馈意见（请按此调整本次输出）】\n{review_feedback.strip()}\n"
        if review_feedback.strip()
        else ""
    )
    instructions = [
        "请基于以上素材生成综合评价分析及结论，必须输出 5 个小节：",
        "1. overall —— 总体绩效概况：3~5 句，含项目得分、得分率与初判等级；",
        "2. highlights —— 绩效亮点：3~5 句，呼应经验做法；",
        "3. issues —— 核心问题：3~5 句，呼应问题及原因分析；",
        "4. suggestions —— 后续建议：3~5 句，呼应整改建议；",
        "5. conclusion —— 评价结论：2~3 句，明确给出评价等级（优/良/中/差）与判定理由。",
        "",
        "要求：",
        "- 各小节须互相呼应，避免重复堆砌；",
        "- 严禁出现 '同上' '略' 等占位说明；",
        "- 仅输出 JSON，不要任何额外文字。",
        "",
        "输出格式（严格 JSON）：",
        "{",
        '  "rating": "良",',
        '  "sections": {',
        '    "overall": "…",',
        '    "highlights": "…",',
        '    "issues": "…",',
        '    "suggestions": "…",',
        '    "conclusion": "…"',
        "  }",
        "}",
    ]
    score_block = (
        f"项目得分：{total:.2f} / {full:.2f}（得分率 {rate:.2%}），初判等级：{rating}。"
        if full
        else f"项目得分：{total:.2f}（缺少满分参考），初判等级：{rating}。"
    )
    return "\n".join(
        [
            preamble.strip(),
            f"项目名称：{project_name}",
            "项目核心内容：",
            (project_core_content or "（未提供）").strip(),
            "",
            "得分概况：",
            score_block,
            "",
            "得分率最高的指标（亮点候选）：",
            top_md,
            "",
            "得分率最低的指标（问题候选）：",
            bottom_md,
            "",
            "经验做法摘要：",
            experience_md,
            "",
            "问题及原因摘要：",
            problem_md,
            "",
            "整改建议摘要：",
            suggestion_md,
            feedback_block,
            "",
            *instructions,
        ]
    )


def _normalize_rating(value: Any, rate: float) -> Rating:
    text = str(value or "").strip()
    if text in ("优", "良", "中", "差"):
        return text  # type: ignore[return-value]
    return _rating_from_rate(rate)


def _fallback_sections(
    *,
    total: float,
    full: float,
    rate: float,
    rating: Rating,
    experience_md: str,
    problem_md: str,
    suggestion_md: str,
) -> dict[str, str]:
    score_text = (
        f"项目总体得分 {total:.2f} / {full:.2f}，得分率 {rate:.2%}，初判等级 {rating}。"
        if full
        else f"项目总体得分 {total:.2f}（缺少满分参考），初判等级 {rating}。"
    )
    return {
        "overall": (
            f"{score_text} 整体反映项目按计划推进，关键节点基本落地，"
            "在过程管控与成效转化等方面形成阶段性成果。"
        ),
        "highlights": (
            "项目在机制建设与过程管控上形成可复制的经验做法，关键证据完整，"
            "对同类项目具有参考价值。\n相关亮点详见经验做法章节："
            + (experience_md[:300] or "（待补充）")
        ),
        "issues": (
            "部分指标得分率偏低，反映出过程管控、资源保障或成效转化方面存在改进空间。"
            "\n相关问题详见问题及原因分析章节：" + (problem_md[:300] or "（待补充）")
        ),
        "suggestions": (
            "建议进一步完善整改机制、压实责任、加强证据留痕与成果转化。"
            "\n相关建议详见整改建议章节：" + (suggestion_md[:300] or "（待补充）")
        ),
        "conclusion": (
            f"综合判断，项目评价等级为 {rating}。"
            "建议按整改建议落实闭环管理，并在下一周期内复评关键指标。"
        ),
    }


def _apply_llm_comprehensive(
    raw_text: str,
    rate: float,
) -> tuple[Rating, dict[str, str]]:
    parsed = parse_json_object(raw_text) or {}
    sections_raw = parsed.get("sections") if isinstance(parsed, dict) else None
    sections: dict[str, str] = {}
    if isinstance(sections_raw, dict):
        for key in SECTION_KEYS:
            value = sections_raw.get(key)
            if isinstance(value, str) and value.strip():
                sections[key] = value.strip()
    rating = _normalize_rating(parsed.get("rating") if isinstance(parsed, dict) else None, rate)
    return rating, sections


def _render_comprehensive(
    project_name: str,
    *,
    total: float,
    full: float,
    rate: float,
    rating: Rating,
    sections: dict[str, str],
) -> str:
    score_line = (
        f"- 项目得分：{total:.2f} / {full:.2f}（得分率 {rate:.2%}）"
        if full
        else f"- 项目得分：{total:.2f}（缺少满分参考）"
    )
    lines = [
        f"# 《{project_name} — 综合评价分析及评价结论》",
        "",
        f"- 生成时间：{now_iso()}",
        score_line,
        f"- 评价等级：{rating}",
        "",
        "## 总体绩效概况",
        sections.get("overall") or "（待补充）",
        "",
        "## 绩效亮点",
        sections.get("highlights") or "（待补充）",
        "",
        "## 核心问题",
        sections.get("issues") or "（待补充）",
        "",
        "## 后续建议",
        sections.get("suggestions") or "（待补充）",
        "",
        "## 评价结论",
        sections.get("conclusion") or "（待补充）",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------


def validate_basis(state: Step11State) -> Step11State:
    if (
        not state.get("final_score_sheet_markdown")
        and not state.get("analysis_rows")
        and not state.get("total_score")
    ):
        return {
            "status": "failed",
            "error": "缺少第七步成果：请先传入得分表或 analysis_rows。",
            "messages": [
                AIMessage(content="第十一步需基于第七步至第十步的结构化成果生成综合评价。")
            ],
            "updated_at": now_iso(),
        }
    name = (state.get("project_name") or "未命名项目").strip() or "未命名项目"
    return {
        "project_name": name,
        "created_at": state.get("created_at") or now_iso(),
        "updated_at": now_iso(),
        "status": "basis_ok",
        "messages": [AIMessage(content=f"已接收前序成果，项目：{name}。开始生成综合评价。")],
    }


def route_after_basis(state: Step11State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


def generate_comprehensive(state: Step11State, runtime: Any = None) -> Step11State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    project_name = state.get("project_name", "未命名项目")
    project_core = str(state.get("project_core_content") or "")
    rows = list(state.get("analysis_rows") or [])

    total, full, rate, default_rating = _compute_score_summary(
        float(state.get("total_score", 0) or 0),
        float(state.get("full_score", 0) or 0),
        rows,
    )
    top_md, bottom_md = _summarize_top_bottom(rows)
    experience_md = _summarize_items(
        list(state.get("experience_items") or []),
        title_key="title",
        detail_key="effect",
    )
    problem_md = _summarize_items(
        list(state.get("problem_items") or []),
        title_key="title",
        detail_key="root_cause",
    )
    suggestion_md = _summarize_items(
        list(state.get("suggestion_items") or []),
        title_key="title",
        detail_key="objective",
    )

    admin_prompt = read_admin_prompt(context, dict(state))
    admin_kb = read_admin_kb(context, dict(state))
    from ._llm import fetch_user_kb_context_sync
    user_kb_context = fetch_user_kb_context_sync(
        project_id=str(context.get("project_id") or ""),
        query=f"{project_name} 可持续性评价",
        step_code="step11",
    )
    review_feedback = (state.get("review_feedback") or "").strip()

    prompt = _build_comprehensive_prompt(
        project_name=project_name,
        project_core_content=project_core,
        total=total,
        full=full,
        rate=rate,
        rating=default_rating,
        top_md=top_md,
        bottom_md=bottom_md,
        experience_md=experience_md,
        problem_md=problem_md,
        suggestion_md=suggestion_md,
        admin_prompt=admin_prompt,
        admin_kb=admin_kb,
        user_kb_context=user_kb_context,
        review_feedback=review_feedback,
    )

    configs = filter_configs_by_compare_models(
        read_model_configs(context),
        list(context.get("compare_models") or []),
        bool(context.get("enable_multi_model", False)),
    )

    error_message = ""
    comparisons: list[ComprehensiveDraft] = []
    sections: dict[str, str]
    rating: Rating
    chosen_model = ""

    try:
        drafts = await_in_sync(
            generate_drafts_async(
                prompt=prompt,
                system_prompt=admin_prompt
                or "你是绩效评价综合分析专家，输出严格符合 JSON 格式。",
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
        rating, parsed_sections = _apply_llm_comprehensive(winner.get("draft", ""), rate)
        if len(parsed_sections) < len(SECTION_KEYS):
            fallback_sections = _fallback_sections(
                total=total,
                full=full,
                rate=rate,
                rating=rating,
                experience_md=experience_md,
                problem_md=problem_md,
                suggestion_md=suggestion_md,
            )
            for key in SECTION_KEYS:
                parsed_sections.setdefault(key, fallback_sections[key])
            chosen_model = f"{chosen_model}+fallback"
        sections = parsed_sections
    except Exception as exc:  # noqa: BLE001
        error_message = f"模型调用失败，已回退到规则模板：{exc}"
        rating = default_rating
        sections = _fallback_sections(
            total=total,
            full=full,
            rate=rate,
            rating=rating,
            experience_md=experience_md,
            problem_md=problem_md,
            suggestion_md=suggestion_md,
        )

    md = _render_comprehensive(
        project_name,
        total=total,
        full=full,
        rate=rate,
        rating=rating,
        sections=sections,
    )
    return {
        "comprehensive_sections": sections,
        "rating": rating,
        "total_score": total,
        "full_score": full,
        "comprehensive_analysis_draft": md,
        "model_comparisons": comparisons,
        "status": "comprehensive_ready" if not error_message else "comprehensive_ready_with_fallback",
        "error": error_message,
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已生成综合评价分析（等级：{rating}）"
                    + (f"（采用模型：{chosen_model}）" if chosen_model else "")
                    + ("，已回退到规则模板。" if error_message else "，可逐节核对。")
                )
            )
        ],
    }


def review_comprehensive(state: Step11State) -> Step11State:
    rnd = int(state.get("review_round", 0)) + 1
    fb = (state.get("review_feedback") or "").strip()
    return {
        "review_round": rnd,
        "status": "comprehensive_reviewed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"已记录第 {rnd} 轮综合评价修改意见：{fb or '（无具体内容）'}")
        ],
    }


def finalize_comprehensive(state: Step11State) -> Step11State:
    project_name = state.get("project_name", "未命名项目")
    sections = dict(state.get("comprehensive_sections") or {})
    if not sections:
        return {
            "status": "blocked",
            "error": "没有可定稿的综合评价分析。",
            "messages": [AIMessage(content="请先生成综合评价草稿后再定稿。")],
            "updated_at": now_iso(),
        }
    total = float(state.get("total_score", 0) or 0)
    full = float(state.get("full_score", 0) or 0)
    rate = (total / full) if full else 0.0
    rating: Rating = state.get("rating") or _rating_from_rate(rate)
    md = _render_comprehensive(
        project_name,
        total=total,
        full=full,
        rate=rate,
        rating=rating,
        sections=sections,
    )
    snapshot = {"rating": rating, "total": total, "full": full, "sections": sections}
    payload = (
        md
        + "\n\n## 机器可读快照（JSON）\n```json\n"
        + json.dumps(snapshot, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    return {
        "comprehensive_sections": sections,
        "rating": rating,
        "final_comprehensive_analysis": md,
        "content_text": md,
        "export_payload": payload,
        "export_filename": f"{project_name}综合评价分析_定稿",
        "status": "completed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"第十一步已完成，评价等级：{rating}。")
        ],
    }


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    graph = StateGraph(Step11State, context_schema=Step11Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_comprehensive", generate_comprehensive)
    graph.add_node("review_comprehensive", review_comprehensive)
    graph.add_node("finalize_comprehensive", finalize_comprehensive)

    graph.add_edge(START, "validate_basis")
    graph.add_conditional_edges(
        "validate_basis",
        route_after_basis,
        {"continue": "generate_comprehensive", "end": END},
    )
    graph.add_edge("generate_comprehensive", "review_comprehensive")
    graph.add_edge("review_comprehensive", "finalize_comprehensive")
    graph.add_edge("finalize_comprehensive", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step11")


graph = build_graph()
