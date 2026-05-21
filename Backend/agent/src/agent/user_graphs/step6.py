"""Step 6 graph for EvalFlow Pro — 生成绩效评价指标体系.

本模块衔接 Step 3/4/5 的成果，基于完整指标体系、分值与评分标准，
生成可视化的绩效评价指标体系表，并支持：

- 一级/二级/三级指标顺序重排（这里以结构化列表表示）
- 按一级指标分组输出
- 汇总评分标准，形成后续第七步分析的输入
- 询问是否需要问卷调查，并在需要时自动生成里克特量表问卷草稿
- 多模型对比与人工修订

注意：本文件只是工作流骨架，真实前端可把这些结构渲染成拖拽表格/树形控件。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import operator
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .step4 import L1ScoreRow
from .step5 import RubricRow

QuestionnaireDecision = Literal["need", "skip"]
ReviewMode = Literal["modify", "approve"]


class QuestionnaireItem(TypedDict, total=False):
    id: str
    indicator_name: str
    question: str
    options: list[str]
    source_note: str


class Step6State(TypedDict, total=False):
    project_name: str
    scored_tree: list[L1ScoreRow]
    rubric_tree: list[RubricRow]
    project_core_content: str

    questionnaire_decision: QuestionnaireDecision
    questionnaire_items: list[QuestionnaireItem]
    questionnaire_draft: str

    review_mode: ReviewMode
    review_round: int
    review_feedback: str

    final_indicator_framework_markdown: str
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
    compare_models: list[str]
    enable_multi_model: bool
    system_prompt_stub: str
    knowledge_stub: str
    output_dir: str


LIKERT_OPTIONS = ["非常不满意", "不满意", "一般", "满意", "非常满意"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _flatten_framework(tree: list[L1ScoreRow]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for l1 in tree:
        for l2 in l1.get("level2", []) or []:
            for l3 in l2.get("level3", []) or []:
                rows.append(
                    {
                        "l1": str(l1.get("name", "")),
                        "l2": str(l2.get("name", "")),
                        "l3": str(l3.get("name", "")),
                        "score": float(l3.get("score", 0)),
                        "tag": str(l3.get("tag", "其他")),
                        "rubric": str(l3.get("rubric", "")),
                    }
                )
    return rows


def _render_framework(project_name: str, tree: list[L1ScoreRow], rubric_rows: list[RubricRow]) -> str:
    rubric_map = {r["id"]: r for r in rubric_rows if r.get("id")}
    lines = [f"《{project_name} — 绩效评价指标体系》", "", f"- 生成时间：{_now_iso()}", "", "## 指标体系表"]
    for l1 in tree:
        lines.append(f"### 一级：{l1.get('name')} ｜ 分值：{float(l1.get('score', 0)):.2f}")
        for l2 in l1.get("level2", []) or []:
            lines.append(f"- 二级：{l2.get('name')} ｜ 分值：{float(l2.get('score', 0)):.2f}")
            for l3 in l2.get("level3", []) or []:
                rid = str(l3.get("id", ""))
                rb = rubric_map.get(rid)
                lines.append(
                    f"  - 三级：{l3.get('name')} ｜ 分值：{float(l3.get('score', 0)):.2f} ｜ "
                    f"指标解释：{rb.get('explanation', '') if rb else ''}"
                )
                lines.append(f"    - 评分标准：{rb.get('rubric', '') if rb else l3.get('rubric', '')}")
    return "\n".join(lines)


def _build_questionnaire_item(row: dict[str, Any], idx: int) -> QuestionnaireItem:
    return {
        "id": f"Q{idx:03d}",
        "indicator_name": f"{row['l1']} / {row['l2']} / {row['l3']}",
        "question": f"您认为本次项目对{row['l3']}的影响是否显著？",
        "options": LIKERT_OPTIONS,
        "source_note": f"根据指标：{row['l3']}（{row['tag']}）生成。",
    }


def validate_basis(state: Step6State) -> Step6State:
    if not state.get("scored_tree") or not state.get("rubric_tree"):
        return {
            "status": "failed",
            "error": "缺少第五步/第四步成果：请先传入 scored_tree 和 rubric_tree。",
            "messages": [AIMessage(content="第六步必须基于第五步评分标准与第四步分值结果生成。")],
            "updated_at": _now_iso(),
        }
    name = (state.get("project_name") or "未命名项目").strip() or "未命名项目"
    return {
        "project_name": name,
        "created_at": state.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
        "status": "basis_ok",
        "messages": [AIMessage(content=f"已接收指标体系、分值与评分标准，项目：{name}。")],
    }


def build_framework(state: Step6State, runtime: Any = None) -> Step6State:
    _ = runtime
    project_name = state.get("project_name", "未命名项目")
    tree = json.loads(json.dumps(state.get("scored_tree") or []))
    rubric_rows = json.loads(json.dumps(state.get("rubric_tree") or []))
    md = _render_framework(project_name, tree, rubric_rows)
    return {
        "final_indicator_framework_markdown": md,
        "export_filename": f"{project_name}绩效评价指标体系",
        "export_payload": md,
        "status": "framework_ready",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="已生成绩效评价指标体系，可调整顺序、预览并导出。")],
    }


def route_questionnaire(state: Step6State) -> str:
    return "need" if state.get("questionnaire_decision") == "need" else "skip"


def generate_questionnaire(state: Step6State, runtime: Any = None) -> Step6State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    rows = _flatten_framework(state.get("scored_tree") or [])
    items = [_build_questionnaire_item(row, i + 1) for i, row in enumerate(rows) if row.get("tag") in ("效益", "其他")]
    models = list(context.get("compare_models", [])) or [context.get("model_name") or "默认模型"]
    if not items:
        draft = "当前指标未发现明显需要问卷调查的条目。"
    else:
        draft = "\n".join([f"{x['id']} {x['question']}（选项：{' / '.join(x['options'])}）" for x in items])
    if context.get("enable_multi_model"):
        draft = "\n\n".join([f"【模型：{m}】\n{draft}" for m in models])
    return {
        "questionnaire_items": items,
        "questionnaire_draft": draft,
        "status": "questionnaire_ready",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="已按里克特量表生成调查问卷草稿，支持人工增删改。")],
    }


def review_questionnaire(state: Step6State) -> Step6State:
    rnd = int(state.get("review_round", 0)) + 1
    fb = (state.get("review_feedback") or "").strip()
    return {
        "review_round": rnd,
        "status": "questionnaire_reviewed",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content=f"已记录第 {rnd} 轮问卷修改意见：{fb or '（无具体内容）'}")],
    }


def finalize_framework(state: Step6State) -> Step6State:
    project_name = state.get("project_name", "未命名项目")
    md = state.get("final_indicator_framework_markdown") or ""
    questionnaire = state.get("questionnaire_draft") or ""
    payload = md + ("\n\n## 调查问卷\n" + questionnaire if questionnaire else "")
    return {
        "export_payload": payload,
        "export_filename": state.get("export_filename") or f"{project_name}绩效评价指标体系",
        "status": "completed",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="第六步已完成，可进入第七步指标分析与得分表生成。")],
    }


def build_graph() -> Any:
    graph = StateGraph(Step6State, context_schema=Step6Context)
    graph.add_node("validate_basis", validate_basis)
    graph.add_node("build_framework", build_framework)
    graph.add_node("generate_questionnaire", generate_questionnaire)
    graph.add_node("review_questionnaire", review_questionnaire)
    graph.add_node("finalize_framework", finalize_framework)

    graph.add_edge(START, "validate_basis")
    graph.add_edge("validate_basis", "build_framework")
    graph.add_conditional_edges("build_framework", route_questionnaire, {"need": "generate_questionnaire", "skip": "finalize_framework"})
    graph.add_edge("generate_questionnaire", "review_questionnaire")
    graph.add_edge("review_questionnaire", "finalize_framework")
    graph.add_edge("finalize_framework", END)

    return graph.compile(checkpointer=MemorySaver(), name="evalflow-pro-step6")


graph = build_graph()
