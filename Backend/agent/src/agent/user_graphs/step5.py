"""Step 5 graph for EvalFlow Pro — 生成评分标准（4 档：优秀 / 良好 / 合格 / 不合格）。

继承 Step 4 的 ``scored_tree`` 结构，为每个三级指标产出四档评分标准：
``优秀 / 良好 / 合格 / 不合格``。状态字段：

- ``score_standards: list[dict]`` —— 结构化数据，每条形如
  ``{"id": "L3-…", "l1_name": …, "l2_name": …, "l3_name": …, "score": …,
   "rubric": {"优秀": "…", "良好": "…", "合格": "…", "不合格": "…"},
   "approved": bool, "model_name": "…"}``。
- ``final_rubrics_markdown`` —— 渲染后的中文 Markdown 正文。
- ``content_text`` —— 与 ``final_rubrics_markdown`` 一致，供工作流持久化层使用。

风格 ``generation_style`` 可选 ``中立 / 尖锐 / 委婉``，仅影响语气，不影响档位含义。
若大模型调用失败，节点会回退到规则模板，并将异常写入 ``state['error']``。
"""

from __future__ import annotations

import asyncio
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

ScoreStyle = Literal["中立", "尖锐", "委婉"]
ReviewMode = Literal["modify", "approve"]

RUBRIC_TIERS: tuple[str, ...] = ("优秀", "良好", "合格", "不合格")


class RubricTiers(TypedDict, total=False):
    优秀: str
    良好: str
    合格: str
    不合格: str


class ScoreStandard(TypedDict, total=False):
    id: str
    l1_name: str
    l2_name: str
    l3_name: str
    score: float
    rubric: RubricTiers
    approved: bool
    model_name: str


class RubricDraft(TypedDict, total=False):
    model_name: str
    label: str
    draft: str
    error: str


class Step5State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    scored_tree: list[L1ScoreRow]
    score_standards: list[ScoreStandard]

    generation_style: ScoreStyle
    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    manual_rubric_overrides: dict[str, dict[str, str]]

    model_comparisons: list[RubricDraft]
    draft_rubrics_markdown: str
    final_rubrics_markdown: str
    content_text: str
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
    model_configs: list[dict[str, Any]]
    compare_models: list[str]
    enable_multi_model: bool
    admin_prompt_content: str
    admin_kb_content: str
    output_dir: str


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _flatten_scored_tree(tree: list[L1ScoreRow]) -> list[ScoreStandard]:
    rows: list[ScoreStandard] = []
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
                        "rubric": {tier: "" for tier in RUBRIC_TIERS},
                        "approved": False,
                        "model_name": "",
                    }
                )
    return rows


def _style_tone(style: ScoreStyle) -> str:
    if style == "尖锐":
        return "语气务必直白严格，对扣分点要锐利点出；不回避问题。"
    if style == "委婉":
        return "语气以建设性、温和提示为主；指出问题时给出可改进路径。"
    return "语气中立、客观、专业，描述事实性证据与判定口径。"


