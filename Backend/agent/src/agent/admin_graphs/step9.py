"""Admin Step 9 graph — 问题及原因分析 Prompt / 知识库管理。"""

from __future__ import annotations

from ._base import build_admin_graph

graph = build_admin_graph(
    step_code="step9",
    step_name="问题及原因分析配置",
    default_prompt_title="问题与原因生成 Prompt",
    default_kb_name="问题与原因知识库",
)
