"""报告管理路由 — /api/v1/reports"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id
from app.core.errors import bad_request, not_found
from app.db.session import get_db

router = APIRouter()


class UpdateRetentionRequest(BaseModel):
    retention_days: int = Field(ge=1, le=365)


@router.get("")
def list_reports(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    from app.services.project_report_service import list_reports as _list

    return {"items": _list(db, user_id)}


@router.get("/{report_id}")
def get_report(
    report_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.services.project_report_service import get_report as _get

    try:
        return _get(db, report_id, user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.patch("/{report_id}")
def update_report_retention(
    report_id: str,
    payload: UpdateRetentionRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.services.project_report_service import update_retention

    try:
        return update_retention(db, report_id, user_id, payload.retention_days)
    except ValueError as exc:
        raise bad_request(str(exc)) from exc


@router.delete("/{report_id}")
def delete_report(
    report_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    from app.services.project_report_service import delete_report as _del

    try:
        _del(db, report_id, user_id)
        return {"message": "deleted"}
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.get("/{report_id}/export")
def export_report(
    report_id: str,
    format: Literal["md", "txt"] = Query(default="md"),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    from app.services.project_report_service import get_report as _get
    from urllib.parse import quote

    try:
        report = _get(db, report_id, user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc

    content = report.get("content_md", "")
    title = report.get("title", "report")
    safe_name = title.replace("/", "_").replace("\\", "_")
    filename = f"{safe_name}.{format}"

    def _iter():
        yield content.encode("utf-8")

    return StreamingResponse(
        _iter(),
        media_type="text/markdown" if format == "md" else "text/plain",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/regenerate/{project_id}")
def regenerate_report(
    project_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.services.project_report_service import generate_report

    try:
        return generate_report(db, project_id=project_id, user_id=user_id)
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