def _fallback_rubric_for_row(row: ScoreStandard, style: ScoreStyle) -> RubricTiers:
    name = row.get("l3_name") or "本指标"
    score = float(row.get("score", 0) or 0)
    tone_hint = "（备注：当前为规则模板回退，建议重试模型调用）"
    if style == "尖锐":
        return {
            "优秀": f"{name} 完成度突出，证据齐全且远超基本要求，可给满分 {score:.2f} 分。{tone_hint}",
            "良好": f"{name} 完成度较好，存在个别瑕疵但不影响整体成效，可给 {score * 0.85:.2f} 分。{tone_hint}",
            "合格": f"{name} 基本达到要求，但存在明显改进空间，可给 {score * 0.6:.2f} 分。{tone_hint}",
            "不合格": f"{name} 未达到基本要求或证据严重不足，扣减至 {max(0.0, score * 0.3):.2f} 分及以下。{tone_hint}",
        }
    if style == "委婉":
        return {
            "优秀": f"{name} 整体表现优秀，建议给予满分 {score:.2f} 分。{tone_hint}",
            "良好": f"{name} 整体表现良好，建议给予 {score * 0.85:.2f} 分。{tone_hint}",
            "合格": f"{name} 基本达标，建议给予 {score * 0.6:.2f} 分，并提示进一步完善方向。{tone_hint}",
            "不合格": f"{name} 暂未达到要求，建议给予 {max(0.0, score * 0.3):.2f} 分，并制订改进计划。{tone_hint}",
        }
    return {
        "优秀": f"{name} 完成质量高、证据充分，可给满分 {score:.2f} 分。{tone_hint}",
        "良好": f"{name} 完成情况较好，可给 {score * 0.85:.2f} 分。{tone_hint}",
        "合格": f"{name} 基本符合要求，可给 {score * 0.6:.2f} 分。{tone_hint}",
        "不合格": f"{name} 未达到基本要求，可给 {max(0.0, score * 0.3):.2f} 分以下。{tone_hint}",
    }


def _normalize_rubric_tiers(raw: Any) -> RubricTiers:
    out: RubricTiers = {tier: "" for tier in RUBRIC_TIERS}
    if not isinstance(raw, dict):
        return out
    alias_map = {
        "优秀": ["优秀", "excellent", "A", "a"],
        "良好": ["良好", "good", "B", "b"],
        "合格": ["合格", "及格", "qualified", "pass", "C", "c"],
        "不合格": ["不合格", "不达标", "fail", "unqualified", "D", "d"],
    }
    lower_keys = {str(k).strip().lower(): v for k, v in raw.items() if isinstance(k, str)}
    for tier, aliases in alias_map.items():
        for alias in aliases:
            text = lower_keys.get(alias.lower()) if alias.lower() in lower_keys else raw.get(alias)
            if isinstance(text, str) and text.strip():
                out[tier] = text.strip()
                break
    return out


def _build_rubric_prompt(
    *,
    project_name: str,
    project_core_content: str,
    rows: list[ScoreStandard],
    style: ScoreStyle,
    admin_prompt: str,
    admin_kb: str,
    review_feedback: str = "",
    user_kb_context: str = "",
) -> str:
    preamble = build_admin_preamble(admin_prompt, admin_kb, user_kb_context)
    indicator_blob = "\n".join(
        f"- id={row['id']} | 一级={row['l1_name']} / 二级={row['l2_name']} / 三级={row['l3_name']} | 满分={row['score']:.2f}"
        for row in rows
    )
    feedback_block = (
        f"\n【人工反馈意见（请按此调整本次输出）】\n{review_feedback.strip()}\n"
        if review_feedback.strip()
        else ""
    )
    style_text = _style_tone(style)
    instructions = [
        "请为下列三级指标分别生成评分标准，必须覆盖四档：优秀 / 良好 / 合格 / 不合格。",
        "要求：",
        "1. 每档输出 1～3 句中文文字，写明判定条件、证据要求与扣分要点；",
        "2. 不允许出现 '同上' '略' 等占位说明；",
        "3. 各档之间界限清晰，不要语义重叠；",
        f"4. 风格控制：{style_text}",
        "",
        "输出格式（严格 JSON，不要任何额外文字）：",
        "{",
        '  "rubrics": [',
        '    {"id": "<对应输入的 id>", "rubric": {"优秀": "...", "良好": "...", "合格": "...", "不合格": "..."}}',
        "  ]",
        "}",
    ]
    return "\n".join(
        [
            preamble.strip(),
            f"项目名称：{project_name}",
            "项目核心内容：",
            (project_core_content or "（未提供，请仅围绕指标含义生成评分标准）").strip(),
            "",
            "待生成评分标准的三级指标列表：",
            indicator_blob or "（空）",
            feedback_block,
            "",
            *instructions,
        ]
    )


