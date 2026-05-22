"""Admin Step 5 graph — 评分标准 Prompt / 知识库管理。"""

from __future__ import annotations

from ._base import build_admin_graph

graph = build_admin_graph(
    step_code="step5",
    step_name="评分标准配置",
    default_prompt_title="评分标准生成 Prompt",
    default_kb_name="评分标准知识库",
)
