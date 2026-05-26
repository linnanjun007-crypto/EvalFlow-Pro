"""Step 7 graph for EvalFlow Pro — 指标体系分析与终审成果生成.

围绕 Step 6 锁定的指标体系拓扑树（``scored_tree``）+ Step 5 评分标准（``score_standards``）
+ Step 2 项目核心内容（``project_core_content``），把每个三级指标拆解成"评价要点"逐要点
表单化录入。前端按 ``indicator_form`` 渲染独立输入框，用户填写"大白话事实 / 该要点得分 /
扣分原因"，本 graph 完成：

1. **评价要点拆分** —— ``expand_points`` 节点按 step5 ``key_points`` 拆分粒度；
2. **AI 专家级翻译** —— ``generate_analysis`` 把大白话 + 项目核心 + 知识库缝合，输出
   ``专家级 analysis``；多模型并列对比放在 ``model_comparisons``；
3. **级联数学引擎** —— ``finalize_analysis`` 自动计算三级 ``score_rate``、二级小计、
   一级小计、全体系总分；满分校验（要点 sum ≤ 三级满分）；
4. **结构化公文输出** —— 按四大一级块（决策 / 过程 / 产出 / 效益）输出
   ``二级 | 三级 | 分值 | 得分 | 得分率`` 5 列分块表；最终再追加总评分表 6 列
   ``一级 | 二级 | 三级 | 分值 | 得分 | 扣分原因``。

LLM 全部失败时回退到 ``实际得分 = 用户填的要点得分 sum，否则按满分 80%`` 的兜底规则。
"""

from __future__ import annotations

import json
import operator
import re
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


# ---------------------------------------------------------------------------
# typed dicts
# ---------------------------------------------------------------------------


class PointSlot(TypedDict, total=False):
    """单个评价要点的表单 schema（用于前端渲染输入框）。"""

    key: str           # P1 / P2 …
    label: str         # 评价要点标题（例如"材料完整性"）
    hint: str          # 提示文案（评分标准摘要）
    suggested_score: float  # 建议满分（按要点平均分摊）


class PointInput(TypedDict, total=False):
    """单个要点的用户输入。"""

    key: str
    label: str
    plain_text: str         # 大白话事实
    score: float            # 得分
    deduction_reason: str   # 扣分/得分原因


class IndicatorForm(TypedDict, total=False):
    id: str
    l1_name: str
    l2_name: str
    l3_name: str
    score: float            # 三级指标满分
    tag: str
    points: list[PointSlot] # 拆出来的要点
    rubric: dict[str, str]


class AnalysisDraft(TypedDict, total=False):
    model_name: str
    label: str
    draft: str
    error: str


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
    point_inputs: list[PointInput]
    model_name: str


class Step7State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    scored_tree: list[L1ScoreRow]
    score_standards: list[ScoreStandard]

    # 问卷回收数据（来自 step6 衍生问卷的现实样本）
    survey_summary: str
    survey_sample_size: int
    survey_satisfaction_rate: float

    # 用户填写的逐要点输入（前端表单回填）
    indicator_inputs: dict[str, list[PointInput]]

    # 表单 schema：前端按它渲染输入框
    indicator_form: list[IndicatorForm]

    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    model_comparisons: list[AnalysisDraft]

    analysis_rows: list[AnalysisRow]
    analysis_draft_markdown: str
    final_score_sheet_markdown: str
    block_tables_markdown: str
    overall_score_table_markdown: str
    total_score: float
    total_full_score: float
    overall_score_rate: float
    level1_subtotals: list[dict[str, Any]]
    level2_subtotals: list[dict[str, Any]]
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


_POINT_SPLIT_RE = re.compile(r"[；;\n、]+")
_BULLET_RE = re.compile(r"^\s*(?:[\-•·●▪◆◇○\*]|\d+[\.\)、])\s*")


def _extract_points(key_points: str) -> list[str]:
    """把 step5 的 ``key_points`` 拆成多个评价要点。

    支持中文/英文分号、换行、顿号；行内的列表符号（- ● 1. 等）会被剥掉。
    """
    text = (key_points or "").strip()
    if not text:
        return []
    raw = _POINT_SPLIT_RE.split(text)
    cleaned: list[str] = []
    for piece in raw:
        item = _BULLET_RE.sub("", piece).strip()
        item = item.strip("：:。.，, ")
        if item and item not in cleaned:
            cleaned.append(item)
    return cleaned