def _apply_llm_rubrics(
    rows: list[ScoreStandard],
    raw_text: str,
    model_name: str,
    style: ScoreStyle,
) -> tuple[int, int]:
    """Apply LLM rubric content into ``rows``. Returns (applied, total)."""

    parsed = parse_json_object(raw_text) or {}
    items = parsed.get("rubrics") if isinstance(parsed, dict) else None
    by_id: dict[str, RubricTiers] = {}
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            row_id = str(item.get("id") or "").strip()
            tiers = _normalize_rubric_tiers(item.get("rubric"))
            if row_id and any(tiers.values()):
                by_id[row_id] = tiers

    applied = 0
    for row in rows:
        tiers = by_id.get(str(row.get("id"))) or {}
        if all(tiers.get(tier) for tier in RUBRIC_TIERS):
            row["rubric"] = tiers
            row["model_name"] = model_name
            applied += 1
        else:
            row["rubric"] = _fallback_rubric_for_row(row, style)
            row["model_name"] = f"{model_name}+fallback"
    return applied, len(rows)


def _apply_manual_overrides(
    rows: list[ScoreStandard], manual: dict[str, dict[str, str]]
) -> int:
    if not manual:
        return 0
    touched = 0
    for row in rows:
        override = manual.get(str(row.get("id")))
        if not isinstance(override, dict):
            continue
        tiers = _normalize_rubric_tiers(override)
        existing: RubricTiers = dict(row.get("rubric") or {})  # type: ignore[assignment]
        changed = False
        for tier in RUBRIC_TIERS:
            text = tiers.get(tier)
            if text:
                existing[tier] = text
                changed = True
        if changed:
            row["rubric"] = existing
            row["approved"] = True
            touched += 1
    return touched


