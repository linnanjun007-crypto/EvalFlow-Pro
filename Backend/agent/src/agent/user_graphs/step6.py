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

    compressed_rubrics: dict[str, str]
    invariants_report: list[str]

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


def _md_escape(text: str) -> str:
    return str(text or "").replace("|", "/").replace("\n", "<br/>").replace("\r", "")


_BENEFIT_TAGS: tuple[str, ...] = ("效益", "社会效益", "经济效益", "生态效益", "可持续")
_BENEFIT_KEYWORDS: tuple[str, ...] = (
    "效益", "满意", "受益", "群众", "村民", "镇村", "村容", "村貌", "结对",
    "帮扶", "产业", "民生", "口碑", "影响力", "长效", "示范",
)


def _is_benefit_row(row: dict[str, Any]) -> bool:
    """判断一条三级指标是否属于"效益/社会效益"环节。前 5 类内部审计指标必须被剔除。"""
    tag = str(row.get("tag") or "").strip()
    if any(t in tag for t in _BENEFIT_TAGS):
        return True
    blob = " ".join(
        str(row.get(k) or "") for k in ("l1", "l2", "l3", "l1_name", "l2_name", "l3_name")
    )
    return any(kw in blob for kw in _BENEFIT_KEYWORDS)


_TOPIC_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("产业", "经济", "增收", "投入产出", "收入"), "产业带动与乡村经济增收"),
    (("村容", "村貌", "环境", "卫生"), "村容村貌与人居环境改善"),
    (("结对", "长效", "可持续", "机制"), "校地长效结对与持续帮扶"),
    (("作风", "纪律", "形象", "学生"), "突击队学生作风纪律与精神面貌"),
    (("满意", "口碑", "群众", "村民"), "受帮扶群众的获得感与满意度"),
    (("文化", "宣传", "示范", "影响力"), "项目文化宣传与示范带动效果"),
    (("民生", "服务", "公共"), "民生服务质量与公共事务参与"),
)


def _slug_topic_for_l3(row: dict[str, Any]) -> str:
    """根据三级指标名称/二级名称推断要塞进 [xxxx] 的「大白话」主题（仅作兜底，模型缺位时使用）。"""
    blob = " ".join(
        str(row.get(k) or "") for k in ("l3", "l2", "l1", "l3_name", "l2_name", "l1_name")
    )
    for keywords, topic in _TOPIC_RULES:
        if any(kw in blob for kw in keywords):
            return topic
    return f"{row.get('l3') or row.get('l3_name') or '受帮扶地区发展'}的实际效果"


def _local_compress_rubric(rubric: dict[str, str], score: float) -> str:
    """规则模板：将四档评分标准压缩为单行紧凑文本（模型回退路径）。"""
    def _short(text: str, limit: int = 36) -> str:
        text = (text or "").strip().replace("\n", " ")
        return text if len(text) <= limit else text[: limit - 1] + "…"
    return (
        f"优≥{score * 0.9:.0f}分:{_short(rubric.get('优秀', ''))};"
        f"良{score * 0.75:.0f}-{score * 0.89:.0f}:{_short(rubric.get('良好', ''))};"
        f"合{score * 0.6:.0f}-{score * 0.74:.0f}:{_short(rubric.get('合格', ''))};"
        f"差≤{score * 0.59:.0f}:{_short(rubric.get('不合格', ''))}"
    )


