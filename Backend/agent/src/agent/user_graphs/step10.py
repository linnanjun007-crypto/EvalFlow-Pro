"""Step 10 graph for EvalFlow Pro — 提炼整改建议.

承接 Step 9 问题及原因分析（``problem_items`` / ``final_problem_markdown``），
逐条生成可落地的整改建议，每条覆盖目标、责任主体、关键举措与时序。

状态字段
~~~~~~~~

- ``suggestion_items: list[SuggestionItem]`` —— 结构化条目；
- ``suggestion_draft_markdown`` —— 草稿正文；
- ``final_suggestion_markdown`` —— 定稿正文；
- ``content_text`` —— 与定稿一致，供工作流持久化使用。

风格 ``style_mode`` 可选 ``中立 / 尖锐 / 委婉``，仅影响语气，不影响建议判定。
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
Priority = Literal["高", "中", "低"]


class SuggestionItem(TypedDict, total=False):
    id: str
    title: str
    related_problem_id: str
    related_problem_title: str
    objective: str
    actions: list[str]
    responsible: str
    timeline: str
    priority: Priority
    expected_outcome: str
    model_name: str


class SuggestionDraft(TypedDict, total=False):
    model_name: str
    label: str
    draft: str
    error: str


class Step10State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    problem_items: list[dict[str, Any]]
    final_problem_markdown: str
    problem_draft_markdown: str
    final_score_sheet_markdown: str

    style_mode: StyleMode
    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    model_comparisons: list[SuggestionDraft]

    suggestion_items: list[SuggestionItem]
    suggestion_draft_markdown: str
    final_suggestion_markdown: str
    content_text: str
    export_filename: str
    export_payload: str

    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step10Context(TypedDict, total=False):
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
        return "语气务必直白严格，建议要硬性指出整改责任与刚性时限；可使用「立即」「严格」「必须」等措辞。"
    if style == "委婉":
        return "语气以建设性、温和提示为主，建议陈述兼顾可行性和阶段性；多使用「建议」「逐步」「鼓励」等措辞。"
    return "语气中立、客观、专业，强调可操作性与可考核性，避免感情色彩。"


def _summarize_problems(items: list[dict[str, Any]], max_items: int = 12) -> str:
    if not items:
        return "（暂未提供结构化问题清单，请基于第九步定稿正文人工归纳。）"
    severity_rank = {"高": 0, "中": 1, "低": 2}
    sorted_items = sorted(
        items,
        key=lambda p: severity_rank.get(str(p.get("severity", "中")), 1),
    )
    head = sorted_items[:max_items]
    lines: list[str] = []
    for p in head:
        lines.append(
            f"- id={p.get('id', '')} ｜ 严重程度：{p.get('severity', '中')} ｜"
            f" 类别：{p.get('category', '其他')} ｜ 标题：{p.get('title', '')}\n"
            f"    问题表现：{p.get('description', '')}\n"
            f"    根本原因：{p.get('root_cause', '')}"
        )
    if len(items) > max_items:
        lines.append(f"…（共 {len(items)} 条问题，仅展示严重程度最高的前 {max_items} 条）")
    return "\n".join(lines)


def _build_suggestion_prompt(
    *,
    project_name: str,
    project_core_content: str,
    problem_summary: str,
    problem_markdown: str,
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
        "请基于以上问题清单提炼整改建议：",
        "1. 原则上每条问题对应 1 条建议，可视情况合并强相关问题，但合并须在 related_problem_id 中列举；",
        "2. 每条建议须包含：title（短句标题，<=20字）、related_problem_id（关联问题 id，多条用逗号分隔）、",
        "   objective（整改目标，1 句）、actions（关键举措列表，3~5 条短句）、responsible（责任主体）、",
        "   timeline（建议时限，如「3 个月内」）、priority（高/中/低）、expected_outcome（预期成效，1~2 句）；",
        "3. 严禁出现 '同上' '略' 等占位说明，严禁脱离问题清单凭空生成；",
        f"4. 风格控制：{style_text}",
        "5. 仅输出 JSON，不要任何额外文字。",
        "",
        "输出格式（严格 JSON）：",
        "{",
        '  "items": [',
        '    {"id": "S1", "title": "…", "related_problem_id": "P1",',
        '     "objective": "…", "actions": ["…","…"], "responsible": "…",',
        '     "timeline": "3 个月内", "priority": "高", "expected_outcome": "…"}',
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
            "第九步问题清单（结构化摘要）：",
            problem_summary,
            "",
            "第九步定稿正文（节选）：",
            (problem_markdown or "（未提供）").strip(),
            feedback_block,
            "",
            *instructions,
        ]
    )


def _normalize_priority(value: Any) -> Priority:
    text = str(value or "").strip()
    if text in ("高", "中", "低"):
        return text  # type: ignore[return-value]
    lowered = text.lower()
    if lowered in ("high", "h"):
        return "高"
    if lowered in ("low", "l"):
        return "低"
    return "中"


def _normalize_actions(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        return [line.strip() for line in raw.splitlines() if line.strip()]
    return []


def _fallback_items(problems: list[dict[str, Any]], style: StyleMode) -> list[SuggestionItem]:
    if not problems:
        return [
            {
                "id": "S1",
                "title": "完善整改工作机制",
                "related_problem_id": "（综合）",
                "related_problem_title": "（综合）",
                "objective": "建立常态化整改工作机制，确保问题闭环管理。",
                "actions": [
                    "明确整改责任部门与牵头领导。",
                    "建立问题清单与整改台账。",
                    "定期开展整改进展督查。",
                ],
                "responsible": "项目主管部门",
                "timeline": "3 个月内",
                "priority": "中",
                "expected_outcome": "实现问题清单化、整改可追溯，避免反复发生。",
                "model_name": "fallback",
            }
        ]
    items: list[SuggestionItem] = []
    for idx, p in enumerate(problems[:6], 1):
        title = str(p.get("title") or f"问题 {idx}")[:20]
        items.append(
            {
                "id": f"S{idx}",
                "title": f"针对「{title}」的整改建议",
                "related_problem_id": str(p.get("id") or ""),
                "related_problem_title": title,
                "objective": "推动问题闭环整改，提升相关指标得分率。",
                "actions": [
                    "明确责任部门与配合单位。",
                    "完善证据资料与工作台账。",
                    "建立阶段性复核机制。",
                ],
                "responsible": "项目主管部门",
                "timeline": "3 个月内",
                "priority": _normalize_priority(p.get("severity")),
                "expected_outcome": "整改到位后该项指标得分率明显提升。",
                "model_name": "fallback",
            }
        )
    return items


def _apply_llm_suggestions(
    raw_text: str,
    model_name: str,
    problems: list[dict[str, Any]],
    style: StyleMode,
) -> list[SuggestionItem]:
    parsed = parse_json_object(raw_text) or {}
    items_raw = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items_raw, list):
        return _fallback_items(problems, style)

    title_index: dict[str, str] = {
        str(p.get("id") or ""): str(p.get("title") or "")
        for p in problems
        if p.get("id")
    }

    out: list[SuggestionItem] = []
    counter = 1
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        objective = str(item.get("objective") or "").strip()
        actions = _normalize_actions(item.get("actions"))
        if not title or not objective or not actions:
            continue
        related_id = str(item.get("related_problem_id") or "").strip()
        related_title = str(item.get("related_problem_title") or "").strip()
        if not related_title and related_id:
            primary_id = related_id.split(",")[0].strip()
            related_title = title_index.get(primary_id, "")
        out.append(
            {
                "id": str(item.get("id") or f"S{counter}"),
                "title": title,
                "related_problem_id": related_id or "（综合）",
                "related_problem_title": related_title or "（综合）",
                "objective": objective,
                "actions": actions,
                "responsible": str(item.get("responsible") or "").strip() or "项目主管部门",
                "timeline": str(item.get("timeline") or "").strip() or "3 个月内",
                "priority": _normalize_priority(item.get("priority")),
                "expected_outcome": str(item.get("expected_outcome") or "").strip()
                or "整改到位后预期成效将明显提升。",
                "model_name": model_name,
            }
        )
        counter += 1
    return out or _fallback_items(problems, style)


def _render_suggestions(project_name: str, items: list[SuggestionItem], style: StyleMode) -> str:
    lines = [
        f"# 《{project_name} — 整改建议》",
        "",
        f"- 生成时间：{now_iso()}",
        f"- 风格模式：{style}",
        f"- 建议条目数：{len(items)}",
        "",
        "## 建议明细",
    ]
    for idx, item in enumerate(items, 1):
        actions = item.get("actions") or []
        actions_md = "\n".join(f"    - {a}" for a in actions) or "    - （待补充）"
        lines.extend(
            [
                "",
                f"### {idx}. {item.get('title')}",
                f"- **关联问题**：{item.get('related_problem_id')}（{item.get('related_problem_title')}）",
                f"- **优先级**：{item.get('priority')}",
                f"- **整改目标**：{item.get('objective')}",
                f"- **责任主体**：{item.get('responsible')}",
                f"- **时限**：{item.get('timeline')}",
                "- **关键举措**：",
                actions_md,
                f"- **预期成效**：{item.get('expected_outcome')}",
            ]
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------


def validate_basis(state: Step10State) -> Step10State:
    if (
        not state.get("problem_items")
        and not state.get("final_problem_markdown")
        and not state.get("problem_draft_markdown")
    ):
        return {
            "status": "failed",
            "error": "缺少第九步成果：请先传入 problem_items 或问题分析正文。",
            "messages": [AIMessage(content="第十步必须基于第九步问题及原因分析生成建议。")],
            "updated_at": now_iso(),
        }
    name = (state.get("project_name") or "未命名项目").strip() or "未命名项目"
    return {
        "project_name": name,
        "created_at": state.get("created_at") or now_iso(),
        "updated_at": now_iso(),
        "status": "basis_ok",
        "messages": [AIMessage(content=f"已接收问题分析，开始生成整改建议，项目：{name}。")],
    }


def route_after_basis(state: Step10State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


def generate_suggestions(state: Step10State, runtime: Any = None) -> Step10State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    project_name = state.get("project_name", "未命名项目")
    project_core = str(state.get("project_core_content") or "")
    problems = list(state.get("problem_items") or [])
    problem_summary = _summarize_problems(problems)
    problem_markdown = str(
        state.get("final_problem_markdown") or state.get("problem_draft_markdown") or ""
    )
    style: StyleMode = state.get("style_mode") or "中立"
    admin_prompt = read_admin_prompt(context, dict(state))
    admin_kb = read_admin_kb(context, dict(state))
    review_feedback = (state.get("review_feedback") or "").strip()

    prompt = _build_suggestion_prompt(
        project_name=project_name,
        project_core_content=project_core,
        problem_summary=problem_summary,
        problem_markdown=problem_markdown,
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
    comparisons: list[SuggestionDraft] = []
    items: list[SuggestionItem]
    chosen_model = ""

    try:
        drafts = await_in_sync(
            generate_drafts_async(
                prompt=prompt,
                system_prompt=admin_prompt
                or "你是绩效评价整改建议专家，输出严格符合 JSON 格式。",
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
        items = _apply_llm_suggestions(winner.get("draft", ""), chosen_model, problems, style)
    except Exception as exc:  # noqa: BLE001
        error_message = f"模型调用失败，已回退到规则模板：{exc}"
        items = _fallback_items(problems, style)

    md = _render_suggestions(project_name, items, style)
    return {
        "suggestion_items": items,
        "suggestion_draft_markdown": md,
        "model_comparisons": comparisons,
        "status": "suggestion_ready" if not error_message else "suggestion_ready_with_fallback",
        "error": error_message,
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已生成 {len(items)} 条整改建议（风格：{style}）"
                    + (f"（采用模型：{chosen_model}）" if chosen_model else "")
                    + ("，已回退到规则模板。" if error_message else "，可逐条修订。")
                )
            )
        ],
    }


def review_suggestions(state: Step10State) -> Step10State:
    rnd = int(state.get("review_round", 0)) + 1
    fb = (state.get("review_feedback") or "").strip()
    return {
        "review_round": rnd,
        "status": "suggestion_reviewed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"已记录第 {rnd} 轮建议修改意见：{fb or '（无具体内容）'}")
        ],
    }


def finalize_suggestions(state: Step10State) -> Step10State:
    project_name = state.get("project_name", "未命名项目")
    style: StyleMode = state.get("style_mode") or "中立"
    items: list[SuggestionItem] = json.loads(json.dumps(state.get("suggestion_items") or []))
    if not items:
        return {
            "status": "blocked",
            "error": "没有可定稿的整改建议。",
            "messages": [AIMessage(content="请先生成建议草稿后再定稿。")],
            "updated_at": now_iso(),
        }
    md = _render_suggestions(project_name, items, style)
    payload = (
        md
        + "\n\n## 机器可读快照（JSON）\n```json\n"
        + json.dumps(items, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    return {
        "suggestion_items": items,
        "final_suggestion_markdown": md,
        "content_text": md,
        "export_payload": payload,
        "export_filename": f"{project_name}整改建议_定稿",
        "status": "completed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"第十步已完成，已固化 {len(items)} 条整改建议。")
        ],
    }


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    graph = StateGraph(Step10State, context_schema=Step10Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_suggestions", generate_suggestions)
    graph.add_node("review_suggestions", review_suggestions)
    graph.add_node("finalize_suggestions", finalize_suggestions)

    graph.add_edge(START, "validate_basis")
    graph.add_conditional_edges(
        "validate_basis",
        route_after_basis,
        {"continue": "generate_suggestions", "end": END},
    )
    graph.add_edge("generate_suggestions", "review_suggestions")
    graph.add_edge("review_suggestions", "finalize_suggestions")
    graph.add_edge("finalize_suggestions", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step10")


graph = build_graph()
