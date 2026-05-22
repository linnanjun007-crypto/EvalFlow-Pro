"""Step 9 graph for EvalFlow Pro — 提炼问题及原因分析.

承接 Step 7 的得分表与分析（``analysis_rows`` / ``final_score_sheet_markdown``），
聚焦扣分点输出结构化的问题清单，每条包含问题描述、根本原因、证据来源与严重程度。

状态字段
~~~~~~~~

- ``problem_items: list[ProblemItem]`` —— 结构化条目；
- ``problem_draft_markdown`` —— 草稿正文；
- ``final_problem_markdown`` —— 定稿正文；
- ``content_text`` —— 与定稿一致，供工作流持久化使用。

风格 ``style_mode`` 可选 ``中立 / 尖锐 / 委婉``，仅影响语气，不改变问题判定标准。
LLM 调用失败时回退到规则模板，``model_name`` 追加 ``+fallback`` 后缀。
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

StyleMode = Literal["中立", "尖锐", "委婉"]
ReviewMode = Literal["modify", "approve"]
Severity = Literal["高", "中", "低"]


class ProblemItem(TypedDict, total=False):
    id: str
    title: str
    category: str
    description: str
    root_cause: str
    evidence: str
    severity: Severity
    indicator_name: str
    model_name: str


class ProblemDraft(TypedDict, total=False):
    model_name: str
    label: str
    draft: str
    error: str


class Step9State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    analysis_rows: list[dict[str, Any]]
    analysis_draft_markdown: str
    final_score_sheet_markdown: str
    final_experience_markdown: str
    field_evidence: str

    style_mode: StyleMode
    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    model_comparisons: list[ProblemDraft]

    problem_items: list[ProblemItem]
    problem_draft_markdown: str
    final_problem_markdown: str
    content_text: str
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
    model_configs: list[dict[str, Any]]
    compare_models: list[str]
    enable_multi_model: bool
    admin_prompt_content: str
    admin_kb_content: str
    output_dir: str


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _style_tone(style: StyleMode) -> str:
    if style == "尖锐":
        return "语气务必直白严格，对问题与责任要锐利点出，避免回避；可使用「严重不足」「明显滞后」等措辞。"
    if style == "委婉":
        return "语气以建设性、温和提示为主，问题陈述客观但留有改进空间；多使用「有待加强」「尚需完善」等措辞。"
    return "语气中立、客观、专业，描述事实性证据与判定依据，不带感情色彩。"


def _summarize_low_score(rows: list[dict[str, Any]], max_rows: int = 12) -> str:
    if not rows:
        return "（暂无第七步分析结果，请基于项目核心内容审慎归纳。）"
    sorted_rows = sorted(
        rows,
        key=lambda r: float(r.get("score_rate", 1) or 1),
    )
    head = sorted_rows[:max_rows]
    lines: list[str] = []
    for row in head:
        rate = float(row.get("score_rate", 0) or 0)
        deduction = str(row.get("deduction_reason") or "").strip() or "（未提供）"
        lines.append(
            f"- {row.get('l1_name', '')} / {row.get('l2_name', '')} / {row.get('l3_name', '')}"
            f" ｜ 得分率 {rate:.2%} ｜ 扣分原因：{deduction}"
            f" ｜ 分析：{row.get('analysis', '')}"
        )
    if len(rows) > max_rows:
        lines.append(f"…（共 {len(rows)} 项，仅展示得分率最低的前 {max_rows} 项）")
    return "\n".join(lines)


def _build_problem_prompt(
    *,
    project_name: str,
    project_core_content: str,
    low_score_summary: str,
    field_evidence: str,
    score_sheet: str,
    style: StyleMode,
    admin_prompt: str,
    admin_kb: str,
    review_feedback: str = "",
) -> str:
    preamble = build_admin_preamble(admin_prompt, admin_kb)
    feedback_block = (
        f"\n【人工反馈意见（请按此调整本次输出）】\n{review_feedback.strip()}\n"
        if review_feedback.strip()
        else ""
    )
    style_text = _style_tone(style)
    instructions = [
        "请基于以上素材提炼 3 ~ 6 条问题及其原因，覆盖管理机制、过程执行、资源保障、成效转化等维度。",
        "要求：",
        "1. 每条问题须包含：title（短句标题，<=20字）、category（机制建设/过程管控/资源保障/成效转化/其他）、",
        "   description（问题表现，2~3 句）、root_cause（根本原因，1~2 句）、evidence（依据，引用具体指标或材料）、",
        "   severity（严重程度：高/中/低）；",
        "2. 严禁出现 '同上' '略' 等占位说明；",
        "3. 必须与第七步扣分原因相呼应，不允许凭空捏造未出现的扣分项；",
        f"4. 风格控制：{style_text}",
        "5. 仅输出 JSON，不要任何额外文字。",
        "",
        "输出格式（严格 JSON）：",
        "{",
        '  "items": [',
        '    {"id": "P1", "title": "…", "category": "过程管控", "description": "…",',
        '     "root_cause": "…", "evidence": "…", "severity": "中"}',
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
            "第七步低得分指标摘要（按得分率升序）：",
            low_score_summary,
            "",
            "现场评价证据：",
            (field_evidence or "（未提供）").strip(),
            "",
            "第七步定稿得分表（节选）：",
            (score_sheet or "（未提供）").strip(),
            feedback_block,
            "",
            *instructions,
        ]
    )


def _fallback_items(style: StyleMode) -> list[ProblemItem]:
    base_descriptions = {
        "中立": (
            "部分指标得分率偏低，反映出过程管控与证据留痕存在不足。",
            "工作分工与资料归档机制不够健全，导致部分关键节点缺乏可追溯证据。",
        ),
        "尖锐": (
            "多个指标得分率严重偏低，过程管控明显失位，证据链严重缺失。",
            "责任边界不清、资料留痕松散，关键节点缺乏强约束，已影响整体评价结果。",
        ),
        "委婉": (
            "部分指标得分率有待提升，过程管控与资料留痕仍有进一步完善空间。",
            "建议进一步明确分工与资料归档要求，逐步健全可追溯机制。",
        ),
    }
    desc, cause = base_descriptions.get(style, base_descriptions["中立"])
    return [
        {
            "id": "P1",
            "title": "过程管控不到位",
            "category": "过程管控",
            "description": desc,
            "root_cause": cause,
            "evidence": "源自第七步低得分率指标及扣分原因。",
            "severity": "中",
            "indicator_name": "（综合）",
            "model_name": "fallback",
        },
        {
            "id": "P2",
            "title": "资源保障覆盖不全",
            "category": "资源保障",
            "description": "项目在资金、人员或技术资源调配上仍存在缺口，影响个别任务推进。",
            "root_cause": "资源统筹机制尚未完全适配项目实际需求。",
            "evidence": "源自得分率较低的资源保障类指标。",
            "severity": "中",
            "indicator_name": "（综合）",
            "model_name": "fallback",
        },
        {
            "id": "P3",
            "title": "成效转化链路不畅",
            "category": "成效转化",
            "description": "项目成果对外服务或受益面有待拓展，部分预期成效尚未充分显现。",
            "root_cause": "成果转化机制与反馈渠道尚未打通。",
            "evidence": "源自得分率较低的成效转化类指标。",
            "severity": "中",
            "indicator_name": "（综合）",
            "model_name": "fallback",
        },
    ]


def _normalize_severity(value: Any) -> Severity:
    text = str(value or "").strip()
    if text in ("高", "中", "低"):
        return text  # type: ignore[return-value]
    lowered = text.lower()
    if lowered in ("high", "h"):
        return "高"
    if lowered in ("low", "l"):
        return "低"
    return "中"


def _apply_llm_problems(raw_text: str, model_name: str, style: StyleMode) -> list[ProblemItem]:
    parsed = parse_json_object(raw_text) or {}
    items_raw = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items_raw, list):
        return _fallback_items(style)
    out: list[ProblemItem] = []
    counter = 1
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        if not title or not description:
            continue
        out.append(
            {
                "id": str(item.get("id") or f"P{counter}"),
                "title": title,
                "category": str(item.get("category") or "其他").strip() or "其他",
                "description": description,
                "root_cause": str(item.get("root_cause") or "").strip() or "（待补充）",
                "evidence": str(item.get("evidence") or "").strip() or "（来源依据待补充）",
                "severity": _normalize_severity(item.get("severity")),
                "indicator_name": str(item.get("indicator_name") or "").strip() or "（综合）",
                "model_name": model_name,
            }
        )
        counter += 1
    return out or _fallback_items(style)


def _render_problems(project_name: str, items: list[ProblemItem], style: StyleMode) -> str:
    lines = [
        f"# 《{project_name} — 问题及原因分析》",
        "",
        f"- 生成时间：{now_iso()}",
        f"- 风格模式：{style}",
        f"- 问题条目数：{len(items)}",
        "",
        "## 问题明细",
    ]
    for idx, item in enumerate(items, 1):
        lines.extend(
            [
                "",
                f"### {idx}. {item.get('title')}",
                f"- **类别**：{item.get('category')}",
                f"- **严重程度**：{item.get('severity')}",
                f"- **问题表现**：{item.get('description')}",
                f"- **根本原因**：{item.get('root_cause')}",
                f"- **依据**：{item.get('evidence')}",
            ]
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------


def validate_basis(state: Step9State) -> Step9State:
    if (
        not state.get("analysis_rows")
        and not state.get("analysis_draft_markdown")
        and not state.get("final_score_sheet_markdown")
        and not state.get("project_core_content")
    ):
        return {
            "status": "failed",
            "error": "缺少前置素材：请提供第七步分析结果或项目核心内容。",
            "messages": [AIMessage(content="第九步至少需要第七步成果或项目核心内容。")],
            "updated_at": now_iso(),
        }
    name = (state.get("project_name") or "未命名项目").strip() or "未命名项目"
    return {
        "project_name": name,
        "created_at": state.get("created_at") or now_iso(),
        "updated_at": now_iso(),
        "status": "basis_ok",
        "messages": [AIMessage(content=f"已接收扣分信息与项目核心内容，项目：{name}。")],
    }


def route_after_basis(state: Step9State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


def generate_problems(state: Step9State, runtime: Any = None) -> Step9State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    project_name = state.get("project_name", "未命名项目")
    project_core = str(state.get("project_core_content") or "")
    analysis_rows = list(state.get("analysis_rows") or [])
    low_score_summary = _summarize_low_score(analysis_rows)
    score_sheet = str(
        state.get("final_score_sheet_markdown")
        or state.get("analysis_draft_markdown")
        or ""
    )
    field_evidence = str(state.get("field_evidence") or "")
    style: StyleMode = state.get("style_mode") or "中立"
    admin_prompt = read_admin_prompt(context, dict(state))
    admin_kb = read_admin_kb(context, dict(state))
    review_feedback = (state.get("review_feedback") or "").strip()

    prompt = _build_problem_prompt(
        project_name=project_name,
        project_core_content=project_core,
        low_score_summary=low_score_summary,
        field_evidence=field_evidence,
        score_sheet=score_sheet,
        style=style,
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
    comparisons: list[ProblemDraft] = []
    items: list[ProblemItem]
    chosen_model = ""

    try:
        drafts = await_in_sync(
            generate_drafts_async(
                prompt=prompt,
                system_prompt=admin_prompt
                or "你是绩效评价问题诊断专家，输出严格符合 JSON 格式。",
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
        items = _apply_llm_problems(winner.get("draft", ""), chosen_model, style)
    except Exception as exc:  # noqa: BLE001
        error_message = f"模型调用失败，已回退到规则模板：{exc}"
        items = _fallback_items(style)

    md = _render_problems(project_name, items, style)
    return {
        "problem_items": items,
        "problem_draft_markdown": md,
        "model_comparisons": comparisons,
        "status": "problem_ready" if not error_message else "problem_ready_with_fallback",
        "error": error_message,
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已提炼 {len(items)} 条问题及原因分析（风格：{style}）"
                    + (f"（采用模型：{chosen_model}）" if chosen_model else "")
                    + ("，已回退到规则模板。" if error_message else "，可逐条修订。")
                )
            )
        ],
    }


def review_problems(state: Step9State) -> Step9State:
    rnd = int(state.get("review_round", 0)) + 1
    fb = (state.get("review_feedback") or "").strip()
    return {
        "review_round": rnd,
        "status": "problem_reviewed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"已记录第 {rnd} 轮问题修改意见：{fb or '（无具体内容）'}")
        ],
    }


def finalize_problems(state: Step9State) -> Step9State:
    project_name = state.get("project_name", "未命名项目")
    style: StyleMode = state.get("style_mode") or "中立"
    items: list[ProblemItem] = json.loads(json.dumps(state.get("problem_items") or []))
    if not items:
        return {
            "status": "blocked",
            "error": "没有可定稿的问题分析。",
            "messages": [AIMessage(content="请先生成问题分析草稿后再定稿。")],
            "updated_at": now_iso(),
        }
    md = _render_problems(project_name, items, style)
    payload = (
        md
        + "\n\n## 机器可读快照（JSON）\n```json\n"
        + json.dumps(items, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    return {
        "problem_items": items,
        "final_problem_markdown": md,
        "content_text": md,
        "export_payload": payload,
        "export_filename": f"{project_name}问题及原因分析_定稿",
        "status": "completed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"第九步已完成，已固化 {len(items)} 条问题分析。")
        ],
    }


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    graph = StateGraph(Step9State, context_schema=Step9Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_problems", generate_problems)
    graph.add_node("review_problems", review_problems)
    graph.add_node("finalize_problems", finalize_problems)

    graph.add_edge(START, "validate_basis")
    graph.add_conditional_edges(
        "validate_basis",
        route_after_basis,
        {"continue": "generate_problems", "end": END},
    )
    graph.add_edge("generate_problems", "review_problems")
    graph.add_edge("review_problems", "finalize_problems")
    graph.add_edge("finalize_problems", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step9")


graph = build_graph()
