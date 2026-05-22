"""Admin Step 8 graph — 经验做法 Prompt / 知识库管理。"""

from __future__ import annotations

from ._base import build_admin_graph

graph = build_admin_graph(
    step_code="step8",
    step_name="经验做法配置",
    default_prompt_title="经验做法生成 Prompt",
    default_kb_name="经验做法知识库",
)
