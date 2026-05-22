"""Admin Step 6 graph — 绩效评价指标体系 Prompt / 知识库管理。"""

from __future__ import annotations

from ._base import build_admin_graph

graph = build_admin_graph(
    step_code="step6",
    step_name="绩效评价指标体系配置",
    default_prompt_title="指标体系与问卷生成 Prompt",
    default_kb_name="指标体系与问卷知识库",
)