def _build_compress_prompt(rows: list[dict[str, Any]]) -> str:
    """要求 LLM 把每条三级指标的 4 档评分标准压成一行核心扣分/拿分条件。"""
    blob_lines: list[str] = []
    for row in rows:
        rb = row.get("rubric") or {}
        blob_lines.append(
            f"- id={row['id']} | {row['l3']} | 满分={row['score']:.0f}\n"
            f"  优秀: {rb.get('优秀', '')}\n"
            f"  良好: {rb.get('良好', '')}\n"
            f"  合格: {rb.get('合格', '')}\n"
            f"  不合格: {rb.get('不合格', '')}"
        )
    return "\n".join(
        [
            "你是绩效评价表排版工程师。请将每条三级指标的「四档评分标准」压缩成一行紧凑文本，",
            "仅保留最核心的扣分条件与拿分阈值，确保最终能塞进 Markdown 表格单元格。",
            "",
            "强制格式（每条一行，禁止换行/项目符号）：",
            "优≥X分:<拿分关键条件>;良Y-Z分:<轻度扣分情形>;合A-B分:<明显扣分情形>;差≤C分:<重度扣分情形>",
            "",
            "要求：",
            "1. 每档文字 ≤ 30 个汉字，必须出现具体材料/百分比/触发条件，不允许「略」「相关材料齐全」等占位；",
            "2. 分数阈值 X/Y/Z/A/B/C 用整数表示，符合 90%/75%/60% 的分档比例；",
            "3. 严格输出 JSON：",
            "{",
            '  "rows": [ {"id": "<id>", "compressed": "<一行紧凑文本>"} ]',
            "}",
            "",
            "待压缩的三级指标：",
            *blob_lines,
        ]
    )


