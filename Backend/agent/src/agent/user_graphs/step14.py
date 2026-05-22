"""Step 14 graph for EvalFlow Pro — 生成绩效评价报告.

汇总 Step 6 ~ Step 13 的全部成果，按 ``report_order`` 顺序组合为最终绩效评价报告。
此步不再调用大模型，仅做结构化组装与目录生成。

状态字段
~~~~~~~~

- ``report_order`` —— 短键顺序数组，默认
  ``['base','work','indicator','score','experience','problem','suggestion','comprehensive']``。
- ``report_sections: list[ReportSection]`` —— 实际渲染顺序与正文映射。
- ``final_report_markdown`` —— 渲染后的报告全文。
- ``content_text`` —— 与 ``final_report_markdown`` 一致，供工作流持久化使用。
"""

from __future__ import annotations

import json
import operator
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from ._llm import now_iso


# 短键 → (二级标题, 状态键候选列表)
SECTION_REGISTRY: dict[str, tuple[str, tuple[str, ...]]] = {
    "base": ("一、基本情况", ("final_base_markdown", "base_info_table_markdown")),
    "work": ("二、绩效评价工作开展情况", ("final_work_markdown", "work_summary_markdown")),
    "indicator": ("三、绩效评价指标体系", ("final_indicator_framework_markdown",)),
    "score": ("四、指标分析与得分表", ("final_score_sheet_markdown",)),
    "experience": ("五、经验做法", ("final_experience_markdown",)),
    "problem": ("六、问题及原因分析", ("final_problem_markdown",)),
    "suggestion": ("七、整改建议", ("final_suggestion_markdown",)),
    "comprehensive": (
        "八、综合评价分析及评价结论",
        ("final_comprehensive_analysis", "final_comprehensive_markdown"),
    ),
}

DEFAULT_REPORT_ORDER: tuple[str, ...] = (
    "base",
    "work",
    "indicator",
    "score",
    "experience",
    "problem",
    "suggestion",
    "comprehensive",
)


class ReportSection(TypedDict, total=False):
    key: str
    title: str
    content: str
    has_content: bool


class Step14State(TypedDict, total=False):
    project_name: str
    rating: str
    total_score: float
    full_score: float

    final_indicator_framework_markdown: str
    final_score_sheet_markdown: str
    final_experience_markdown: str
    final_problem_markdown: str
    final_suggestion_markdown: str
    final_comprehensive_analysis: str
    final_base_markdown: str
    base_info_table_markdown: str
    final_work_markdown: str
    work_summary_markdown: str

    report_order: list[str]
    report_sections: list[ReportSection]
    final_report_markdown: str
    content_text: str
    export_filename: str
    export_payload: str

    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step14Context(TypedDict, total=False):
    project_id: str
    user_id: str
    output_dir: str


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _resolve_section_content(state: Step14State, key: str) -> tuple[str, str]:
    title, candidates = SECTION_REGISTRY.get(
        key,
        (f"附加章节：{key}", (key,)),
    )
    for field in candidates:
        text = str(state.get(field) or "").strip()
        if text:
            return title, text
    return title, ""


def _normalize_order(order: list[str] | None) -> list[str]:
    if not order:
        return list(DEFAULT_REPORT_ORDER)
    seen: set[str] = set()
    cleaned: list[str] = []
    for key in order:
        k = str(key or "").strip()
        if not k or k in seen:
            continue
        seen.add(k)
        cleaned.append(k)
    if not cleaned:
        return list(DEFAULT_REPORT_ORDER)
    return cleaned


