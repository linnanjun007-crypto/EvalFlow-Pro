"""Step 3 graph for EvalFlow Pro — 生成指标体系.

严格以第二步产出的 **项目核心内容** 为唯一依据，
结合 Prompt / 知识库，实现：

- 一级 / 二级 / 三级指标（可选四级 ``indicator_depth=4``）；
- 指标体系类型、自有 JSON 一键导入、模板库一键导入；
- 导入后支持「一键优化」骨架（LLM 基于项目核心内容优化）；
- 支持按单个二级指标优化（LLM 对照核心内容校对）；
- 按二级指标 **逐个** 生成三级指标及解释，每批支持人机协同与多模型对比；
- 满意后写入成品区字段，全部二级完成后进入定稿状态。

**与 Step 2 的衔接（必填）**

调用本图时请在 state 中传入第二步定稿内容，二选一（优先前者）：

- ``project_core_content``：建议直接传入 Step 2 的 ``final_core_content``；
- 或 ``final_core_content``：与 Step 2 字段名一致时可直接复用。

未提供核心内容时，本图将失败并提示，避免脱离第二步依据。
"""

from __future__ import annotations

import asyncio
import json
import operator
import re
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, TypedDict, cast

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from .step1 import (
    _call_openai_compatible_model,
    _call_openai_compatible_model_async,
    _normalize_temperature,
    _read_model_config,
    _read_model_configs,
)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

SystemType = Literal[
    "项目支出指标体系",
    "部门整体指标体系",
    "下级政府整体运行指标体系",
    "专项债指标体系",
    "社保基金指标体系",
    "自定义",
]

ImportMode = Literal["none", "own", "template"]
SkeletonOptimizeMode = Literal["none", "one_click", "per_level2"]
IndicatorDepth = Literal[3, 4]


class Level4Entry(TypedDict, total=False):
    code: str
    name: str
    explanation: str


class Level3Entry(TypedDict, total=False):
    code: str
    name: str
    explanation: str
    level4: list[Level4Entry]


class FlatL2Task(TypedDict, total=False):
    """Work queue: one second-level indicator per row (逐个二级拆解)."""

    level1_name: str
    level2_name: str
    target_l3_count: int
    l3_section_markdown: str


class ModelComparison(TypedDict):
    model_name: str
    label: str
    draft: str
    error: str


class Step3State(TypedDict, total=False):
    """LangGraph state for Step 3."""

    project_name: str
    # --- Step 2 handoff (required) ---
    project_core_content: str
    final_core_content: str

    system_type: SystemType
    indicator_depth: IndicatorDepth

    import_mode: ImportMode
    imported_indicator_json: str
    template_id: str

    skeleton_optimize_mode: SkeletonOptimizeMode
    per_optimize_level2_name: str

    # Skeleton editing
    skeleton_edit_action: Literal["add_l1", "remove_l1", "add_l2", "remove_l2", "edit_l1", "edit_l2", "set_l3_count", ""]
    skeleton_edit_payload: str

    flat_l2_tasks: list[FlatL2Task]
    active_l2_index: int

    l3_active_draft: str
    l3_model_comparisons: list[ModelComparison]

    final_indicator_markdown: str
    export_filename: str
    export_payload: str

    review_round: int
    review_mode: Literal["modify", "approve"]
    review_feedback: str

    core_basis_digest: str
    messages: Annotated[list[BaseMessage], operator.add]
    status: str
    error: str
    created_at: str
    updated_at: str


class Step3Context(TypedDict, total=False):
    project_id: str
    user_id: str
    model_name: str
    compare_models: list[str]
    enable_multi_model: bool
    system_prompt_stub: str
    knowledge_stub: str
    output_dir: str
    workflow_state: dict[str, Any]
    chat_mode: bool


SYSTEM_TYPES: tuple[str, ...] = (
    "项目支出指标体系",
    "部门整体指标体系",
    "下级政府整体运行指标体系",
    "专项债指标体系",
    "社保基金指标体系",
    "自定义",
)

# 非「自定义」时给出的默认一级 + 二级骨架
TYPE_DEFAULT_TASKS: dict[str, list[tuple[str, str, int]]] = {
    "项目支出指标体系": [
        ("决策环节", "项目立项与批复合规性", 3),
        ("决策环节", "可行性论证与目标设定", 3),
        ("过程环节", "资金到位与拨付", 3),
        ("过程环节", "政府采购与合同管理", 3),
        ("产出环节", "数量与质量完成情况", 3),
        ("效益环节", "经济效益与社会效益", 3),
    ],
    "部门整体指标体系": [
        ("履职基础", "基本运行保障", 3),
        ("履职效果", "重点工作完成情况", 3),
        ("能力建设", "内部管理与监督", 3),
        ("社会评价", "服务对象满意度", 3),
    ],
    "下级政府整体运行指标体系": [
        ("财政运行", "预算执行与库款保障", 3),
        ("公共服务", "教育医疗卫生等供给", 3),
        ("生态环境", "污染防治与绿色发展", 3),
        ("风险防控", "债务与金融风险", 3),
    ],
    "专项债指标体系": [
        ("项目准备", "一案两书与合规手续", 3),
        ("融资平衡", "收益覆盖本息", 3),
        ("建设运营", "工程进度与质量", 3),
        ("风险与偿债", "资金使用与还本付息", 3),
    ],
    "社保基金指标体系": [
        ("基金运行", "收支平衡与结余", 3),
        ("参保扩面", "覆盖率与稽核", 3),
        ("待遇发放", "及时足额与内控", 3),
        ("基金安全", "违规冒领与风控", 3),
    ],
}