def _flatten_indicators(
    tree: list[L1ScoreRow],
    standards: list[ScoreStandard],
) -> list[dict[str, Any]]:
    """按 step6 拓扑顺序展平到三级指标，并附带 step5 锁定的 rubric/key_points。"""
    rubric_index: dict[str, ScoreStandard] = {
        str(s.get("id", "")): s for s in standards if s.get("id")
    }
    rows: list[dict[str, Any]] = []
    for l1 in tree:
        for l2 in l1.get("level2", []) or []:
            for l3 in l2.get("level3", []) or []:
                row_id = str(l3.get("id", ""))
                std = rubric_index.get(row_id, {})
                key_points_text = str(
                    std.get("key_points") or l3.get("key_points") or ""
                )
                rubric = std.get("rubric") or l3.get("rubric") or {}
                rows.append(
                    {
                        "id": row_id,
                        "l1_name": str(l1.get("name", "")),
                        "l2_name": str(l2.get("name", "")),
                        "l3_name": str(l3.get("name", "")),
                        "score": float(l3.get("score", 0) or 0),
                        "tag": str(l3.get("tag") or std.get("tag") or "其他"),
                        "rubric": dict(rubric),
                        "key_points": key_points_text,
                    }
                )
    return rows


def _build_form(rows: list[dict[str, Any]]) -> list[IndicatorForm]:
    """为每个三级指标拆出评价要点表单。要点平均摊分作为前端 Validator 默认值。"""
    forms: list[IndicatorForm] = []
    for row in rows:
        score = float(row.get("score", 0) or 0)
        rubric = dict(row.get("rubric") or {})
        labels = _extract_points(row.get("key_points") or "")
        if not labels:
            # 若 step5 没填 key_points，至少给"整体执行情况"一个兜底要点，避免前端空表
            labels = ["整体执行情况"]
        avg = round(score / max(len(labels), 1), 2)
        slots: list[PointSlot] = []
        for idx, label in enumerate(labels):
            tier_hint = (rubric.get("良好") or rubric.get("合格") or "").strip()
            slots.append(
                {
                    "key": f"P{idx + 1}",
                    "label": label,
                    "hint": tier_hint[:120] if tier_hint else "",
                    "suggested_score": avg,
                }
            )
        forms.append(
            {
                "id": str(row.get("id", "")),
                "l1_name": str(row.get("l1_name", "")),
                "l2_name": str(row.get("l2_name", "")),
                "l3_name": str(row.get("l3_name", "")),
                "score": score,
                "tag": str(row.get("tag") or "其他"),
                "points": slots,
                "rubric": rubric,
            }
        )
    return forms


def _normalize_inputs(
    inputs: dict[str, list[PointInput]] | None,
    forms: list[IndicatorForm],
) -> dict[str, list[PointInput]]:
    """前端提交的 inputs 与 form schema 对齐：补齐缺失要点、夹紧得分到 [0, 满分]。"""
    out: dict[str, list[PointInput]] = {}
    raw = inputs or {}
    for form in forms:
        ind_id = form.get("id", "")
        full = float(form.get("score", 0) or 0)
        slots = form.get("points") or []
        provided = raw.get(ind_id) or []
        by_key: dict[str, PointInput] = {}
        if isinstance(provided, list):
            for item in provided:
                if isinstance(item, dict):
                    by_key[str(item.get("key") or "").strip()] = item  # type: ignore[assignment]
        merged: list[PointInput] = []
        for slot in slots:
            k = slot.get("key", "")
            src = by_key.get(k, {})
            try:
                score_val = float(src.get("score", 0) or 0)
            except (TypeError, ValueError):
                score_val = 0.0
            score_val = max(0.0, min(full, round(score_val, 2)))
            merged.append(
                {
                    "key": k,
                    "label": str(slot.get("label", "")),
                    "plain_text": str(src.get("plain_text") or "").strip(),
                    "score": score_val,
                    "deduction_reason": str(src.get("deduction_reason") or "").strip(),
                }
            )
        out[ind_id] = merged
    return out


def _sum_point_score(pts: list[PointInput]) -> float:
    return round(sum(float(p.get("score", 0) or 0) for p in pts), 2)