def _render_report(
    project_name: str,
    sections: list[ReportSection],
    *,
    rating: str = "",
    total: float = 0.0,
    full: float = 0.0,
) -> str:
    score_lines: list[str] = []
    if total or full:
        if full:
            rate = total / full if full else 0.0
            score_lines.append(
                f"- 项目得分：{total:.2f} / {full:.2f}（得分率 {rate:.2%}）"
            )
        else:
            score_lines.append(f"- 项目得分：{total:.2f}")
    if rating:
        score_lines.append(f"- 评价等级：{rating}")

    lines = [
        f"# 《{project_name} — 绩效评价报告》",
        "",
        f"- 生成时间：{now_iso()}",
        *score_lines,
        "",
        "## 报告目录",
    ]
    for idx, section in enumerate(sections, 1):
        marker = "" if section.get("has_content") else "（待补充）"
        lines.append(f"{idx}. {section.get('title')}{marker}")

    for section in sections:
        lines.extend(
            [
                "",
                f"## {section.get('title')}",
                str(section.get("content") or "（本节内容暂未提供，请回到对应步骤补全。）"),
            ]
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# nodes
# ---------------------------------------------------------------------------


def validate_basis(state: Step14State) -> Step14State:
    has_any = any(
        state.get(field)
        for _, candidates in SECTION_REGISTRY.values()
        for field in candidates
    )
    if not has_any:
        return {
            "status": "failed",
            "error": "缺少前置成果：请先完成第六步至第十三步任意一步并传入对应字段。",
            "messages": [AIMessage(content="第十四步需基于前序步骤的至少一个定稿成果。")],
            "updated_at": now_iso(),
        }
    name = (state.get("project_name") or "未命名项目").strip() or "未命名项目"
    return {
        "project_name": name,
        "created_at": state.get("created_at") or now_iso(),
        "updated_at": now_iso(),
        "status": "basis_ok",
        "messages": [AIMessage(content=f"已接收前序成果，项目：{name}。开始组装评价报告。")],
    }


def route_after_basis(state: Step14State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


def generate_report(state: Step14State, runtime: Any = None) -> Step14State:
    _ = runtime
    project_name = state.get("project_name", "未命名项目")
    order = _normalize_order(list(state.get("report_order") or []))

    sections: list[ReportSection] = []
    for key in order:
        title, content = _resolve_section_content(state, key)
        sections.append(
            {
                "key": key,
                "title": title,
                "content": content,
                "has_content": bool(content),
            }
        )

    rating = str(state.get("rating") or "").strip()
    total = float(state.get("total_score", 0) or 0)
    full = float(state.get("full_score", 0) or 0)
    md = _render_report(project_name, sections, rating=rating, total=total, full=full)
    missing = [s.get("title") for s in sections if not s.get("has_content")]
    return {
        "report_order": order,
        "report_sections": sections,
        "final_report_markdown": md,
        "status": "report_ready",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已组装 {len(sections)} 个章节"
                    + (
                        f"；以下章节暂未填充：{ '、'.join(str(t) for t in missing) }"
                        if missing
                        else "；全部章节均已填充。"
                    )
                )
            )
        ],
    }


def finalize_report(state: Step14State) -> Step14State:
    project_name = state.get("project_name", "未命名项目")
    md = str(state.get("final_report_markdown") or "")
    if not md:
        return {
            "status": "blocked",
            "error": "未生成报告正文。",
            "messages": [AIMessage(content="请先生成报告草稿后再定稿。")],
            "updated_at": now_iso(),
        }
    sections: list[ReportSection] = json.loads(json.dumps(state.get("report_sections") or []))
    snapshot = {
        "project_name": project_name,
        "report_order": state.get("report_order") or list(DEFAULT_REPORT_ORDER),
        "rating": state.get("rating") or "",
        "total_score": float(state.get("total_score", 0) or 0),
        "full_score": float(state.get("full_score", 0) or 0),
        "sections": [
            {"key": s.get("key"), "title": s.get("title"), "has_content": bool(s.get("has_content"))}
            for s in sections
        ],
    }
    payload = (
        md
        + "\n\n## 机器可读快照（JSON）\n```json\n"
        + json.dumps(snapshot, ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    return {
        "final_report_markdown": md,
        "content_text": md,
        "export_payload": payload,
        "export_filename": f"{project_name}绩效评价报告_定稿",
        "status": "completed",
        "updated_at": now_iso(),
        "messages": [
            AIMessage(content="第十四步已完成，绩效评价报告已可导出。")
        ],
    }


# ---------------------------------------------------------------------------
# graph
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    graph = StateGraph(Step14State, context_schema=Step14Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("generate_report", generate_report)
    graph.add_node("finalize_report", finalize_report)

    graph.add_edge(START, "validate_basis")
    graph.add_conditional_edges(
        "validate_basis",
        route_after_basis,
        {"continue": "generate_report", "end": END},
    )
    graph.add_edge("generate_report", "finalize_report")
    graph.add_edge("finalize_report", END)
    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step14")


graph = build_graph()