def _render_framework(
    project_name: str,
    tree: list[L1ScoreRow],
    standards: list[ScoreStandard],
    compressed_rubrics: dict[str, str] | None = None,
) -> str:
    """以 6 列表格形式渲染绩效评价指标体系。

    列：一级指标 / 二级指标 / 三级指标 / 分值 / 指标解释 / 评分标准。
    一/二级指标在该组首行渲染，其余行留空，以保持可读性；分值在每行体现三级指标分值。
    评分标准列：优先使用 ``compressed_rubrics``（一行紧凑文本），否则回退到原始四档。
    """

    rubric_index: dict[str, ScoreStandard] = {
        str(s.get("id", "")): s for s in standards if s.get("id")
    }
    explanation_index: dict[str, str] = {
        str(s.get("id", "")): str(s.get("key_points") or "")
        for s in standards
        if s.get("id")
    }
    compressed_rubrics = compressed_rubrics or {}

    lines = [
        f"# 《{project_name} — 绩效评价指标体系》",
        "",
        f"- 生成时间：{now_iso()}",
        "",
        "## 指标体系表",
        "",
        "| 一级指标 | 二级指标 | 三级指标 | 分值 | 指标解释 | 评分标准 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    last_l1: str = ""
    last_l2: str = ""
    for l1 in tree:
        l1_score = float(l1.get("score", 0) or 0)
        l1_name = str(l1.get("name", ""))
        l1_label = f"{l1_name}（{l1_score:.0f} 分）"
        for l2 in l1.get("level2", []) or []:
            l2_score = float(l2.get("score", 0) or 0)
            l2_name = str(l2.get("name", ""))
            l2_label = f"{l2_name}（{l2_score:.0f} 分）"
            l3_list = l2.get("level3", []) or []
            if not l3_list:
                continue
            for l3 in l3_list:
                row_id = str(l3.get("id", ""))
                l3_name = str(l3.get("name", ""))
                l3_score = float(l3.get("score", 0) or 0)
                explanation = explanation_index.get(row_id) or str(l3.get("key_points") or "")
                rubric_dict = rubric_index.get(row_id, {}).get("rubric") or {}
                if compressed_rubrics.get(row_id):
                    rubric_text = compressed_rubrics[row_id]
                else:
                    rubric_text = _local_compress_rubric(rubric_dict, l3_score)
                l1_cell = l1_label if l1_name != last_l1 else ""
                l2_cell = l2_label if (l2_name != last_l2 or l1_name != last_l1) else ""
                last_l1 = l1_name
                last_l2 = l2_name
                lines.append(
                    "| {l1} | {l2} | {l3} | {score} | {expl} | {rubric} |".format(
                        l1=_md_escape(l1_cell),
                        l2=_md_escape(l2_cell),
                        l3=_md_escape(l3_name),
                        score=f"{l3_score:.0f}",
                        expl=_md_escape(explanation or "（暂无解释）"),
                        rubric=_md_escape(rubric_text),
                    )
                )
    lines.append("")
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
        f" | 分值={row['score']:.0f} | 维度={row.get('tag', '效益')}"
        f" | 参考主题（仅作兜底，可重写）=「{_slug_topic_for_l3(row)}」"
        for row in rows
    )
    feedback_block = (
        f"\n【人工反馈意见（请按此调整本次输出）】\n{review_feedback.strip()}\n"
        if review_feedback.strip()
        else ""
    )
    instructions = [
        "你是百千万工程突击队项目「满意度调查问卷」设计专家。请仅针对【效益环节 / 经济效益与社会效益】",
        "为受帮扶的「镇村两委、当地村民、受帮扶群众」设计真正能看懂的配套问卷。",
        "",
        "【刚性约束】",
        "1. 数量：必须生成 4~6 道题，不允许更少也不允许更多；",
        "   —— 即便上方只列出 1 条效益三级指标，也必须围绕「经济、民生、村貌、学生作风、长效结对、",
        "   文化宣传与示范带动」等多个侧面拆出 4~6 道不同主题的题目，绝不能因指标少而少出题；",
        "2. 题型：100% 单选题，禁止填空、多选、是否题、矩阵题；",
        "3. 题干句式严格锁死为：「您认为本次高校突击队项目对 [xxxx] 的影响是否显著？」",
        "   —— 不得改写、不得删减、不得添加额外解释；",
        "4. [xxxx] 必须是大白话主题词（≤14 字），如：产业带动、村容村貌改善、长效结对、",
        "   学生作风纪律、村民获得感、文化宣传与示范带动 等；不允许出现「指标」「绩效」「效益维度」等术语；",
        f"5. 选项严格固定为：{' / '.join(LIKERT_OPTIONS)}（顺序不得调换）；",
        "6. 不同题之间 [xxxx] 主题不得重复，需覆盖经济、民生、村貌、学生作风、长效机制等不同侧面；",
        "7. 当上方指标仅 1 条时，所有题目的 indicator_id 都填写该唯一指标的 id 即可，但 topic 必须各不相同。",
        "",
        "【关于「参考主题」字段的使用规则】",
        "- 它只是一个兜底建议，目的是防止模型完全失败时仍能渲染出问卷；",
        "- 你必须优先基于项目核心内容、用户知识库与反馈意见，",
        "  自行提炼一个比参考主题更贴切、更朴素的大白话短语作为 [xxxx]；",
        "- 仅当项目内容稀薄、确实无法提炼时，才允许直接复用「参考主题」原文；",
        "- 即便复用，也尽量做轻度润色（如简化为更通俗的口语化短语）。",
        "",
        "输出格式（严格 JSON，不要任何额外文字）：",
        "{",
        '  "items": [',
        '    {"id": "Q001", "indicator_id": "L3-…", "topic": "<填进 [xxxx] 的大白话主题>",',
        '     "question": "您认为本次高校突击队项目对 <topic> 的影响是否显著？",',
        '     "options": ["非常不满意","不满意","一般","满意","非常满意"]}',
        "  ]",
        "}",
    ]
    return "\n".join(
        [
            preamble.strip(),
            f"项目名称：{project_name}",
            "项目核心内容：",
            (project_core_content or "（未提供，请围绕受帮扶镇村的真实获得感设计问题）").strip(),
            "",
            "可参考的【效益环节】三级指标列表（已自动剔除立项/论证/资金/采购/产出等内部审计指标）：",
            indicator_blob or "（空）",
            feedback_block,
            "",
            *instructions,
        ]
    )


_QUESTION_TEMPLATE = "您认为本次高校突击队项目对 {topic} 的影响是否显著？"


def _normalize_question_text(question: str, topic: str) -> str:
    """无论模型返回什么，都强制套回锁死句式。"""
    topic_clean = (topic or "").strip().strip("[]【】「」 ").rstrip("？?。.")
    if not topic_clean:
        # 题干里若已含"对 …的影响"，可尝试提取
        marker = "对 "
        end_marker = " 的影响"
        if marker in question and end_marker in question:
            seg = question.split(marker, 1)[1].split(end_marker, 1)[0].strip()
            topic_clean = seg.strip("[]【】「」 ")
    if not topic_clean:
        topic_clean = "受帮扶地区发展"
    return _QUESTION_TEMPLATE.format(topic=topic_clean), topic_clean


