"""Step 13 graph for EvalFlow Pro — 绩效评价工作开展情况.

承接 Step 2 项目核心内容与 Step 12 基础信息，结构化生成评价工作组织开展情况：

- 绩效评价目的；
- 评价对象；
- 评价范围；
- 评价原则；
- 评价指标；
- 评价方法；
- 评价标准；
- 工作过程。

状态字段
~~~~~~~~

- ``work_sections: list[WorkSection]`` —— 结构化条目；
- ``work_summary_markdown`` —— 渲染后的正文（同时回填 ``final_work_markdown`` 别名）；
- ``content_text`` —— 与正文一致，供工作流持久化使用。
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

DEFAULT_SECTION_TITLES: tuple[str, ...] = (
    "绩效评价目的",
    "评价对象",
    "评价范围",
    "评价原则",
    "评价指标",
    "评价方法",
    "评价标准",
    "工作过程",
)


class WorkSection(TypedDict, total=False):
    title: str
    content: str


class WorkDraft(TypedDict, total=False):
    model_name: str
    label: str
    draft: str
    error: str


class Step13State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    final_base_markdown: str
    base_info_table_markdown: str
    final_indicator_framework_markdown: str
    final_score_sheet_markdown: str

    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    model_comparisons: list[WorkDraft]

    work_sections: list[WorkSection]
    work_draft_markdown: str
    work_summary_markdown: str
    final_work_markdown: str
    content_text: str
    export_filename: str
    export_payload: str

    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step13Context(TypedDict, total=False):
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


def _build_work_prompt(
    *,
    project_name: str,
    project_core_content: str,
    base_md: str,
    framework_md: str,
    score_md: str,
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
    titles_blob = "、".join(DEFAULT_SECTION_TITLES)
    instructions = [
        f"请基于以上素材，生成 8 个固定小节：{titles_blob}。",
        "要求：",
        "1. 每个小节 2~4 句中文，描述具体做法、依据或范围；",
        "2. 「评价指标」「评价标准」需引用第六/七步框架；",
        "3. 「工作过程」需说明资料收集、分析、复核与成稿等环节；",
        "4. 严禁出现 '同上' '略' 等占位说明，缺失数据写「待补充」；",
        "5. 仅输出 JSON，不要任何额外文字。",
        "",
        "输出格式（严格 JSON）：",
        "{",
        '  "sections": [',
        '    {"title": "绩效评价目的", "content": "…"}',
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
            "项目基础信息（节选）：",
            (base_md or "（未提供）").strip(),
            "",
            "指标体系（节选）：",
            (framework_md or "（未提供）").strip(),
            "",
            "得分表（节选）：",
            (score_md or "（未提供）").strip(),
            feedback_block,
            "",
            *instructions,
        ]
    )


def _fallback_sections() -> list[WorkSection]:
    fallbacks = {
        "绩效评价目的": "通过开展绩效评价，全面了解项目实施成效，强化预算绩效管理与责任落实。",
        "评价对象": "本次评价覆盖项目所涉及的资金、任务与业务单元。",
        "评价范围": "包括项目整个执行周期内的资金使用、任务推进与产出成效。",
        "评价原则": "坚持客观、公正、独立、规范的原则，证据先行、口径一致。",
        "评价指标": "依据本次重新构建的指标体系开展评价，含一级、二级、三级指标。",
        "评价方法": "采用资料核查、现场访谈、数据比对、问卷调查等综合方法。",
        "评价标准": "依据评分标准（优秀 / 良好 / 合格 / 不合格）与既定打分规则。",
        "工作过程": "资料收集 → 现场调研 → 指标打分 → 草稿撰写 → 复核定稿。",
    }
    return [{"title": title, "content": fallbacks[title]} for title in DEFAULT_SECTION_TITLES]


def _apply_llm_sections(raw_text: str) -> list[WorkSection]:
    parsed = parse_json_object(raw_text) or {}
    items_raw = parsed.get("sections") if isinstance(parsed, dict) else None
    if not isinstance(items_raw, list):
        return _fallback_sections()
    by_title: dict[str, str] = {}
    for item in items_raw:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        content = str(item.get("content") or "").strip()
        if title and content:
            by_title[title] = content
    fallback_map = {s["title"]: s["content"] for s in _fallback_sections()}
    return [
        {
            "title": title,
            "content": by_title.get(title) or fallback_map.get(title) or "（待补充）",
        }
        for title in DEFAULT_SECTION_TITLES
    ]


def _render_work(project_name: str, sections: list[WorkSection]) -> str:
    lines = [
        f"# 《{project_name} — 绩效评价工作开展情况》",
        "",
        f"- 生成时间：{now_iso()}",
        f"- 小节数：{len(sections)}",
        "",
        "## 工作开展情况明细",
    ]
    for section in sections:
        lines.extend(
            [
                "",
                f"### {section.get('title')}",
                str(section.get("content") or "（待补充）"),
            ]
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------


def validate_basis(state: Step13State) -> Step13State:
    if not state.get("project_core_content") and not (
        state.get("final_base_markdown") or state.get("base_info_table_markdown")
    ):
        return {
            "status": "failed",
            "error": "缺少前置素材：请先提供项目核心内容或第十二步基础信息。",
            "messages": [
                AIMessage(content="第十三步至少需要项目核心内容或第十二步基础信息。")
            ],
            "updated_at": now_iso(),
        }
    name = (state.get("project_name") or "未命名项目").strip() or "未命名项目"
    return {
        "project_name": name,
        "created_at": state.get("created_at") or now_iso(),
        "updated_at": now_iso(),
        "status": "basis_ok",
        "messages": [
            AIMessage(content=f"已接收核心内容与基础信息，项目：{name}。开始生成工作开展情况。")
        ],
    }


def route_after_basis(state: Step13State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


def generate_work(state: Step13State, runtime: Any = None) -> Step13State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    project_name = state.get("project_name", "未命名项目")
    project_core = str(state.get("project_core_content") or "")
    base_md = str(
        state.get("final_base_markdown") or state.get("base_info_table_markdown") or ""
    )
    framework_md = str(state.get("final_indicator_framework_markdown") or "")
    score_md = str(state.get("final_score_sheet_markdown") or "")
    admin_prompt = read_admin_prompt(context, dict(state))
    admin_kb = read_admin_kb(context, dict(state))
    from ._llm import fetch_user_kb_context_sync
    user_kb_context = fetch_user_kb_context_sync(
        project_id=str(context.get("project_id") or ""),
        query=f"{project_name} 评价结论 工作底稿",
        step_code="step13",
    )
    review_feedback = (state.get("review_feedback") or "").strip()

    prompt = _build_work_prompt(
        project_name=project_name,
        project_core_content=project_core,
        base_md=base_md,
        framework_md=framework_md,
        score_md=score_md,
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
    comparisons: list[WorkDraft] = []
    sections: list[WorkSection]
    chosen_model = ""

    try:
        drafts = await_in_sync(
            generate_drafts_async(
                prompt=prompt,
                system_prompt=admin_prompt
                or "你是绩效评价工作开展情况撰写专家，输出严格符合 JSON 格式。",
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
        sections = _apply_llm_sections(winner.get("draft", ""))
    except Exception as exc:  # noqa: BLE001
        error_message = f"模型调用失败，已回退到规则模板：{exc}"
        sections = _fallback_sections()

    md = _render_work(project_name, sections)
    return {
        "work_sections": sections,
        "work_draft_markdown": md,
        "model_comparisons": comparisons,
        "status": "work_ready" if not error_message else "work_ready_with_fallback",
        "error": error_message,
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已生成绩效评价工作开展情况（{len(sections)} 个小节）"
                    + (f"（采用模型：{chosen_model}）" if chosen_model else "")
                    + ("，已回退到规则模板。" if error_message else "，可逐节修订。")
                )
            )
        ],
    }


def review_work(state: Step13State) -> Step13State:
    rnd = int(state.get("review_round", 0)) + 1
    fb = (state.get("review_feedback") or "").strip()
    return {
        "review_round": rnd,
        "status": "work_reviewed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"已记录第 {rnd} 轮工作开展情况修改意见：{fb or '（无具体内容）'}")
        ],
    }


def finalize_work(state: Step13State) -> Step13State:
    project_name = state.get("project_name", "未命名项目")
    sections: list[WorkSection] = json.loads(json.dumps(state.get("work_sections") or []))
    if not sections:
        return {
            "status": "blocked",
            "error": "没有可定稿的工作开展情况。",
            "messages": [AIMessage(content="请先生成工作开展情况草稿后再定稿。")],
            "updated_at": now_iso(),
        }
    md = _render_work(project_name, sections)
    payload = (
        md
        + "\n\n## 机器可读快照（JSON）\n```json\n"
        + json.dumps(sections, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    return {
        "work_sections": sections,
        "work_summary_markdown": md,
        "final_work_markdown": md,
        "content_text": md,
        "export_payload": payload,
        "export_filename": f"{project_name}绩效评价工作开展情况_定稿",
        "status": "completed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"第十三步已完成，已固化 {len(sections)} 个工作小节。")
        ],
    }


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    graph = StateGraph(Step13State, context_schema=Step13Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_work", generate_work)
    graph.add_node("review_work", review_work)
    graph.add_node("finalize_work", finalize_work)

    graph.add_edge(START, "validate_basis")
    graph.add_conditional_edges(
        "validate_basis",
        route_after_basis,
        {"continue": "generate_work", "end": END},
    )
    graph.add_edge("generate_work", "review_work")
    graph.add_edge("review_work", "finalize_work")
    graph.add_edge("finalize_work", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step13")


graph = build_graph()
