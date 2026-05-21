"""Unified workflow router for EvalFlow Pro.

This module exposes a single ``graph`` object that can route to either the
client-side workflow graphs or the admin-side workflow graphs based on the
``workflow_role`` field in state.

Supported roles:

- ``user`` / ``client`` / ``client_graphs`` -> ``agent.user_graphs``
- ``admin`` / ``manager`` / ``admin_graphs`` -> ``agent.admin_graphs``

The router is intentionally lightweight: it delegates to the appropriate
module-level graph object so existing step graphs remain the source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .user_graphs import step1 as user_step1
from .admin_graphs import step1 as admin_step1

WorkflowRole = Literal["user", "client", "client_graphs", "admin", "manager", "admin_graphs"]


class RouterState(TypedDict, total=False):
    workflow_role: WorkflowRole
    workflow_name: str
    status: str
    error: str
    selected_graph: str
    messages: list[Any]


class RouterContext(TypedDict, total=False):
    project_id: str
    user_id: str
    model_name: str
    compare_models: list[str]
    enable_multi_model: bool
    system_prompt_stub: str
    knowledge_stub: str
    output_dir: str


@dataclass(frozen=True)
class _GraphRef:
    name: str
    graph: Any


_GRAPHS = {
    "user": _GraphRef("user", user_step1.graph),
    "client": _GraphRef("user", user_step1.graph),
    "client_graphs": _GraphRef("user", user_step1.graph),
    "admin": _GraphRef("admin", admin_step1.graph),
    "manager": _GraphRef("admin", admin_step1.graph),
    "admin_graphs": _GraphRef("admin", admin_step1.graph),
}


def _select_role(state: RouterState) -> str:
    role = (state.get("workflow_role") or "user").strip().lower()
    return role if role in _GRAPHS else "user"


def route_workflow(state: RouterState) -> RouterState:
    role = _select_role(state)
    ref = _GRAPHS[role]
    return {
        "workflow_name": ref.name,
        "selected_graph": ref.name,
        "status": "routed",
    }


def build_graph() -> Any:
    graph = StateGraph(RouterState, context_schema=RouterContext)
    graph.add_node("route_workflow", route_workflow)
    graph.add_edge(START, "route_workflow")
    graph.add_edge("route_workflow", END)
    return graph.compile(name="evalflow-pro-router")


graph = build_graph()

__all__ = ["graph", "build_graph", "RouterState", "RouterContext"]
