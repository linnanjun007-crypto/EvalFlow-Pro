"""RerankService — 调用 Cohere/Jina/BGE/SiliconFlow 兼容的 /rerank 接口。"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.model_registry import ModelRegistry

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30.0


def get_active_rerank_model(db: Session) -> ModelRegistry | None:
    result = db.scalar(
        select(ModelRegistry).where(
            ModelRegistry.kind == "rerank",
            ModelRegistry.is_default.is_(True),
            ModelRegistry.enabled.is_(True),
        )
    )
    if result:
        return result
    result = db.scalar(
        select(ModelRegistry).where(
            ModelRegistry.kind == "rerank",
            ModelRegistry.enabled.is_(True),
        )
    )
    return result


async def rerank_documents(
    *,
    query: str,
    documents: list[str],
    base_url: str,
    api_key: str,
    model_name: str,
    top_n: int = 5,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[tuple[int, float]]:
    """调用 rerank API，返回 [(原始 index, relevance_score), ...] 按分数降序。

    兼容 Cohere / Jina / BGE / SiliconFlow 的 /rerank 端点格式。
    """
    if not documents:
        return []

    base = base_url.rstrip("/")
    endpoint = base if base.endswith("/rerank") else f"{base}/rerank"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": model_name,
        "query": query,
        "documents": documents,
        "top_n": min(top_n, len(documents)),
        "return_documents": False,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    return _extract_results(data)


def _extract_results(data: Any) -> list[tuple[int, float]]:
    """从 rerank 响应中提取 (index, score) 列表。

    Cohere 格式: {"results": [{"index": 0, "relevance_score": 0.9}, ...]}
    Jina 格式:   {"results": [{"index": 0, "relevance_score": 0.9}, ...]}
    """
    if not isinstance(data, dict):
        raise RuntimeError("Rerank API 返回格式异常")
    results = data.get("results")
    if not isinstance(results, list):
        raise RuntimeError("Rerank API 返回缺少 results 字段")
    out: list[tuple[int, float]] = []
    for item in results:
        idx = item.get("index", 0)
        score = item.get("relevance_score", 0.0)
        out.append((int(idx), float(score)))
    out.sort(key=lambda x: x[1], reverse=True)
    return out
