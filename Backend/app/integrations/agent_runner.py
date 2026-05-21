from __future__ import annotations

from importlib import import_module
from functools import lru_cache
from typing import Any


ROLE_PACKAGE = {
    "user": "user_graphs",
    "client": "user_graphs",
    "client_graphs": "user_graphs",
    "admin": "admin_graphs",
    "manager": "admin_graphs",
    "admin_graphs": "admin_graphs",
}


@lru_cache(maxsize=None)
def _load_graph(role: str, step_code: str):
    package = ROLE_PACKAGE.get(role)
    if not package:
        return None
    module_name = f"agent.src.agent.{package}.{step_code}"
    try:
        module = import_module(module_name)
    except ModuleNotFoundError:
        return None
    return getattr(module, "graph", None)


class AgentRunner:
    def run(self, role: str, step_code: str, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        role = role.lower().strip()
        step_code = step_code.lower().strip()

        graph = _load_graph(role, step_code)
        if graph is None:
            fallback_graph = _load_graph(role, "chat") or _load_graph(role, "step1")
            if fallback_graph is not None:
                graph = fallback_graph
                context = {**context, "fallback_step_code": step_code, "chat_mode": True}
                payload = {**payload, "step_code": step_code}

        if graph is not None:
            thread_id = str(
                context.get("thread_id")
                or payload.get("thread_id")
                or payload.get("session_id")
                or f"{role}:{step_code}:{payload.get('project_id', 'default')}:{payload.get('run_id', '')}"
            )
            config = {"configurable": {"thread_id": thread_id}}
            result = graph.invoke(payload, config=config, context=context)
            if isinstance(result, dict):
                result.setdefault("workflow_role", role)
                result.setdefault("step_code", step_code)
                result.setdefault("thread_id", thread_id)
                if context.get("fallback_step_code"):
                    result.setdefault("fallback_step_code", context.get("fallback_step_code"))
            return result

        return {
            "role": role,
            "step_code": step_code,
            "payload": payload,
            "context": context,
            "status": "not_implemented",
            "message": "当前步骤尚未提供专用图，已降级到统一路由层但仍缺少可执行图。",
        }
