"""Admin Step 11 graph — 综合评价分析 Prompt / 知识库管理。"""

from __future__ import annotations

from ._base import build_admin_graph

graph = build_admin_graph(
    step_code="step11",
    step_name="综合评价分析配置",
    default_prompt_title="综合评价生成 Prompt",
    default_kb_name="综合评价知识库",
)