def _aggregate_point_text(pts: list[PointInput]) -> tuple[str, str]:
    """把要点级输入合成两个长字符串：plain_text 拼接、deduction_reason 拼接。"""
    plain_parts: list[str] = []
    reason_parts: list[str] = []
    for p in pts:
        label = (p.get("label") or "").strip()
        plain = (p.get("plain_text") or "").strip()
        if plain:
            plain_parts.append(f"【{label}】{plain}")
        reason = (p.get("deduction_reason") or "").strip()
        if reason and reason not in {"无", "—", "-"}:
            reason_parts.append(f"{label}：{reason}")
    return ("；".join(plain_parts), "；".join(reason_parts))


def _build_analysis_prompt(
    *,
    project_name: str,
    project_core_content: str,
    survey_summary: str,
    forms: list[IndicatorForm],
    inputs: dict[str, list[PointInput]],
    admin_prompt: str,
    admin_kb: str,
    review_feedback: str = "",
    user_kb_context: str = "",
) -> str:
    preamble = build_admin_preamble(admin_prompt, admin_kb, user_kb_context)
    blocks: list[str] = []
    for form in forms:
        ind_id = form.get("id", "")
        pts = inputs.get(ind_id) or []
        rubric = form.get("rubric") or {}
        rubric_lines = "\n".join(
            f"      - {tier}：{(rubric.get(tier) or '').strip() or '（待补充）'}"
            for tier in ("优秀", "良好", "合格", "不合格")
        )
        point_lines: list[str] = []
        for p in pts:
            point_lines.append(
                f"      - 要点[{p.get('key')}] {p.get('label')}："
                f"用户大白话={p.get('plain_text') or '（未填）'}；"
                f"得分={float(p.get('score', 0) or 0):.2f}；"
                f"扣分原因={p.get('deduction_reason') or '无'}"
            )
        blocks.append(
            "\n".join(
                [
                    f"- id={ind_id}",
                    f"  一级={form['l1_name']} / 二级={form['l2_name']} / 三级={form['l3_name']}",
                    f"  满分={float(form.get('score', 0) or 0):.2f}",
                    "    评分标准：",
                    rubric_lines,
                    "    用户填写的逐要点事实（务必全部覆盖）：",
                    *(point_lines or ["      - （用户未填写要点输入）"]),
                ]
            )
        )
    indicators_text = "\n".join(blocks) or "（空）"

    feedback_block = (
        f"\n【人工反馈意见（请按此调整本次输出）】\n{review_feedback.strip()}\n"
        if review_feedback.strip()
        else ""
    )

    instructions = [
        "请基于以上素材，对每个三级指标生成专家级分析（务必覆盖所有指标）：",
        "1. analysis —— 中文 2~4 句，须把用户填写的【大白话】事实与项目核心内容、",
        "   行业知识库缝合，写成『语境严密、逻辑无懈可击』的公文式专家分析；严禁出现『略』『同上』。",
        "2. obtained_score —— 若用户已填写要点得分（>0），严格等于『用户填写各要点得分之和』；",
        "   若用户全部未填（用户得分=0 且 大白话为空），按 rubric 档位估分：",
        "   默认按『合格』档中位（满分 × 0.675）落分，再依据已知项目核心 / 行业知识库做 ±10% 微调；",
        "   严禁全部归零；保留两位小数。",
        "3. deduction_reason —— 汇总所有要点的扣分原因；用户未填且按 rubric 估分时，写明",
        "   『当前缺现场台账，按 rubric「合格」档中位估分，建议补充 XXX 材料以校准』。",
        "4. 严禁照抄评分标准条款；分析中应自动引用项目真实学校 / 团队 / 帮扶村庄 / 实施地名等。",
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
            "现场问卷与样本数据：",
            (survey_summary or "（未提供，请基于评分标准与核心内容审慎判断）").strip(),
            "",
            "待分析三级指标列表（含用户大白话输入）：",
            indicators_text,
            feedback_block,
            "",
            *instructions,
        ]
    )


