from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.task_job import TaskJob


class TaskService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_task(self, step_code: str, project_id: str, task_type: str = "generate") -> dict[str, Any]:
        task = TaskJob(
            id=str(uuid4()),
            project_id=project_id,
            step_code=step_code,
            task_type=task_type,
            status="pending",
            progress=0,
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        return {
            "task_id": task.id,
            "step_code": task.step_code,
            "project_id": task.project_id,
            "status": task.status,
        }

    def get_task(self, task_id: str) -> dict[str, Any]:
        task = self.db.get(TaskJob, task_id)
        if not task:
            return {"task_id": task_id, "status": "not_found", "progress": 0}
        return {
            "task_id": task.id,
            "status": task.status,
            "progress": task.progress,
        }
