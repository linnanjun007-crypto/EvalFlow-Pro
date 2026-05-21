from __future__ import annotations

from pydantic import BaseModel, Field


class ConversationMessageCreate(BaseModel):
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)
    model_name: str | None = None


class ConversationCreateRequest(BaseModel):
    project_id: str = Field(min_length=1)
    step_code: str = Field(min_length=1)
    user_id: str | None = None
    title: str | None = None


class ConversationCreateResponse(BaseModel):
    id: str
    project_id: str
    step_code: str
    title: str
    status: str


class ConversationMessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    model_name: str | None = None


class ConversationDetailResponse(BaseModel):
    conversation: ConversationCreateResponse
    messages: list[ConversationMessageResponse]