def _fallback_question(row: dict[str, Any], idx: int) -> QuestionnaireItem:
    topic = _slug_topic_for_l3(row)
    return {
        "id": f"Q{idx:03d}",
        "indicator_id": str(row.get("id", "")),
        "indicator_name": f"{row.get('l1', '')} / {row.get('l2', '')} / {row.get('l3', '')}",
        "question": _QUESTION_TEMPLATE.format(topic=topic),
        "options": list(LIKERT_OPTIONS),
        "source_note": f"规则模板（主题：{topic}）",
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
    """解析模型输出并强制套用锁死句式、限定 4~6 道、主题去重。

    主题优先级：模型给出的 topic（润色后） → 题干中能解析出的 topic →
    ``_slug_topic_for_l3`` 规则兜底。规则只是最后的安全网，不是首选。
    """

    parsed = parse_json_object(raw_text) or {}
    items_raw = parsed.get("items") if isinstance(parsed, dict) else None
    rows_by_id: dict[str, dict[str, Any]] = {str(r.get("id", "")): r for r in rows}

    items: list[QuestionnaireItem] = []
    used_topics: set[str] = set()
    counter = 1

    if isinstance(items_raw, list):
        for item in items_raw:
            if not isinstance(item, dict):
                continue
            indicator_id = str(item.get("indicator_id") or "").strip()
            row = rows_by_id.get(indicator_id) or (rows[len(items)] if len(items) < len(rows) else None)
            if row is None:
                continue
            topic_raw = str(item.get("topic") or "").strip()
            question_raw = str(item.get("question") or "").strip()
            # 优先用模型 topic / 题干里能解析出来的 topic；只有都没有才落到规则兜底。
            primary_topic = topic_raw or ""
            question, topic = _normalize_question_text(question_raw, primary_topic)
            if not topic or topic in used_topics:
                # 撞车或为空：再用规则兜底，挤一个不冲突的主题出来。
                fallback_topic = _slug_topic_for_l3(row)
                if fallback_topic and fallback_topic not in used_topics:
                    topic = fallback_topic
                    question = _QUESTION_TEMPLATE.format(topic=topic)
                else:
                    continue
            used_topics.add(topic)
            options = _normalize_options(item.get("options"))
            if len(options) != 5:
                options = list(LIKERT_OPTIONS)
            note_source = "模型生成" if topic_raw and topic == topic_raw.strip("[]【】「」 ").rstrip("？?。.") else "模型生成 + 规则兜底"
            items.append(
                {
                    "id": str(item.get("id") or f"Q{counter:03d}").strip(),
                    "indicator_id": str(row.get("id", "")),
                    "indicator_name": f"{row.get('l1', '')} / {row.get('l2', '')} / {row.get('l3', '')}",
                    "question": question,
                    "options": options,
                    "source_note": f"{note_source}（主题：{topic}）",
                    "model_name": model_name,
                }
            )
            counter += 1

    # 模型给的题不足 4 道时，补齐至 4。备用主题池保证即便 rows 只有 1 条也能拆出多道题。
    default_pool: tuple[str, ...] = (
        "产业带动与乡村经济增收",
        "村容村貌与人居环境改善",
        "校地长效结对与持续帮扶",
        "突击队学生作风纪律与精神面貌",
        "受帮扶群众的获得感与满意度",
        "项目文化宣传与示范带动效果",
        "民生服务质量与公共事务参与",
    )
    rule_topic_for_rows: list[str] = [_slug_topic_for_l3(row) for row in rows]
    seed_row = rows[0] if rows else {"id": "", "l1": "", "l2": "", "l3": ""}
    extras: list[str] = list(rule_topic_for_rows) + list(default_pool)
    extras_iter = iter(extras)
    while len(items) < 4:
        topic = next(extras_iter, None)
        if topic is None:
            break
        if topic in used_topics:
            continue
        used_topics.add(topic)
        # 优先关联到能匹配此主题的 row，匹配不到就退到 seed_row
        match_row = next(
            (r for r in rows if _slug_topic_for_l3(r) == topic),
            seed_row,
        )
        items.append(
            {
                "id": f"Q{counter:03d}",
                "indicator_id": str(match_row.get("id", "")),
                "indicator_name": f"{match_row.get('l1', '')} / {match_row.get('l2', '')} / {match_row.get('l3', '')}",
                "question": _QUESTION_TEMPLATE.format(topic=topic),
                "options": list(LIKERT_OPTIONS),
                "source_note": f"规则补齐（主题：{topic}）",
                "model_name": "rule-fallback",
            }
        )
        counter += 1

    # 多于 6 道时按主题去重后截断
    if len(items) > 6:
        items = items[:6]
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
    # 关键：每次 validate 都把上一轮残留的产物清空，避免 MemorySaver 把旧 framework / 旧问卷
    # 直接带回，让"重新生成"形同虚设。
    return {
        "project_name": name,
        "final_indicator_framework_markdown": "",
        "questionnaire_items": [],
        "questionnaire_draft": "",
        "model_comparisons": [],
        "content_text": "",
        "export_payload": "",
        "review_round": 0,
        "created_at": state.get("created_at") or now_iso(),
        "updated_at": now_iso(),
        "status": "basis_ok",
        "messages": [AIMessage(content=f"已接收指标体系、分值与评分标准，项目：{name}。")],
    }


def route_after_basis(state: Step6State) -> str:
    return "end" if state.get("status") == "failed" else "continue"


# ---------------------------------------------------------------------------
# 硬约束：分值闭环 / L3 颗粒度 / 解释 & rubric 必填
# ---------------------------------------------------------------------------


_DEFAULT_RUBRIC_HINTS = {
    "优秀": "材料齐全、流程规范、数据支撑充分，达成度 ≥ 90%",
    "良好": "材料基本齐全、流程合规但存在轻微瑕疵，达成度 75%–89%",
    "合格": "材料/流程存在缺漏或轻度违规，扣分不超过 30%，达成度 60%–74%",
    "不合格": "关键材料缺失或严重违规扣分 > 40%，达成度 < 60%",
}


def _round2(x: float) -> float:
    return round(float(x or 0) + 1e-9, 2)


def _balance_children(children: list[dict[str, Any]], target: float, key: str = "score") -> None:
    """按当前权重把 children[*][key] 之和严格配平到 target，最后一项用减法吸差，确保 sum == target。"""
    total = sum(float(c.get(key, 0) or 0) for c in children)
    if total <= 0 or not children:
        if children:
            avg = _round2(target / len(children))
            for c in children[:-1]:
                c[key] = avg
            children[-1][key] = _round2(target - avg * (len(children) - 1))
        return
    accum = 0.0
    for c in children[:-1]:
        share = _round2(target * (float(c.get(key, 0) or 0) / total))
        c[key] = share
        accum += share
    children[-1][key] = _round2(target - accum)


def _ensure_rubric_full(rb: dict[str, str] | None, score: float) -> dict[str, str]:
    rb = dict(rb or {})
    for tier in ("优秀", "良好", "合格", "不合格"):
        if not str(rb.get(tier, "")).strip():
            rb[tier] = _DEFAULT_RUBRIC_HINTS[tier]
    return rb


def enforce_invariants(state: Step6State) -> Step6State:
    """硬约束：分值闭环 + L3 颗粒度 + 解释/rubric 必填。

    - L3 之和必须严格等于其 L2 的 score；L2 之和必须严格等于其 L1 的 score；
      不闭合时按各 child 当前权重 scale，最后一项做减法吸差。
    - 每个 L2 至少 2 个 L3 观测点；不足则按现有 L3 名拆出 "—观测点2/3"，平均分配剩余分值。
    - L3 的 key_points / 二级解释为空时，用 L2 + L3 名拼默认提示。
    - score_standards 中每条 rubric 必须含 优秀/良好/合格/不合格 四档，缺档用通用兜底文案补齐。
    """

    tree = json.loads(json.dumps(state.get("scored_tree") or []))
    standards: list[dict[str, Any]] = list(state.get("score_standards") or [])
    rubric_index = {str(s.get("id", "")): s for s in standards}
    invariants_report: list[str] = []

    # --- 三级颗粒度 + 三级分值闭环到 L2 ---
    for l1 in tree:
        for l2 in l1.get("level2", []) or []:
            l3_list = list(l2.get("level3") or [])
            if len(l3_list) < 2:
                base = l3_list[0] if l3_list else {
                    "id": f"L3-AUTO-{l2.get('name', '')}",
                    "name": f"{l2.get('name', '')}—观测点1",
                    "score": float(l2.get("score") or 0),
                    "key_points": "",
                    "rubric": {},
                }
                if not l3_list:
                    l3_list = [base]
                add = {
                    "id": f"{base.get('id') or 'L3-AUTO'}-2",
                    "name": f"{l2.get('name', '')}—观测点2",
                    "score": _round2(float(l2.get("score") or 0) / 2),
                    "key_points": str(base.get("key_points") or ""),
                    "rubric": dict(base.get("rubric") or {}),
                }
                l3_list.append(add)
                invariants_report.append(
                    f"[L2 颗粒度] 『{l2.get('name')}』原仅 1 项 L3，已自动补出『{add['name']}』。"
                )
                l2["level3"] = l3_list
            l2_score = float(l2.get("score") or 0)
            _balance_children(l3_list, l2_score, key="score")
        # --- 二级闭环到 L1 ---
        l1_score = float(l1.get("score") or 0)
        _balance_children(l1.get("level2", []) or [], l1_score, key="score")

    # --- L3 解释 / rubric 兜底；并把矫正后的 score 同步进 score_standards ---
    for l1 in tree:
        for l2 in l1.get("level2", []) or []:
            for l3 in l2.get("level3") or []:
                lid = str(l3.get("id", ""))
                if not str(l3.get("key_points") or "").strip():
                    l3["key_points"] = (
                        f"该指标考察『{l2.get('name')}』在『{l1.get('name')}』中的执行实况，"
                        "重点核查台账、流程合规性与目标达成度。"
                    )
                    invariants_report.append(f"[L3 解释] 『{l3.get('name')}』缺指标解释，已补默认。")
                rb_full = _ensure_rubric_full(l3.get("rubric") or {}, float(l3.get("score") or 0))
                l3["rubric"] = rb_full
                std = rubric_index.get(lid)
                if std is None:
                    std = {
                        "id": lid,
                        "l1_name": l1.get("name"),
                        "l2_name": l2.get("name"),
                        "l3_name": l3.get("name"),
                        "score": l3.get("score"),
                        "key_points": l3.get("key_points"),
                        "rubric": rb_full,
                        "approved": False,
                        "model_name": "auto-enforce",
                    }
                    standards.append(std)
                    rubric_index[lid] = std
                    invariants_report.append(f"[score_standards] 『{l3.get('name')}』缺评分标准，已自动补全四档。")
                else:
                    std["score"] = l3.get("score")
                    std["key_points"] = std.get("key_points") or l3.get("key_points")
                    std["rubric"] = _ensure_rubric_full(std.get("rubric") or {}, float(l3.get("score") or 0))

    return {
        "scored_tree": tree,
        "score_standards": standards,
        "invariants_report": invariants_report,
        "status": "invariants_enforced",
        "updated_at": now_iso(),
        "messages": (
            [AIMessage(content=f"已应用 {len(invariants_report)} 条硬约束修复。")] if invariants_report
            else [AIMessage(content="指标体系已通过分值闭环 / 颗粒度 / 解释 / rubric 四项硬约束。")]
        ),
    }


def compress_rubrics_node(state: Step6State, runtime: Any = None) -> Step6State:
    """调用 LLM 把 step5 评分标准压缩成单行紧凑文本，确保 step6 表格可直接打印。

    模型返回 ``{"rows": [{"id": ..., "compressed": ...}]}``；任何条目缺失或解析失败
    都会用 ``_local_compress_rubric`` 兜底，确保最终 dict 一定齐全。
    """

    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    standards = state.get("score_standards") or []
    rows_for_prompt: list[dict[str, Any]] = []
    fallback_map: dict[str, str] = {}
    for s in standards:
        sid = str(s.get("id", "")).strip()
        if not sid:
            continue
        rb = s.get("rubric") or {}
        score = float(s.get("score", 0) or 0)
        rows_for_prompt.append(
            {
                "id": sid,
                "l3": str(s.get("l3_name", "")),
                "score": score,
                "rubric": rb,
            }
        )
        fallback_map[sid] = _local_compress_rubric(rb, score)

    if not rows_for_prompt:
        return {
            "compressed_rubrics": {},
            "status": "rubrics_compressed",
            "updated_at": now_iso(),
        }

    prompt = _build_compress_prompt(rows_for_prompt)
    configs = filter_configs_by_compare_models(
        read_model_configs(context),
        list(context.get("compare_models") or []),
        bool(context.get("enable_multi_model", False)),
    )

    compressed: dict[str, str] = {}
    error_message = ""
    chosen_model = ""

    try:
        drafts = await_in_sync(
            generate_drafts_async(
                prompt=prompt,
                system_prompt="你是政府绩效评价表排版工程师，输出严格 JSON。",
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
                txt = str(item.get("compressed") or "").strip().replace("\n", " ")
                if sid and txt:
                    compressed[sid] = txt
    except Exception as exc:  # noqa: BLE001
        error_message = f"压缩评分标准时模型调用失败，已回退到规则模板：{exc}"

    # 缺失项一律 fallback，保证最终表格的"评分标准"列不会留空
    for sid, fb in fallback_map.items():
        compressed.setdefault(sid, fb)

    return {
        "compressed_rubrics": compressed,
        "status": "rubrics_compressed",
        "updated_at": now_iso(),
        "error": error_message,
        "messages": [
            AIMessage(
                content=(
                    f"已压缩 {len(compressed)} 条评分标准为表格紧凑文本"
                    + (f"（采用模型：{chosen_model}）" if chosen_model else "")
                    + ("，部分条目使用规则模板。" if error_message else "。")
                )
            )
        ],
    }


def build_framework(state: Step6State) -> Step6State:
    project_name = state.get("project_name", "未命名项目")
    tree = json.loads(json.dumps(state.get("scored_tree") or []))
    standards = json.loads(json.dumps(state.get("score_standards") or []))
    compressed = state.get("compressed_rubrics") or {}
    md = _render_framework(project_name, tree, standards, compressed)
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
    all_rows = _flatten_framework(
        state.get("scored_tree") or [],
        state.get("score_standards") or [],
    )
    # 强制只保留效益环节指标，过滤掉立项/论证/资金/采购/产出等内部审计指标。
    rows = [r for r in all_rows if _is_benefit_row(r)]
    if not rows:
        return {
            "questionnaire_items": [],
            "questionnaire_draft": "（指标列表中没有「效益环节」三级指标，无法生成满意度问卷。）",
            "status": "questionnaire_empty",
            "updated_at": now_iso(),
            "messages": [AIMessage(content="未发现可生成问卷的效益环节三级指标。")],
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
    graph.add_node("enforce_invariants", enforce_invariants)
    graph.add_node("compress_rubrics", compress_rubrics_node)
    graph.add_node("build_framework", build_framework)
    graph.add_node("generate_questionnaire", generate_questionnaire)
    graph.add_node("review_questionnaire", review_questionnaire)
    graph.add_node("finalize_framework", finalize_framework)

    graph.add_edge(START, "validate_basis")
    graph.add_conditional_edges(
        "validate_basis",
        route_after_basis,
        {"continue": "enforce_invariants", "end": END},
    )
    graph.add_edge("enforce_invariants", "compress_rubrics")
    graph.add_edge("compress_rubrics", "build_framework")
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
