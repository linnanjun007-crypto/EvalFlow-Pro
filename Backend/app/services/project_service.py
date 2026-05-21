from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project


class ProjectService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_project(self, name: str, description: str | None = None, user_id: str = "demo-user-id") -> dict[str, Any]:
        project = Project(
            id=str(uuid4()),
            user_id=user_id,
            name=name,
            description=description,
            status="active",
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        return self._to_dict(project)

    def list_projects(self, user_id: str = "demo-user-id") -> list[dict[str, Any]]:
        items = self.db.scalars(select(Project).where(Project.user_id == user_id)).all()
        return [self._to_dict(item) for item in items]

    def get_project(self, project_id: str, user_id: str = "demo-user-id") -> dict[str, Any]:
        item = self.db.scalar(select(Project).where(Project.id == project_id, Project.user_id == user_id))
        if not item:
            raise ValueError("项目不存在")
        return self._to_dict(item)

    def update_project(
        self,
        project_id: str,
        user_id: str = "demo-user-id",
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        item = self.db.scalar(select(Project).where(Project.id == project_id, Project.user_id == user_id))
        if not item:
            raise ValueError("项目不存在")
        if name is not None:
            item.name = name
        if description is not None:
            item.description = description
        if status is not None:
            item.status = status
        self.db.commit()
        self.db.refresh(item)
        return self._to_dict(item)

    def delete_project(self, project_id: str, user_id: str = "demo-user-id") -> None:
        item = self.db.scalar(select(Project).where(Project.id == project_id, Project.user_id == user_id))
        if not item:
            raise ValueError("项目不存在")
        self.db.delete(item)
        self.db.commit()

    def _to_dict(self, item: Project) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "status": item.status,
        }
