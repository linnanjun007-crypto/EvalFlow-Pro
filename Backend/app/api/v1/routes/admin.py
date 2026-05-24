from typing import Literal

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_actor_user_id
from app.core.errors import bad_request, not_found
from app.db.session import get_db
from app.integrations.agent_runner import AgentRunner
from app.models.audit_log import AuditLog
from app.models.llm_call import LlmCall
from app.models.project import Project
from app.models.task_job import TaskJob
from app.models.user import User
from app.services.admin_service import AdminService
from app.services.audit_service import AuditService

router = APIRouter()
_agent_runner = AgentRunner()


class PromptCreateRequest(BaseModel):
    step_code: str = Field(default="step1", min_length=1)
    title: str = Field(default="Untitled", min_length=1)
    content: str = Field(default="")


class PromptUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None


class ModelCreateRequest(BaseModel):
    name: str = Field(default="model", min_length=1)
    model_id: str = Field(default="unknown", min_length=1)
    api_key: str | None = None
    base_url: str | None = None
    supports_vision: bool = False
    kind: str = "chat"
    dimensions: int | None = None


class ModelToggleRequest(BaseModel):
    enabled: bool | None = None
    name: str | None = None
    model_id: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    supports_vision: bool | None = None
    kind: str | None = None
    dimensions: int | None = None


class KbCreateRequest(BaseModel):
    step_code: str = Field(default="step1", min_length=1)
    name: str = Field(default="kb", min_length=1)
    storage_ref: str = Field(default="")


class KbUpdateRequest(BaseModel):
    name: str | None = None
    storage_ref: str | None = None


class ModuleOrderUpdateRequest(BaseModel):
    module_order: list[str] = Field(default_factory=list)


class StepConfigSaveRequest(BaseModel):
    prompt_title: str = Field(default="资料清单生成 Prompt")
    prompt_content: str = Field(default="")
    kb_name: str = Field(default="资料清单知识库")
    kb_content: str = Field(default="")
    action: Literal["save", "preview"] = "save"


def get_admin_service(db: Session = Depends(get_db)) -> AdminService:
    return AdminService(db)


def get_audit_service(db: Session = Depends(get_db)) -> AuditService:
    return AuditService(db)


