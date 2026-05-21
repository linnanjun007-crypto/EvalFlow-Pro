from __future__ import annotations

import json
from uuid import uuid4
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.memory import ProjectMemoryEntry, ProjectMemorySession, ProjectStepRun


def _json_default(value: Any) -> Any:
    if hasattr(value, "content") and hasattr(value, "type"):
        return {"type": getattr(value, "type", value.__class__.__name__), "content": getattr(value, "content", "")}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return str(value)


class MemoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def ensure_session(self, project_id: str, user_id: str | None, step_code: str | None, memory_scope: str, thread_id: str | None = None) -> ProjectMemorySession:
        existing = self.db.scalar(
            select(ProjectMemorySession).where(
                ProjectMemorySession.project_id == project_id,
                ProjectMemorySession.user_id == user_id,
                ProjectMemorySession.step_code == step_code,
                ProjectMemorySession.memory_scope == memory_scope,
                ProjectMemorySession.status == 'active',
            )
        )
        if existing:
            return existing
        session = ProjectMemorySession(
            id=str(uuid4()),
            project_id=project_id,
            user_id=user_id,
            step_code=step_code,
            memory_scope=memory_scope,
            summary=None,
            status='active',
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        return session

    def append_entry(
        self,
        session_id: str,
        project_id: str,
        user_id: str | None,
        step_code: str,
        memory_type: str,
        content: str,
        metadata: dict[str, object] | None = None,
        embedding_model: str | None = None,
    ) -> ProjectMemoryEntry:
        entry = ProjectMemoryEntry(
            id=str(uuid4()),
            session_id=session_id,
            project_id=project_id,
            user_id=user_id,
            step_code=step_code,
            memory_type=memory_type,
            content=content,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
            embedding_model=embedding_model,
        )
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def save_run(
        self,
        project_id: str,
        user_id: str | None,
        step_code: str,
        workflow_role: str,
        input_payload: dict[str, object],
        output_payload: dict[str, object] | None,
        status: str,
        error_message: str | None = None,
        duration_ms: int | None = None,
    ) -> ProjectStepRun:
        run = ProjectStepRun(
            id=str(uuid4()),
            project_id=project_id,
            user_id=user_id,
            step_code=step_code,
            workflow_role=workflow_role,
            input_json=json.dumps(input_payload, ensure_ascii=False, default=_json_default),
            output_json=json.dumps(output_payload, ensure_ascii=False, default=_json_default) if output_payload is not None else None,
            status=status,
            error_message=error_message,
            duration_ms=duration_ms,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run
