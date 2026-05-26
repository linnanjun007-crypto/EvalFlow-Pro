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

from ._llm import (
    build_admin_preamble,
    collect_errors,
    filter_configs_by_compare_models,
    first_successful_draft,
    generate_drafts_async,
    parse_json_object,
    read_admin_kb,
    read_admin_prompt,
    read_model_configs,
)
from .step3 import FlatL2Task

# ---------------------------------------------------------------------------

ScoreTag = Literal["产出", "效益", "其他"]
AssignMode = Literal["llm", "manual"]


class L3ScoreRow(TypedDict, total=False):
    id: str
    name: str
    score: float
    tag: ScoreTag
    key_points: str


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
    project_core_content: str
    final_indicator_markdown: str
    flat_l2_tasks: list[FlatL2Task]

    assign_mode: AssignMode
    manual_l3_scores: dict[str, float]
    scoring_tree_json: str

    scored_tree: list[L1ScoreRow]
    validation_report: ValidationReport
    score_notes: str

    customized_key_points: dict[str, str]
    key_points_source: Literal["model", "fallback", "mixed", ""]

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
    model_configs: list[dict[str, Any]]
    compare_models: list[str]
    enable_multi_model: bool
    admin_prompt_content: str
    admin_kb_content: str
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


def _parse_l3_names_from_markdown(md: str, l2_name: str, target_count: int, l1_name: str = "") -> list[str]:
    """从 step3 的 l3_section_markdown 中提取三级指标名称列表。

    格式示例：``1. **编码 名称**`` 或 ``- **名称**``。
    若解析失败则基于二级名称与一级环节兜底生成 1-2 个具体观测点名。
    """
    names: list[str] = []
    if md and md.strip():
        for line in md.splitlines():
            m = re.match(r"^\s*\d+\.\s*\*\*(?:[A-Za-z0-9\-]+\s+)?(.+?)\*\*", line)
            if m:
                names.append(m.group(1).strip())
                continue
            m2 = re.match(r"^\s*[-*]\s*\*\*(.+?)\*\*", line)
            if m2:
                names.append(m2.group(1).strip())
    if names:
        return names[:max(target_count, len(names))]
    return _generate_default_l3_names(l2_name, target_count, l1_name)


_L2_KEYWORD_TEMPLATES: list[tuple[tuple[str, ...], list[str]]] = [
    (("立项", "批复", "申报"), ["立项依据充分性", "审批程序规范性"]),
    (("可行性", "目标设定", "绩效目标"), ["可行性论证规范性", "绩效目标合理性"]),
    (("预算编制", "预算安排", "资金安排"), ["预算编制科学性", "资金来源合规性"]),
    (("资金到位", "资金拨付", "拨付"), ["资金到位率", "拨付及时性"]),
    (("资金管理", "资金使用", "财务管理"), ["资金使用合规性", "财务核算规范性"]),
    (("政府采购", "采购管理"), ["政府采购规范性", "供应商履约管理"]),
    (("合同管理", "合同履约", "履约"), ["合同签订规范性", "合同履约管理"]),
    (("项目执行", "项目实施", "实施进度", "进度管理"), ["实施进度完成率", "内控制度健全性"]),
    (("组织保障", "组织实施", "队伍建设"), ["组织架构完善性", "突击队履职到位率"]),
    (("数量与质量", "完成情况", "完成数量", "完成率"), ["实践任务完成率", "成果质量合格率"]),
    (("数量",), ["实践任务完成数", "服务覆盖镇村数"]),
    (("质量",), ["成果验收合格率", "技术标准达标率"]),
    (("时效", "进度"), ["任务按期完成率", "阶段交付及时率"]),
    (("成本",), ["成本控制有效性", "资金使用效率"]),
    (("经济效益", "经济社会效益", "经济与社会"), ["投入产出效益", "社会效益与地方满意度"]),
    (("社会效益",), ["社会效益与地方满意度", "媒体与社会影响力"]),
    (("生态效益", "环境"), ["环境改善程度", "资源利用效率"]),
    (("可持续", "长效"), ["长效机制建设", "示范推广价值"]),
    (("满意度",), ["服务对象满意度", "主管部门评价"]),
    (("人才培养", "培训"), ["本土人才培养数", "培训成效合格率"]),
]


