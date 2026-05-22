"""Admin Step 12 graph — 基本情况 Prompt / 知识库管理。"""

from __future__ import annotations

from ._base import build_admin_graph

graph = build_admin_graph(
    step_code="step12",
    step_name="基本情况配置",
    default_prompt_title="基本情况生成 Prompt",
    default_kb_name="基本情况知识库",
)
