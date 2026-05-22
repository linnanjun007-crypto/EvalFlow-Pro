"""Step 12 graph for EvalFlow Pro — 项目基础信息.

承接 Step 2 的项目核心内容，结构化生成项目基础信息：

- 项目背景；
- 项目内容；
- 项目组织管理情况；
- 项目资金投入情况；
- 项目绩效目标。

状态字段
~~~~~~~~

- ``base_sections: list[BaseSection]`` —— 结构化条目（标题 + 内容）；
- ``base_info_table_markdown`` —— 渲染后的正文（同时回填 ``final_base_markdown`` 别名）；
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
    "项目背景",
    "项目内容",
    "项目组织管理情况",
    "项目资金投入情况",
    "项目绩效目标",
)


class BaseSection(TypedDict, total=False):
    title: str
    content: str


class BaseDraft(TypedDict, total=False):
    model_name: str
    label: str
    draft: str
    error: str


class Step12State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    field_evidence: str
    final_comprehensive_analysis: str

    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    model_comparisons: list[BaseDraft]

    base_sections: list[BaseSection]
    base_draft_markdown: str
    base_info_table_markdown: str
    final_base_markdown: str
    content_text: str
    export_filename: str
    export_payload: str

    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step12Context(TypedDict, total=False):
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


def _build_base_prompt(
    *,
    project_name: str,
    project_core_content: str,
    field_evidence: str,
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
    titles_blob = "、".join(DEFAULT_SECTION_TITLES)
    instructions = [
        f"请基于项目核心内容，生成 5 个固定小节：{titles_blob}。",
        "要求：",
        "1. 每个小节 3~5 句中文，覆盖关键事实（背景/内容/管理/资金/目标）；",
        "2. 引用具体数据或文件名时必须来源于核心内容或现场证据；",
        "3. 严禁出现 '同上' '略' 等占位说明，缺失数据写「待补充」；",
        "4. 仅输出 JSON，不要任何额外文字。",
        "",
        "输出格式（严格 JSON）：",
        "{",
        '  "sections": [',
        '    {"title": "项目背景", "content": "…"},',
        '    {"title": "项目内容", "content": "…"},',
        '    {"title": "项目组织管理情况", "content": "…"},',
        '    {"title": "项目资金投入情况", "content": "…"},',
        '    {"title": "项目绩效目标", "content": "…"}',
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
            (field_evidence or "（未提供）").strip(),
            feedback_block,
            "",
            *instructions,
        ]
    )


def _fallback_sections() -> list[BaseSection]:
    fallbacks = {
        "项目背景": "结合项目核心内容，概述项目设立背景、政策依据与现实需求。",
        "项目内容": "概述项目主要实施内容与任务安排。",
        "项目组织管理情况": "概述组织架构、职责分工、过程管理与监督机制。",
        "项目资金投入情况": "概述预算安排、资金来源、拨付与使用情况。",
        "项目绩效目标": "概述产出、效益与满意度等目标。",
    }
    return [{"title": title, "content": fallbacks[title]} for title in DEFAULT_SECTION_TITLES]


def _apply_llm_sections(raw_text: str) -> list[BaseSection]:
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


def _render_base(project_name: str, sections: list[BaseSection]) -> str:
    lines = [
        f"# 《{project_name} — 项目基础信息》",
        "",
        f"- 生成时间：{now_iso()}",
        f"- 小节数：{len(sections)}",
        "",
        "## 基础信息明细",
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


def validate_basis(state: Step12State) -> Step12State:
    if not state.get("project_core_content"):
        return {
            "status": "failed",
            "error": "缺少第二步核心内容：请先传入 project_core_content。",
            "messages": [AIMessage(content="第十二步必须基于第二步项目核心内容生成基础信息。")],
            "updated_at": now_iso(),
        }
    name = (state.get("project_name") or "未命名项目").strip() or "未命名项目"
    return {
        "project_name": name,
        "created_at": state.get("created_at") or now_iso(),
        "updated_at": now_iso(),
        "status": "basis_ok",
        "messages": [AIMessage(content=f"已接收项目核心内容，项目：{name}。开始生成基础信息。")],
    }


def route_after_basis(state: Step12State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


def generate_base(state: Step12State, runtime: Any = None) -> Step12State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    project_name = state.get("project_name", "未命名项目")
    project_core = str(state.get("project_core_content") or "")
    field_evidence = str(state.get("field_evidence") or "")
    admin_prompt = read_admin_prompt(context, dict(state))
    admin_kb = read_admin_kb(context, dict(state))
    review_feedback = (state.get("review_feedback") or "").strip()

    prompt = _build_base_prompt(
        project_name=project_name,
        project_core_content=project_core,
        field_evidence=field_evidence,
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
    comparisons: list[BaseDraft] = []
    sections: list[BaseSection]
    chosen_model = ""

    try:
        drafts = await_in_sync(
            generate_drafts_async(
                prompt=prompt,
                system_prompt=admin_prompt
                or "你是绩效评价基础信息撰写专家，输出严格符合 JSON 格式。",
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

    md = _render_base(project_name, sections)
    return {
        "base_sections": sections,
        "base_draft_markdown": md,
        "model_comparisons": comparisons,
        "status": "base_ready" if not error_message else "base_ready_with_fallback",
        "error": error_message,
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已生成项目基础信息（{len(sections)} 个小节）"
                    + (f"（采用模型：{chosen_model}）" if chosen_model else "")
                    + ("，已回退到规则模板。" if error_message else "，可逐节修订。")
                )
            )
        ],
    }


def review_base(state: Step12State) -> Step12State:
    rnd = int(state.get("review_round", 0)) + 1
    fb = (state.get("review_feedback") or "").strip()
    return {
        "review_round": rnd,
        "status": "base_reviewed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"已记录第 {rnd} 轮基础信息修改意见：{fb or '（无具体内容）'}")
        ],
    }


def finalize_base(state: Step12State) -> Step12State:
    project_name = state.get("project_name", "未命名项目")
    sections: list[BaseSection] = json.loads(json.dumps(state.get("base_sections") or []))
    if not sections:
        return {
            "status": "blocked",
            "error": "没有可定稿的基础信息。",
            "messages": [AIMessage(content="请先生成基础信息草稿后再定稿。")],
            "updated_at": now_iso(),
        }
    md = _render_base(project_name, sections)
    payload = (
        md
        + "\n\n## 机器可读快照（JSON）\n```json\n"
        + json.dumps(sections, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    return {
        "base_sections": sections,
        "base_info_table_markdown": md,
        "final_base_markdown": md,
        "content_text": md,
        "export_payload": payload,
        "export_filename": f"{project_name}项目基础信息_定稿",
        "status": "completed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"第十二步已完成，已固化 {len(sections)} 个基础信息小节。")
        ],
    }


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    graph = StateGraph(Step12State, context_schema=Step12Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_base", generate_base)
    graph.add_node("review_base", review_base)
    graph.add_node("finalize_base", finalize_base)

    graph.add_edge(START, "validate_basis")
    graph.add_conditional_edges(
        "validate_basis",
        route_after_basis,
        {"continue": "generate_base", "end": END},
    )
    graph.add_edge("generate_base", "review_base")
    graph.add_edge("review_base", "finalize_base")
    graph.add_edge("finalize_base", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step12")


graph = build_graph()