_L1_FALLBACK_TEMPLATES: list[tuple[tuple[str, ...], list[str]]] = [
    (("决策",), ["立项依据充分性", "审批程序规范性"]),
    (("过程",), ["资金使用合规性", "实施进度完成率"]),
    (("产出",), ["实践任务完成率", "成果质量合格率"]),
    (("效益",), ["社会效益与地方满意度", "投入产出效益"]),
]


def _generate_default_l3_names(l2_name: str, target_count: int, l1_name: str = "") -> list[str]:
    """基于二级指标关键词与一级环节兜底生成 1-2 个具体观测点名称（无“XX达标情况”废话）。"""
    n = max(1, min(target_count, 2))
    for keywords, templates in _L2_KEYWORD_TEMPLATES:
        if any(kw in l2_name for kw in keywords):
            return templates[:n]
    if l1_name:
        for keywords, templates in _L1_FALLBACK_TEMPLATES:
            if any(kw in l1_name for kw in keywords):
                return templates[:n]
    if n == 1:
        return [f"{l2_name}规范性"]
    return [f"{l2_name}规范性", f"{l2_name}有效性"]


_L3_KEY_POINTS: dict[str, str] = {
    "立项依据充分性": "取证：立项申报书、上位规划文件、调研报告、可行性论证报告原件；扣分：缺申报书扣 60%，无可研论证扣 40%，与上位规划无对应章节扣 30%",
    "审批程序规范性": "取证：立项批复文件、校地双方任务书、三重一大会议纪要；扣分：缺批复扣 60%，无任务书扣 40%，未经集体决策扣 30%",
    "可行性论证规范性": "取证：可行性研究报告、专家论证意见、风险评估报告；扣分：缺可研报告扣 60%，无专家论证扣 40%，未识别重大风险扣 30%",
    "绩效目标合理性": "取证：绩效目标申报表、量化指标对照表、目标分解清单；扣分：目标未量化扣 40%，与上位规划脱节扣 30%，未分解到年度/节点扣 20%",
    "预算编制科学性": "取证：预算明细表、定额测算依据、同类项目对比表；扣分：预算未到三级科目扣 30%，无测算依据扣 40%，单项偏差>20% 未说明扣 20%",
    "资金来源合规性": "取证：财政拨款文件、自筹资金到账凭证、配套资金到位证明；扣分：配套资金未足额到位每差 10% 扣 10 分，自筹未到账扣 50%，渠道违规扣 100%",
    "资金到位率": "取证：资金到账银行回单、配套资金到位证明、台账明细；扣分：到位率<90% 扣 30%，<70% 扣 60%，逾期到位无说明扣 30%",
    "拨付及时性": "取证：拨付节点表、银行流水、合同付款条款；扣分：每延迟 1 个节点扣 10%，截留挪用一经发现扣 100%，无台账扣 50%",
    "资金拨付及时性": "取证：资金拨付台账、银行回单、合同付款节点表；扣分：每延迟 1 个节点扣 10%，截留挪用一经发现扣 100%，无台账扣 50%",
    "资金使用合规性": "取证：报销凭证、记账明细、公务卡流水；扣分：白条入账每张扣 5 分，超预算未审批扣 30%，发票不合规每项扣 3 分",
    "财务核算规范性": "取证：会计账簿、月度对账单、审计报告；扣分：账目混乱扣 50%，未单独核算扣 40%，审计意见非无保留扣 30%",
    "政府采购规范性": "取证：采购计划、招标文件、评标记录、中标公告；扣分：未按规定方式采购扣 60%，无评标记录扣 40%，违规分包扣 50%",
    "供应商履约管理": "取证：供应商资质审核表、履约评估表、违约处置记录；扣分：未审核资质扣 40%，无履约评估扣 30%，违约未处置扣 50%",
    "合同签订规范性": "取证：合同文本、法务审查意见、用印审批记录；扣分：未经法务审查扣 40%，关键条款缺失扣 30%，越权签订扣 60%",
    "合同履约管理": "取证：履约台账、变更协议、验收单、违约处置文件；扣分：履约率<90% 扣 30%，无验收单扣 40%，未处置违约扣 50%",
    "实施进度完成率": "取证：项目周报/月报、里程碑验收单、变更审批单；扣分：关键节点完成率<90% 扣 30%，<70% 扣 60%，未办理变更审批扣 30%",
    "内控制度健全性": "取证：项目管理办法、安全制度文本、考勤记录、工作日志；扣分：制度文件不齐每缺 1 项扣 10 分，无考勤记录扣 30%，安全事故一票否决",
    "组织架构完善性": "取证：组织架构图、岗位职责说明、任命文件；扣分：架构缺位扣 40%，无任命文件扣 30%，权责不清扣 20%",
    "突击队履职到位率": "取证：突击队驻点考勤、工作日志、镇村签到记录；扣分：出勤率<80% 扣 30%，无工作日志扣 40%，擅自脱岗一票否决",
    "实践任务完成率": "取证：任务清单、阶段成果交付记录、镇村签收单、第三方核查报告；扣分：完成率<90% 扣 30%，<70% 扣 60%，无交付记录扣 50%",
    "实践任务完成数": "取证：任务台账、镇村签收清单、第三方核查报告；扣分：完成数<计划 90% 扣 30%，<70% 扣 60%，无签收凭证扣 50%",
    "服务覆盖镇村数": "取证：驻点签到表、镇村合作协议、覆盖清单及佐证；扣分：覆盖镇村数<计划 80% 扣 40%，无签到记录扣 30%，对象造假一票否决",
    "成果质量合格率": "取证：第三方/主管部门验收意见、专家评审表、整改记录；扣分：一次性合格率<80% 扣 30%，重大整改项扣 50%，无验收文件扣 80%",
    "任务完成数量": "取证：任务台账、镇村签收清单、第三方核查报告；扣分：完成数<计划 90% 扣 30%，<70% 扣 60%，无签收凭证扣 50%",
    "服务覆盖范围": "取证：驻点签到表、服务对象名册、镇村合作协议；扣分：覆盖镇村数<计划 80% 扣 40%，无签到记录扣 30%，对象造假一票否决",
    "成果验收合格率": "取证：第三方/主管部门验收意见书、专家评审表；扣分：一次性通过率<80% 扣 30%，存在重大整改项扣 50%，无验收文件扣 80%",
    "技术标准达标率": "取证：技术方案、第三方检测报告、行业规范对照表；扣分：核心技术指标未达标每项扣 10 分，未对照行业标准扣 30%",
    "任务按期完成率": "取证：任务清单及完成时间、延期情况说明；扣分：按期完成率<90% 扣 30%，<70% 扣 60%，逾期无书面说明扣 50%",
    "阶段交付及时率": "取证：阶段成果交付记录、审核回执；扣分：月报/季报缺报每次扣 5 分，逾期>7 天每次扣 10 分",
    "成本控制有效性": "取证：决算与预算对照表、成本节约说明；扣分：超预算>10% 未审批扣 40%，超预算>30% 扣 80%，无成本分析扣 30%",
    "资金使用效率": "取证：单位投入产出测算表、同类项目效率对比；扣分：单位产出低于同类均值扣 20%，资金沉淀>30% 扣 30%",
    "投入产出效益": "取证：项目总投入决算表、可量化产出清单（培训人次、规划文本、转化项目数等）、单位投入产出测算；扣分：产出无法量化扣 50%，投入产出比低于同类均值扣 30%，无测算依据扣 40%",
    "社会效益与地方满意度": "取证：受帮扶镇村两委书面评价、县直主管部门评价函、群众抽样满意度调查报告（样本量≥30）、典型案例报道；扣分：综合满意率<85% 扣 30%，<70% 扣 60%，缺书面评价扣 50%，无群众调查扣 40%",
    "投入产出比": "取证：项目总投入决算表、可量化收益清单（培训人次、规划文本数、转化项目数）；扣分：产出无法量化扣 50%，投入产出比低于同类项目均值扣 30%",
    "群众满意度": "取证：第三方抽样调查报告、调查问卷原件、统计分析表；扣分：样本量<30 扣 30%，满意率<85% 扣 30%，<70% 扣 60%，无第三方背书扣 50%",
    "社会影响力": "取证：省市级媒体报道清单及链接、典型案例入选文件、推广简报；扣分：无省级及以上媒体报道扣 30%，未形成可推广案例扣 40%",
    "媒体与社会影响力": "取证：省市级媒体报道清单、推广简报、典型案例入选文件、网络传播数据；扣分：无省级及以上报道扣 30%，未形成可推广案例扣 40%，传播范围未量化扣 20%",
    "服务对象满意度": "取证：服务对象问卷、访谈记录；扣分：满意率<85% 扣 30%，<70% 扣 60%，问卷回收率<80% 扣 20%",
    "主管部门评价": "取证：受帮扶单位/主管部门盖章评价函；扣分：缺书面评价扣 60%，评价为基本满意以下扣 40%",
    "环境改善程度": "取证：环境质量监测报告（前后对比）、第三方核查；扣分：监测指标无改善扣 50%，无监测数据扣 80%",
    "资源利用效率": "取证：资源消耗台账、单位产出测算；扣分：单位资源产出低于行业均值扣 30%，无台账扣 50%",
    "长效机制建设": "取证：校地长期合作协议、常态化驻点机制文件、轮换计划；扣分：未签长期协议扣 50%，无常态化机制扣 40%",
    "示范推广价值": "取证：可复制案例文本、被省市级简报/媒体推广报道、被纳入典型经验文件；扣分：无可复制案例扣 50%，未被推广报道扣 30%",
    "本土人才培养数": "取证：培训签到表、考核合格证书、带头人花名册；扣分：培训人数<计划 80% 扣 30%，考核合格率<80% 扣 30%，无证书扣 40%",
    "培训成效合格率": "取证：培训考核试卷、合格证书、回访评估表；扣分：合格率<80% 扣 30%，<60% 扣 60%，无考核记录扣 50%",
}