# 模板库
TEMPLATE_LIBRARY: dict[str, list[tuple[str, str, int]]] = {
    "classic_performance_v1": [
        ("决策", "依据充分与程序合规", 3),
        ("过程", "资金管理与组织实施", 3),
        ("产出", "产出数量与质量", 3),
        ("效益", "经济、社会、环境效益", 3),
    ],
    "classic_procurement_v1": [
        ("决策", "采购需求与审批", 3),
        ("过程", "招标投标与合同履约", 3),
        ("产出", "交付与验收", 3),
        ("效益", "成本节约与满意度", 3),
    ],
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z"


def _resolve_core_content(state: Step3State) -> str:
    return (state.get("project_core_content") or state.get("final_core_content") or "").strip()


def _core_basis_snippet(core: str, max_chars: int = 3000) -> str:
    core = core.strip()
    if not core:
        return ""
    if len(core) <= max_chars:
        return core
    return core[:max_chars] + "\n\n…（以下省略，生成时仍以完整传入的第二步核心内容为依据。）"


def _digest(core: str, limit: int = 400) -> str:
    one_line = re.sub(r"\s+", " ", core.strip())[:limit]
    return one_line + ("…" if len(core) > limit else "")


def _tasks_from_tuples(rows: list[tuple[str, str, int]]) -> list[FlatL2Task]:
    return [
        {"level1_name": a, "level2_name": b, "target_l3_count": c, "l3_section_markdown": ""}
        for a, b, c in rows
    ]


def _parse_own_import(json_str: str) -> list[FlatL2Task] | None:
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return None
    tasks: list[FlatL2Task] = []
    if isinstance(data, dict) and "tasks" in data:
        arr = data["tasks"]
    elif isinstance(data, list):
        arr = data
    else:
        return None
    for row in arr:
        if not isinstance(row, dict):
            continue
        l1 = row.get("level1") or row.get("l1") or row.get("一级")
        l2 = row.get("level2") or row.get("l2") or row.get("二级")
        n = row.get("target_l3_count") or row.get("n") or 3
        if l1 and l2:
            tasks.append(
                {
                    "level1_name": str(l1),
                    "level2_name": str(l2),
                    "target_l3_count": max(1, min(20, int(n))),
                    "l3_section_markdown": "",
                }
            )
    return tasks or None


def _get_llm_context(runtime: Any) -> dict[str, Any]:
    """Extract LLM configuration from runtime context."""
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    return context if isinstance(context, dict) else {}


def _admin_prompt_and_kb(state: Step3State, context: dict[str, Any]) -> tuple[str, str]:
    admin_prompt = str(
        state.get("admin_system_prompt")
        or context.get("admin_system_prompt")
        or context.get("system_prompt_stub")
        or ""
    ).strip()
    admin_kb = str(
        state.get("admin_knowledge_base")
        or context.get("admin_knowledge_base")
        or context.get("knowledge_stub")
        or ""
    ).strip()
    return admin_prompt, admin_kb


# ---------------------------------------------------------------------------
# LLM prompts
# ---------------------------------------------------------------------------


def _build_system_prompt(admin_prompt: str) -> str:
    if admin_prompt:
        return admin_prompt
    return (
        "你是严谨的政务/财政绩效评价指标体系设计专家。"
        "你精通财政支出绩效评价、部门整体支出评价、政府运行评价、"
        "专项债绩效评价和社保基金绩效评价。"
        "你输出的指标体系必须结构清晰、层级分明、指标可衡量、解释有依据。"
    )


def _build_skeleton_prompt(
    core_content: str,
    system_type: str,
    admin_kb: str,
) -> str:
    kb_section = f"\n\n参考知识库：\n{admin_kb}" if admin_kb else ""
    return f"""请基于以下项目核心内容，为"{system_type}"生成一级和二级指标体系。

## 项目核心内容
{core_content}{kb_section}

## 要求
1. 一级指标控制在3-6个，每个一级指标下包含2-5个二级指标。
2. 一级指标应覆盖决策、过程、产出、效益等维度（如适用）。
3. 二级指标应具体、可衡量，与项目核心内容紧密相关。
4. 指标体系类型为"{system_type}"，请据此调整指标命名风格。

请严格按以下JSON格式输出，不要输出其他内容：
```json
{{
  "tasks": [
    {{"level1": "一级指标名称", "level2": "二级指标名称", "target_l3_count": 3}},
    ...
  ]
}}
```
注意：target_l3_count 为建议的三级指标数量，默认填3。
"""


def _build_l3_generation_prompt(
    core_content: str,
    system_type: str,
    depth: int,
    level1_name: str,
    level2_name: str,
    target_count: int,
    admin_kb: str,
) -> str:
    kb_section = f"\n\n参考知识库：\n{admin_kb}" if admin_kb else ""
    level4_req = ""
    if depth == 4:
        level4_req = "\n5. 每个三级指标下再给出2-3个四级细项（含细项名称和简要解释）。"

    return f"""请基于以下项目核心内容，为指标体系生成三级指标及指标解释。

## 项目核心内容
{core_content}{kb_section}

## 指标体系信息
- 体系类型：{system_type}
- 指标深度：{depth} 级
- 一级指标：{level1_name}
- 二级指标：{level2_name}
- 需要生成的三级指标数量：{target_count} 个

## 要求
1. 严格对照项目核心内容中与「{level2_name}」相关的表述，生成 {target_count} 个三级指标。
2. 每个三级指标包含：指标编码、指标名称、指标解释。
3. 指标解释应说明该指标的衡量目的、数据来源建议、与项目核心内容的关联。
4. 如果项目核心内容未覆盖某些方面，可在解释中标注"建议补充"，但不要凭空编造数据。{level4_req}

请严格按以下JSON格式输出，不要输出其他内容：
```json
{{
  "level3_indicators": [
    {{
      "code": "{level1_name[:2]}-01",
      "name": "三级指标名称",
      "explanation": "指标解释：说明该指标的衡量目的、与项目核心内容的关联、数据来源建议等。",
      "level4": [
        {{"code": "{level1_name[:2]}-01-01", "name": "四级细项名称", "explanation": "细项解释"}}
      ]
    }}
  ]
}}
```
注意：level4 数组仅在指标深度为4级时输出，否则省略。
"""


def _build_optimize_prompt(
    core_content: str,
    system_type: str,
    tasks_json: str,
    per_level2_name: str,
    admin_kb: str,
) -> str:
    kb_section = f"\n\n参考知识库：\n{admin_kb}" if admin_kb else ""
    scope = f"请仅优化二级指标「{per_level2_name}」及其所属的一级指标。" if per_level2_name else "请优化全部的一级和二级指标。"

    return f"""请基于以下项目核心内容，优化现有的指标体系骨架。

## 项目核心内容
{core_content}{kb_section}

## 当前指标体系骨架
```json
{tasks_json}
```

## 要求
1. {scope}
2. 检查一级指标是否完整覆盖项目核心内容的关键维度，如有遗漏请补充。
3. 检查二级指标是否准确对应其一级指标，措辞是否规范，与项目核心内容是否紧密相关。
4. 删除与项目核心内容无关或重复的指标。
5. 调整 target_l3_count 建议值（保持1-20之间）。
6. 体系类型为"{system_type}"，请保持指标命名风格一致。

请严格按以下JSON格式输出优化后的完整指标体系骨架，不要输出其他内容：
```json
{{
  "tasks": [
    {{"level1": "一级指标名称", "level2": "二级指标名称", "target_l3_count": 3}},
    ...
  ]
}}
```
"""


def _build_refine_prompt(
    core_content: str,
    system_type: str,
    level1_name: str,
    level2_name: str,
    current_draft: str,
    feedback: str,
    depth: int,
    admin_kb: str,
) -> str:
    kb_section = f"\n\n参考知识库：\n{admin_kb}" if admin_kb else ""
    level4_req = ""
    if depth == 4:
        level4_req = "\n- 每个三级指标下仍需包含四级细项。"

    return f"""请根据以下修改意见，重新生成三级指标及指标解释。

## 项目核心内容
{core_content}{kb_section}

## 当前二级指标
- 体系类型：{system_type}
- 一级指标：{level1_name}
- 二级指标：{level2_name}
- 指标深度：{depth} 级

## 当前三级指标草案
{current_draft}

## 修改意见
{feedback}

## 要求
1. 严格根据修改意见进行调整，同时保持与项目核心内容的一致性。
2. 保持三级指标的数量和结构合理。{level4_req}
3. 每个三级指标包含：指标编码、指标名称、指标解释。

请严格按以下JSON格式输出，不要输出其他内容：
```json
{{
  "level3_indicators": [
    {{
      "code": "编码",
      "name": "三级指标名称",
      "explanation": "指标解释",
      "level4": []
    }}
  ]
}}
```
"""


# ---------------------------------------------------------------------------
# LLM call helpers
# ---------------------------------------------------------------------------


def _call_llm(
    prompt: str,
    context: dict[str, Any],
    admin_prompt: str = "",
    temperature: float | None = None,
) -> str:
    """Call the primary model with the given prompt."""
    configs = _read_model_configs(context)
    if not configs:
        raise RuntimeError("缺少客户端模型配置：请在模型配置中设置 Base URL、API Key 和模型名。")
    cfg = configs[0]
    return _call_openai_compatible_model(
        base_url=str(cfg["base_url"]),
        api_key=str(cfg["api_key"]),
        model_name=str(cfg["model_name"]),
        prompt=prompt,
        temperature=temperature if temperature is not None else float(cfg.get("temperature", 0.2)),
        system_prompt=_build_system_prompt(admin_prompt),
        timeout_seconds=120.0,
    )


async def _call_llm_async(
    prompt: str,
    config: dict[str, Any],
    admin_prompt: str = "",
) -> str:
    """Call a specific model asynchronously."""
    return await _call_openai_compatible_model_async(
        base_url=str(config["base_url"]),
        api_key=str(config["api_key"]),
        model_name=str(config["model_name"]),
        prompt=prompt,
        temperature=float(config.get("temperature", 0.2)),
        system_prompt=_build_system_prompt(admin_prompt),
        timeout_seconds=120.0,
    )


def _call_multiple_models(
    prompt: str,
    context: dict[str, Any],
    admin_prompt: str = "",
) -> list[ModelComparison]:
    """Call multiple models in parallel and return comparison results."""
    configs = _read_model_configs(context)
    if not configs:
        raise RuntimeError("缺少客户端模型配置。")

    async def _run_all() -> list[ModelComparison]:
        async def _one(cfg: dict[str, Any]) -> ModelComparison:
            model_name = str(cfg["model_name"])
            label = str(cfg.get("label") or model_name)
            try:
                draft = await _call_llm_async(prompt, cfg, admin_prompt)
                return {"model_name": model_name, "label": label, "draft": draft, "error": ""}
            except Exception as exc:
                return {"model_name": model_name, "label": label, "draft": "", "error": str(exc)}

        return await asyncio.gather(*[_one(cfg) for cfg in configs])

    return asyncio.run(_run_all())


def _extract_json_from_response(text: str) -> dict[str, Any] | None:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try to find JSON in ```json blocks
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try to find JSON object in text
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _parse_l3_json(response_json: dict[str, Any], depth: IndicatorDepth) -> str:
    """Convert the LLM JSON response for L3 indicators to markdown."""
    indicators = response_json.get("level3_indicators") or []
    if not indicators:
        return "（模型未返回有效的三级指标数据）"

    lines: list[str] = []
    for i, item in enumerate(indicators):
        if not isinstance(item, dict):
            continue
        code = item.get("code") or f"L3-{i + 1:02d}"
        name = item.get("name") or f"三级指标 {i + 1}"
        expl = item.get("explanation") or ""
        lines.append(f"{i + 1}. **{code} {name}**")
        if expl:
            lines.append(f"   - 指标解释：{expl}")
        if depth == 4:
            level4_items = item.get("level4") or []
            if level4_items:
                for j, l4 in enumerate(level4_items):
                    if isinstance(l4, dict):
                        l4_code = l4.get("code") or f"{code}-{j + 1:02d}"
                        l4_name = l4.get("name") or f"四级细项 {j + 1}"
                        l4_expl = l4.get("explanation") or ""
                        lines.append(f"   - 四级细项 {j + 1}：**{l4_code} {l4_name}**")
                        if l4_expl:
                            lines.append(f"     {l4_expl}")
        lines.append("")
    lines.append("> 本批三级指标由大模型基于第二步核心内容生成，可在成品区直接编辑或通过对话修改。")
    return "\n".join(lines)


def _render_full_framework_markdown(
    project_name: str,
    system_type: str,
    depth: IndicatorDepth,
    core_digest: str,
    tasks: list[FlatL2Task],
) -> str:
    lines = [
        f"# 《{project_name} — 指标体系（{system_type}）》",
        "",
        f"- 生成时间：{_now_iso()}",
        f"- 指标深度：{depth} 级",
        "- **依据**：第二步项目核心内容（见文首摘要）。",
        "",
        "## 核心内容依据摘要",
        "",
        core_digest,
        "",
        "---",
        "",
        "## 指标体系全表",
        "",
    ]
    for idx, t in enumerate(tasks, start=1):
        lines.append(f"### {idx}. 一级：{t['level1_name']} ｜ 二级：{t['level2_name']}")
        body = (t.get("l3_section_markdown") or "_（该二级下三级指标尚未定稿）_").strip()
        lines.append("")
        lines.append(body)
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*定稿后可用于第四步赋分等环节。*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Skeleton editing helpers
# ---------------------------------------------------------------------------


def _apply_skeleton_edit(
    tasks: list[FlatL2Task],
    action: str,
    payload: str,
) -> list[FlatL2Task]:
    """Apply CRUD operations on the skeleton task list."""
    result = list(tasks)
    try:
        data = json.loads(payload) if payload else {}
    except json.JSONDecodeError:
        data = {}

    if action == "add_l1":
        l1_name = str(data.get("level1_name") or data.get("name") or "").strip()
        if l1_name:
            result.append({
                "level1_name": l1_name,
                "level2_name": "待定义二级指标",
                "target_l3_count": 3,
                "l3_section_markdown": "",
            })
    elif action == "remove_l1":
        l1_name = str(data.get("level1_name") or data.get("name") or "").strip()
        result = [t for t in result if t["level1_name"] != l1_name]
    elif action == "add_l2":
        l1_name = str(data.get("level1_name") or "").strip()
        l2_name = str(data.get("level2_name") or data.get("name") or "").strip()
        target = int(data.get("target_l3_count", 3))
        if l1_name and l2_name:
            result.append({
                "level1_name": l1_name,
                "level2_name": l2_name,
                "target_l3_count": max(1, min(20, target)),
                "l3_section_markdown": "",
            })
    elif action == "remove_l2":
        l1_name = str(data.get("level1_name") or "").strip()
        l2_name = str(data.get("level2_name") or data.get("name") or "").strip()
        result = [t for t in result if not (t["level1_name"] == l1_name and t["level2_name"] == l2_name)]
    elif action == "edit_l1":
        old_name = str(data.get("old_name") or data.get("level1_name") or "").strip()
        new_name = str(data.get("new_name") or data.get("name") or "").strip()
        if old_name and new_name:
            for t in result:
                if t["level1_name"] == old_name:
                    t["level1_name"] = new_name
    elif action == "edit_l2":
        l1_name = str(data.get("level1_name") or "").strip()
        old_l2 = str(data.get("old_name") or data.get("old_level2_name") or "").strip()
        new_l2 = str(data.get("new_name") or data.get("new_level2_name") or "").strip()
        if l1_name and old_l2 and new_l2:
            for t in result:
                if t["level1_name"] == l1_name and t["level2_name"] == old_l2:
                    t["level2_name"] = new_l2
    elif action == "set_l3_count":
        l1_name = str(data.get("level1_name") or "").strip()
        l2_name = str(data.get("level2_name") or "").strip()
        count = int(data.get("target_l3_count", 3))
        if l1_name and l2_name:
            for t in result:
                if t["level1_name"] == l1_name and t["level2_name"] == l2_name:
                    t["target_l3_count"] = max(1, min(20, count))

    return result


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------


def validate_core_basis(state: Step3State) -> Step3State:
    if state.get("status") == "chat":
        return {
            "status": "chat",
            "updated_at": _now_iso(),
        }

    core = _resolve_core_content(state)
    if not core:
        return {
            "status": "failed",
            "error": "缺少第二步项目核心内容：请传入 project_core_content 或 final_core_content。",
            "messages": [
                AIMessage(
                    content="第三步必须以第二步定稿后的项目核心内容为依据，请先完成第二步并传入核心内容全文。"
                )
            ],
            "updated_at": _now_iso(),
        }

    digest = _digest(core, 480)
    name = (state.get("project_name") or "未命名项目").strip() or "未命名项目"

    return {
        "project_name": name,
        "project_core_content": core,
        "core_basis_digest": digest,
        "active_l2_index": int(state.get("active_l2_index", 0)),
        "review_round": int(state.get("review_round", 0)),
        "created_at": state.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
        "status": "basis_ok",
        "messages": [
            AIMessage(
                content=(
                    f"已校验第二步核心内容（摘要长度 {len(digest)} 字符级预览），项目：{name}。"
                    "后续生成均以此内容为依据。"
                )
            )
        ],
    }


def build_indicator_skeleton(state: Step3State, runtime: Any = None) -> Step3State:
    core = _resolve_core_content(state)
    system_type = state.get("system_type") or "项目支出指标体系"
    if system_type not in SYSTEM_TYPES:
        system_type = "自定义"

    import_mode = state.get("import_mode") or "none"
    skeleton_edit_action = str(state.get("skeleton_edit_action") or "").strip()

    # Handle skeleton editing actions first
    existing_tasks = list(state.get("flat_l2_tasks") or [])
    if skeleton_edit_action and existing_tasks:
        edited = _apply_skeleton_edit(
            existing_tasks,
            skeleton_edit_action,
            str(state.get("skeleton_edit_payload") or ""),
        )
        if edited:
            return {
                "flat_l2_tasks": edited,
                "active_l2_index": 0,
                "skeleton_edit_action": "",
                "skeleton_edit_payload": "",
                "status": "skeleton_ready",
                "updated_at": _now_iso(),
                "messages": [
                    AIMessage(
                        content=f"骨架已更新（操作：{skeleton_edit_action}），共 {len(edited)} 个二级指标节点。"
                    )
                ],
            }

    # Build skeleton from scratch
    tasks: list[FlatL2Task] = []
    context = _get_llm_context(runtime)
    admin_prompt, admin_kb = _admin_prompt_and_kb(state, context)
    snippet = _core_basis_snippet(core)

    if import_mode == "own" and state.get("imported_indicator_json"):
        parsed = _parse_own_import(state["imported_indicator_json"])
        if parsed:
            tasks = parsed
        else:
            return {
                "status": "failed",
                "error": "自有指标体系 JSON 解析失败。",
                "messages": [
                    AIMessage(
                        content="imported_indicator_json 无法解析，请检查格式（支持 {tasks:[{level1,level2,target_l3_count}]}）。"
                    )
                ],
                "updated_at": _now_iso(),
            }
    elif import_mode == "template":
        tid = state.get("template_id") or "classic_performance_v1"
        tpl = TEMPLATE_LIBRARY.get(tid) or TEMPLATE_LIBRARY["classic_performance_v1"]
        tasks = _tasks_from_tuples(tpl)
    elif system_type == "自定义":
        # Use LLM to generate L1/L2 skeleton from core content
        try:
            prompt = _build_skeleton_prompt(snippet, system_type, admin_kb)
            raw = _call_llm(prompt, context, admin_prompt)
            parsed = _extract_json_from_response(raw)
            if parsed:
                arr = parsed.get("tasks") or []
                if isinstance(arr, list) and arr:
                    for row in arr:
                        if isinstance(row, dict):
                            l1 = row.get("level1") or row.get("l1") or ""
                            l2 = row.get("level2") or row.get("l2") or ""
                            n = row.get("target_l3_count") or 3
                            if l1 and l2:
                                tasks.append({
                                    "level1_name": str(l1),
                                    "level2_name": str(l2),
                                    "target_l3_count": max(1, min(20, int(n))),
                                    "l3_section_markdown": "",
                                })
            if not tasks:
                # Fallback placeholder
                tasks = [
                    {
                        "level1_name": "自定义一级",
                        "level2_name": "基于核心内容生成的二级指标",
                        "target_l3_count": 4,
                        "l3_section_markdown": "",
                    }
                ]
        except Exception as exc:
            return {
                "status": "failed",
                "error": f"LLM 生成自定义骨架失败：{exc}",
                "messages": [AIMessage(content=f"大模型生成自定义指标体系骨架时出错：{exc}")],
                "updated_at": _now_iso(),
            }
    else:
        rows = TYPE_DEFAULT_TASKS.get(system_type, TYPE_DEFAULT_TASKS["项目支出指标体系"])
        tasks = _tasks_from_tuples(list(rows))

    # Apply skeleton optimization via LLM
    opt_mode = state.get("skeleton_optimize_mode") or "none"
    per = (state.get("per_optimize_level2_name") or "").strip()

    if opt_mode != "none" and tasks:
        try:
            tasks_json = json.dumps(
                [{"level1": t["level1_name"], "level2": t["level2_name"], "target_l3_count": t["target_l3_count"]} for t in tasks],
                ensure_ascii=False,
                indent=2,
            )
            prompt = _build_optimize_prompt(snippet, system_type, tasks_json, per, admin_kb)
            raw = _call_llm(prompt, context, admin_prompt)
            parsed = _extract_json_from_response(raw)
            if parsed:
                arr = parsed.get("tasks") or []
                if isinstance(arr, list) and arr:
                    new_tasks: list[FlatL2Task] = []
                    for row in arr:
                        if isinstance(row, dict):
                            l1 = row.get("level1") or row.get("l1") or ""
                            l2 = row.get("level2") or row.get("l2") or ""
                            n = row.get("target_l3_count") or 3
                            if l1 and l2:
                                new_tasks.append({
                                    "level1_name": str(l1),
                                    "level2_name": str(l2),
                                    "target_l3_count": max(1, min(20, int(n))),
                                    "l3_section_markdown": "",
                                })
                    if new_tasks:
                        tasks = new_tasks
        except Exception as exc:
            # Optimization failure is non-fatal; keep original skeleton
            pass

    return {
        "system_type": cast(SystemType, system_type),
        "flat_l2_tasks": tasks,
        "active_l2_index": 0,
        "l3_active_draft": "",
        "l3_model_comparisons": [],
        "review_round": 0,
        "skeleton_edit_action": "",
        "skeleton_edit_payload": "",
        "status": "skeleton_ready",
        "updated_at": _now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已构建指标体系骨架，共 {len(tasks)} 个二级指标节点，将 **逐个** 生成三级指标。"
                    f"类型：{system_type}，导入模式：{import_mode}。"
                )
            )
        ],
    }


def route_after_validate(state: Step3State) -> str:
    if state.get("status") == "failed":
        return "end"
    if state.get("status") == "chat":
        return "chat"
    return "continue"


def generate_l3_for_active_l2(state: Step3State, runtime: Any = None) -> Step3State:
    context = _get_llm_context(runtime)
    admin_prompt, admin_kb = _admin_prompt_and_kb(state, context)
    core = _resolve_core_content(state)
    snippet = _core_basis_snippet(core)
    tasks = state.get("flat_l2_tasks") or []
    idx = int(state.get("active_l2_index", 0))

    if not tasks or idx >= len(tasks):
        return {
            "status": "failed",
            "error": "二级指标队列为空或索引越界。",
            "messages": [AIMessage(content="内部状态异常：请重新构建骨架。")],
            "updated_at": _now_iso(),
        }

    task = tasks[idx]
    project_name = state.get("project_name", "未命名项目")
    system_type = str(state.get("system_type", "项目支出指标体系"))
    depth: IndicatorDepth = state.get("indicator_depth") or 3
    if depth not in (3, 4):
        depth = 3
    target_count = max(1, int(task.get("target_l3_count") or 3))

    multi = bool(context.get("enable_multi_model", False))
    configs = _read_model_configs(context)

    if not configs:
        return {
            "status": "failed",
            "error": "缺少客户端模型配置。",
            "messages": [AIMessage(content="请在模型配置中设置 Base URL、API Key 和模型名。")],
            "updated_at": _now_iso(),
        }

    l3_prompt = _build_l3_generation_prompt(
        snippet, system_type, depth, task["level1_name"], task["level2_name"], target_count, admin_kb
    )

    try:
        if multi and len(configs) > 1:
            comparisons = _call_multiple_models(l3_prompt, context, admin_prompt)
        else:
            raw = _call_llm(l3_prompt, context, admin_prompt)
            cfg = configs[0]
            comparisons = [{
                "model_name": str(cfg["model_name"]),
                "label": str(cfg.get("label") or cfg["model_name"]),
                "draft": raw,
                "error": "",
            }]

        # Parse each model's response to markdown
        parsed_comparisons: list[ModelComparison] = []
        for comp in comparisons:
            draft_text = comp["draft"]
            parsed_json = _extract_json_from_response(draft_text)
            if parsed_json:
                draft_text = _parse_l3_json(parsed_json, depth)
            parsed_comparisons.append({
                "model_name": comp["model_name"],
                "label": comp["label"],
                "draft": draft_text,
                "error": comp.get("error", ""),
            })

        primary_draft = parsed_comparisons[0]["draft"] if parsed_comparisons else ""

    except Exception as exc:
        return {
            "status": "failed",
            "error": f"LLM 生成三级指标失败：{exc}",
            "messages": [AIMessage(content=f"大模型生成三级指标时出错：{exc}")],
            "updated_at": _now_iso(),
        }

    return {
        "l3_active_draft": primary_draft,
        "l3_model_comparisons": parsed_comparisons,
        "status": "l3_draft_ready",
        "updated_at": _now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已为第 {idx + 1}/{len(tasks)} 个二级指标「{task['level2_name']}」"
                    f"生成 {len(parsed_comparisons)} 份三级指标草案（含指标解释），请对比、修改或批准。"
                )
            )
        ],
    }


def route_l3_review(state: Step3State) -> str:
    return "approve" if state.get("review_mode") == "approve" else "modify"


def refine_l3_batch(state: Step3State, runtime: Any = None) -> Step3State:
    context = _get_llm_context(runtime)
    admin_prompt, admin_kb = _admin_prompt_and_kb(state, context)
    fb = state.get("review_feedback", "").strip()
    rnd = int(state.get("review_round", 0)) + 1
    cur = state.get("l3_active_draft") or ""

    if not fb:
        return {
            "review_round": rnd,
            "status": "l3_refined",
            "updated_at": _now_iso(),
            "messages": [AIMessage(content=f"第 {rnd} 轮：未提供修改意见，保持当前草案不变。")],
        }

    tasks = state.get("flat_l2_tasks") or []
    idx = int(state.get("active_l2_index", 0))
    task = tasks[idx] if idx < len(tasks) else None
    if not task:
        return {
            "status": "failed",
            "error": "当前二级指标索引越界。",
            "messages": [AIMessage(content="内部状态异常：请重新构建骨架。")],
            "updated_at": _now_iso(),
        }

    core = _resolve_core_content(state)
    snippet = _core_basis_snippet(core)
    system_type = str(state.get("system_type", ""))
    depth: IndicatorDepth = state.get("indicator_depth") or 3

    try:
        prompt = _build_refine_prompt(
            snippet, system_type, task["level1_name"], task["level2_name"],
            cur, fb, depth, admin_kb,
        )
        raw = _call_llm(prompt, context, admin_prompt)
        parsed = _extract_json_from_response(raw)
        if parsed:
            refined = _parse_l3_json(parsed, depth)
        else:
            # If parsing fails, append feedback as comment
            refined = (
                f"{cur}\n\n"
                f"【第 {rnd} 轮修订意见】\n{fb}\n\n"
                f"【模型响应】\n{raw}\n\n"
                "> 请再次审阅，如需进一步修改可继续提出意见。"
            )
        return {
            "review_round": rnd,
            "l3_active_draft": refined,
            "status": "l3_refined",
            "updated_at": _now_iso(),
            "messages": [
                AIMessage(content=f"已根据第 {rnd} 轮修改意见，重新生成「{task['level2_name']}」的三级指标。请审阅。")
            ],
        }
    except Exception as exc:
        # Fallback: merge feedback as annotation
        merged = (
            f"{cur}\n\n"
            f"【第 {rnd} 轮修订意见（LLM 调用失败，意见已附上）】\n{fb}\n\n"
            f"> 模型优化失败：{exc}。请手动编辑或重试。"
        )
        return {
            "review_round": rnd,
            "l3_active_draft": merged,
            "status": "l3_refined",
            "updated_at": _now_iso(),
            "messages": [
                AIMessage(content=f"已记录第 {rnd} 轮修改意见（LLM 调用失败，意见已附加到草案中）。")
            ],
        }


def advance_after_l3_approve(state: Step3State) -> Step3State:
    tasks = list(state.get("flat_l2_tasks") or [])
    idx = int(state.get("active_l2_index", 0))
    draft = (state.get("l3_active_draft") or "").strip()

    if idx < len(tasks):
        tasks[idx] = {
            **tasks[idx],
            "l3_section_markdown": draft or tasks[idx].get("l3_section_markdown", ""),
        }

    next_idx = idx + 1
    return {
        "flat_l2_tasks": tasks,
        "active_l2_index": next_idx,
        "l3_active_draft": "",
        "l3_model_comparisons": [],
        "review_round": 0,
        "review_feedback": "",
        "status": "l3_level_saved",
        "updated_at": _now_iso(),
        "messages": [
            AIMessage(
                content=(
                    f"已保存第 {idx + 1} 个二级指标下的三级指标与解释。"
                    f"{' 请继续下一个二级指标。' if next_idx < len(tasks) else ' 全部二级已完成，即将定稿。'}"
                )
            )
        ],
    }


def route_more_l2(state: Step3State) -> str:
    tasks = state.get("flat_l2_tasks") or []
    idx = int(state.get("active_l2_index", 0))
    return "more" if idx < len(tasks) else "finalize"


def finalize_indicator_system(state: Step3State) -> Step3State:
    core = _resolve_core_content(state)
    tasks = state.get("flat_l2_tasks") or []
    project_name = state.get("project_name", "未命名项目")
    system_type = str(state.get("system_type", ""))
    depth: IndicatorDepth = state.get("indicator_depth") or 3
    digest = state.get("core_basis_digest") or _digest(core, 480)

    full = _render_full_framework_markdown(project_name, system_type, depth, digest, tasks)
    fn = f"{project_name}指标体系_定稿"

    return {
        "final_indicator_markdown": full,
        "export_payload": full,
        "export_filename": fn,
        "status": "completed",
        "updated_at": _now_iso(),
        "messages": [
            AIMessage(
                content="全部二级指标下的三级指标已处理完毕，指标体系已定稿，可一键导入成品区并进入下一环节。"
            )
        ],
    }


def _compose_chat_reply(state: Step3State, context: Step3Context) -> str:
    workflow_state = dict(context.get("workflow_state") or {}) if isinstance(context.get("workflow_state"), dict) else {}
    project_name = state.get("project_name") or str(workflow_state.get("project_name") or context.get("project_id") or "未命名项目")
    step_code = str(workflow_state.get("step_code") or context.get("step_code") or "step3")
    digest = state.get("core_basis_digest") or ""
    current = state.get("final_indicator_markdown") or state.get("l3_active_draft") or ""
    workflow_result = workflow_state.get("current_result") if isinstance(workflow_state.get("current_result"), dict) else {}
    if not current and workflow_result:
        current = str(
            workflow_result.get("content_text")
            or workflow_result.get("final_indicator_markdown")
            or workflow_result.get("final_manifest")
            or ""
        ).strip()
    last_user = ""
    for message in reversed(list(state.get("messages", []))):
        if isinstance(message, HumanMessage):
            last_user = str(message.content).strip()
            break
    lines = [
        f"已进入 Step3 对话模式：{project_name} / {step_code}",
        "",
        "我会基于第二步核心内容来回答，并保持指标体系层级和口径一致。",
    ]
    if digest:
        lines.extend(["", f"核心依据摘要：{digest}"])
    if current:
        lines.extend(["", "当前指标稿摘要：", current[:1200]])
    if last_user:
        lines.extend(["", f"你的输入：{last_user}"])
    lines.extend(
        [
            "",
            "建议：",
            "1. 指明要调整的一级/二级指标名称；",
            "2. 指明三级指标数量、描述风格和约束；",
            "3. 需要时我可输出可直接导入成品区的修订稿。",
        ]
    )
    return "\n".join(lines)


def _chat_node(state: Step3State, runtime: Any) -> Step3State:
    context = (getattr(runtime, "context", {}) or {}) if runtime is not None else {}
    reply = _compose_chat_reply(state, context)
    return {
        "status": "chat_reply",
        "updated_at": _now_iso(),
        "messages": [AIMessage(content=reply)],
    }


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    graph = StateGraph(Step3State, context_schema=Step3Context)

    graph.add_node("validate_core_basis", validate_core_basis)
    graph.add_node("build_indicator_skeleton", build_indicator_skeleton)
    graph.add_node("generate_l3_for_active_l2", generate_l3_for_active_l2)
    graph.add_node("refine_l3_batch", refine_l3_batch)
    graph.add_node("advance_after_l3_approve", advance_after_l3_approve)
    graph.add_node("finalize_indicator_system", finalize_indicator_system)
    graph.add_node("chat", _chat_node)

    graph.add_edge(START, "validate_core_basis")
    graph.add_conditional_edges(
        "validate_core_basis",
        lambda s: "chat" if s.get("status") == "chat" else route_after_validate(s),
        {"chat": "chat", "continue": "build_indicator_skeleton", "end": END},
    )

    graph.add_conditional_edges(
        "build_indicator_skeleton",
        lambda s: "bad" if s.get("status") == "failed" else "ok",
        {"bad": END, "ok": "generate_l3_for_active_l2"},
    )

    graph.add_conditional_edges(
        "generate_l3_for_active_l2",
        route_l3_review,
        {
            "modify": "refine_l3_batch",
            "approve": "advance_after_l3_approve",
        },
    )
    graph.add_edge("refine_l3_batch", "generate_l3_for_active_l2")

    graph.add_conditional_edges(
        "advance_after_l3_approve",
        route_more_l2,
        {"more": "generate_l3_for_active_l2", "finalize": "finalize_indicator_system"},
    )
    graph.add_edge("finalize_indicator_system", END)
    graph.add_edge("chat", END)

    memory = MemorySaver()
    return graph.compile(
        checkpointer=memory,
        name="evalflow-pro-step3",
        interrupt_after=["generate_l3_for_active_l2"],
    )


graph = build_graph()