@router.get("/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db)) -> dict[str, object]:
    """管理端仪表盘 KPI 数据。"""
    total_users = db.scalar(select(func.count(User.id))) or 0
    active_users = db.scalar(select(func.count(User.id)).where(User.status == "active")) or 0
    total_projects = db.scalar(select(func.count(Project.id))) or 0
    total_llm_calls = db.scalar(select(func.count(LlmCall.id))) or 0
    total_tokens = db.scalar(select(func.coalesce(func.sum(LlmCall.total_tokens), 0))) or 0
    total_tasks = db.scalar(select(func.count(TaskJob.id))) or 0
    failed_tasks = db.scalar(select(func.count(TaskJob.id)).where(TaskJob.status == "failed")) or 0
    failure_rate = round((failed_tasks / total_tasks) * 100, 2) if total_tasks else 0.0

    audit_svc = AuditService(db)
    recent_events = audit_svc.list_logs(limit=5)

    return {
        "users": {"total": int(total_users), "active": int(active_users)},
        "projects": int(total_projects),
        "llm_calls": int(total_llm_calls),
        "total_tokens": int(total_tokens),
        "tasks": {"total": int(total_tasks), "failed": int(failed_tasks), "failure_rate": failure_rate},
        "recent_events": recent_events,
    }


@router.get("/steps")
def list_admin_steps(service: AdminService = Depends(get_admin_service)) -> dict[str, list[dict[str, object]]]:
    return {"items": service.list_admin_steps()}


@router.get("/steps/{step_code}")
def get_admin_step(step_code: str, service: AdminService = Depends(get_admin_service)) -> dict[str, object]:
    try:
        service.ensure_step_defaults(step_code)
        return service.get_admin_step(step_code)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.get("/steps/{step_code}/active-config")
def get_active_step_config(step_code: str, service: AdminService = Depends(get_admin_service)) -> dict[str, object]:
    try:
        return service.get_active_config(step_code)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.get("/steps/{step_code}/runtime-config")
def get_client_runtime_config(step_code: str, service: AdminService = Depends(get_admin_service)) -> dict[str, object]:
    """客户端调用：仅返回是否存在启用配置，不返回 Prompt/知识库正文。"""
    return service.get_client_runtime_config(step_code)


@router.post("/steps/{step_code}/config")
def save_step_config(
    step_code: str,
    payload: StepConfigSaveRequest = Body(...),
    actor_user_id: str = Depends(get_actor_user_id),
    service: AdminService = Depends(get_admin_service),
) -> dict[str, object]:
    if step_code not in {item["code"] for item in service.list_admin_steps()}:
        raise not_found("管理端步骤不存在")

    active = service.get_active_config(step_code)
    graph_payload = {
        "step_code": step_code,
        "action": payload.action,
        "project_name": f"管理端·{step_code}",
        "prompt_title": payload.prompt_title,
        "prompt_text": payload.prompt_content,
        "kb_name": payload.kb_name,
        "knowledge_text": payload.kb_content,
        "previous_prompt_text": active.get("prompt_text") or "",
        "previous_knowledge_text": active.get("knowledge_text") or "",
        "previous_prompt_title": active.get("prompt_title") or "",
        "previous_kb_name": active.get("kb_name") or "",
        "actor_user_id": actor_user_id,
    }
    graph_result = _agent_runner.run(role="admin", step_code=step_code, payload=graph_payload, context={"user_id": actor_user_id})
    if not isinstance(graph_result, dict):
        raise bad_request("配置处理失败")

    if graph_result.get("status") == "validation_failed":
        raise bad_request(str(graph_result.get("error") or "配置校验未通过"))

    change_entries = graph_result.get("change_entries") or []
    if payload.action == "save":
        step = service.apply_graph_save(
            actor_user_id=actor_user_id,
            step_code=step_code,
            prompt_title=payload.prompt_title,
            prompt_content=payload.prompt_content,
            kb_name=payload.kb_name,
            kb_content=payload.kb_content,
            change_entries=change_entries,
        )
    else:
        step = service.get_admin_step(step_code)

    return {
        "step": step,
        "graph_result": graph_result,
        "change_entries": change_entries,
    }


@router.put("/steps/{step_code}/module-order")
def update_module_order(
    step_code: str,
    payload: ModuleOrderUpdateRequest = Body(...),
    service: AdminService = Depends(get_admin_service),
) -> dict[str, object]:
    try:
        return service.update_module_order(step_code, payload.module_order)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.get("/change-logs")
def list_change_logs(
    step_code: str | None = None,
    target_type: str | None = None,
    limit: int = 100,
    audit: AuditService = Depends(get_audit_service),
) -> dict[str, list[dict[str, object]]]:
    return {"items": audit.list_logs(step_code=step_code, target_type=target_type, limit=limit)}


@router.get("/prompts")
def list_prompts(step_code: str | None = None, service: AdminService = Depends(get_admin_service)) -> dict[str, list[dict[str, object]]]:
    return {"items": service.list_prompts(step_code)}


@router.post("/prompts")
def create_prompt(
    payload: PromptCreateRequest = Body(...),
    actor_user_id: str = Depends(get_actor_user_id),
    service: AdminService = Depends(get_admin_service),
) -> dict[str, object]:
    return service.create_prompt(payload.step_code, payload.title, payload.content, actor_user_id=actor_user_id)


@router.patch("/prompts/{prompt_id}")
def update_prompt(
    prompt_id: str,
    payload: PromptUpdateRequest = Body(...),
    actor_user_id: str = Depends(get_actor_user_id),
    service: AdminService = Depends(get_admin_service),
) -> dict[str, object]:
    try:
        return service.update_prompt(prompt_id, payload.title, payload.content, actor_user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.patch("/prompts/{prompt_id}/activate")
def activate_prompt(
    prompt_id: str,
    actor_user_id: str = Depends(get_actor_user_id),
    service: AdminService = Depends(get_admin_service),
) -> dict[str, object]:
    try:
        return service.activate_prompt(prompt_id, actor_user_id=actor_user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.delete("/prompts/{prompt_id}")
def delete_prompt(
    prompt_id: str,
    actor_user_id: str = Depends(get_actor_user_id),
    service: AdminService = Depends(get_admin_service),
) -> dict[str, str]:
    try:
        service.delete_prompt(prompt_id, actor_user_id=actor_user_id)
        return {"message": "deleted"}
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.get("/models")
def list_models(service: AdminService = Depends(get_admin_service)) -> dict[str, list[dict[str, object]]]:
    return {"items": service.list_models()}


@router.post("/models")
def create_model(
    payload: ModelCreateRequest = Body(...),
    service: AdminService = Depends(get_admin_service),
) -> dict[str, object]:
    return service.create_model(
        name=payload.name,
        model_id=payload.model_id,
        api_key=payload.api_key,
        base_url=payload.base_url,
        supports_vision=payload.supports_vision,
        kind=payload.kind,
        dimensions=payload.dimensions,
    )


@router.patch("/models/{model_id}")
def toggle_model(
    model_id: str,
    payload: ModelToggleRequest = Body(...),
    service: AdminService = Depends(get_admin_service),
) -> dict[str, object]:
    try:
        return service.update_model(model_id, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.delete("/models/{model_id}")
def delete_model(model_id: str, service: AdminService = Depends(get_admin_service)) -> dict[str, str]:
    try:
        service.delete_model(model_id)
        return {"message": "deleted"}
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.post("/models/{model_id}/set-default")
def set_default_model(
    model_id: str,
    actor_user_id: str = Depends(get_actor_user_id),
    service: AdminService = Depends(get_admin_service),
) -> dict[str, object]:
    try:
        return service.set_default_model(model_id, actor_user_id=actor_user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.get("/kbs")
def list_kbs(step_code: str | None = None, service: AdminService = Depends(get_admin_service)) -> dict[str, list[dict[str, object]]]:
    return {"items": service.list_kbs(step_code)}


@router.post("/kbs")
def create_kb(
    payload: KbCreateRequest = Body(...),
    actor_user_id: str = Depends(get_actor_user_id),
    service: AdminService = Depends(get_admin_service),
) -> dict[str, object]:
    return service.create_kb(payload.step_code, payload.name, payload.storage_ref, actor_user_id=actor_user_id)


@router.patch("/kbs/{kb_id}")
def update_kb(
    kb_id: str,
    payload: KbUpdateRequest = Body(...),
    actor_user_id: str = Depends(get_actor_user_id),
    service: AdminService = Depends(get_admin_service),
) -> dict[str, object]:
    try:
        return service.update_kb(kb_id, payload.name, payload.storage_ref, actor_user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.patch("/kbs/{kb_id}/activate")
def activate_kb(
    kb_id: str,
    actor_user_id: str = Depends(get_actor_user_id),
    service: AdminService = Depends(get_admin_service),
) -> dict[str, object]:
    try:
        return service.activate_kb(kb_id, actor_user_id=actor_user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.delete("/kbs/{kb_id}")
def delete_kb(
    kb_id: str,
    actor_user_id: str = Depends(get_actor_user_id),
    service: AdminService = Depends(get_admin_service),
) -> dict[str, str]:
    try:
        service.delete_kb(kb_id, actor_user_id=actor_user_id)
        return {"message": "deleted"}
    except ValueError as exc:
        raise not_found(str(exc)) from exc