def _key_points_for(name: str) -> str:
    if name in _L3_KEY_POINTS:
        return _L3_KEY_POINTS[name]
    for k, v in _L3_KEY_POINTS.items():
        if k in name or name in k:
            return v
    return (
        f"取证：{name}相关台账、第三方核查/评价文件、过程影像或佐证材料；"
        f"扣分：核心数据缺失扣 50%，关键凭证不齐每项扣 10%，造假一票否决"
    )


def _await_in_sync(coro: Any) -> Any:
    """在同步节点里执行 awaitable，兼容已有事件循环（如 ``langgraph dev``）。"""

    import asyncio

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None
    if loop is not None and loop.is_running():
        return asyncio.run_coroutine_threadsafe(coro, loop).result()
    return asyncio.run(coro)


def _build_customize_key_points_prompt(
    *,
    project_name: str,
    project_core_content: str,
    rows: list[dict[str, Any]],
    admin_prompt: str,
    admin_kb: str,
    user_kb_context: str = "",
) -> str:
    """让模型基于项目核心内容为每条三级指标生成「取证清单 + 扣分细则」。"""

    preamble = build_admin_preamble(admin_prompt, admin_kb, user_kb_context)
    indicator_blob = "\n".join(
        f"- id={row['id']} | 一级={row['l1']} / 二级={row['l2']} / 三级={row['l3']}"
        f" | 维度={row.get('tag', '其他')} | 模板兜底=「{row.get('template', '')}」"
        for row in rows
    )
    instructions = [
        "你是百千万工程突击队项目的资深绩效评价专家。请围绕本项目的真实情境，",
        "为下方每条「三级指标」生成一条贴合项目实际的『取证与扣分细则』。",
        "",
        "【刚性约束】",
        "1. 每条输出仅 1 行，结构严格为：",
        "   取证：<逗号或顿号分隔的若干份具体凭证/台账/报告，3~6 项>；",
        "   扣分：<逗号或顿号分隔的 2~4 条扣分情形，必须含百分比阈值，例如 缺 X 扣 50%>",
        "2. 取证项必须落到具体材料类型（如：立项批复、合同、银行回单、第三方验收报告、",
        "   群众抽样问卷、镇村签收单、媒体报道清单 等），禁止「相关材料」「佐证文件」等泛词；",
        "3. 扣分项要给出可量化阈值（如 完成率<90% 扣 30%、缺 X 扣 60%、造假一票否决），",
        "   不允许「酌情扣分」「视情况而定」等模糊表述；",
        "4. 必须围绕高校突击队项目的实际情境（驻点镇村、校地结对、群众满意度等），",
        "   不允许照抄通用模板；如指标与高校项目结合点弱，则参照模板兜底但必须做一次具体化润色；",
        "5. 同一行总长度建议 ≤ 80 个汉字，确保后续表格可读；",
        "6. 严格输出 JSON，禁止任何额外说明文字：",
        "{",
        '  "rows": [ {"id": "<指标 id>", "key_points": "取证：…；扣分：…"} ]',
        "}",
    ]
    return "\n".join(
        [
            preamble.strip(),
            f"项目名称：{project_name}",
            "项目核心内容：",
            (project_core_content or "（未提供，请围绕高校突击队驻镇帮镇扶村项目通用情境设计）").strip(),
            "",
            "待生成取证扣分细则的三级指标列表：",
            indicator_blob or "（空）",
            "",
            *instructions,
        ]
    )