def _fallback_analysis_row(
    form: IndicatorForm,
    pts: list[PointInput],
) -> AnalysisRow:
    score = float(form.get("score", 0) or 0)
    user_sum = _sum_point_score(pts)
    # 无 LLM 时：用户填了取用户和；未填按 rubric『合格』档中位 (满分 × 0.675) 兜底，
    # 而不是 0.8（避免与"已填高分"无差异）。
    obtained = round(user_sum if user_sum > 0 else score * 0.675, 2)
    obtained = max(0.0, min(score, obtained))
    plain_text, agg_reason = _aggregate_point_text(pts)
    if user_sum > 0:
        deduction = agg_reason or ("证据不足，按评分标准酌情扣分。" if obtained < score else "无")
    else:
        deduction = "用户未提交现场台账，按 rubric『合格』档中位估分，建议补充材料后人工校准。"
    plain = plain_text or "未提供大白话事实"
    analysis = (
        f"基于现场反馈（{plain}），对「{form.get('l3_name')}」按评分标准做规则模板估算，"
        "建议人工补充专家级文本。"
    )
    return {
        "id": str(form.get("id", "")),
        "l1_name": str(form.get("l1_name", "")),
        "l2_name": str(form.get("l2_name", "")),
        "l3_name": str(form.get("l3_name", "")),
        "score": score,
        "obtained_score": obtained,
        "score_rate": (obtained / score) if score else 0.0,
        "deduction_reason": deduction,
        "analysis": analysis,
        "point_inputs": pts,
        "model_name": "fallback",
    }


def _apply_llm_analysis(
    forms: list[IndicatorForm],
    inputs: dict[str, list[PointInput]],
    raw_text: str,
    model_name: str,
) -> list[AnalysisRow]:
    parsed = parse_json_object(raw_text) or {}
    items = parsed.get("rows") if isinstance(parsed, dict) else None
    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                rid = str(item.get("id") or "").strip()
                if rid:
                    by_id[rid] = item

    out: list[AnalysisRow] = []
    for form in forms:
        ind_id = str(form.get("id", ""))
        score = float(form.get("score", 0) or 0)
        pts = inputs.get(ind_id) or []
        item = by_id.get(ind_id)
        if not item:
            out.append(_fallback_analysis_row(form, pts))
            continue
        # 实际得分以"用户要点输入和"为准（用户是裁决者）；模型返回值仅作 sanity 校对。
        # 当用户完全没填（user_sum == 0），模型也给 0 时，按 rubric『合格』档中位（满分×0.675）兜底，
        # 避免出现"全 0 无差异"的输出（实际是用户没现场材料而非真扣完所有分）。
        user_sum = _sum_point_score(pts)
        try:
            model_obtained = float(item.get("obtained_score", 0))
        except (TypeError, ValueError):
            model_obtained = user_sum
        if user_sum > 0:
            obtained = user_sum
        elif model_obtained >= score * 0.3:
            obtained = model_obtained
        else:
            obtained = round(score * 0.675, 2)
        obtained = max(0.0, min(score, round(obtained, 2)))
        _, agg_reason = _aggregate_point_text(pts)
        deduction = (
            str(item.get("deduction_reason") or "").strip()
            or agg_reason
            or ("无" if obtained == score else "证据不足，按评分标准扣分。")
        )
        analysis = str(item.get("analysis") or "").strip()
        if not analysis:
            analysis = (
                f"模型未返回 {form.get('l3_name')} 的分析，已回退到规则模板。"
            )
            source_model = f"{model_name}+fallback"
        else:
            source_model = model_name
        out.append(
            {
                "id": ind_id,
                "l1_name": str(form.get("l1_name", "")),
                "l2_name": str(form.get("l2_name", "")),
                "l3_name": str(form.get("l3_name", "")),
                "score": score,
                "obtained_score": obtained,
                "score_rate": (obtained / score) if score else 0.0,
                "deduction_reason": deduction,
                "analysis": analysis,
                "point_inputs": pts,
                "model_name": source_model,
            }
        )
    return out


# ---------------------------------------------------------------------------
# 级联计算 + markdown 渲染
# ---------------------------------------------------------------------------


def _classify_l1_block(name: str) -> str:
    """把一级指标名字归类到决策 / 过程 / 产出 / 效益 四块。"""
    n = name or ""
    if "决策" in n:
        return "决策"
    if "过程" in n:
        return "过程"
    if "产出" in n:
        return "产出"
    if "效益" in n:
        return "效益"
    return "其他"


