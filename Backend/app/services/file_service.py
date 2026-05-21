from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.file import File


class FileService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_file_record(
        self,
        project_id: str,
        user_id: str,
        file_name: str,
        file_type: str,
        storage_key: str,
        source_type: str | None = None,
        file_size: int | None = None,
        metadata_json: str | None = None,
        project_name: str | None = None,
        draft_thread_id: str | None = None,
        draft_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not storage_key:
            storage_key = f"projects/{project_id}/files/{file_name}"

        _ = draft_payload
        if source_type == "step1_draft_commit" and draft_thread_id:
            old_drafts = self.db.scalars(
                select(File).where(
                    File.project_id == project_id,
                    File.source_type.in_(["step1_draft", "step1_draft_commit"]),
                    File.storage_key != storage_key,
                    File.metadata_json.contains(draft_thread_id),
                )
            ).all()
            for old_draft in old_drafts:
                self.db.delete(old_draft)

        existing = self.db.scalar(
            select(File).where(
                File.project_id == project_id,
                File.file_name == file_name,
                File.storage_key == storage_key,
            )
        )
        if existing:
            existing.user_id = user_id
            existing.file_type = file_type
            existing.parse_status = "pending"
            existing.source_type = source_type
            existing.file_size = file_size
            existing.metadata_json = metadata_json
            if project_name:
                existing.project_name = project_name
            self.db.commit()
            self.db.refresh(existing)
            return self._to_dict(existing)

        item = File(
            id=str(uuid4()),
            project_id=project_id,
            user_id=user_id,
            project_name=project_name,
            file_name=file_name,
            file_type=file_type,
            storage_key=storage_key,
            parse_status="pending",
            source_type=source_type,
            file_size=file_size,
            metadata_json=metadata_json,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return self._to_dict(item)

    def list_files(self, project_id: str) -> list[dict[str, Any]]:
        items = self.db.scalars(select(File).where(File.project_id == project_id)).all()
        return [self._to_dict(item) for item in items]

    def get_file(self, file_id: str, project_id: str) -> dict[str, Any]:
        item = self.db.scalar(select(File).where(File.id == file_id, File.project_id == project_id))
        if not item:
            raise ValueError("文件不存在")
        return self._to_dict(item)

    def delete_file(self, file_id: str, project_id: str) -> None:
        item = self.db.scalar(select(File).where(File.id == file_id, File.project_id == project_id))
        if not item:
            raise ValueError("文件不存在")
        self.db.delete(item)
        self.db.commit()

    def _to_dict(self, item: File) -> dict[str, Any]:
        return {
            "id": item.id,
            "project_id": item.project_id,
            "user_id": item.user_id,
            "project_name": item.project_name,
            "file_name": item.file_name,
            "file_type": item.file_type,
            "storage_key": item.storage_key,
            "parse_status": item.parse_status,
            "source_type": item.source_type,
            "file_size": item.file_size,
            "metadata_json": item.metadata_json,
        }
