"""Step 8 graph for EvalFlow Pro — 提炼经验做法.

承接 Step 7 的得分表与分析（`analysis_rows` / `final_score_sheet_markdown`），
结合 Step 2 项目核心内容与现场评价证据，输出可复制的经验做法。

状态字段
~~~~~~~~

- ``experience_items: list[ExperienceItem]`` —— 结构化条目（标题/类别/做法/成效/证据）。
- ``experience_draft_markdown`` —— 草稿正文（人工可改）。
- ``final_experience_markdown`` —— 定稿正文。
- ``content_text`` —— 与定稿一致，供工作流持久化使用。

LLM 调用失败时回退到 3 条规则模板，模型名追加 ``+fallback`` 后缀。
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


class ExperienceItem(TypedDict, total=False):
    id: str
    title: str
    category: str
    description: str
    effect: str
    evidence: str
    model_name: str


class ExperienceDraft(TypedDict, total=False):
    model_name: str
    label: str
    draft: str
    error: str


class Step8State(TypedDict, total=False):
    project_name: str
    project_core_content: str
    analysis_rows: list[dict[str, Any]]
    analysis_draft_markdown: str
    final_score_sheet_markdown: str
    field_evidence: str

    review_mode: ReviewMode
    review_round: int
    review_feedback: str
    model_comparisons: list[ExperienceDraft]

    experience_items: list[ExperienceItem]
    experience_draft_markdown: str
    final_experience_markdown: str
    content_text: str
    export_filename: str
    export_payload: str

    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step8Context(TypedDict, total=False):
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


def _summarize_analysis(rows: list[dict[str, Any]], max_rows: int = 12) -> str:
    if not rows:
        return "（暂无第七步分析结果，请基于项目核心内容审慎归纳。）"
    lines: list[str] = []
    sorted_rows = sorted(
        rows,
        key=lambda r: float(r.get("score_rate", 0) or 0),
        reverse=True,
    )
    head = sorted_rows[:max_rows]
    for row in head:
        rate = float(row.get("score_rate", 0) or 0)
        lines.append(
            f"- {row.get('l1_name', '')} / {row.get('l2_name', '')} / "
            f"{row.get('l3_name', '')} ｜ 得分率 {rate:.2%} ｜ 分析：{row.get('analysis', '')}"
        )
    if len(rows) > max_rows:
        lines.append(f"…（共 {len(rows)} 项，仅展示前 {max_rows} 项高分指标）")
    return "\n".join(lines)


def _build_experience_prompt(
    *,
    project_name: str,
    project_core_content: str,
    analysis_summary: str,
    field_evidence: str,
    score_sheet: str,
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
    instructions = [
        "请基于以上素材提炼 3 ~ 6 条经验做法，覆盖组织管理、过程控制、结果产出等维度。",
        "要求：",
        "1. 每条经验须包含：title（短句标题，<=20字）、category（机制建设/过程管控/资源保障/成效转化/其他）、",
        "   description（具体做法，2~3 句）、effect（成效或可复制价值，1~2 句）、evidence（来源依据，可引用具体指标或现场材料）；",
        "2. 严禁出现 '同上' '略' 等占位说明，严禁与第七步扣分原因冲突；",
        "3. 仅输出 JSON，不要任何额外文字。",
        "",
        "输出格式（严格 JSON）：",
        "{",
        '  "items": [',
        '    {"id": "E1", "title": "…", "category": "机制建设", "description": "…",',
        '     "effect": "…", "evidence": "…"}',
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
            "第七步分析摘要：",
            analysis_summary,
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


def _fallback_items() -> list[ExperienceItem]:
    return [
        {
            "id": "E1",
            "title": "规范组织实施",
            "category": "机制建设",
            "description": "建立清晰的职责分工与项目推进机制，明确牵头部门与协作单位，固化工作流程。",
            "effect": "保障项目按期推进，关键节点责任到人，可被同类项目复用。",
            "evidence": "源自项目核心内容及高得分率指标。",
            "model_name": "fallback",
        },
        {
            "id": "E2",
            "title": "强化过程管控",
            "category": "过程管控",
            "description": "对关键节点和资料留痕进行跟踪管理，定期开展自查并形成台账。",
            "effect": "提升资料完备度与执行规范性，便于事后评价与审计。",
            "evidence": "源自第七步评分表与分析摘要。",
            "model_name": "fallback",
        },
        {
            "id": "E3",
            "title": "聚焦结果导向",
            "category": "成效转化",
            "description": "围绕目标产出与效益开展资源统筹，建立成果转化与反馈机制。",
            "effect": "提升资金/资源使用效率，强化项目成果对外服务能力。",
            "evidence": "源自第七步绩效分析与得分率较高的成效类指标。",
            "model_name": "fallback",
        },
    ]


def _apply_llm_experience(raw_text: str, model_name: str) -> list[ExperienceItem]:
    parsed = parse_json_object(raw_text) or {}
    items_raw = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items_raw, list):
        return _fallback_items()
    out: list[ExperienceItem] = []
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
                "id": str(item.get("id") or f"E{counter}"),
                "title": title,
                "category": str(item.get("category") or "其他").strip() or "其他",
                "description": description,
                "effect": str(item.get("effect") or "").strip() or "（待补充）",
                "evidence": str(item.get("evidence") or "").strip() or "（来源依据待补充）",
                "model_name": model_name,
            }
        )
        counter += 1
    return out or _fallback_items()


def _render_experience(project_name: str, items: list[ExperienceItem]) -> str:
    lines = [
        f"# 《{project_name} — 经验做法》",
        "",
        f"- 生成时间：{now_iso()}",
        f"- 经验条目数：{len(items)}",
        "",
        "## 经验明细",
    ]
    for idx, item in enumerate(items, 1):
        lines.extend(
            [
                "",
                f"### {idx}. {item.get('title')}",
                f"- **类别**：{item.get('category')}",
                f"- **具体做法**：{item.get('description')}",
                f"- **成效与价值**：{item.get('effect')}",
                f"- **依据**：{item.get('evidence')}",
            ]
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------


def validate_basis(state: Step8State) -> Step8State:
    if not state.get("project_core_content") and not state.get("analysis_rows"):
        return {
            "status": "failed",
            "error": "缺少前置素材：请提供项目核心内容或第七步分析结果。",
            "messages": [AIMessage(content="第八步至少需要项目核心内容或第七步成果。")],
            "updated_at": now_iso(),
        }
    name = (state.get("project_name") or "未命名项目").strip() or "未命名项目"
    return {
        "project_name": name,
        "created_at": state.get("created_at") or now_iso(),
        "updated_at": now_iso(),
        "status": "basis_ok",
        "messages": [AIMessage(content=f"已接收第七步成果与项目核心内容，项目：{name}。")],
    }


def route_after_basis(state: Step8State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


def generate_experience(state: Step8State, runtime: Any = None) -> Step8State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    project_name = state.get("project_name", "未命名项目")
    project_core = str(state.get("project_core_content") or "")
    analysis_rows = list(state.get("analysis_rows") or [])
    analysis_summary = _summarize_analysis(analysis_rows)
    score_sheet = str(state.get("final_score_sheet_markdown") or state.get("analysis_draft_markdown") or "")
    field_evidence = str(state.get("field_evidence") or "")
    admin_prompt = read_admin_prompt(context, dict(state))
    admin_kb = read_admin_kb(context, dict(state))
    review_feedback = (state.get("review_feedback") or "").strip()

    prompt = _build_experience_prompt(
        project_name=project_name,
        project_core_content=project_core,
        analysis_summary=analysis_summary,
        field_evidence=field_evidence,
        score_sheet=score_sheet,
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
    comparisons: list[ExperienceDraft] = []
    items: list[ExperienceItem]
    chosen_model = ""

    try:
        drafts = await_in_sync(
            generate_drafts_async(
                prompt=prompt,
                system_prompt=admin_prompt
                or "你是绩效评价经验做法提炼专家，输出严格符合 JSON 格式。",
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
        items = _apply_llm_experience(winner.get("draft", ""), chosen_model)
    except Exception as exc:  # noqa: BLE001
        error_message = f"模型调用失败，已回退到规则模板：{exc}"
        items = _fallback_items()

    md = _render_experience(project_name, items)
    return {
        "experience_items": items,
        "experience_draft_markdown": md,
        "model_comparisons": comparisons,
        "status": "experience_ready" if not error_message else "experience_ready_with_fallback",
        "error": error_message,
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已提炼 {len(items)} 条经验做法"
                    + (f"（采用模型：{chosen_model}）" if chosen_model else "")
                    + ("，已回退到规则模板。" if error_message else "，可逐条修订。")
                )
            )
        ],
    }


def review_experience(state: Step8State) -> Step8State:
    rnd = int(state.get("review_round", 0)) + 1
    fb = (state.get("review_feedback") or "").strip()
    return {
        "review_round": rnd,
        "status": "experience_reviewed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"已记录第 {rnd} 轮经验做法修改意见：{fb or '（无具体内容）'}")
        ],
    }


def finalize_experience(state: Step8State) -> Step8State:
    project_name = state.get("project_name", "未命名项目")
    items: list[ExperienceItem] = json.loads(json.dumps(state.get("experience_items") or []))
    if not items:
        return {
            "status": "blocked",
            "error": "没有可定稿的经验做法。",
            "messages": [AIMessage(content="请先生成经验做法草稿后再定稿。")],
            "updated_at": now_iso(),
        }
    md = _render_experience(project_name, items)
    payload = (
        md
        + "\n\n## 机器可读快照（JSON）\n```json\n"
        + json.dumps(items, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    return {
        "experience_items": items,
        "final_experience_markdown": md,
        "content_text": md,
        "export_payload": payload,
        "export_filename": f"{project_name}经验做法_定稿",
        "status": "completed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content=f"第八步已完成，已固化 {len(items)} 条经验做法。")
        ],
    }


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    graph = StateGraph(Step8State, context_schema=Step8Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_experience", generate_experience)
    graph.add_node("review_experience", review_experience)
    graph.add_node("finalize_experience", finalize_experience)

    graph.add_edge(START, "validate_basis")
    graph.add_conditional_edges(
        "validate_basis",
        route_after_basis,
        {"continue": "generate_experience", "end": END},
    )
    graph.add_edge("generate_experience", "review_experience")
    graph.add_edge("review_experience", "finalize_experience")
    graph.add_edge("finalize_experience", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step8")


graph = build_graph()