_L1_BLOCK_TITLES = {
    "决策": "一、项目决策情况分析",
    "过程": "二、项目过程情况分析",
    "产出": "三、项目产出情况分析",
    "效益": "四、项目效益情况分析",
    "其他": "五、其他指标分析",
}


def _md_escape(text: str) -> str:
    return (text or "").replace("|", "/").replace("\n", "<br/>")


def _compute_subtotals(
    rows: list[AnalysisRow],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float, float]:
    """级联计算：(level1_subtotals, level2_subtotals, total, full)."""
    l1_buckets: dict[str, dict[str, Any]] = {}
    l2_buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for r in rows:
        l1 = str(r.get("l1_name") or "")
        l2 = str(r.get("l2_name") or "")
        score = float(r.get("score", 0) or 0)
        obtained = float(r.get("obtained_score", 0) or 0)
        l1b = l1_buckets.setdefault(l1, {"l1_name": l1, "obtained": 0.0, "full": 0.0})
        l1b["obtained"] = round(l1b["obtained"] + obtained, 2)
        l1b["full"] = round(l1b["full"] + score, 2)
        l2b = l2_buckets.setdefault(
            (l1, l2),
            {"l1_name": l1, "l2_name": l2, "obtained": 0.0, "full": 0.0},
        )
        l2b["obtained"] = round(l2b["obtained"] + obtained, 2)
        l2b["full"] = round(l2b["full"] + score, 2)
    total = round(sum(b["obtained"] for b in l1_buckets.values()), 2)
    full = round(sum(b["full"] for b in l1_buckets.values()), 2)
    return list(l1_buckets.values()), list(l2_buckets.values()), total, full


def _render_block_tables(rows: list[AnalysisRow]) -> str:
    """按四大块（决策 / 过程 / 产出 / 效益）输出 5 列表 + 块内小计。"""
    grouped: dict[str, list[AnalysisRow]] = {}
    for r in rows:
        key = _classify_l1_block(str(r.get("l1_name") or ""))
        grouped.setdefault(key, []).append(r)
    lines: list[str] = ["## 一、二、三、四 指标分析（按一级指标分块）", ""]
    block_order = ["决策", "过程", "产出", "效益", "其他"]
    for block_key in block_order:
        bucket = grouped.get(block_key)
        if not bucket:
            continue
        title = _L1_BLOCK_TITLES.get(block_key, block_key)
        # 取第一条作为该块的一级指标名（更具体）
        l1_name = bucket[0].get("l1_name") or block_key
        lines.append(f"### {title}（{l1_name}）")
        lines.append("")
        # 先输出该块内每个三级指标的分析正文
        last_l2: str | None = None
        for r in bucket:
            l2 = str(r.get("l2_name") or "")
            if l2 != last_l2:
                lines.append(f"**二级 · {l2}**")
                last_l2 = l2
            score = float(r.get("score", 0) or 0)
            obtained = float(r.get("obtained_score", 0) or 0)
            rate = (obtained / score) if score else 0.0
            lines.append(
                f"- 三级 · {r.get('l3_name')}（满分 {score:.2f} ｜ 得分 {obtained:.2f} ｜ 得分率 {rate:.2%}）"
            )
            lines.append(f"  - 分析：{r.get('analysis') or ''}")
            lines.append(f"  - 扣分原因：{r.get('deduction_reason') or '无'}")
        # 再输出 5 列结构化表
        lines.append("")
        lines.append("| 二级指标 | 三级指标 | 分值 | 得分 | 得分率 |")
        lines.append("| --- | --- | --- | --- | --- |")
        sub_full = 0.0
        sub_obt = 0.0
        for r in bucket:
            score = float(r.get("score", 0) or 0)
            obtained = float(r.get("obtained_score", 0) or 0)
            rate = (obtained / score) if score else 0.0
            sub_full += score
            sub_obt += obtained
            lines.append(
                f"| {_md_escape(str(r.get('l2_name') or ''))} "
                f"| {_md_escape(str(r.get('l3_name') or ''))} "
                f"| {score:.2f} | {obtained:.2f} | {rate:.2%} |"
            )
        sub_rate = (sub_obt / sub_full) if sub_full else 0.0
        lines.append(
            f"| **小计** |  | **{sub_full:.2f}** | **{sub_obt:.2f}** | **{sub_rate:.2%}** |"
        )
        lines.append("")
    return "\n".join(lines)


