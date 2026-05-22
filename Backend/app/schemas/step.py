from typing import Any

from pydantic import BaseModel, Field


class StepGenerateRequest(BaseModel):
    project_id: str = Field(min_length=1)
    review_mode: str | None = None
    review_feedback: str | None = None
    workflow_role: str = "user"
    step_code: str | None = None
    payload: dict[str, Any] | None = None


class StepGenerateResponse(BaseModel):
    task_id: str | None = None
    step_code: str
    message: str
    status: str = "queued"


class StepResultResponse(BaseModel):
    project_id: str
    step_code: str
    status: str
    result: dict[str, Any]
