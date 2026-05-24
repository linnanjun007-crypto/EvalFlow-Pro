"""Step 6 graph for EvalFlow Pro — 绩效评价指标体系 + 里克特量表问卷.

继承 Step 4 的 ``scored_tree`` 与 Step 5 的 ``score_standards``，输出可视化的
绩效评价指标体系 Markdown 表，并在 ``questionnaire_decision == 'need'`` 时调用
大模型生成里克特 5 级问卷草稿。

状态字段
~~~~~~~~

- ``final_indicator_framework_markdown`` —— 渲染后的指标体系正文。
- ``questionnaire_items: list[QuestionnaireItem]`` —— 结构化问卷条目。
- ``questionnaire_draft: str`` —— 问卷 Markdown 草稿。
- ``content_text`` —— 与正文一致，供工作流持久化使用。

里克特量表固定 5 级：``非常不满意 / 不满意 / 一般 / 满意 / 非常满意``。
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

QuestionnaireDecision = Literal["need", "skip"]
ReviewMode = Literal["modify", "approve"]

LIKERT_OPTIONS: tuple[str, ...] = ("非常不满意", "不满意", "一般", "满意", "非常满意")


class QuestionnaireItem(TypedDict, total=False):
    id: str
    indicator_id: str
    indicator_name: str
    question: str
    options: list[str]
    source_note: str
    model_name: str


class FrameworkDraft(TypedDict, total=False):
    model_name: str
    label: str
    draft: str
    error: str


class Step6State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    scored_tree: list[L1ScoreRow]
    score_standards: list[ScoreStandard]

    questionnaire_decision: QuestionnaireDecision
    questionnaire_items: list[QuestionnaireItem]
    questionnaire_draft: str

    review_mode: ReviewMode
    review_round: int
    review_feedback: str

    model_comparisons: list[FrameworkDraft]
    final_indicator_framework_markdown: str
    content_text: str
    export_filename: str
    export_payload: str

    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step6Context(TypedDict, total=False):
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


def _flatten_framework(
    tree: list[L1ScoreRow], standards: list[ScoreStandard]
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
                        "l1": str(l1.get("name", "")),
                        "l2": str(l2.get("name", "")),
                        "l3": str(l3.get("name", "")),
                        "score": float(l3.get("score", 0)),
                        "tag": str(l3.get("tag", "其他")),
                        "rubric": dict(rubric),
                    }
                )
    return rows


def _render_framework(
    project_name: str,
    tree: list[L1ScoreRow],
    standards: list[ScoreStandard],
) -> str:
    rubric_index: dict[str, ScoreStandard] = {
        str(s.get("id", "")): s for s in standards if s.get("id")
    }
    lines = [
        f"# 《{project_name} — 绩效评价指标体系》",
        "",
        f"- 生成时间：{now_iso()}",
        "",
        "## 指标体系表",
    ]
    for l1 in tree:
        lines.append(
            f"### 一级：{l1.get('name')} ｜ 分值：{float(l1.get('score', 0)):.2f}"
        )
        for l2 in l1.get("level2", []) or []:
            lines.append(
                f"- 二级：{l2.get('name')} ｜ 分值：{float(l2.get('score', 0)):.2f}"
            )
            for l3 in l2.get("level3", []) or []:
                row_id = str(l3.get("id", ""))
                rubric = rubric_index.get(row_id, {}).get("rubric") or {}
                lines.append(
                    f"  - 三级：{l3.get('name')} ｜ 分值：{float(l3.get('score', 0)):.2f} ｜ "
                    f"指标维度：{l3.get('tag', '其他')}"
                )
                if rubric:
                    for tier in ("优秀", "良好", "合格", "不合格"):
                        text = (rubric.get(tier) or "").strip() or "（待补充）"
                        lines.append(f"    - **{tier}**：{text}")
                else:
                    lines.append("    - 评分标准：（暂未生成，请回到第五步补全）")
    return "\n".join(lines)


def _build_questionnaire_prompt(
    *,
    project_name: str,
    project_core_content: str,
    rows: list[dict[str, Any]],
    admin_prompt: str,
    admin_kb: str,
    user_kb_context: str = "",
    review_feedback: str = "",
) -> str:
    preamble = build_admin_preamble(admin_prompt, admin_kb, user_kb_context)
    indicator_blob = "\n".join(
        f"- id={row['id']} | 一级={row['l1']} / 二级={row['l2']} / 三级={row['l3']}"
        f" | 分值={row['score']:.2f} | 维度={row['tag']}"
        for row in rows
    )
    feedback_block = (
        f"\n【人工反馈意见（请按此调整本次输出）】\n{review_feedback.strip()}\n"
        if review_feedback.strip()
        else ""
    )
    instructions = [
        "请基于以下三级指标生成里克特 5 级满意度问卷。",
        "要求：",
        "1. 每个三级指标至少 1 道题；侧重满意度/感知/影响，避免事实型问题；",
        "2. 题干使用第二人称（您），中文，30 字以内；",
        f"3. 选项严格使用 5 级量表：{' / '.join(LIKERT_OPTIONS)}；",
        "4. 不允许出现 '是/否' 题或多选题；不允许重复题干；",
        "",
        "输出格式（严格 JSON，不要任何额外文字）：",
        "{",
        '  "items": [',
        '    {"id": "Q001", "indicator_id": "L3-…", "question": "…",',
        '     "options": ["非常不满意","不满意","一般","满意","非常满意"]}',
        "  ]",
        "}",
    ]
    return "\n".join(
        [
            preamble.strip(),
            f"项目名称：{project_name}",
            "项目核心内容：",
            (project_core_content or "（未提供，请仅围绕指标维度出题）").strip(),
            "",
            "三级指标列表：",
            indicator_blob or "（空）",
            feedback_block,
            "",
            *instructions,
        ]
    )


def _fallback_question(row: dict[str, Any], idx: int) -> QuestionnaireItem:
    return {
        "id": f"Q{idx:03d}",
        "indicator_id": str(row.get("id", "")),
        "indicator_name": f"{row['l1']} / {row['l2']} / {row['l3']}",
        "question": f"您对本项目在「{row['l3']}」方面的表现是否满意？",
        "options": list(LIKERT_OPTIONS),
        "source_note": f"规则模板（指标维度：{row.get('tag', '其他')}）",
        "model_name": "fallback",
    }


def _normalize_options(raw: Any) -> list[str]:
    if isinstance(raw, list) and len(raw) == 5:
        return [str(x).strip() for x in raw if str(x).strip()]
    return list(LIKERT_OPTIONS)


def _apply_llm_questionnaire(
    rows: list[dict[str, Any]],
    raw_text: str,
    model_name: str,
) -> list[QuestionnaireItem]:
    parsed = parse_json_object(raw_text) or {}
    items_raw = parsed.get("items") if isinstance(parsed, dict) else None

    by_indicator: dict[str, list[dict[str, Any]]] = {}
    if isinstance(items_raw, list):
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            indicator_id = str(item.get("indicator_id") or "").strip()
            question = str(item.get("question") or "").strip()
            if not indicator_id or not question:
                continue
            options = _normalize_options(item.get("options"))
            if len(options) != 5:
                options = list(LIKERT_OPTIONS)
            by_indicator.setdefault(indicator_id, []).append(
                {
                    "id": str(item.get("id") or "").strip(),
                    "question": question,
                    "options": options,
                }
            )

    items: list[QuestionnaireItem] = []
    counter = 1
    for row in rows:
        indicator_id = str(row.get("id", ""))
        candidates = by_indicator.get(indicator_id, [])
        if candidates:
            for cand in candidates:
                items.append(
                    {
                        "id": cand["id"] or f"Q{counter:03d}",
                        "indicator_id": indicator_id,
                        "indicator_name": f"{row['l1']} / {row['l2']} / {row['l3']}",
                        "question": cand["question"],
                        "options": cand["options"],
                        "source_note": f"模型生成（指标维度：{row.get('tag', '其他')}）",
                        "model_name": model_name,
                    }
                )
                counter += 1
        else:
            items.append(_fallback_question(row, counter))
            counter += 1
    return items


def _render_questionnaire(items: list[QuestionnaireItem]) -> str:
    if not items:
        return "（暂无问卷条目）"
    lines = ["# 里克特 5 级满意度问卷草稿", ""]
    current_indicator: str | None = None
    for item in items:
        if item.get("indicator_name") != current_indicator:
            current_indicator = str(item.get("indicator_name") or "")
            lines.extend(["", f"## {current_indicator}"])
        lines.append(f"- **{item.get('id')}** {item.get('question')}")
        lines.append(f"  - 选项：{' / '.join(item.get('options') or LIKERT_OPTIONS)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------


def validate_basis(state: Step6State) -> Step6State:
    if not state.get("scored_tree"):
        return {
            "status": "failed",
            "error": "缺少第四步成果：请先传入 scored_tree。",
            "messages": [AIMessage(content="第六步必须基于第四步定稿分值结构。")],
            "updated_at": now_iso(),
        }
    if not state.get("score_standards"):
        return {
            "status": "failed",
            "error": "缺少第五步成果：请先传入 score_standards。",
            "messages": [AIMessage(content="第六步必须基于第五步评分标准生成。")],
            "updated_at": now_iso(),
        }
    name = (state.get("project_name") or "未命名项目").strip() or "未命名项目"
    return {
        "project_name": name,
        "created_at": state.get("created_at") or now_iso(),
        "updated_at": now_iso(),
        "status": "basis_ok",
        "messages": [AIMessage(content=f"已接收指标体系、分值与评分标准，项目：{name}。")],
    }


def route_after_basis(state: Step6State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


def build_framework(state: Step6State) -> Step6State:
    project_name = state.get("project_name", "未命名项目")
    tree = json.loads(json.dumps(state.get("scored_tree") or []))
    standards = json.loads(json.dumps(state.get("score_standards") or []))
    md = _render_framework(project_name, tree, standards)
    return {
        "final_indicator_framework_markdown": md,
        "content_text": md,
        "export_filename": f"{project_name}绩效评价指标体系",
        "export_payload": md,
        "status": "framework_ready",
        "updated_at": now_iso(),
        "messages": [AIMessage(content="已生成绩效评价指标体系，可调整顺序、预览并导出。")],
    }


def route_questionnaire(state: Step6State) -> str:
    return "need" if state.get("questionnaire_decision") == "need" else "skip"


def generate_questionnaire(state: Step6State, runtime: Any = None) -> Step6State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    rows = _flatten_framework(
        state.get("scored_tree") or [],
        state.get("score_standards") or [],
    )
    if not rows:
        return {
            "questionnaire_items": [],
            "questionnaire_draft": "（指标列表为空，无法生成问卷。）",
            "status": "questionnaire_empty",
            "updated_at": now_iso(),
            "messages": [AIMessage(content="未发现可生成问卷的三级指标。")],
        }

    project_name = state.get("project_name", "未命名项目")
    project_core = str(state.get("project_core_content") or "")
    admin_prompt = read_admin_prompt(context, dict(state))
    admin_kb = read_admin_kb(context, dict(state))
    from ._llm import fetch_user_kb_context_sync
    user_kb_context = fetch_user_kb_context_sync(
        project_id=str(context.get("project_id") or ""),
        query=f"{project_name} 资金绩效 支出效率",
        step_code="step6",
    )
    review_feedback = (state.get("review_feedback") or "").strip()

    prompt = _build_questionnaire_prompt(
        project_name=project_name,
        project_core_content=project_core,
        rows=rows,
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
    comparisons: list[FrameworkDraft] = []
    items: list[QuestionnaireItem]
    chosen_model = ""

    try:
        drafts = await_in_sync(
            generate_drafts_async(
                prompt=prompt,
                system_prompt=admin_prompt
                or "你是绩效评价问卷设计专家，输出严格符合 JSON 格式。",
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
        items = _apply_llm_questionnaire(rows, winner.get("draft", ""), chosen_model)
    except Exception as exc:  # noqa: BLE001
        error_message = f"模型调用失败，已回退到规则模板：{exc}"
        items = [_fallback_question(row, idx + 1) for idx, row in enumerate(rows)]

    draft_md = _render_questionnaire(items)
    return {
        "questionnaire_items": items,
        "questionnaire_draft": draft_md,
        "model_comparisons": comparisons,
        "status": "questionnaire_ready" if not error_message else "questionnaire_ready_with_fallback",
        "error": error_message,
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已按里克特 5 级量表生成 {len(items)} 道问卷题"
                    + (f"（采用模型：{chosen_model}）" if chosen_model else "")
                    + ("，已回退到规则模板。" if error_message else "，可逐题修订。")
                )
            )
        ],
    }


def review_questionnaire(state: Step6State) -> Step6State:
    rnd = int(state.get("review_round", 0)) + 1
    fb = (state.get("review_feedback") or "").strip()
    return {
        "review_round": rnd,
        "status": "questionnaire_reviewed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"已记录第 {rnd} 轮问卷修改意见：{fb or '（无具体内容）'}")
        ],
    }


def finalize_framework(state: Step6State) -> Step6State:
    project_name = state.get("project_name", "未命名项目")
    md = state.get("final_indicator_framework_markdown") or ""
    questionnaire = state.get("questionnaire_draft") or ""
    payload_parts = [md]
    if questionnaire:
        payload_parts.append("\n\n## 调查问卷\n" + questionnaire)
    items = state.get("questionnaire_items") or []
    if items:
        payload_parts.append(
            "\n\n## 机器可读快照（JSON）\n```json\n"
            + json.dumps(items, ensure_ascii=False, indent=2)
            + "\n```\n"
        )
    payload = "".join(payload_parts)
    return {
        "content_text": md,
        "export_payload": payload,
        "export_filename": state.get("export_filename") or f"{project_name}绩效评价指标体系",
        "status": "completed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content="第六步已完成，可进入第七步指标分析与得分表生成。")
        ],
    }


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    graph = StateGraph(Step6State, context_schema=Step6Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("build_framework", build_framework)
    graph.add_node("generate_questionnaire", generate_questionnaire)
    graph.add_node("review_questionnaire", review_questionnaire)
    graph.add_node("finalize_framework", finalize_framework)

    graph.add_edge(START, "validate_basis")
    graph.add_conditional_edges(
        "validate_basis",
        route_after_basis,
        {"continue": "build_framework", "end": END},
    )
    graph.add_conditional_edges(
        "build_framework",
        route_questionnaire,
        {"need": "generate_questionnaire", "skip": "finalize_framework"},
    )
    graph.add_edge("generate_questionnaire", "review_questionnaire")
    graph.add_edge("review_questionnaire", "finalize_framework")
    graph.add_edge("finalize_framework", END)

    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step6")


graph = build_graph()
