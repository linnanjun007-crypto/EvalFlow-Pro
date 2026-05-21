from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.integrations.agent_runner import AgentRunner


def extract_message_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    content = getattr(value, 'content', None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(value, dict):
        content = value.get('content')
        if isinstance(content, str):
            return content.strip()
    return ''


def extract_last_ai_message_text(result: dict[str, Any]) -> str:
    messages = result.get('messages')
    if not isinstance(messages, list):
        return ''
    for message in reversed(messages):
        role = getattr(message, 'type', None) or getattr(message, 'role', None)
        if isinstance(message, dict):
            role = message.get('type') or message.get('role') or role
        text = extract_message_text(message)
        if text and str(role).lower() in {'ai', 'assistant'}:
            return text
    for message in reversed(messages):
        text = extract_message_text(message)
        if text:
            return text
    return ''


class ChatService:
    def __init__(self) -> None:
        self.runner = AgentRunner()

    def send(
        self,
        project_id: str,
        step_code: str,
        user_message: str,
        messages: list[dict[str, Any]],
        workflow_role: str,
        workflow_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        graph_messages = []
        for message in messages:
            role = str(message.get('role', 'user'))
            content = str(message.get('content', ''))
            if role == 'assistant':
                graph_messages.append(AIMessage(content=content))
            else:
                graph_messages.append(HumanMessage(content=content))

        workflow_state = workflow_state or {}
        latest_user_text = str(workflow_state.get('latest_user_message') or user_message).strip()
        graph_messages = [message for message in graph_messages if not isinstance(message, HumanMessage) or message.content.strip() != latest_user_text]
        graph_messages.append(HumanMessage(content=latest_user_text))

        payload = {
            'project_id': project_id,
            'step_code': step_code,
            'status': 'chat',
            'messages': graph_messages,
            'workflow_state': workflow_state,
        }
        model_provider = str(
            workflow_state.get('active_model_provider')
            or workflow_state.get('client_model_provider')
            or workflow_state.get('model_provider')
            or 'openai-compatible'
        ).strip()
        model_name = str(
            workflow_state.get('active_model_name')
            or workflow_state.get('client_model_name')
            or workflow_state.get('model_name')
            or workflow_state.get('model')
            or ''
        ).strip()
        base_url = str(
            workflow_state.get('active_base_url')
            or workflow_state.get('client_model_base_url')
            or workflow_state.get('base_url')
            or ''
        ).strip()
        api_key = str(
            workflow_state.get('active_api_key')
            or workflow_state.get('client_model_api_key')
            or workflow_state.get('api_key')
            or ''
        ).strip()
        try:
            temperature = float(
                workflow_state.get('active_temperature')
                or workflow_state.get('client_model_temperature')
                or workflow_state.get('temperature')
                or 0.2
            )
        except (TypeError, ValueError):
            temperature = 0.2
        temperature = min(2.0, max(0.0, temperature))

        chat_context = {
            'project_id': project_id,
            'workflow_role': workflow_role,
            'step_code': step_code,
            'chat_mode': True,
            'workflow_state': workflow_state,
            'model_provider': model_provider,
            'model_name': model_name,
            'base_url': base_url,
            'api_key': api_key,
            'temperature': temperature,
            'active_model_provider': model_provider,
            'active_model_name': model_name,
            'active_base_url': base_url,
            'active_api_key': api_key,
            'active_temperature': temperature,
            'latest_user_message': latest_user_text,
        }
        for key in ('active_model_configs', 'model_configs'):
            if key in workflow_state:
                chat_context[key] = workflow_state[key]

        result = self.runner.run(
            role=workflow_role,
            step_code=step_code,
            payload=payload,
            context=chat_context,
        )
        result_status = str(result.get('status') or '')
        if result_status in {'chat_small_talk', 'chat_qa', 'chat_reply'} or result_status.startswith('chat_intent_'):
            answer_candidates = [
                result.get('answer'),
                result.get('message'),
                result.get('content'),
                result.get('draft_manifest'),
                result.get('final_manifest'),
            ]
        else:
            answer_candidates = [
                result.get('draft_manifest'),
                result.get('final_manifest'),
                result.get('answer'),
                result.get('message'),
                result.get('content'),
            ]
        answer = next((item for item in answer_candidates if isinstance(item, str) and item.strip()), '')
        if not answer:
            answer = extract_last_ai_message_text(result)
        if not answer and result_status == 'chat_model_failed':
            error_text = result.get('error')
            answer = f'AI 对话模型调用失败：{error_text}。请检查当前生效模型的 Base URL、API Key 和模型名是否正确。' if isinstance(error_text, str) and error_text.strip() else ''
        if not answer:
            answer = 'AI 已完成调用，但未返回可展示的文本。请检查当前模型配置或稍后重试。'
        return {
            'project_id': project_id,
            'step_code': step_code,
            'answer': answer,
            'status': result.get('status', 'ok'),
            'title': result.get('title'),
            'fallback_step_code': result.get('fallback_step_code'),
            'chat_intent': result.get('chat_intent'),
        }