def _flatten_l3_rows(tree: list[L1ScoreRow]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for l1 in tree:
        for l2 in l1.get("level2", []) or []:
            for l3 in l2.get("level3", []) or []:
                row_id = str(l3.get("id", "")).strip()
                if not row_id:
                    continue
                name = str(l3.get("name", ""))
                out.append(
                    {
                        "id": row_id,
                        "l1": str(l1.get("name", "")),
                        "l2": str(l2.get("name", "")),
                        "l3": name,
                        "tag": str(l3.get("tag", "其他")),
                        "template": _key_points_for(name),
                    }
                )
    return out


def _build_tree_from_flat_tasks(tasks: list[FlatL2Task]) -> list[L1ScoreRow]:
    """将 Step3 的 flat_l2_tasks 转为分层树，三级指标从 l3_section_markdown 解析真实名称。"""

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
            target_n = max(1, min(int(task.get("target_l3_count") or 2), 3))
            l3_md = task.get("l3_section_markdown") or ""
            l3_names = _parse_l3_names_from_markdown(l3_md, task["level2_name"], target_n, l1_name)
            l3_list: list[L3ScoreRow] = []
            for j, name in enumerate(l3_names):
                l3_list.append(
                    {
                        "id": _slug(name, "L3", l1_idx * 1000 + l2_idx * 100 + j),
                        "name": name,
                        "score": 0,
                        "tag": _infer_tag(l1_name, task["level2_name"], name),
                        "key_points": _key_points_for(name),
                    }
                )
            l2_rows.append(
                {
                    "id": _slug(task["level2_name"], "L2", l2_idx),
                    "name": task["level2_name"],
                    "level1_name": l1_name,
                    "score": 0,
                    "tag": _infer_tag(l1_name, task["level2_name"]),
                    "level3": l3_list,
                }
            )
        tree.append(
            {
                "id": _slug(l1_name, "L1", l1_idx),
                "name": l1_name,
                "score": 0,
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
                        "score": int(round(float(l3.get("score", 0) or 0))),
                        "tag": cast_tag(l3.get("tag")),
                        "key_points": str(l3.get("key_points") or _key_points_for(str(l3.get("name", "")))),
                    }
                )
            l2s.append(
                {
                    "id": str(l2.get("id", "")),
                    "name": str(l2.get("name", "")),
                    "level1_name": str(l1.get("name", "")),
                    "score": int(round(float(l2.get("score", 0) or 0))),
                    "tag": cast_tag(l2.get("tag")),
                    "level3": l3s,
                }
            )
        out.append(
            {
                "id": str(l1.get("id", "")),
                "name": str(l1.get("name", "")),
                "score": int(round(float(l1.get("score", 0) or 0))),
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
            l2["score"] = int(sum(int(x.get("score", 0) or 0) for x in l3s))
        l2s = l1.get("level2", []) or []
        l1["score"] = int(sum(int(x.get("score", 0) or 0) for x in l2s))
    return tree


def _distribute_integer_scores(items: list[Any], total: int) -> list[int]:
    """将 ``total`` 整数总分按等权基线 + 余数补偿分配给 ``items``，返回每项整数分。"""
    n = len(items)
    if n == 0 or total <= 0:
        return [0] * n
    base = total // n
    remainder = total - base * n
    scores = [base] * n
    for i in range(remainder):
        scores[i] += 1
    return scores


def _distribute_llm_like_scores(tree: list[L1ScoreRow], model_label: str) -> list[L1ScoreRow]:
    """模拟大模型整数赋分：自顶向下将 100 分等权切分到一级 → 二级 → 三级，确保整数且守恒。"""
    _ = model_label
    n_l1 = len(tree)
    if n_l1 == 0:
        return tree
    l1_scores = _distribute_integer_scores(tree, int(SUM_TARGET))
    for l1, l1_total in zip(tree, l1_scores):
        l2s = l1.get("level2", []) or []
        l2_scores = _distribute_integer_scores(l2s, l1_total)
        for l2, l2_total in zip(l2s, l2_scores):
            l3s = l2.get("level3", []) or []
            l3_scores = _distribute_integer_scores(l3s, l2_total)
            for l3, sc in zip(l3s, l3_scores):
                l3["score"] = sc
            l2["score"] = l2_total
        l1["score"] = l1_total
    return _rollup(tree)


def _apply_manual_l3(tree: list[L1ScoreRow], manual: dict[str, float]) -> list[L1ScoreRow]:
    if not manual:
        return tree
    for l3 in _iter_l3(tree):
        lid = l3.get("id", "")
        if lid in manual:
            l3["score"] = int(round(float(manual[lid])))
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


def _render_scores_markdown(
    project_name: str,
    tree: list[L1ScoreRow],
    report: ValidationReport,
    customized_key_points: dict[str, str] | None = None,
) -> str:
    """渲染分值表为 7 列 Markdown 表格：一级/一级总分/二级/二级总分/三级/三级分值/核心考核要点。"""
    customized_key_points = customized_key_points or {}
    lines: list[str] = [
        f"# 《{project_name} — 评估指标分值表》",
        "",
        f"- 生成时间：{_now_iso()}",
        f"- 校验硬约束（一至三维）：{'通过' if report.get('hard_pass') else '未通过'}",
        f"- 产出+效益占比预警（四维）："
        f"一级={'是' if report.get('dim4_warn_l1') else '否'}；"
        f"二级={'是' if report.get('dim4_warn_l2') else '否'}；"
        f"三级={'是' if report.get('dim4_warn_l3') else '否'}",
        "",
        "## 分值明细",
        "",
        "| 一级指标 | 一级总分 | 二级指标 | 二级总分 | 具体观测点/三级指标 | 观测点分值 | 核心考核要点 |",
        "| --- | :---: | --- | :---: | --- | :---: | --- |",
    ]

    def _fmt_int(v: Any) -> str:
        try:
            return str(int(round(float(v or 0))))
        except (TypeError, ValueError):
            return "0"

    def _esc(text: str) -> str:
        return str(text or "").replace("|", "丨").replace("\n", " ").strip()

    grand_l1 = 0
    grand_l2 = 0
    grand_l3 = 0

    for l1 in tree:
        l1_name = _esc(l1.get("name", ""))
        l1_score = _fmt_int(l1.get("score", 0))
        grand_l1 += int(l1_score)
        l1_emitted = False

        l2_list = l1.get("level2", []) or []
        if not l2_list:
            lines.append(f"| {l1_name} | {l1_score} | — | — | — | — | — |")
            continue

        for l2 in l2_list:
            l2_name = _esc(l2.get("name", ""))
            l2_score = _fmt_int(l2.get("score", 0))
            grand_l2 += int(l2_score)
            l2_emitted = False

            l3_list = l2.get("level3", []) or []
            if not l3_list:
                left_l1 = l1_name if not l1_emitted else ""
                left_l1_score = l1_score if not l1_emitted else ""
                lines.append(f"| {left_l1} | {left_l1_score} | {l2_name} | {l2_score} | — | — | — |")
                l1_emitted = True
                continue

            for l3 in l3_list:
                l3_name = _esc(l3.get("name", ""))
                l3_score = _fmt_int(l3.get("score", 0))
                grand_l3 += int(l3_score)
                row_id = str(l3.get("id", "")).strip()
                kp_raw = customized_key_points.get(row_id) or l3.get("key_points") or _key_points_for(l3.get("name", ""))
                kp = _esc(kp_raw)
                left_l1 = l1_name if not l1_emitted else ""
                left_l1_score = l1_score if not l1_emitted else ""
                left_l2 = l2_name if not l2_emitted else ""
                left_l2_score = l2_score if not l2_emitted else ""
                lines.append(
                    f"| {left_l1} | {left_l1_score} | {left_l2} | {left_l2_score} | {l3_name} | {l3_score} | {kp} |"
                )
                l1_emitted = True
                l2_emitted = True

    lines.append(f"| **合计** | **{grand_l1}** | — | **{grand_l2}** | — | **{grand_l3}** | — |")
    lines.append("")

    if report.get("messages"):
        lines.append("## 校验与预警信息")
        for m in report["messages"]:
            lines.append(f"- {m}")
        lines.append("")
    return "\n".join(lines)


def _simulate_model_score_drafts(
    project_name: str,
    tree: list[L1ScoreRow],
    models: list[str],
    customized_key_points: dict[str, str] | None = None,
) -> list[ModelComparison]:
    out: list[ModelComparison] = []
    for m in models:
        draft_tree = json.loads(json.dumps(tree))
        _distribute_llm_like_scores(draft_tree, m)
        rep = _validate_four_dimensions(draft_tree)
        body = _render_scores_markdown(project_name, draft_tree, rep, customized_key_points)
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
        "project_core_content": str(state.get("project_core_content") or "").strip(),
        "flat_l2_tasks": tasks if not parsed_from_json else [],
        "final_indicator_markdown": md,
        "created_at": state.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
        "status": "basis_ok",
        "messages": [AIMessage(content=f"已接收第三步资料，项目：{name}。将进入赋分与校验流程。")],
    }
    if parsed_from_json:
        out["scored_tree"] = parsed_from_json
    else:
        # 关键：每次重新进入 step4 都丢弃 MemorySaver 里残留的旧 scored_tree，
        # 强制 build_scored_tree 基于最新的 flat_l2_tasks（含最新的 _L3_KEY_POINTS / 模板）重建。
        out["scored_tree"] = []
        out["final_scores_markdown"] = ""
    # 同时清空旧的模型生成取证扣分细则，避免 MemorySaver 把上一轮结果带回。
    out["customized_key_points"] = {}
    out["key_points_source"] = ""
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


def customize_key_points_node(state: Step4State, runtime: Any = None) -> Step4State:
    """让 LLM 基于项目核心内容生成定制化「取证 + 扣分细则」，失败时回退到 ``_L3_KEY_POINTS`` 模板。

    生成结果以 ``{l3_id: 一行文本}`` 形式存入 ``customized_key_points``，由
    ``_render_scores_markdown`` 在渲染时优先使用；缺失项自动用模板兜底，确保
    任何指标行都有可见的取证扣分依据。
    """

    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    tree = state.get("scored_tree") or []
    rows = _flatten_l3_rows(tree)

    if not rows:
        return {
            "customized_key_points": {},
            "key_points_source": "fallback",
            "status": "key_points_ready",
            "updated_at": _now_iso(),
        }

    # 先准备模板兜底，保证最终 dict 一定齐全。
    fallback_map: dict[str, str] = {row["id"]: row["template"] for row in rows}

    project_name = state.get("project_name", "未命名项目")
    project_core = str(state.get("project_core_content") or "")
    admin_prompt = read_admin_prompt(context, dict(state))
    admin_kb = read_admin_kb(context, dict(state))
    try:
        from ._llm import fetch_user_kb_context_sync

        user_kb_context = fetch_user_kb_context_sync(
            project_id=str(context.get("project_id") or ""),
            query=f"{project_name} 取证 扣分 评价依据",
            step_code="step4",
        )
    except Exception:  # noqa: BLE001
        user_kb_context = ""

    prompt = _build_customize_key_points_prompt(
        project_name=project_name,
        project_core_content=project_core,
        rows=rows,
        admin_prompt=admin_prompt,
        admin_kb=admin_kb,
        user_kb_context=user_kb_context,
    )
    configs = filter_configs_by_compare_models(
        read_model_configs(context),
        list(context.get("compare_models") or []),
        bool(context.get("enable_multi_model", False)),
    )

    customized: dict[str, str] = {}
    error_message = ""
    chosen_model = ""
    model_hits = 0

    try:
        drafts = _await_in_sync(
            generate_drafts_async(
                prompt=prompt,
                system_prompt=admin_prompt
                or "你是政府绩效评价专家，输出严格 JSON。",
                configs=configs,
            )
        )
        winner = first_successful_draft(drafts)
        if winner is None:
            raise RuntimeError(collect_errors(drafts) or "所有模型调用均失败")
        chosen_model = winner.get("model_name", "")
        parsed = parse_json_object(winner.get("draft", "")) or {}
        items = parsed.get("rows") if isinstance(parsed, dict) else None
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                sid = str(item.get("id") or "").strip()
                txt = str(item.get("key_points") or "").strip().replace("\n", " ")
                if sid and txt and sid in fallback_map:
                    customized[sid] = txt
                    model_hits += 1
    except Exception as exc:  # noqa: BLE001
        error_message = f"取证扣分细则模型调用失败，已回退到规则模板：{exc}"

    # 缺失项一律 fallback，保证渲染时不会出现空格。
    for sid, fb in fallback_map.items():
        customized.setdefault(sid, fb)

    # 同步把生成结果回写到 scored_tree 节点的 key_points，方便 step5/step6 直接读取。
    new_tree = json.loads(json.dumps(tree))
    for l1 in new_tree:
        for l2 in l1.get("level2", []) or []:
            for l3 in l2.get("level3", []) or []:
                lid = str(l3.get("id", "")).strip()
                if lid in customized:
                    l3["key_points"] = customized[lid]

    if error_message:
        source: Literal["model", "fallback", "mixed", ""] = "fallback"
    elif model_hits == 0:
        source = "fallback"
    elif model_hits < len(fallback_map):
        source = "mixed"
    else:
        source = "model"

    return {
        "scored_tree": new_tree,
        "customized_key_points": customized,
        "key_points_source": source,
        "status": "key_points_ready",
        "updated_at": _now_iso(),
        "error": error_message,
        "messages": [
            AIMessage(
                content=(
                    f"已为 {len(fallback_map)} 条三级指标生成取证扣分细则"
                    + (f"（采用模型：{chosen_model}，模型贡献 {model_hits} 条，其余使用模板）"
                       if chosen_model else "")
                    + ("，已部分回退到规则模板。" if error_message else "。")
                )
            )
        ],
    }


def assign_scores(state: Step4State, runtime: Any = None) -> Step4State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    tree = json.loads(json.dumps(state.get("scored_tree") or []))
    mode = state.get("assign_mode") or "llm"
    project_name = state.get("project_name", "未命名项目")
    customized = state.get("customized_key_points") or {}

    if mode == "manual":
        tree = _apply_manual_l3(tree, dict(state.get("manual_l3_scores") or {}))
    else:
        multi = bool(context.get("enable_multi_model", False))
        models = list(context.get("compare_models", [])) or [context.get("model_name") or "默认模型"]
        if multi:
            comps = _simulate_model_score_drafts(project_name, tree, models, customized)
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
    md = _render_scores_markdown(project_name, tree, rep, customized)
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
    customized = state.get("customized_key_points") or {}
    md = _render_scores_markdown(project_name, tree, rep, customized)
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
    """整数均分并回卷，用于尝试修复一/三维度守恒（确保所有分值为整数且合计 100）。"""
    tree = json.loads(json.dumps(state.get("scored_tree") or []))
    l3s = _iter_l3(tree)
    n = len(l3s)
    if n:
        scores = _distribute_integer_scores(l3s, int(SUM_TARGET))
        for row, sc in zip(l3s, scores):
            row["score"] = sc
    tree = _rollup(tree)
    return {
        "scored_tree": tree,
        "normalize_used": True,
        "status": "auto_normalized",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="已执行三级整数均分归一化并回卷，将重新校验。")],
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
    customized = state.get("customized_key_points") or {}
    if not rep.get("hard_pass"):
        return {
            "status": "blocked",
            "error": "校验未通过，禁止定稿。",
            "messages": [AIMessage(content="一至三维校验未通过前不可确认分值，请先修正。")],
            "updated_at": _now_iso(),
        }
    md = _render_scores_markdown(project_name, tree, rep, customized)
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
    graph.add_node("customize_key_points", customize_key_points_node)
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
    graph.add_edge("build_scored_tree", "customize_key_points")
    graph.add_edge("customize_key_points", "assign_scores")
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
