from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool

from app.core.deps import get_current_user_id
from app.db.session import SessionLocal
from app.integrations.agent_runner import AgentRunner
from app.models.file import File
from app.services.admin_service import AdminService
from app.services.memory_service import MemoryService
from sqlalchemy import select

router = APIRouter()
runner = AgentRunner()
ACTIVE_RUNS: dict[str, Event] = {}

ROLE_DIRS = {
    'user': 'user_graphs',
    'client': 'user_graphs',
    'client_graphs': 'user_graphs',
    'admin': 'admin_graphs',
    'manager': 'admin_graphs',
    'admin_graphs': 'admin_graphs',
}


def _normalize_temperature(value: Any, default: float = 0.2) -> float:
    try:
        temperature = float(value)
    except (TypeError, ValueError):
        temperature = default
    return min(2.0, max(0.0, temperature))


def _normalize_model_configs(context: dict[str, Any], body: dict[str, Any]) -> list[dict[str, Any]]:
    raw_configs = context.get('active_model_configs') or context.get('model_configs') or body.get('model_configs') or body.get('active_model_configs') or []
    configs: list[dict[str, Any]] = []
    if isinstance(raw_configs, list):
        for index, item in enumerate(raw_configs):
            if not isinstance(item, dict):
                continue
            model_name = str(item.get('model_name') or item.get('name') or '').strip()
            base_url = str(item.get('base_url') or '').strip()
            api_key = str(item.get('api_key') or '').strip()
            if not (model_name and base_url and api_key):
                continue
            configs.append(
                {
                    'id': str(item.get('id') or f'model-{index + 1}'),
                    'label': str(item.get('label') or model_name).strip(),
                    'provider': str(item.get('provider') or 'openai-compatible').strip(),
                    'model_name': model_name,
                    'base_url': base_url,
                    'api_key': api_key,
                    'temperature': _normalize_temperature(item.get('temperature')),
                    'enabled': item.get('enabled') is not False,
                }
            )
    return [item for item in configs if item['enabled']]


