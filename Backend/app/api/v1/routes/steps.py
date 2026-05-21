from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.core.errors import bad_request
from app.db.session import get_db
from app.schemas.step import StepGenerateRequest, StepGenerateResponse, StepResultResponse
from app.services.step_service import StepService

router = APIRouter()


def get_step_service(db: Session = Depends(get_db)) -> StepService:
    return StepService(db)


@router.post("/{step_code}/generate", response_model=StepGenerateResponse)
def generate_step(
    step_code: str,
    payload: StepGenerateRequest,
    service: StepService = Depends(get_step_service),
) -> dict[str, str | None]:
    try:
        result = service.generate_step(
            project_id=payload.project_id,
            step_code=step_code,
            role=payload.workflow_role,
            payload=payload.payload | {"review_mode": payload.review_mode, "review_feedback": payload.review_feedback},
            context={"project_id": payload.project_id, "workflow_role": payload.workflow_role},
        )
        return {
            "task_id": result["task_id"],
            "step_code": step_code,
            "message": "step generated",
            "status": result["status"],
        }
    except ValueError as exc:
        raise bad_request(str(exc)) from exc


@router.get("/status")
def get_workflow_status(project_id: str, service: StepService = Depends(get_step_service)) -> dict[str, object]:
    return service.get_workflow_status(project_id=project_id)


@router.get("/{step_code}/result", response_model=StepResultResponse)
def get_step_result(step_code: str, project_id: str, service: StepService = Depends(get_step_service)) -> dict[str, object]:
    return service.get_step_result(project_id=project_id, step_code=step_code)


@router.post("/{step_code}/save")
def save_step_result(
    step_code: str,
    payload: dict[str, object] = Body(...),
    service: StepService = Depends(get_step_service),
) -> dict[str, object]:
    try:
        return service.save_step_result(
            project_id=str(payload.get("project_id") or ""),
            step_code=step_code,
            title=str(payload.get("title") or f"{step_code} 输出"),
            content_text=str(payload.get("content_text") or ""),
            content_json=str(payload.get("content_json") or "{}"),
            model_name=str(payload.get("model_name") or "manual-edit"),
        )
    except ValueError as exc:
        raise bad_request(str(exc)) from exc


@router.get("/{step_code}/histories")
def list_step_histories(step_code: str, project_id: str, service: StepService = Depends(get_step_service)) -> dict[str, object]:
    return {"items": service.list_step_histories(project_id=project_id, step_code=step_code)}


@router.delete("/{step_code}/histories/{output_id}")
def delete_step_history(step_code: str, output_id: str, project_id: str, service: StepService = Depends(get_step_service)) -> dict[str, str]:
    try:
        service.delete_step_output(project_id=project_id, step_code=step_code, output_id=output_id)
        return {"message": "deleted"}
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
