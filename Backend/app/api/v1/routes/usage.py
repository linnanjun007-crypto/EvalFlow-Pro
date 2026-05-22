from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id
from app.db.session import get_db
from app.models.file import File
from app.models.llm_call import LlmCall
from app.models.project import Project
from app.models.step_output import StepOutput
from app.models.task_job import TaskJob

router = APIRouter()


@router.get("")
def usage_summary(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """返回当前用户的用量摘要：项目数、文件数、步骤生成次数、LLM 调用与 token 总量、按步骤维度的调用分布。"""
    project_ids = [pid for pid, in db.execute(select(Project.id).where(Project.user_id == user_id)).all()]
    project_count = len(project_ids)
    active_project_count = db.scalar(
        select(func.count(Project.id)).where(Project.user_id == user_id, Project.status == "active")
    ) or 0

    file_count = db.scalar(select(func.count(File.id)).where(File.user_id == user_id)) or 0

    step_output_count = 0
    task_total = 0
    task_succeeded = 0
    task_failed = 0
    if project_ids:
        step_output_count = db.scalar(
            select(func.count(StepOutput.id)).where(StepOutput.project_id.in_(project_ids))
        ) or 0
        task_total = db.scalar(select(func.count(TaskJob.id)).where(TaskJob.project_id.in_(project_ids))) or 0
        task_succeeded = db.scalar(
            select(func.count(TaskJob.id)).where(TaskJob.project_id.in_(project_ids), TaskJob.status == "succeeded")
        ) or 0
        task_failed = db.scalar(
            select(func.count(TaskJob.id)).where(TaskJob.project_id.in_(project_ids), TaskJob.status == "failed")
        ) or 0

    llm_count = db.scalar(select(func.count(LlmCall.id)).where(LlmCall.user_id == user_id)) or 0
    total_tokens = db.scalar(select(func.coalesce(func.sum(LlmCall.total_tokens), 0)).where(LlmCall.user_id == user_id)) or 0
    prompt_tokens = db.scalar(select(func.coalesce(func.sum(LlmCall.prompt_tokens), 0)).where(LlmCall.user_id == user_id)) or 0
    completion_tokens = db.scalar(
        select(func.coalesce(func.sum(LlmCall.completion_tokens), 0)).where(LlmCall.user_id == user_id)
    ) or 0
    avg_latency = db.scalar(
        select(func.coalesce(func.avg(LlmCall.latency_ms), 0)).where(LlmCall.user_id == user_id)
    ) or 0

    by_step_rows = db.execute(
        select(
            LlmCall.step_code,
            func.count(LlmCall.id),
            func.coalesce(func.sum(LlmCall.total_tokens), 0),
        )
        .where(LlmCall.user_id == user_id)
        .group_by(LlmCall.step_code)
        .order_by(LlmCall.step_code)
    ).all()
    by_step = [
        {"step_code": row[0] or "unknown", "calls": int(row[1] or 0), "total_tokens": int(row[2] or 0)}
        for row in by_step_rows
    ]

    by_model_rows = db.execute(
        select(
            LlmCall.model_name,
            func.count(LlmCall.id),
            func.coalesce(func.sum(LlmCall.total_tokens), 0),
        )
        .where(LlmCall.user_id == user_id)
        .group_by(LlmCall.model_name)
        .order_by(func.count(LlmCall.id).desc())
    ).all()
    by_model = [
        {"model_name": row[0] or "unknown", "calls": int(row[1] or 0), "total_tokens": int(row[2] or 0)}
        for row in by_model_rows
    ]

    failure_rate = round((task_failed / task_total) * 100, 2) if task_total else 0.0

    return {
        "user_id": user_id,
        "projects": {"total": int(project_count), "active": int(active_project_count)},
        "files": int(file_count),
        "steps_generated": int(step_output_count),
        "tasks": {
            "total": int(task_total),
            "succeeded": int(task_succeeded),
            "failed": int(task_failed),
            "failure_rate": failure_rate,
        },
        "llm": {
            "calls": int(llm_count),
            "total_tokens": int(total_tokens),
            "prompt_tokens": int(prompt_tokens),
            "completion_tokens": int(completion_tokens),
            "avg_latency_ms": int(avg_latency),
        },
        "by_step": by_step,
        "by_model": by_model,
    }
