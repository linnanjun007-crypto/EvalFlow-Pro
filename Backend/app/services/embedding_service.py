"""EmbeddingService — 批量调用 OpenAI 兼容 /embeddings 接口。"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.model_registry import ModelRegistry

logger = logging.getLogger(__name__)

BATCH_SIZE = 64
DEFAULT_TIMEOUT = 60.0

# ── 写死的 embedding 配置（调试用） ──
_HARDCODED_EMBEDDING = SimpleNamespace(
    id="hardcoded-embedding-model",
    name="text-embedding-3-small",
    model_id="text-embedding-3-small",
    base_url="https://api.openai-proxy.org/v1",
    api_key="sk-LgE5l2b3e6oBoduab3fwGqYA8Y5Qn0UdAybDQmqbb5XzOE5i",
    kind="embedding",
    dimensions=1536,
    is_default=True,
    enabled=True,
)


def get_active_embedding_model(db: Session) -> Any:
    # 优先找 is_default=True 的
    result = db.scalar(
        select(ModelRegistry).where(
            ModelRegistry.kind == "embedding",
            ModelRegistry.is_default.is_(True),
            ModelRegistry.enabled.is_(True),
        )
    )
    if result:
        return result

    # 没有标记默认的，退而求其次：取第一条启用的 embedding 模型
    result = db.scalar(
        select(ModelRegistry).where(
            ModelRegistry.kind == "embedding",
            ModelRegistry.enabled.is_(True),
        )
    )
    if result:
        logger.info("未找到默认 embedding 模型，自动使用: id=%s name=%s", result.id, result.name)
        return result

    logger.warning("数据库无可用 embedding 模型，回退到写死的调试配置")
    return _HARDCODED_EMBEDDING


async def embed_texts(
    texts: list[str],
    *,
    base_url: str,
    api_key: str,
    model_name: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[list[float]]:
    """批量 embed，自动按 BATCH_SIZE 分批。返回与 texts 等长的向量列表。"""

    if not texts:
        return []

    base = base_url.rstrip("/")
    endpoint = base if base.endswith("/embeddings") else f"{base}/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    all_embeddings: list[list[float]] = []

    async with httpx.AsyncClient(timeout=timeout) as client:
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            payload: dict[str, Any] = {
                "model": model_name,
                "input": batch,
            }
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            batch_embeddings = _extract_embeddings(data, len(batch))
            all_embeddings.extend(batch_embeddings)

    return all_embeddings


def _extract_embeddings(data: Any, expected_count: int) -> list[list[float]]:
    """从 OpenAI 兼容响应中提取 embedding 向量。"""
    if not isinstance(data, dict):
        raise RuntimeError("Embedding API 返回格式异常")
    items = data.get("data")
    if not isinstance(items, list) or len(items) < expected_count:
        raise RuntimeError(f"Embedding API 返回数量不匹配: 期望 {expected_count}, 得到 {len(items) if items else 0}")
    sorted_items = sorted(items, key=lambda x: x.get("index", 0))
    return [item["embedding"] for item in sorted_items[:expected_count]]
