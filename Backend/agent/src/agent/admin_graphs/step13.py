"""Admin Step 13 graph — 工作开展情况 Prompt / 知识库管理。"""

from __future__ import annotations

from ._base import build_admin_graph

graph = build_admin_graph(
    step_code="step13",
    step_name="工作开展情况配置",
    default_prompt_title="工作开展情况生成 Prompt",
    default_kb_name="工作开展情况知识库",
)
