"""Admin Step 14 graph — 评价报告 Prompt / 知识库管理。"""

from __future__ import annotations

from ._base import build_admin_graph

graph = build_admin_graph(
    step_code="step14",
    step_name="评价报告配置",
    default_prompt_title="评价报告生成 Prompt",
    default_kb_name="评价报告知识库",
)
