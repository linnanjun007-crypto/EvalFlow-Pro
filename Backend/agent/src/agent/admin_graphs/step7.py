"""Admin Step 7 graph — 指标分析与得分 Prompt / 知识库管理。"""

from __future__ import annotations

from ._base import build_admin_graph

graph = build_admin_graph(
    step_code="step7",
    step_name="指标分析与得分配置",
    default_prompt_title="指标分析生成 Prompt",
    default_kb_name="指标分析知识库",
)
