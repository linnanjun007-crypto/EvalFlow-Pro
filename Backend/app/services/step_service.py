from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.integrations.agent_runner import AgentRunner
from app.models.step_history import StepHistory
from app.models.step_output import StepOutput
from app.models.task_job import TaskJob
from app.services.memory_service import MemoryService


def _dumps_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value), ensure_ascii=False)


class StepService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.runner = AgentRunner()

    def generate_step(self, project_id: str, step_code: str, role: str, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        task = TaskJob(
            id=str(uuid4()),
            project_id=project_id,
            step_code=step_code,
            task_type="generate",
            status="running",
            progress=10,
        )
        self.db.add(task)
        self.db.flush()

        result = self.runner.run(role=role, step_code=step_code, payload=payload, context=context)
        content_text = self._extract_text(result)
        content_json = _dumps_json(result)

        memory = MemoryService(self.db)
        session = memory.ensure_session(project_id=project_id, user_id=payload.get('user_id') if isinstance(payload.get('user_id'), str) else None, step_code=step_code, memory_scope='short_term')
        memory.append_entry(
            session_id=session.id,
            project_id=project_id,
            user_id=payload.get('user_id') if isinstance(payload.get('user_id'), str) else None,
            step_code=step_code,
            memory_type='short_term',
            content=content_text,
            metadata={'role': role},
        )

        step_output = StepOutput(
            id=str(uuid4()),
            project_id=project_id,
            step_code=step_code,
            title=f"{step_code} 输出",
            content_json=content_json,
            content_text=content_text,
            version=1,
            is_final=True,
        )
        self.db.add(step_output)
        self.db.flush()

        step_history = StepHistory(
            id=str(uuid4()),
            step_output_id=step_output.id,
            model_name=self._extract_model_name(result, context),
            prompt_version_id=None,
            content_json=content_json,
            content_text=content_text,
        )
        self.db.add(step_history)

        task.status = "succeeded"
        task.progress = 100
        self.db.commit()

        return {
            "task_id": task.id,
            "step_output_id": step_output.id,
            "step_code": step_code,
            "status": task.status,
            "result": result,
        }

    def get_step_result(self, project_id: str, step_code: str) -> dict[str, Any]:
        item = self.db.scalar(
            select(StepOutput)
            .where(StepOutput.project_id == project_id, StepOutput.step_code == step_code)
            .order_by(desc(StepOutput.version))
        )
        if not item:
            return {"project_id": project_id, "step_code": step_code, "status": "not_found", "result": {}}
        return {
            "project_id": project_id,
            "step_code": step_code,
            "status": "succeeded" if item.is_final else "draft",
            "result": {
                "id": item.id,
                "title": item.title,
                "content_json": item.content_json,
                "content_text": item.content_text,
                "version": item.version,
                "is_final": item.is_final,
            },
        }

    def get_workflow_status(self, project_id: str, total_steps: int = 14) -> dict[str, Any]:
        outputs = self.db.scalars(
            select(StepOutput)
            .where(StepOutput.project_id == project_id)
            .order_by(desc(StepOutput.version))
        ).all()
        latest_by_step: dict[str, StepOutput] = {}
        for output in outputs:
            latest_by_step.setdefault(output.step_code, output)

        steps = []
        done_steps = 0
        for index in range(1, total_steps + 1):
            step_code = f"step{index}"
            output = latest_by_step.get(step_code)
            done = bool(output and output.is_final)
            if done:
                done_steps += 1
            steps.append(
                {
                    "step_code": step_code,
                    "status": "succeeded" if done else "draft" if output else "not_found",
                    "done": done,
                    "version": output.version if output else None,
                    "title": output.title if output else None,
                }
            )

        return {
            "project_id": project_id,
            "total_steps": total_steps,
            "done_steps": done_steps,
            "status": "succeeded" if done_steps == total_steps else "running" if done_steps > 0 else "queued",
            "progress": round(done_steps / total_steps * 100) if total_steps else 0,
            "steps": steps,
        }

    def save_step_result(
        self,
        project_id: str,
        step_code: str,
        title: str,
        content_text: str,
        content_json: str,
        model_name: str = "manual-edit",
    ) -> dict[str, Any]:
        if not project_id:
            raise ValueError("project_id is required")
        if not content_text.strip():
            raise ValueError("content_text is required")

        latest = self.db.scalar(
            select(StepOutput)
            .where(StepOutput.project_id == project_id, StepOutput.step_code == step_code)
            .order_by(desc(StepOutput.version))
        )
        version = int(latest.version) + 1 if latest else 1
        step_output = StepOutput(
            id=str(uuid4()),
            project_id=project_id,
            step_code=step_code,
            title=title,
            content_json=content_json,
            content_text=content_text,
            version=version,
            is_final=True,
        )
        self.db.add(step_output)
        self.db.flush()
        self.db.add(
            StepHistory(
                id=str(uuid4()),
                step_output_id=step_output.id,
                model_name=model_name,
                prompt_version_id=None,
                content_json=content_json,
                content_text=content_text,
            )
        )
        self.db.commit()

        if step_code == "step14":
            self._maybe_generate_project_report(project_id)

        return {
            "id": step_output.id,
            "project_id": project_id,
            "step_code": step_code,
            "title": title,
            "content_text": content_text,
            "content_json": content_json,
            "version": version,
            "is_final": True,
        }

    def _maybe_generate_project_report(self, project_id: str) -> None:
        """Step14 完成时尝试生成项目完整报告，失败不阻塞主流程。"""
        import logging

        from app.models.project import Project
        from app.services.project_report_service import generate_report

        logger = logging.getLogger(__name__)
        try:
            project = self.db.get(Project, project_id)
            if not project:
                return
            generate_report(self.db, project_id=project_id, user_id=project.user_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto generate project report failed: %s", exc)

    def list_step_histories(self, project_id: str, step_code: str) -> list[dict[str, Any]]:
        outputs = self.db.scalars(
            select(StepOutput)
            .where(StepOutput.project_id == project_id, StepOutput.step_code == step_code)
            .order_by(desc(StepOutput.version))
        ).all()
        return [
            {
                "id": item.id,
                "title": item.title,
                "content_json": item.content_json,
                "content_text": item.content_text,
                "version": item.version,
                "is_final": item.is_final,
            }
            for item in outputs
        ]

    def delete_step_output(self, project_id: str, step_code: str, output_id: str) -> None:
        item = self.db.scalar(select(StepOutput).where(StepOutput.project_id == project_id, StepOutput.step_code == step_code, StepOutput.id == output_id))
        if not item:
            raise ValueError("历史版本不存在")
        history = self.db.scalar(select(StepHistory).where(StepHistory.step_output_id == output_id))
        if history:
            self.db.delete(history)
        self.db.delete(item)
        self.db.commit()

    def _extract_text(self, result: dict[str, Any]) -> str:
        for key in (
            "content_text",
            "final_manifest",
            "final_core_content",
            "final_indicator_markdown",
            "final_score_markdown",
            "final_standard_markdown",
            "final_report_markdown",
            "draft_manifest",
            "core_content_draft",
            "verification_digest",
            "export_payload",
            "message",
        ):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return str(result)

    def _extract_model_name(self, result: dict[str, Any], context: dict[str, Any]) -> str:
        if isinstance(result.get("model_name"), str):
            return result["model_name"]
        if isinstance(context.get("model_name"), str):
            return context["model_name"]
        return "default-model"
