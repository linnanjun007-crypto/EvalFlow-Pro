from __future__ import annotations

from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.integrations.agent_runner import AgentRunner
from app.models.conversation import Conversation, ConversationMessage


class ConversationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.runner = AgentRunner()

    def create_conversation(self, project_id: str, step_code: str, user_id: str | None = None, title: str | None = None) -> Conversation:
        conversation = Conversation(
            id=str(uuid4()),
            project_id=project_id,
            step_code=step_code,
            user_id=user_id,
            title=title or f'{step_code} 对话',
            status='active',
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def list_messages(self, conversation_id: str) -> list[ConversationMessage]:
        return list(self.db.scalars(select(ConversationMessage).where(ConversationMessage.conversation_id == conversation_id).order_by(ConversationMessage.created_at.asc())).all())

    def append_message(self, conversation_id: str, role: str, content: str, model_name: str | None = None) -> ConversationMessage:
        message = ConversationMessage(
            id=str(uuid4()),
            conversation_id=conversation_id,
            role=role,
            content=content,
            model_name=model_name,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def send_message(self, conversation_id: str, user_message: str, workflow_role: str = 'user') -> dict[str, object]:
        conversation = self.db.get(Conversation, conversation_id)
        if not conversation:
            raise ValueError('会话不存在')

        history = self.list_messages(conversation_id)
        self.append_message(conversation_id, 'user', user_message)

        payload_messages = []
        for item in history:
            if item.role == 'assistant':
                payload_messages.append(AIMessage(content=item.content))
            else:
                payload_messages.append(HumanMessage(content=item.content))
        payload_messages.append(HumanMessage(content=user_message))

        result = self.runner.run(
            role=workflow_role,
            step_code=conversation.step_code,
            payload={
                'project_id': conversation.project_id,
                'step_code': conversation.step_code,
                'status': 'chat',
                'messages': payload_messages,
            },
            context={
                'project_id': conversation.project_id,
                'step_code': conversation.step_code,
                'workflow_role': workflow_role,
                'chat_mode': True,
                'thread_id': conversation_id,
            },
        )

        answer = str(result.get('answer') or result.get('message') or result.get('content') or result)
        assistant_message = self.append_message(conversation_id, 'assistant', answer, model_name=str(result.get('model_name')) if result.get('model_name') else None)
        return {
            'conversation_id': conversation_id,
            'project_id': conversation.project_id,
            'step_code': conversation.step_code,
            'answer': assistant_message.content,
            'status': str(result.get('status', 'ok')),
        }
