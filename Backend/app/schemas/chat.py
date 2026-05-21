from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    project_id: str = Field(min_length=1)
    step_code: str = Field(min_length=1)
    user_message: str = Field(min_length=1)
    workflow_role: str = Field(default='user')
    messages: list[ChatMessage] = Field(default_factory=list)
    workflow_state: dict[str, object] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    project_id: str
    step_code: str
    answer: str
    status: str
    title: str | None = None
    chat_intent: str | None = None
