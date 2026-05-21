from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter()


def get_chat_service(_: Session = Depends(get_db)) -> ChatService:
    return ChatService()


@router.post('/send', response_model=ChatResponse)
def send_chat(payload: ChatRequest, service: ChatService = Depends(get_chat_service)) -> dict[str, object]:
    workflow_state = payload.workflow_state or {}
    return service.send(
        project_id=payload.project_id,
        step_code=payload.step_code,
        user_message=payload.user_message,
        messages=[m.model_dump() for m in payload.messages],
        workflow_role=payload.workflow_role,
        workflow_state=workflow_state,
    )
