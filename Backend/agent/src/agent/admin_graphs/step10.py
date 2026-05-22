"""Admin Step 10 graph — 整改建议 Prompt / 知识库管理。"""

from __future__ import annotations

from ._base import build_admin_graph

graph = build_admin_graph(
    step_code="step10",
    step_name="整改建议配置",
    default_prompt_title="整改建议生成 Prompt",
    default_kb_name="整改建议知识库",
)
