"""Global chat graph for EvalFlow Pro.

This fallback graph is used when a specific step graph is not available.
It provides a workflow-aware assistant response that summarizes the current
project, step, and recent conversation context.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.graph import END, START, StateGraph


class ChatState(TypedDict, total=False):
    project_id: str
    step_code: str
    workflow_state: dict[str, Any]
    messages: list[BaseMessage]
    status: str
    answer: str
    updated_at: str


class ChatContext(TypedDict, total=False):
    project_id: str
    workflow_role: str
    step_code: str
    chat_mode: bool
    workflow_state: dict[str, Any]
    fallback_step_code: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _latest_user_message(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            content = str(message.content).strip()
            if content:
                return content
    return ""


def _format_state_summary(context: ChatContext, state: ChatState) -> str:
    workflow_state = dict(context.get("workflow_state") or state.get("workflow_state") or {})
    current_result = workflow_state.get("current_result")
    parts: list[str] = []
    project_id = str(state.get("project_id") or workflow_state.get("project_id") or context.get("project_id") or "")
    step_code = str(state.get("step_code") or workflow_state.get("step_code") or context.get("step_code") or "")
    step_title = str(workflow_state.get("step_title") or workflow_state.get("stepTitle") or "")
    prompt_hint = str(workflow_state.get("prompt_hint") or workflow_state.get("promptHint") or "")
    file_count = workflow_state.get("file_count")
    media_count = workflow_state.get("media_count")
    document_count = workflow_state.get("document_count")
    if project_id:
        parts.append(f"项目：{project_id}")
    if step_code:
        parts.append(f"步骤：{step_code}")
    if step_title:
        parts.append(f"步骤标题：{step_title}")
    if file_count is not None:
        parts.append(f"文件数：{file_count}")
    if media_count is not None or document_count is not None:
        parts.append(f"图片/PDF：{media_count or 0}，文档：{document_count or 0}")
    if prompt_hint:
        parts.append(f"提示：{prompt_hint}")
    return "\n".join(parts)


def _chat_node(state: ChatState, runtime: Any) -> ChatState:
    messages = list(state.get("messages", []))
    context = getattr(runtime, "context", {}) or {}
    workflow_state = dict(context.get("workflow_state") or state.get("workflow_state") or {})
    current_result = workflow_state.get("current_result")
    last_user = _latest_user_message(messages)
    summary = _format_state_summary(context, state)
    fallback_step = context.get("fallback_step_code")
    reply_lines = [
        "已进入统一对话模式。",
        "",
        "我会结合当前工作流上下文回答你的问题，并尽量给出下一步可执行建议。",
    ]
    if summary:
        reply_lines.extend(["", summary])
    if current_result:
        reply_lines.extend(["", f"当前结果摘要：{str(current_result)[:500]}"])
    if fallback_step:
        reply_lines.extend(["", f"当前步骤尚无专用图，已从 {fallback_step} 降级到统一对话助手。"])
    if last_user:
        reply_lines.extend(["", f"你的输入：{last_user}"])
    reply_lines.extend(
        [
            "",
            "建议：",
            "1. 直接说明你要生成、修改或检查的内容；",
            "2. 如需我按步骤执行，请给出目标步骤名或业务约束；",
            "3. 如果当前步骤未接入专用流程，我会基于全局状态先给出可执行建议。",
        ]
    )
    return {
        "status": "chat_reply",
        "answer": "\n".join(reply_lines),
        "updated_at": _now_iso(),
        "messages": [AIMessage(content="\n".join(reply_lines))],
    }


def build_graph() -> Any:
    graph = StateGraph(ChatState, context_schema=ChatContext)
    graph.add_node("chat", _chat_node)
    graph.add_edge(START, "chat")
    graph.add_edge("chat", END)
    return graph.compile(name="evalflow-pro-chat-fallback")


graph = build_graph()

__all__ = ["graph", "build_graph", "ChatState", "ChatContext"]
