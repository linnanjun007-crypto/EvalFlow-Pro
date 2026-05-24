from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id
from app.core.errors import not_found
from app.db.session import get_db
from app.services.kb_service import KbService
from app.services.project_service import ProjectService

router = APIRouter()


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class ProjectKbBindRequest(BaseModel):
    kb_ids: list[str] = Field(default_factory=list)


def get_project_service(db: Session = Depends(get_db)) -> ProjectService:
    return ProjectService(db)


def get_kb_service(db: Session = Depends(get_db)) -> KbService:
    return KbService(db)


@router.get("")
def list_projects(
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
) -> dict[str, list[dict[str, object]]]:
    return {"items": service.list_projects(user_id=user_id)}


@router.post("")
def create_project(
    payload: ProjectCreateRequest = Body(...),
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
) -> dict[str, object]:
    return service.create_project(user_id=user_id, name=payload.name, description=payload.description)


@router.get("/{project_id}")
def get_project(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
) -> dict[str, object]:
    try:
        return service.get_project(project_id, user_id=user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.patch("/{project_id}")
def update_project(
    project_id: str,
    payload: ProjectUpdateRequest = Body(...),
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
) -> dict[str, object]:
    try:
        return service.update_project(
            project_id,
            user_id=user_id,
            name=payload.name,
            description=payload.description,
            status=payload.status,
        )
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.delete("/{project_id}")
def delete_project(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    service: ProjectService = Depends(get_project_service),
) -> dict[str, str]:
    try:
        service.delete_project(project_id, user_id=user_id)
        return {"message": "deleted"}
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.get("/{project_id}/kbs")
def list_project_kbs(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    kb_service: KbService = Depends(get_kb_service),
) -> dict[str, list[dict[str, object]]]:
    return {"items": kb_service.list_project_kbs(project_id, user_id)}


@router.put("/{project_id}/kbs")
def set_project_kbs(
    project_id: str,
    payload: ProjectKbBindRequest = Body(...),
    user_id: str = Depends(get_current_user_id),
    kb_service: KbService = Depends(get_kb_service),
) -> dict[str, list[dict[str, object]]]:
    return {"items": kb_service.set_project_kbs(project_id, user_id, payload.kb_ids)}
