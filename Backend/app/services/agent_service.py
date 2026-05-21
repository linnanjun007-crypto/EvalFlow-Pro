from __future__ import annotations

from typing import Any

from app.integrations.agent_runner import AgentRunner


class AgentService:
    def __init__(self) -> None:
        self.runner = AgentRunner()

    def run_user_step(self, step_code: str, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return self.runner.run(role="user", step_code=step_code, payload=payload, context=context)

    def run_admin_step(self, step_code: str, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return self.runner.run(role="admin", step_code=step_code, payload=payload, context=context)