def _apply_active_model_config(context: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    model_configs = _normalize_model_configs(context, body)
    if model_configs:
        primary = model_configs[0]
        context['active_model_configs'] = model_configs
        context['model_configs'] = model_configs
        body['model_configs'] = model_configs
        body['active_model_configs'] = model_configs
        context['compare_models'] = [item['model_name'] for item in model_configs]
        context['enable_multi_model'] = len(model_configs) > 1
        body['compare_models'] = [item['model_name'] for item in model_configs]
        body['enable_multi_model'] = len(model_configs) > 1
        active_model_name = primary['model_name']
        active_base_url = primary['base_url']
        active_api_key = primary['api_key']
        active_provider = primary['provider']
        active_temperature = primary['temperature']
    else:
        active_model_name = str(
            context.get('active_model_name')
            or context.get('saved_model_name')
            or context.get('client_model_name')
            or context.get('model_name')
            or body.get('active_model_name')
            or body.get('saved_model_name')
            or body.get('model_name')
            or ''
        ).strip()
        active_base_url = str(
            context.get('active_base_url')
            or context.get('saved_base_url')
            or context.get('client_model_base_url')
            or context.get('base_url')
            or body.get('active_base_url')
            or body.get('saved_base_url')
            or body.get('base_url')
            or ''
        ).strip()
        active_api_key = str(
            context.get('active_api_key')
            or context.get('saved_api_key')
            or context.get('client_model_api_key')
            or context.get('api_key')
            or body.get('active_api_key')
            or body.get('saved_api_key')
            or body.get('api_key')
            or ''
        ).strip()
        active_provider = str(
            context.get('active_model_provider')
            or context.get('saved_model_provider')
            or context.get('client_model_provider')
            or context.get('model_provider')
            or body.get('active_model_provider')
            or body.get('saved_model_provider')
            or body.get('model_provider')
            or 'openai-compatible'
        ).strip()
        active_temperature = _normalize_temperature(
            context.get('active_temperature')
            or context.get('saved_temperature')
            or context.get('client_model_temperature')
            or context.get('temperature')
            or body.get('active_temperature')
            or body.get('saved_temperature')
            or body.get('temperature')
        )

    context.update(
        {
            'model_provider': active_provider,
            'model_name': active_model_name,
            'base_url': active_base_url,
            'api_key': active_api_key,
            'temperature': active_temperature,
            'active_model_provider': active_provider,
            'active_model_name': active_model_name,
            'active_base_url': active_base_url,
            'active_api_key': active_api_key,
            'active_temperature': active_temperature,
        }
    )
    body['temperature'] = active_temperature
    return context


def _discover_graphs() -> list[dict[str, Any]]:
    base_dir = Path(__file__).resolve().parents[4] / 'agent' / 'src' / 'agent'
    discovered: list[dict[str, Any]] = []
    for role_name, role_dir_name in ROLE_DIRS.items():
        role_dir = base_dir / role_dir_name
        if not role_dir.exists():
            continue
        for file in sorted(role_dir.glob('step*.py')):
            if file.name == '__init__.py':
                continue
            discovered.append(
                {
                    'role': role_name,
                    'step_code': file.stem,
                    'module': f'agent.src.agent.{role_dir_name}.{file.stem}',
                }
            )
    return discovered


@router.get('/capabilities')
def get_capabilities() -> dict[str, Any]:
    return {
        'graphs': _discover_graphs(),
        'roles': sorted(ROLE_DIRS.keys()),
        'memory': {
            'short_term': 'postgres',
            'long_term': 'postgres + optional pgvector',
        },
    }


@router.post('/runs/{run_id}/cancel')
def cancel_agent_run(run_id: str) -> dict[str, Any]:
    cancel_event = ACTIVE_RUNS.get(run_id)
    if cancel_event is None:
        return {'run_id': run_id, 'cancelled': False, 'status': 'not_found_or_finished'}
    cancel_event.set()
    return {'run_id': run_id, 'cancelled': True, 'status': 'cancelling'}


@router.post('/run')
async def run_agent(payload: dict[str, Any] = Body(...), user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    role = str(payload.get('workflow_role') or payload.get('role') or 'client')
    step_code = str(payload.get('step_code') or 'step1')
    context = dict(payload.get('context') or {})
    body = dict(payload.get('payload') or {})
    context = _apply_active_model_config(context, body)
    project_id = str(body.get('project_id') or context.get('project_id') or '')
    memory_scope = str(context.get('memory_scope') or 'short_term')

    is_admin_workflow = role in {'admin', 'manager', 'admin_graphs'}
    if not project_id and not is_admin_workflow:
        raise HTTPException(status_code=400, detail='project_id is required')
    if not project_id:
        project_id = f'admin-{step_code}'

    thread_id = str(context.get('thread_id') or body.get('thread_id') or f'{step_code}:{project_id}')

    with SessionLocal() as db:
        if role in {'client', 'user', 'client_graphs'}:
            admin_cfg = AdminService(db).get_active_config(step_code)
            active_prompt = admin_cfg.get('active_prompt') or {}
            active_kb = admin_cfg.get('active_kb') or {}
            body['admin_system_prompt'] = admin_cfg.get('prompt_text') or ''
            body['admin_knowledge_base'] = admin_cfg.get('knowledge_text') or ''
            body['prompt_version_id'] = active_prompt.get('id')
            body['kb_version_id'] = active_kb.get('id')
            context['prompt_version_id'] = active_prompt.get('id')
            context['kb_version_id'] = active_kb.get('id')

        files = db.scalars(select(File).where(File.project_id == project_id)).all() if project_id and not project_id.startswith('admin-') else []
        project_files = [
            {
                'id': item.id,
                'file_name': item.file_name,
                'file_type': item.file_type,
                'storage_key': item.storage_key,
                'parse_status': item.parse_status,
                'project_name': item.project_name,
            }
            for item in files
            if item.storage_key and not str(item.storage_key).startswith('local-upload://')
        ]
        media_file_paths = [item['storage_key'] for item in project_files if str(item.get('file_type') or '').lower().endswith(('png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'tiff', 'pdf'))]
        text_doc_file_paths = [item['storage_key'] for item in project_files if item['storage_key'] not in media_file_paths]
        file_paths = [item['storage_key'] for item in project_files]
        memory = MemoryService(db)
        session = memory.ensure_session(project_id=project_id, user_id=user_id, step_code=step_code, memory_scope=memory_scope)
        session_id = session.id
        memory.append_entry(
            session_id=session_id,
            project_id=project_id,
            user_id=user_id,
            step_code=step_code,
            memory_type='short_term',
            content=str(body.get('prompt') or body.get('user_message') or ''),
            metadata={'role': role, 'thread_id': thread_id, 'context': {k: v for k, v in context.items() if k != 'api_key'}},
        )

    if project_files:
        body['file_paths'] = file_paths
        body['media_file_paths'] = body.get('media_file_paths') or media_file_paths
        body['text_doc_file_paths'] = body.get('text_doc_file_paths') or text_doc_file_paths
        body['project_files'] = body.get('project_files') or project_files
    else:
        body.setdefault('file_paths', file_paths)
        body.setdefault('media_file_paths', media_file_paths)
        body.setdefault('text_doc_file_paths', text_doc_file_paths)
        body.setdefault('project_files', project_files)
    body.setdefault('project_name', body.get('project_name') or f'项目 {project_id}')
    body.setdefault('session_id', session_id)
    body.setdefault('thread_id', thread_id)
    run_id = str(context.get('run_id') or body.get('run_id') or uuid4())
    body['run_id'] = run_id
    body.setdefault('memory_scope', memory_scope)
    cancel_event = Event()
    ACTIVE_RUNS[run_id] = cancel_event

    try:
        context = {**context, 'thread_id': thread_id, 'run_id': run_id, 'cancel_event': cancel_event}
        result = await run_in_threadpool(runner.run, role=role, step_code=step_code, payload=body, context=context)
        if cancel_event.is_set():
            raise HTTPException(status_code=499, detail='agent run cancelled')
    except ModuleNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f'未找到对应的 agent graph: {role}/{step_code}') from exc
    finally:
        ACTIVE_RUNS.pop(run_id, None)

    content_text = None
    if isinstance(result, dict):
        for key in ('final_manifest', 'final_core_content', 'final_indicator_markdown', 'draft_manifest', 'core_content_draft', 'verification_digest'):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                content_text = value
                break
        result = {**result, 'content_text': content_text}
        if role in {'client', 'user', 'client_graphs'} and isinstance(result, dict):
            for sensitive_key in ('admin_system_prompt', 'admin_knowledge_base', 'prompt_text', 'knowledge_text'):
                result.pop(sensitive_key, None)

    with SessionLocal() as db:
        memory = MemoryService(db)
        memory.save_run(
            project_id=project_id,
            user_id=user_id,
            step_code=step_code,
            workflow_role=role,
            input_payload={'payload': body, 'context': context},
            output_payload=result if isinstance(result, dict) else {'result': result},
            status='success',
        )

    return {
        'role': role,
        'step_code': step_code,
        'result': result,
        'memory_scope': memory_scope,
    }
