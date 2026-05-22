"""Admin Step 3 graph — 指标体系骨架 Prompt / 知识库管理。"""

from __future__ import annotations

from ._base import build_admin_graph

graph = build_admin_graph(
    step_code="step3",
    step_name="指标体系配置",
    default_prompt_title="指标体系生成 Prompt",
    default_kb_name="指标体系知识库",
)
