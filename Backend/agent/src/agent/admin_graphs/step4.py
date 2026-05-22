"""Admin Step 4 graph — 指标分值 Prompt / 知识库管理。"""

from __future__ import annotations

from ._base import build_admin_graph

graph = build_admin_graph(
    step_code="step4",
    step_name="指标分值配置",
    default_prompt_title="指标分值生成 Prompt",
    default_kb_name="指标分值知识库",
)