def _render_markdown(project_name: str, rows: list[ScoreStandard]) -> str:
    lines = [
        f"# 《{project_name} — 评分标准定稿》",
        "",
        f"- 生成时间：{now_iso()}",
        f"- 指标数：{len(rows)}",
        "",
        "## 评分标准明细",
    ]
    current_l1: str | None = None
    current_l2: str | None = None
    for row in rows:
        if row.get("l1_name") != current_l1:
            current_l1 = str(row.get("l1_name") or "")
            lines.append(f"### 一级：{current_l1}")
            current_l2 = None
        if row.get("l2_name") != current_l2:
            current_l2 = str(row.get("l2_name") or "")
            lines.append(f"- **二级：{current_l2}**")
        rubric = row.get("rubric") or {}
        status = "已确认" if row.get("approved") else "待确认"
        lines.append(
            f"  - 三级：{row.get('l3_name')} ｜ 满分：{row.get('score', 0):.2f} ｜ 状态：{status}"
        )
        for tier in RUBRIC_TIERS:
            text = (rubric.get(tier) or "").strip() or "（待补充）"
            lines.append(f"    - **{tier}**：{text}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------


def validate_step4_basis(state: Step5State) -> Step5State:
    tree = list(state.get("scored_tree") or [])
    if not tree:
        return {
            "status": "failed",
            "error": "缺少第四步定稿分值结构：请传入 scored_tree 后再生成评分标准。",
            "messages": [
                AIMessage(content="第五步需基于第四步已确认的 scored_tree 生成评分标准。")
            ],
            "updated_at": now_iso(),
        }
    name = (state.get("project_name") or "未命名项目").strip() or "未命名项目"
    rows = state.get("score_standards") or _flatten_scored_tree(tree)
    return {
        "project_name": name,
        "score_standards": rows,
        "created_at": state.get("created_at") or now_iso(),
        "updated_at": now_iso(),
        "status": "basis_ok",
        "messages": [
            AIMessage(content=f"已接收第四步分值结构，项目：{name}。开始逐项生成评分标准。")
        ],
    }


def route_after_basis(state: Step5State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


def generate_rubrics(state: Step5State, runtime: Any = None) -> Step5State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    rows: list[ScoreStandard] = json.loads(json.dumps(state.get("score_standards") or []))
    if not rows:
        return {
            "status": "failed",
            "error": "score_standards 为空，无法生成评分标准。",
            "updated_at": now_iso(),
            "messages": [AIMessage(content="未发现可生成评分标准的三级指标。")],
        }

    style: ScoreStyle = state.get("generation_style") or "中立"
    project_name = state.get("project_name", "未命名项目")
    project_core = str(state.get("project_core_content") or "")
    admin_prompt = read_admin_prompt(context, dict(state))
    admin_kb = read_admin_kb(context, dict(state))
    review_feedback = (state.get("review_feedback") or "").strip()

    from ._llm import fetch_user_kb_context_sync
    user_kb_context = fetch_user_kb_context_sync(
        project_id=str(context.get("project_id") or ""),
        query=f"{project_name} 评分标准 指标体系",
        step_code="step5",
    )

    prompt = _build_rubric_prompt(
        project_name=project_name,
        project_core_content=project_core,
        rows=rows,
        style=style,
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
    comparisons: list[RubricDraft] = []
    chosen_model = ""

    try:
        drafts = await_in_sync(
            generate_drafts_async(
                prompt=prompt,
                system_prompt=admin_prompt or "你是绩效评价评分标准编制专家，输出严格符合 JSON 格式。",
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
        _apply_llm_rubrics(rows, winner.get("draft", ""), chosen_model, style)
    except Exception as exc:  # noqa: BLE001
        error_message = f"模型调用失败，已回退到规则模板：{exc}"
        for row in rows:
            row["rubric"] = _fallback_rubric_for_row(row, style)
            row["model_name"] = "fallback"

    overrides = state.get("manual_rubric_overrides") or {}
    if isinstance(overrides, dict) and overrides:
        _apply_manual_overrides(rows, overrides)

    md = _render_markdown(project_name, rows)
    return {
        "score_standards": rows,
        "model_comparisons": comparisons,
        "draft_rubrics_markdown": md,
        "status": "rubrics_generated" if not error_message else "rubrics_generated_with_fallback",
        "error": error_message,
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已为 {len(rows)} 个三级指标生成 4 档评分标准"
                    + (f"（采用模型：{chosen_model}）" if chosen_model else "")
                    + ("，已回退到规则模板。" if error_message else "，可逐项核对或修改。")
                )
            )
        ],
    }


def review_rubrics(state: Step5State) -> Step5State:
    feedback = (state.get("review_feedback") or "").strip()
    round_no = int(state.get("review_round", 0)) + 1
    return {
        "review_round": round_no,
        "status": "reviewed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=f"已记录第 {round_no} 轮评分标准修改意见：{feedback or '（无具体内容）'}"
            )
        ],
    }


def finalize_rubrics(state: Step5State) -> Step5State:
    rows: list[ScoreStandard] = json.loads(json.dumps(state.get("score_standards") or []))
    project_name = state.get("project_name", "未命名项目")
    if not rows:
        return {
            "status": "blocked",
            "error": "没有可定稿的评分标准。",
            "messages": [AIMessage(content="请先生成评分标准草稿后再定稿。")],
            "updated_at": now_iso(),
        }
    for row in rows:
        row["approved"] = True
    md = _render_markdown(project_name, rows)
    payload = (
        md
        + "\n\n## 机器可读快照（JSON）\n```json\n"
        + json.dumps(rows, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    return {
        "score_standards": rows,
        "final_rubrics_markdown": md,
        "content_text": md,
        "export_payload": payload,
        "export_filename": f"{project_name}评分标准_定稿",
        "status": "completed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content="评分标准已定稿，可用于第七步指标分析与得分计算。")
        ],
    }


# ---------------------------------------------------------------------------
# async helper
# ---------------------------------------------------------------------------


def await_in_sync(coro: Any) -> Any:
    """Run an awaitable from inside a sync node.

    LangGraph still runs node functions synchronously by default; this is a
    thin wrapper around ``asyncio.run`` that also tolerates being called from
    inside an existing event loop (e.g. ``langgraph dev``).
    """

    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, loop).result()
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


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

    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step5")


graph = build_graph()
