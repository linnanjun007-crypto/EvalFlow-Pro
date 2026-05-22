"""Admin Step 2 graph — 核心内容 Prompt / 知识库管理。"""

from __future__ import annotations

from ._base import build_admin_graph

graph = build_admin_graph(
    step_code="step2",
    step_name="核心内容配置",
    default_prompt_title="核心内容生成 Prompt",
    default_kb_name="核心内容知识库",
)
