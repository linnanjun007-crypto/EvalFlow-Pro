from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.conversation import Conversation
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationDetailResponse,
    ConversationMessageCreate,
    ConversationMessageResponse,
)
from app.services.conversation_service import ConversationService

router = APIRouter()


def get_conversation_service(db: Session = Depends(get_db)) -> ConversationService:
    return ConversationService(db)


@router.post('', response_model=ConversationCreateResponse)
def create_conversation(payload: ConversationCreateRequest, service: ConversationService = Depends(get_conversation_service)) -> dict[str, object]:
    conversation = service.create_conversation(payload.project_id, payload.step_code, payload.user_id, payload.title)
    return {
        'id': conversation.id,
        'project_id': conversation.project_id,
        'step_code': conversation.step_code,
        'title': conversation.title,
        'status': conversation.status,
    }


@router.get('/{conversation_id}', response_model=ConversationDetailResponse)
def get_conversation(conversation_id: str, service: ConversationService = Depends(get_conversation_service)) -> dict[str, object]:
    conversation = service.db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail='会话不存在')
    messages = service.list_messages(conversation_id)
    return {
        'conversation': {
            'id': conversation.id,
            'project_id': conversation.project_id,
            'step_code': conversation.step_code,
            'title': conversation.title,
            'status': conversation.status,
        },
        'messages': [
            {'id': msg.id, 'conversation_id': msg.conversation_id, 'role': msg.role, 'content': msg.content, 'model_name': msg.model_name}
            for msg in messages
        ],
    }


@router.post('/{conversation_id}/messages')
def send_message(conversation_id: str, payload: ConversationMessageCreate = Body(...), service: ConversationService = Depends(get_conversation_service)) -> dict[str, object]:
    return service.send_message(conversation_id, payload.content, workflow_role='user')
