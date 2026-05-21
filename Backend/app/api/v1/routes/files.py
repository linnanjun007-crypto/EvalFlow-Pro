from pathlib import Path
from uuid import uuid4

from typing import Any

from fastapi import APIRouter, Body, Depends, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.errors import not_found
from app.db.session import get_db
from app.services.file_service import FileService

router = APIRouter()


class FileCreateRequest(BaseModel):
    user_id: str = Field(default="demo-user-id")
    project_name: str | None = None
    file_name: str = Field(default="unnamed", min_length=1)
    file_type: str = Field(default="unknown", min_length=1)
    storage_key: str = Field(default="")
    source_type: str | None = None
    file_size: int | None = None
    metadata_json: str | None = None
    draft_thread_id: str | None = None
    draft_payload: dict[str, Any] | None = None


def get_file_service(db: Session = Depends(get_db)) -> FileService:
    return FileService(db)


@router.post("/{project_id}")
def create_file_record(
    project_id: str,
    payload: FileCreateRequest = Body(...),
    service: FileService = Depends(get_file_service),
) -> dict[str, object]:
    return service.create_file_record(
        project_id=project_id,
        user_id=payload.user_id,
        file_name=payload.file_name,
        file_type=payload.file_type,
        storage_key=payload.storage_key,
        source_type=payload.source_type,
        file_size=payload.file_size,
        metadata_json=payload.metadata_json,
        project_name=payload.project_name,
        draft_thread_id=payload.draft_thread_id,
        draft_payload=payload.draft_payload,
    )


@router.post("/{project_id}/upload")
async def upload_file(
    project_id: str,
    user_id: str = "demo-user-id",
    upload: UploadFile = File(...),
    service: FileService = Depends(get_file_service),
) -> dict[str, object]:
    safe_name = Path(upload.filename or "unnamed").name
    suffix = Path(safe_name).suffix.lower().lstrip(".") or "unknown"
    target_dir = Path(__file__).resolve().parents[4] / "storage" / "projects" / project_id / "files"
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}_{safe_name}"
    target_path = target_dir / stored_name
    content = await upload.read()
    target_path.write_bytes(content)
    created = service.create_file_record(
        project_id=project_id,
        user_id=user_id,
        file_name=safe_name,
        file_type=suffix,
        storage_key=str(target_path),
        source_type="local_upload",
        file_size=len(content),
        metadata_json=None,
        project_name=Path(safe_name).stem,
    )
    return {**created, "message": "uploaded", "stored_path": str(target_path)}


@router.get("/{project_id}")
def list_files(project_id: str, service: FileService = Depends(get_file_service)) -> dict[str, list[dict[str, object]]]:
    return {"items": service.list_files(project_id)}


@router.get("/{project_id}/{file_id}")
def get_file(project_id: str, file_id: str, service: FileService = Depends(get_file_service)) -> dict[str, object]:
    try:
        return service.get_file(file_id, project_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.delete("/{project_id}/{file_id}")
def delete_file(project_id: str, file_id: str, service: FileService = Depends(get_file_service)) -> dict[str, str]:
    try:
        service.delete_file(file_id, project_id)
        return {"message": "deleted"}
    except ValueError as exc:
        raise not_found(str(exc)) from exc
