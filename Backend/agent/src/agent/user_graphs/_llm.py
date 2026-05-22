"""Shared LLM helpers for EvalFlow Pro user graphs (steps 5–13).

Step 1 already has its own copy of these helpers — they were extracted here so
all later steps share one openai-compatible HTTP client + model-config reader
without duplicating the code.

Public surface
--------------

- ``call_llm_async`` / ``call_llm``       — single openai-compatible call.
- ``read_model_configs``                  — extract enabled models from runtime
                                            context, with primary fallback.
- ``generate_drafts_async``               — fan out the same prompt across the
                                            given configs in parallel; returns
                                            a list of ``ModelDraft`` results
                                            (first successful is the primary).
- ``parse_json_object`` / ``parse_json_array`` — best-effort JSON-from-LLM.
- ``read_admin_prompt`` / ``read_admin_kb`` — pull admin prompt / kb content
                                              out of runtime context with
                                              backwards-compat aliases.
- ``ensure_model_configs``                — raise a clear error when no model
                                            is configured.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any, TypedDict

import httpx


DEFAULT_TIMEOUT = 90.0
DEFAULT_SYSTEM_PROMPT = "你是严谨的政务/财政绩效评价文档生成助手。"


class ModelConfig(TypedDict, total=False):
    id: str
    label: str
    provider: str
    model_name: str
    base_url: str
    api_key: str
    temperature: float
    enabled: bool


class ModelDraft(TypedDict, total=False):
    model_name: str
    label: str
    provider: str
    temperature: float
    draft: str
    error: str


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_temperature(value: Any, default: float = 0.2) -> float:
    try:
        temperature = float(value)
    except (TypeError, ValueError):
        temperature = default
    return min(2.0, max(0.0, temperature))


def _build_request(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    prompt: str,
    temperature: float,
    system_prompt: str,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    base = base_url.rstrip("/")
    endpoint = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt or DEFAULT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": normalize_temperature(temperature),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    return endpoint, headers, payload


def _extract_content(data: Any) -> str:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices:
        raise RuntimeError("模型接口未返回 choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("模型接口未返回有效 content")
    return content.strip()


async def call_llm_async(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    prompt: str,
    temperature: float = 0.2,
    timeout_seconds: float = DEFAULT_TIMEOUT,
    system_prompt: str = "",
) -> str:
    endpoint, headers, payload = _build_request(
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        prompt=prompt,
        temperature=temperature,
        system_prompt=system_prompt,
    )
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    return _extract_content(data)


def call_llm(
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    prompt: str,
    temperature: float = 0.2,
    timeout_seconds: float = DEFAULT_TIMEOUT,
    system_prompt: str = "",
) -> str:
    endpoint, headers, payload = _build_request(
        base_url=base_url,
        api_key=api_key,
        model_name=model_name,
        prompt=prompt,
        temperature=temperature,
        system_prompt=system_prompt,
    )
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    return _extract_content(data)


def _read_primary_model(context: dict[str, Any]) -> ModelConfig:
    return {
        "id": "primary",
        "label": str(context.get("active_model_name") or context.get("model_name") or "默认模型").strip(),
        "provider": str(context.get("active_model_provider") or context.get("model_provider") or "openai-compatible").strip(),
        "model_name": str(context.get("active_model_name") or context.get("model_name") or "").strip(),
        "base_url": str(context.get("active_base_url") or context.get("base_url") or "").strip(),
        "api_key": str(context.get("active_api_key") or context.get("api_key") or "").strip(),
        "temperature": normalize_temperature(
            context.get("active_temperature") if "active_temperature" in context else context.get("temperature")
        ),
        "enabled": True,
    }


def read_model_configs(context: dict[str, Any] | None) -> list[ModelConfig]:
    """Pick enabled models from context, falling back to the primary model."""

    context = context or {}
    raw_configs = context.get("active_model_configs") or context.get("model_configs") or []
    configs: list[ModelConfig] = []
    if isinstance(raw_configs, list):
        for index, item in enumerate(raw_configs):
            if not isinstance(item, dict):
                continue
            model_name = str(item.get("model_name") or "").strip()
            base_url = str(item.get("base_url") or "").strip()
            api_key = str(item.get("api_key") or "").strip()
            if not (model_name and base_url and api_key) or item.get("enabled") is False:
                continue
            configs.append(
                {
                    "id": str(item.get("id") or f"model-{index + 1}"),
                    "label": str(item.get("label") or model_name).strip(),
                    "provider": str(item.get("provider") or "openai-compatible").strip(),
                    "model_name": model_name,
                    "base_url": base_url,
                    "api_key": api_key,
                    "temperature": normalize_temperature(item.get("temperature")),
                    "enabled": True,
                }
            )
    if configs:
        return configs
    primary = _read_primary_model(context)
    return [primary] if primary["model_name"] and primary["base_url"] and primary["api_key"] else []


def filter_configs_by_compare_models(
    configs: list[ModelConfig],
    compare_models: list[str] | None,
    enable_multi_model: bool,
) -> list[ModelConfig]:
    """Honor ``enable_multi_model`` + ``compare_models`` in runtime context."""

    if not configs:
        return configs
    if not enable_multi_model:
        return configs[:1]
    requested = {str(m).strip() for m in (compare_models or []) if str(m).strip()}
    if requested:
        filtered = [c for c in configs if c["model_name"] in requested]
        if filtered:
            return filtered
    return configs


def ensure_model_configs(configs: list[ModelConfig]) -> None:
    if not configs:
        raise RuntimeError(
            "缺少客户端模型配置：请提供 model_configs 或 base_url/api_key/model_name"
        )


async def generate_drafts_async(
    *,
    prompt: str,
    system_prompt: str,
    configs: list[ModelConfig],
    timeout_seconds: float = DEFAULT_TIMEOUT,
) -> list[ModelDraft]:
    """Run ``prompt`` across every config concurrently.

    Each result holds either ``draft`` (success) or ``error`` (failure).
    Caller decides what to do when **all** entries failed.
    """

    ensure_model_configs(configs)

    async def _one(config: ModelConfig) -> ModelDraft:
        model_name = str(config["model_name"])
        base: ModelDraft = {
            "model_name": model_name,
            "label": str(config.get("label") or model_name),
            "provider": str(config.get("provider") or "openai-compatible"),
            "temperature": float(config.get("temperature") or 0.2),
        }
        try:
            draft = await call_llm_async(
                base_url=str(config["base_url"]),
                api_key=str(config["api_key"]),
                model_name=model_name,
                prompt=prompt,
                temperature=float(config.get("temperature") or 0.2),
                system_prompt=system_prompt,
                timeout_seconds=timeout_seconds,
            )
            return {**base, "draft": draft}
        except Exception as exc:  # noqa: BLE001
            return {**base, "draft": "", "error": str(exc)}

    return await asyncio.gather(*(_one(cfg) for cfg in configs))


def generate_drafts(
    *,
    prompt: str,
    system_prompt: str,
    configs: list[ModelConfig],
    timeout_seconds: float = DEFAULT_TIMEOUT,
) -> list[ModelDraft]:
    """Sync wrapper around :func:`generate_drafts_async`."""

    return asyncio.run(
        generate_drafts_async(
            prompt=prompt,
            system_prompt=system_prompt,
            configs=configs,
            timeout_seconds=timeout_seconds,
        )
    )


def first_successful_draft(drafts: list[ModelDraft]) -> ModelDraft | None:
    for d in drafts:
        if d.get("draft"):
            return d
    return None


def collect_errors(drafts: list[ModelDraft]) -> str:
    parts: list[str] = []
    for d in drafts:
        if not d.get("draft") and d.get("error"):
            parts.append(f"{d.get('model_name')}: {d.get('error')}")
    return "; ".join(parts)


_JSON_OBJECT_PATTERN = re.compile(r"\{[\s\S]*\}")
_JSON_ARRAY_PATTERN = re.compile(r"\[[\s\S]*\]")


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove ```json … ``` fences
        cleaned = re.sub(r"^```[a-zA-Z0-9]*\s*", "", cleaned)
        cleaned = re.sub(r"```\s*$", "", cleaned)
    return cleaned.strip()


def parse_json_object(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    candidate = _strip_code_fence(text)
    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        pass
    match = _JSON_OBJECT_PATTERN.search(candidate)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


def parse_json_array(text: str) -> list[Any] | None:
    if not text:
        return None
    candidate = _strip_code_fence(text)
    try:
        data = json.loads(candidate)
        return data if isinstance(data, list) else None
    except Exception:  # noqa: BLE001
        pass
    match = _JSON_ARRAY_PATTERN.search(candidate)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, list) else None
    except Exception:  # noqa: BLE001
        return None


def read_admin_prompt(context: dict[str, Any] | None, state: dict[str, Any] | None = None) -> str:
    """Return the admin prompt for this step, accepting both new and legacy keys."""

    context = context or {}
    state = state or {}
    candidates = (
        state.get("admin_prompt_content"),
        state.get("admin_system_prompt"),
        state.get("prompt_content"),
        state.get("prompt_text"),
        context.get("admin_prompt_content"),
        context.get("admin_system_prompt"),
        context.get("prompt_content"),
        context.get("prompt_text"),
    )
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def read_admin_kb(context: dict[str, Any] | None, state: dict[str, Any] | None = None) -> str:
    """Return the admin knowledge base for this step."""

    context = context or {}
    state = state or {}
    candidates = (
        state.get("admin_kb_content"),
        state.get("admin_knowledge_base"),
        state.get("kb_content"),
        state.get("knowledge_text"),
        context.get("admin_kb_content"),
        context.get("admin_knowledge_base"),
        context.get("kb_content"),
        context.get("knowledge_text"),
    )
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def build_admin_preamble(prompt: str, kb: str) -> str:
    """Render admin Prompt + KB blocks for inclusion in the user prompt."""

    parts: list[str] = []
    if prompt:
        parts.extend(["【管理端 Prompt 配置】", prompt.strip(), ""])
    if kb:
        parts.extend(["【管理端知识库】", kb.strip(), ""])
    return "\n".join(parts).rstrip() + ("\n\n" if parts else "")


__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "DEFAULT_TIMEOUT",
    "ModelConfig",
    "ModelDraft",
    "build_admin_preamble",
    "call_llm",
    "call_llm_async",
    "collect_errors",
    "ensure_model_configs",
    "filter_configs_by_compare_models",
    "first_successful_draft",
    "generate_drafts",
    "generate_drafts_async",
    "normalize_temperature",
    "now_iso",
    "parse_json_array",
    "parse_json_object",
    "read_admin_kb",
    "read_admin_prompt",
    "read_model_configs",
]