def _render_overall_table(
    rows: list[AnalysisRow],
    l1_subs: list[dict[str, Any]],
    total: float,
    full: float,
) -> str:
    """总评分表 6 列：一级 | 二级 | 三级 | 分值 | 得分 | 扣分原因。"""
    lines: list[str] = [
        "## 项目绩效评价总评分表",
        "",
        "| 一级指标 | 二级指标 | 三级指标 | 分值 | 得分 | 扣分原因 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    last_l1: str | None = None
    last_l2: str | None = None
    for r in rows:
        l1 = str(r.get("l1_name") or "")
        l2 = str(r.get("l2_name") or "")
        score = float(r.get("score", 0) or 0)
        obtained = float(r.get("obtained_score", 0) or 0)
        l1_cell = l1 if l1 != last_l1 else ""
        l2_cell = l2 if (l2 != last_l2 or l1 != last_l1) else ""
        last_l1, last_l2 = l1, l2
        reason = r.get("deduction_reason") or "无"
        lines.append(
            f"| {_md_escape(l1_cell)} | {_md_escape(l2_cell)} | {_md_escape(str(r.get('l3_name') or ''))} "
            f"| {score:.2f} | {obtained:.2f} | {_md_escape(str(reason))} |"
        )
    # 一级小计
    for sub in l1_subs:
        lines.append(
            f"| **{_md_escape(str(sub.get('l1_name')))} 小计** |  |  | "
            f"**{float(sub.get('full', 0) or 0):.2f}** | **{float(sub.get('obtained', 0) or 0):.2f}** |  |"
        )
    rate = (total / full) if full else 0.0
    lines.append(
        f"| **总计** |  |  | **{full:.2f}** | **{total:.2f}** | 总得分率 **{rate:.2%}** |"
    )
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
            AIMessage(content="已接收指标体系、评分标准与项目核心内容，开始生成要点级表单。")
        ],
    }


def route_after_basis(state: Step7State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


def expand_points(state: Step7State) -> Step7State:
    """按 step5 ``key_points`` 把每个三级指标拆成多个评价要点表单。"""
    rows = _flatten_indicators(
        state.get("scored_tree") or [],
        state.get("score_standards") or [],
    )
    forms = _build_form(rows)
    if not forms:
        return {
            "status": "failed",
            "error": "未能展开任何三级指标；请确认 scored_tree / score_standards 内容。",
            "messages": [AIMessage(content="无可展开的三级指标。")],
            "updated_at": now_iso(),
        }
    inputs = _normalize_inputs(state.get("indicator_inputs"), forms)
    return {
        "indicator_form": forms,
        "indicator_inputs": inputs,
        "status": "form_ready",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已按评分标准的『评价要点』为 {len(forms)} 个三级指标渲染表单，"
                    "请在前端逐要点填写大白话事实、得分与扣分原因。"
                )
            )
        ],
    }


