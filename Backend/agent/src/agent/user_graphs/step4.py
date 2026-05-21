"""Step 4 graph for EvalFlow Pro — 生成分值.

基于第三步完成的指标体系（:mod:`agent.graphs.step3` 的 ``flat_l2_tasks`` 与/或
``final_indicator_markdown``），为指标赋分，并为后续评分标准编制提供结构化数据基础。

功能对齐 ``doc/_docx_extract.txt`` 第四步说明：

- **赋分方式**：大模型自动赋分（Prompt / 知识库由 ``Step4Context`` 占位，可替换为真实调用），
  支持人工直接覆盖分值；或 **完全人工赋分**（通过 state 传入各级分值）。
- **校验通过后方可确认**：四维校验逻辑见 ``validate_four_dimensions``。
- **一维度**：所有一级指标分值之和为 100；所有二级之和为 100；所有三级之和为 100。
- **二维/三维度**：逐级父子守恒（一级=下属二级之和=其下全部三级之和；二级=下属三级之和）。
- **四维度**：各级「产出 + 效益」类指标分值之和应 **&lt; 60**；若 **≥ 60** 仅作 **预警**（不阻止数值守恒类校验通过）。

**与 Step 3 的衔接**

建议在 state 中传入第三步定稿结构：

- ``flat_l2_tasks``：与 Step3 相同的 ``FlatL2Task`` 列表（推荐）；
- 可选 ``final_indicator_markdown``：仅作文档/审计展示，赋分以结构化树为准。

若仅有 Markdown、无 ``flat_l2_tasks``，本图将尝试使用 ``scoring_tree_json``（见 ``_parse_scoring_tree_json``），
否则失败并提示。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import json
import operator
import re
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .step3 import FlatL2Task

# ---------------------------------------------------------------------------

ScoreTag = Literal["产出", "效益", "其他"]
AssignMode = Literal["llm", "manual"]


class L3ScoreRow(TypedDict, total=False):
    id: str
    name: str
    score: float
    tag: ScoreTag


class L2ScoreRow(TypedDict, total=False):
    id: str
    name: str
    level1_name: str
    score: float
    tag: ScoreTag
    level3: list[L3ScoreRow]


class L1ScoreRow(TypedDict, total=False):
    id: str
    name: str
    score: float
    tag: ScoreTag
    level2: list[L2ScoreRow]


class ValidationReport(TypedDict, total=False):
    dim1_ok: bool
    dim2_ok: bool
    dim3_ok: bool
    dim4_warn_l1: bool
    dim4_warn_l2: bool
    dim4_warn_l3: bool
    messages: list[str]
    hard_pass: bool


class ModelComparison(TypedDict):
    model_name: str
    draft: str


class Step4State(TypedDict, total=False):
    project_name: str
    final_indicator_markdown: str
    flat_l2_tasks: list[FlatL2Task]

    assign_mode: AssignMode
    manual_l3_scores: dict[str, float]
    scoring_tree_json: str

    scored_tree: list[L1ScoreRow]
    validation_report: ValidationReport
    score_notes: str

    model_comparisons: list[ModelComparison]
    draft_scores_markdown: str
    final_scores_markdown: str
    export_filename: str
    export_payload: str

    review_round: int
    review_mode: Literal["modify", "approve"]
    review_feedback: str
    normalize_used: bool

    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step4Context(TypedDict, total=False):
    project_id: str
    user_id: str
    model_name: str
    compare_models: list[str]
    enable_multi_model: bool
    system_prompt_stub: str
    knowledge_stub: str
    output_dir: str


SUM_TARGET = 100.0
EPS = 0.02
OUTPUT_BENEFIT_CAP = 60.0


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _slug(s: str, prefix: str, idx: int) -> str:
    base = re.sub(r"\s+", "-", s.strip())[:40]
    return f"{prefix}-{idx}-{base}"


def _infer_tag(*names: str) -> ScoreTag:
    blob = " ".join(names)
    if "产出" in blob:
        return "产出"
    if "效益" in blob:
        return "效益"
    return "其他"


def _build_tree_from_flat_tasks(tasks: list[FlatL2Task]) -> list[L1ScoreRow]:
    """将 Step3 的 flat_l2_tasks 转为分层树（三级为合成节点，便于赋分与校验）。"""

    by_l1: dict[str, list[FlatL2Task]] = defaultdict(list)
    for t in tasks:
        by_l1[t["level1_name"]].append(t)

    tree: list[L1ScoreRow] = []
    l1_idx = 0
    for l1_name, l2_list in by_l1.items():
        l1_idx += 1
        l2_rows: list[L2ScoreRow] = []
        l2_idx = 0
        for task in l2_list:
            l2_idx += 1
            n = max(1, int(task.get("target_l3_count") or 1))
            l3_list: list[L3ScoreRow] = []
            for j in range(n):
                l3_list.append(
                    {
                        "id": _slug(task["level2_name"], "L3", l2_idx * 100 + j),
                        "name": f"{task['level2_name']}—观测点{j + 1}",
                        "score": 0.0,
                        "tag": _infer_tag(l1_name, task["level2_name"], f"点{j + 1}"),
                    }
                )
            l2_rows.append(
                {
                    "id": _slug(task["level2_name"], "L2", l2_idx),
                    "name": task["level2_name"],
                    "level1_name": l1_name,
                    "score": 0.0,
                    "tag": _infer_tag(l1_name, task["level2_name"]),
                    "level3": l3_list,
                }
            )
        tree.append(
            {
                "id": _slug(l1_name, "L1", l1_idx),
                "name": l1_name,
                "score": 0.0,
                "tag": _infer_tag(l1_name),
                "level2": l2_rows,
            }
        )
    return tree


def _parse_scoring_tree_json(raw: str) -> list[L1ScoreRow] | None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    out: list[L1ScoreRow] = []
    for l1 in data:
        if not isinstance(l1, dict):
            continue
        l2s: list[L2ScoreRow] = []
        for l2 in l1.get("level2", []) or []:
            if not isinstance(l2, dict):
                continue
            l3s: list[L3ScoreRow] = []
            for l3 in l2.get("level3", []) or []:
                if not isinstance(l3, dict):
                    continue
                l3s.append(
                    {
                        "id": str(l3.get("id", "")),
                        "name": str(l3.get("name", "")),
                        "score": float(l3.get("score", 0)),
                        "tag": cast_tag(l3.get("tag")),
                    }
                )
            l2s.append(
                {
                    "id": str(l2.get("id", "")),
                    "name": str(l2.get("name", "")),
                    "level1_name": str(l1.get("name", "")),
                    "score": float(l2.get("score", 0)),
                    "tag": cast_tag(l2.get("tag")),
                    "level3": l3s,
                }
            )
        out.append(
            {
                "id": str(l1.get("id", "")),
                "name": str(l1.get("name", "")),
                "score": float(l1.get("score", 0)),
                "tag": cast_tag(l1.get("tag")),
                "level2": l2s,
            }
        )
    return out or None


def cast_tag(v: Any) -> ScoreTag:
    if v in ("产出", "效益", "其他"):
        return v  # type: ignore[return-value]
    return "其他"


def _iter_l3(tree: list[L1ScoreRow]) -> list[L3ScoreRow]:
    rows: list[L3ScoreRow] = []
    for l1 in tree:
        for l2 in l1.get("level2", []) or []:
            rows.extend(l2.get("level3", []) or [])
    return rows


def _rollup(tree: list[L1ScoreRow]) -> list[L1ScoreRow]:
    for l1 in tree:
        for l2 in l1.get("level2", []) or []:
            l3s = l2.get("level3", []) or []
            l2["score"] = round(sum(float(x.get("score", 0)) for x in l3s), 4)
        l2s = l1.get("level2", []) or []
        l1["score"] = round(sum(float(x.get("score", 0)) for x in l2s), 4)
    return tree


def _distribute_llm_like_scores(tree: list[L1ScoreRow], model_label: str) -> list[L1ScoreRow]:
    """模拟大模型赋分：在叶子层分配权重后向上汇总，满足守恒。"""
    _ = model_label
    l3s = _iter_l3(tree)
    n = len(l3s)
    if n == 0:
        return tree
    base = SUM_TARGET / n
    for i, row in enumerate(l3s):
        jitter = (i % 7) * 0.03 - 0.09
        row["score"] = max(0.0, round(base + jitter, 4))
    s = sum(float(x["score"]) for x in l3s)
    if abs(s - SUM_TARGET) > EPS:
        scale = SUM_TARGET / s
        for row in l3s:
            row["score"] = round(float(row["score"]) * scale, 4)
    return _rollup(tree)


def _apply_manual_l3(tree: list[L1ScoreRow], manual: dict[str, float]) -> list[L1ScoreRow]:
    if not manual:
        return tree
    for l3 in _iter_l3(tree):
        lid = l3.get("id", "")
        if lid in manual:
            l3["score"] = round(float(manual[lid]), 4)
    return _rollup(tree)


def _sum_output_benefit_l1(tree: list[L1ScoreRow]) -> float:
    return sum(float(l1["score"]) for l1 in tree if l1.get("tag") in ("产出", "效益"))


def _sum_output_benefit_l2(tree: list[L1ScoreRow]) -> float:
    s = 0.0
    for l1 in tree:
        for l2 in l1.get("level2", []) or []:
            if l2.get("tag") in ("产出", "效益"):
                s += float(l2.get("score", 0))
    return s


def _sum_output_benefit_l3(tree: list[L1ScoreRow]) -> float:
    s = 0.0
    for l3 in _iter_l3(tree):
        if l3.get("tag") in ("产出", "效益"):
            s += float(l3.get("score", 0))
    return s


def _validate_four_dimensions(tree: list[L1ScoreRow]) -> ValidationReport:
    msgs: list[str] = []
    l1_sum = sum(float(l1.get("score", 0)) for l1 in tree)
    l2_sum = sum(float(l2.get("score", 0)) for l1 in tree for l2 in l1.get("level2", []) or [])
    l3_sum = sum(float(l3.get("score", 0)) for l3 in _iter_l3(tree))

    dim1_ok = (
        abs(l1_sum - SUM_TARGET) <= EPS
        and abs(l2_sum - SUM_TARGET) <= EPS
        and abs(l3_sum - SUM_TARGET) <= EPS
    )
    if not dim1_ok:
        msgs.append(
            f"一维度未通过：一级合计={l1_sum:.2f}，二级合计={l2_sum:.2f}，三级合计={l3_sum:.2f}（期望均为 {SUM_TARGET:.0f}）。"
        )

    dim2_ok = True
    dim3_ok = True
    for l1 in tree:
        l2s = l1.get("level2", []) or []
        sum_l2 = sum(float(x.get("score", 0)) for x in l2s)
        sum_l3_under_l1 = 0.0
        for l2 in l2s:
            l3s = l2.get("level3", []) or []
            sum_l3 = sum(float(x.get("score", 0)) for x in l3s)
            sum_l3_under_l1 += sum_l3
            if abs(float(l2.get("score", 0)) - sum_l3) > EPS:
                dim3_ok = False
                msgs.append(
                    f"三维度未通过：二级「{l2.get('name')}」分值 {l2.get('score')} 与其三级之和 {sum_l3:.2f} 不一致。"
                )
        if abs(float(l1.get("score", 0)) - sum_l2) > EPS or abs(float(l1.get("score", 0)) - sum_l3_under_l1) > EPS:
            dim2_ok = False
            msgs.append(
                f"二维度未通过：一级「{l1.get('name')}」分值 {l1.get('score')} 与下属二级之和 {sum_l2:.2f} "
                f"或三级之和 {sum_l3_under_l1:.2f} 不一致。"
            )

    ob1 = _sum_output_benefit_l1(tree)
    ob2 = _sum_output_benefit_l2(tree)
    ob3 = _sum_output_benefit_l3(tree)
    dim4_warn_l1 = ob1 >= OUTPUT_BENEFIT_CAP - EPS
    dim4_warn_l2 = ob2 >= OUTPUT_BENEFIT_CAP - EPS
    dim4_warn_l3 = ob3 >= OUTPUT_BENEFIT_CAP - EPS
    if dim4_warn_l1:
        msgs.append(
            f"四维度预警（一级）：产出+效益类一级指标分值合计为 {ob1:.2f} 分，应小于 {OUTPUT_BENEFIT_CAP:.0f} 分。"
        )
    if dim4_warn_l2:
        msgs.append(
            f"四维度预警（二级）：产出+效益类二级指标分值合计为 {ob2:.2f} 分，应小于 {OUTPUT_BENEFIT_CAP:.0f} 分。"
        )
    if dim4_warn_l3:
        msgs.append(
            f"四维度预警（三级）：产出+效益类三级指标分值合计为 {ob3:.2f} 分，应小于 {OUTPUT_BENEFIT_CAP:.0f} 分。"
        )

    hard_pass = dim1_ok and dim2_ok and dim3_ok
    return {
        "dim1_ok": dim1_ok,
        "dim2_ok": dim2_ok,
        "dim3_ok": dim3_ok,
        "dim4_warn_l1": dim4_warn_l1,
        "dim4_warn_l2": dim4_warn_l2,
        "dim4_warn_l3": dim4_warn_l3,
        "messages": msgs,
        "hard_pass": hard_pass,
    }


def _render_scores_markdown(project_name: str, tree: list[L1ScoreRow], report: ValidationReport) -> str:
    lines = [
        f"《{project_name} — 指标体系分值表》",
        "",
        f"- 生成时间：{_now_iso()}",
        f"- 校验硬约束（一至三维）：{'通过' if report.get('hard_pass') else '未通过'}",
        f"- 产出+效益占比预警（四维）："
        f"一级={'是' if report.get('dim4_warn_l1') else '否'}；"
        f"二级={'是' if report.get('dim4_warn_l2') else '否'}；"
        f"三级={'是' if report.get('dim4_warn_l3') else '否'}",
        "",
        "## 分值明细",
    ]
    for l1 in tree:
        lines.append(f"### 一级：{l1['name']} ｜ 分值：{l1.get('score', 0)} ｜ 标签：{l1.get('tag')}")
        for l2 in l1.get("level2", []) or []:
            lines.append(f"- **二级** {l2.get('name')} ｜ {l2.get('score')} ｜ {l2.get('tag')}")
            for l3 in l2.get("level3", []) or []:
                lines.append(f"  - 三级 `{l3.get('id')}` {l3.get('name')} ｜ {l3.get('score')} ｜ {l3.get('tag')}")
        lines.append("")
    if report.get("messages"):
        lines.append("## 校验与预警信息")
        for m in report["messages"]:
            lines.append(f"- {m}")
    return "\n".join(lines)


def _simulate_model_score_drafts(project_name: str, tree: list[L1ScoreRow], models: list[str]) -> list[ModelComparison]:
    out: list[ModelComparison] = []
    for m in models:
        draft_tree = json.loads(json.dumps(tree))
        _distribute_llm_like_scores(draft_tree, m)
        rep = _validate_four_dimensions(draft_tree)
        body = _render_scores_markdown(project_name, draft_tree, rep)
        out.append({"model_name": m, "draft": body + f"\n\n【模型 {m}】可对比其它模型赋分方案后，择一写入人工确认稿。\n"})
    return out


def validate_step3_basis(state: Step4State) -> Step4State:
    tasks = list(state.get("flat_l2_tasks") or [])
    md = (state.get("final_indicator_markdown") or "").strip()
    sj = (state.get("scoring_tree_json") or "").strip()

    existing_tree = state.get("scored_tree")
    parsed_from_json: list[L1ScoreRow] | None = None
    if not tasks and sj:
        parsed_from_json = _parse_scoring_tree_json(sj)

    has_tree = bool(existing_tree) or bool(parsed_from_json)
    if not tasks and not has_tree:
        return {
            "status": "failed",
            "error": "缺少第三步指标体系结构：请传入 flat_l2_tasks，或传入可解析的 scoring_tree_json。",
            "messages": [
                AIMessage(
                    content="第四步需基于第三步完整指标体系赋分，请先传入 Step3 的 flat_l2_tasks（推荐）或 scoring_tree_json。"
                )
            ],
            "updated_at": _now_iso(),
        }

    name = (state.get("project_name") or "未命名项目").strip() or "未命名项目"
    out: Step4State = {
        "project_name": name,
        "flat_l2_tasks": tasks if not parsed_from_json else [],
        "final_indicator_markdown": md,
        "created_at": state.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
        "status": "basis_ok",
        "messages": [AIMessage(content=f"已接收第三步资料，项目：{name}。将进入赋分与校验流程。")],
    }
    if parsed_from_json:
        out["scored_tree"] = parsed_from_json
    return out


def route_after_basis(state: Step4State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


def build_scored_tree(state: Step4State) -> Step4State:
    if state.get("scored_tree"):
        tree = state["scored_tree"]
    else:
        tree = _build_tree_from_flat_tasks(state.get("flat_l2_tasks") or [])
    return {
        "scored_tree": tree,
        "status": "tree_ready",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content=f"已生成分层赋分树，共 {len(_iter_l3(tree))} 个三级指标节点。")],
    }


def assign_scores(state: Step4State, runtime: Any = None) -> Step4State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    tree = json.loads(json.dumps(state.get("scored_tree") or []))
    mode = state.get("assign_mode") or "llm"
    project_name = state.get("project_name", "未命名项目")

    if mode == "manual":
        tree = _apply_manual_l3(tree, dict(state.get("manual_l3_scores") or {}))
    else:
        multi = bool(context.get("enable_multi_model", False))
        models = list(context.get("compare_models", [])) or [context.get("model_name") or "默认模型"]
        if multi:
            comps = _simulate_model_score_drafts(project_name, tree, models)
            tree = json.loads(json.dumps(state.get("scored_tree") or []))
            _distribute_llm_like_scores(tree, comps[0]["model_name"] if comps else "默认模型")
            return {
                "scored_tree": _rollup(tree),
                "model_comparisons": comps,
                "draft_scores_markdown": comps[0]["draft"] if comps else "",
                "status": "scores_assigned",
                "updated_at": _now_iso(),
                "messages": [AIMessage(content=f"大模型已给出 {len(comps)} 套赋分方案（多模型对比），默认采用首套并汇总为当前分值树。")],
            }
        _distribute_llm_like_scores(tree, context.get("model_name") or "默认模型")

    tree = _rollup(tree)
    rep = _validate_four_dimensions(tree)
    md = _render_scores_markdown(project_name, tree, rep)
    return {
        "scored_tree": tree,
        "model_comparisons": [],
        "draft_scores_markdown": md,
        "validation_report": rep,
        "status": "scores_assigned",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="已完成赋分（人工或单模型自动），请查看校验结果并确认。")],
    }


def validate_scores_node(state: Step4State) -> Step4State:
    tree = state.get("scored_tree") or []
    rep = _validate_four_dimensions(tree)
    project_name = state.get("project_name", "未命名项目")
    md = _render_scores_markdown(project_name, tree, rep)
    return {
        "validation_report": rep,
        "draft_scores_markdown": md,
        "status": "validated" if rep.get("hard_pass") else "validation_failed",
        "updated_at": _now_iso(),
        "messages": [
            AIMessage(
                content=(
                    "校验完成：一至三维 "
                    + ("**通过**" if rep.get("hard_pass") else "**未通过**，请调整 manual_l3_scores 或切换赋分方式后重试。")
                    + " 四维预警见表内说明。"
                )
            )
        ],
    }


def route_after_validation(state: Step4State) -> str:
    rep = state.get("validation_report") or {}
    if not rep.get("hard_pass"):
        return "abort" if state.get("normalize_used") else "normalize"
    if state.get("review_mode") == "approve":
        return "finalize"
    if state.get("review_mode") == "modify" and (state.get("review_feedback") or "").strip():
        return "refine"
    return "hold"


def hold_for_score_review(state: Step4State) -> Step4State:
    _ = state
    return {
        "status": "awaiting_confirm",
        "updated_at": _now_iso(),
        "messages": [
            AIMessage(
                content=(
                    "一至三维校验已通过。请在下一次调用中设置："
                    "``review_mode='approve'`` 以定稿；"
                    "或 ``review_mode='modify'`` 且填写 ``review_feedback``，"
                    "并视需要更新 ``manual_l3_scores`` 后再次执行以重新赋分。"
                )
            )
        ],
    }


def normalize_scores(state: Step4State) -> Step4State:
    """自动将三级均分并回卷，用于尝试修复一/三维度守恒。"""
    tree = json.loads(json.dumps(state.get("scored_tree") or []))
    l3s = _iter_l3(tree)
    n = len(l3s)
    if n:
        v = round(SUM_TARGET / n, 4)
        for row in l3s:
            row["score"] = v
    tree = _rollup(tree)
    return {
        "scored_tree": tree,
        "normalize_used": True,
        "status": "auto_normalized",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="已执行三级均分归一化并回卷，将重新校验。")],
    }


def abort_validation(state: Step4State) -> Step4State:
    _ = state
    return {
        "status": "failed",
        "error": "自动归一化后仍无法通过一至三维校验，请检查结构或人工赋分。",
        "messages": [AIMessage(content="分值守恒校验失败：请用 assign_mode=manual 传入 manual_l3_scores（按三级 id）后重试。")],
        "updated_at": _now_iso(),
    }


def refine_scores_feedback(state: Step4State) -> Step4State:
    fb = (state.get("review_feedback") or "").strip()
    rnd = int(state.get("review_round", 0)) + 1
    notes = (state.get("score_notes") or "").strip()
    block = f"【第 {rnd} 轮意见】\n{fb}\n" if fb else ""
    return {
        "review_round": rnd,
        "score_notes": (notes + "\n" + block).strip(),
        "status": "refine_requested",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="已记录赋分调整意见；请同步更新 manual_l3_scores 或改选 assign_mode=llm 后再次赋分。")],
    }


def finalize_scores(state: Step4State) -> Step4State:
    tree = state.get("scored_tree") or []
    rep = state.get("validation_report") or _validate_four_dimensions(tree)
    project_name = state.get("project_name", "未命名项目")
    if not rep.get("hard_pass"):
        return {
            "status": "blocked",
            "error": "校验未通过，禁止定稿。",
            "messages": [AIMessage(content="一至三维校验未通过前不可确认分值，请先修正。")],
            "updated_at": _now_iso(),
        }
    md = _render_scores_markdown(project_name, tree, rep)
    payload = md + "\n\n## 机器可读快照（JSON）\n```json\n" + json.dumps(tree, ensure_ascii=False, indent=2) + "\n```\n"
    return {
        "final_scores_markdown": md,
        "export_payload": payload,
        "export_filename": f"{project_name}指标体系分值_定稿",
        "status": "completed",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="分值已确认，可作为后续评分标准编制的数据基础，并支持导出。")],
    }


def build_graph() -> Any:
    graph = StateGraph(Step4State, context_schema=Step4Context)

    graph.add_node("validate_step3_basis", validate_step3_basis)
    graph.add_node("build_scored_tree", build_scored_tree)
    graph.add_node("assign_scores", assign_scores)
    graph.add_node("validate_scores_node", validate_scores_node)
    graph.add_node("normalize_scores", normalize_scores)
    graph.add_node("abort_validation", abort_validation)
    graph.add_node("hold_for_score_review", hold_for_score_review)
    graph.add_node("refine_scores_feedback", refine_scores_feedback)
    graph.add_node("finalize_scores", finalize_scores)

    graph.add_edge(START, "validate_step3_basis")
    graph.add_conditional_edges(
        "validate_step3_basis",
        route_after_basis,
        {"continue": "build_scored_tree", "end": END},
    )
    graph.add_edge("build_scored_tree", "assign_scores")
    graph.add_edge("assign_scores", "validate_scores_node")

    graph.add_conditional_edges(
        "validate_scores_node",
        route_after_validation,
        {
            "normalize": "normalize_scores",
            "abort": "abort_validation",
            "finalize": "finalize_scores",
            "refine": "refine_scores_feedback",
            "hold": "hold_for_score_review",
        },
    )
    graph.add_edge("refine_scores_feedback", "assign_scores")
    graph.add_edge("normalize_scores", "validate_scores_node")
    graph.add_edge("abort_validation", END)
    graph.add_edge("hold_for_score_review", END)
    graph.add_edge("finalize_scores", END)

    memory = MemorySaver()
    return graph.compile(
        checkpointer=memory,
        name="evalflow-pro-step4",
        interrupt_after=["validate_scores_node"],
    )


graph = build_graph()