def generate_analysis(state: Step7State, runtime: Any = None) -> Step7State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    project_name = state.get("project_name", "未命名项目")
    forms = state.get("indicator_form") or []
    if not forms:
        # 兼容直接调用 generate 的场景：先现场展开
        rows = _flatten_indicators(
            state.get("scored_tree") or [],
            state.get("score_standards") or [],
        )
        forms = _build_form(rows)
    inputs = _normalize_inputs(state.get("indicator_inputs"), forms)
    if not forms:
        return {
            "analysis_rows": [],
            "analysis_draft_markdown": "（指标列表为空，无法生成分析。）",
            "status": "failed",
            "error": "无可分析的三级指标。",
            "updated_at": now_iso(),
            "messages": [AIMessage(content="未发现可分析的三级指标。")],
        }

    project_core = str(state.get("project_core_content") or "")
    survey_summary = str(state.get("survey_summary") or "")
    sample = state.get("survey_sample_size")
    rate = state.get("survey_satisfaction_rate")
    if sample or rate:
        survey_summary = (
            (survey_summary + "\n" if survey_summary else "")
            + (f"有效样本量：{int(sample) if sample else '-'}；" if sample else "")
            + (f"综合满意率：{float(rate):.2%}" if rate else "")
        ).strip()

    admin_prompt = read_admin_prompt(context, dict(state))
    admin_kb = read_admin_kb(context, dict(state))
    from ._llm import fetch_user_kb_context_sync
    user_kb_context = fetch_user_kb_context_sync(
        project_id=str(context.get("project_id") or ""),
        query=f"{project_name} 项目实施 学校 团队 帮扶村庄",
        step_code="step7",
    )
    review_feedback = (state.get("review_feedback") or "").strip()

    prompt = _build_analysis_prompt(
        project_name=project_name,
        project_core_content=project_core,
        survey_summary=survey_summary,
        forms=forms,
        inputs=inputs,
        admin_prompt=admin_prompt,
        admin_kb=admin_kb,
        review_feedback=review_feedback,
        user_kb_context=user_kb_context,
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
        analysis_rows = _apply_llm_analysis(
            forms, inputs, winner.get("draft", ""), chosen_model
        )
    except Exception as exc:  # noqa: BLE001
        error_message = f"模型调用失败，已回退到规则模板：{exc}"
        analysis_rows = [
            _fallback_analysis_row(form, inputs.get(str(form.get("id", "")), []))
            for form in forms
        ]

    l1_subs, l2_subs, total, full = _compute_subtotals(analysis_rows)
    block_md = _render_block_tables(analysis_rows)
    overall_md = _render_overall_table(analysis_rows, l1_subs, total, full)
    draft_md = "\n\n".join([block_md, overall_md])
    return {
        "analysis_rows": analysis_rows,
        "analysis_draft_markdown": draft_md,
        "block_tables_markdown": block_md,
        "overall_score_table_markdown": overall_md,
        "level1_subtotals": l1_subs,
        "level2_subtotals": l2_subs,
        "total_score": total,
        "total_full_score": full,
        "overall_score_rate": (total / full) if full else 0.0,
        "model_comparisons": comparisons,
        "status": "analysis_ready" if not error_message else "analysis_ready_with_fallback",
        "error": error_message,
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已完成 {len(analysis_rows)} 个三级指标分析"
                    + (f"（采用模型：{chosen_model}）" if chosen_model else "")
                    + f"，项目得分 {total:.2f} / {full:.2f}。"
                    + ("（已回退到规则模板）" if error_message else "")
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
    l1_subs, l2_subs, total, full = _compute_subtotals(rows)
    block_md = _render_block_tables(rows)
    overall_md = _render_overall_table(rows, l1_subs, total, full)
    md = "\n\n".join(
        [
            f"# 《{project_name} — 指标体系分析与得分表》",
            f"- 生成时间：{now_iso()}",
            f"- 三级指标数：{len(rows)}",
            f"- 项目得分：{total:.2f} / {full:.2f}（得分率 {(total / full):.2%}）"
            if full else f"- 项目得分：{total:.2f}",
            block_md,
            overall_md,
        ]
    )
    payload = (
        md
        + "\n\n## 机器可读快照（JSON）\n```json\n"
        + json.dumps(rows, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    return {
        "analysis_rows": rows,
        "final_score_sheet_markdown": md,
        "block_tables_markdown": block_md,
        "overall_score_table_markdown": overall_md,
        "level1_subtotals": l1_subs,
        "level2_subtotals": l2_subs,
        "total_score": total,
        "total_full_score": full,
        "overall_score_rate": (total / full) if full else 0.0,
        "content_text": md,
        "export_payload": payload,
        "export_filename": f"{project_name}项目绩效评价指标体系得分表",
        "status": "completed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"第七步已完成，项目得分 {total:.2f} / {full:.2f}，"
                    f"导出文件名：《{project_name}项目绩效评价指标体系得分表.docx》。"
                )
            )
        ],
    }


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    graph = StateGraph(Step7State, context_schema=Step7Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("expand_points", expand_points)
    graph.add_node("generate_analysis", generate_analysis)
    graph.add_node("review_analysis", review_analysis)
    graph.add_node("finalize_analysis", finalize_analysis)

    graph.add_edge(START, "validate_basis")
    graph.add_conditional_edges(
        "validate_basis",
        route_after_basis,
        {"continue": "expand_points", "end": END},
    )
    graph.add_edge("expand_points", "generate_analysis")
    graph.add_edge("generate_analysis", "review_analysis")
    graph.add_edge("review_analysis", "finalize_analysis")
    graph.add_edge("finalize_analysis", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step7")


graph = build_graph()
