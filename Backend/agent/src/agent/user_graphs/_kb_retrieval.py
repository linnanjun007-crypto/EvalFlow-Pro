"""KB 检索助手 — 统一为 step1-14 提供知识库上下文注入。

调用方式：
    kb_ctx = await retrieve_kb_context(project_id=..., query=..., top_k=5)
    if kb_ctx:
        preamble += kb_ctx + "\n\n"

检索管道：
    1) 向量召回 top 20（pgvector cosine）
    2) BM25 召回 top 20（PG tsvector + jieba 预分词）
    3) RRF 融合（k 由 KB.rrf_k 决定，权重 0.5/0.5）
    4) 若启用 rerank 且配置了默认 rerank 模型 → 调用 rerank 重排，否则直接取融合 top_k
    5) 按 max_chars 截断，拼成 markdown 注入 prompt

任何异常都返回空字符串，不打断 step 执行。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

STEP_QUERY_HINTS: dict[str, str] = {
    "step1": "项目资料清单 文件列表",
    "step2": "核心内容提取 关键信息",
    "step3": "指标体系构建 绩效指标",
    "step4": "预算对比分析 资金拨付",
    "step5": "合规性审查 制度合同",
    "step6": "资金绩效评分 支出效率",
    "step7": "项目管理评分 实施方案",
    "step8": "产出评分 验收成果",
    "step9": "综合评分汇总",
    "step10": "效果评分 社会效益",
    "step11": "可持续性评价",
    "step12": "问题与建议",
    "step13": "评价结论",
    "step14": "终稿报告生成",
}

CANDIDATE_POOL = 20


async def retrieve_kb_context(
    *,
    project_id: str,
    query: str,
    top_k: int = 5,
    max_chars: int = 4000,
    kb_ids: list[str] | None = None,
    step_code: str = "",
) -> str:
    """返回注入 prompt 的 markdown block；任何异常都返回 ''。"""
    try:
        return await _do_retrieve(
            project_id=project_id,
            query=query,
            top_k=top_k,
            max_chars=max_chars,
            kb_ids=kb_ids,
            step_code=step_code,
        )
    except Exception as exc:
        logger.warning("retrieve_kb_context failed: %s", exc)
        return ""


async def _do_retrieve(
    *,
    project_id: str,
    query: str,
    top_k: int,
    max_chars: int,
    kb_ids: list[str] | None,
    step_code: str,
) -> str:
    import sys
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[4]
    sys.path.insert(0, str(backend_root))

    from sqlalchemy import text as sa_text

    from app.db.session import SessionLocal
    from app.services.embedding_service import embed_texts, get_active_embedding_model

    db = SessionLocal()
    try:
        if not kb_ids:
            rows = db.execute(
                sa_text(
                    "SELECT kb_id FROM project_knowledge_bases WHERE project_id = :pid AND enabled = TRUE"
                ),
                {"pid": project_id},
            ).fetchall()
            kb_ids = [r[0] for r in rows]

        if not kb_ids:
            return ""

        emb_model = get_active_embedding_model(db)
        if not emb_model:
            return ""

        hint = STEP_QUERY_HINTS.get(step_code, "")
        full_query = f"{hint} {query}".strip() if hint else query

        candidates = await hybrid_search(
            db,
            query=full_query,
            kb_ids=kb_ids,
            emb_model=emb_model,
            candidate_pool=CANDIDATE_POOL,
        )
        if not candidates:
            return ""

        # 取首个 KB 的开关（项目可能绑多个 KB，行为取第一个的策略）
        kb_flags = _get_kb_flags(db, kb_ids[0])
        final_rows = await _apply_rerank_if_enabled(
            full_query, candidates, top_k=top_k, kb_flags=kb_flags
        )

        if not final_rows:
            final_rows = candidates[:top_k]

        lines = ["【知识库检索结果】", ""]
        total_chars = 0
        for idx, row in enumerate(final_rows, 1):
            snippet = str(row["content"]).strip()
            file_name = row.get("file_name", "")
            chunk_index = row.get("chunk_index", 0)
            if total_chars + len(snippet) > max_chars:
                snippet = snippet[: max_chars - total_chars]
                lines.append(f"[{idx}] (来源: {file_name} · 第{chunk_index}段) {snippet}...")
                break
            lines.append(f"[{idx}] (来源: {file_name} · 第{chunk_index}段) {snippet}")
            total_chars += len(snippet)

        return "\n".join(lines)
    finally:
        db.close()


async def hybrid_search(
    db,
    *,
    query: str,
    kb_ids: list[str],
    emb_model: Any,
    candidate_pool: int = CANDIDATE_POOL,
) -> list[dict[str, Any]]:
    """向量+BM25 双路召回 + RRF 融合，返回融合后的候选列表（已带 content/file_name/chunk_index）。"""
    from sqlalchemy import text as sa_text

    from app.services.embedding_service import embed_texts
    from app.services.text_tokenizer import tokenize_zh

    vectors = await embed_texts(
        [query],
        base_url=emb_model.base_url or "",
        api_key=emb_model.api_key or "",
        model_name=emb_model.model_id,
    )
    if not vectors:
        return []
    vec_literal = "[" + ",".join(f"{x:.7f}" for x in vectors[0]) + "]"

    # 1) 向量召回
    vec_rows = db.execute(
        sa_text(
            """
            SELECT c.id
            FROM kb_chunks c
            WHERE c.kb_id = ANY(CAST(:ids AS varchar[]))
            ORDER BY c.embedding <=> CAST(:q AS vector)
            LIMIT :pool
            """
        ),
        {"q": vec_literal, "ids": kb_ids, "pool": candidate_pool},
    ).fetchall()
    vec_ids = [r[0] for r in vec_rows]

    # 2) BM25 召回（KB 级开关 + 单 KB 开关取交集）
    bm25_ids: list[int] = []
    enable_bm25 = _any_kb_bm25_enabled(db, kb_ids)
    tokens = tokenize_zh(query)
    if enable_bm25 and tokens.strip():
        bm25_rows = db.execute(
            sa_text(
                """
                SELECT c.id
                FROM kb_chunks c, plainto_tsquery('simple', :tokens) q
                WHERE c.kb_id = ANY(CAST(:ids AS varchar[]))
                  AND c.content_tsv @@ q
                ORDER BY ts_rank_cd(c.content_tsv, q) DESC
                LIMIT :pool
                """
            ),
            {"tokens": tokens, "ids": kb_ids, "pool": candidate_pool},
        ).fetchall()
        bm25_ids = [r[0] for r in bm25_rows]

    # 3) RRF 融合
    rrf_k = _get_rrf_k(db, kb_ids[0])
    fused_ids = _rrf_fuse(vec_ids, bm25_ids, k=rrf_k, top=candidate_pool)
    if not fused_ids:
        fused_ids = vec_ids[:candidate_pool]
    if not fused_ids:
        return []

    # 4) 拉回完整内容，并保持融合顺序
    rows = db.execute(
        sa_text(
            """
            SELECT c.id, c.content, c.chunk_index, d.file_name
            FROM kb_chunks c
            JOIN kb_documents d ON d.id = c.document_id
            WHERE c.id = ANY(CAST(:ids AS bigint[]))
            """
        ),
        {"ids": fused_ids},
    ).fetchall()
    by_id = {r[0]: r for r in rows}
    out: list[dict[str, Any]] = []
    for cid in fused_ids:
        if cid not in by_id:
            continue
        cid_, content, chunk_index, file_name = by_id[cid]
        out.append({
            "id": int(cid_),
            "content": content,
            "chunk_index": int(chunk_index),
            "file_name": file_name,
        })
    return out


def _rrf_fuse(
    vec_ids: list[int],
    bm25_ids: list[int],
    *,
    k: int = 60,
    w_vec: float = 0.5,
    w_bm25: float = 0.5,
    top: int = 20,
) -> list[int]:
    score: dict[int, float] = {}
    for rank, cid in enumerate(vec_ids):
        score[cid] = score.get(cid, 0.0) + w_vec / (k + rank + 1)
    for rank, cid in enumerate(bm25_ids):
        score[cid] = score.get(cid, 0.0) + w_bm25 / (k + rank + 1)
    return sorted(score, key=lambda x: score[x], reverse=True)[:top]


def _get_kb_flags(db, kb_id: str) -> dict[str, Any]:
    from sqlalchemy import text as sa_text
    row = db.execute(
        sa_text(
            "SELECT enable_bm25, enable_rerank, rrf_k FROM user_knowledge_bases WHERE id = :id"
        ),
        {"id": kb_id},
    ).fetchone()
    if not row:
        return {"enable_bm25": True, "enable_rerank": True, "rrf_k": 60}
    return {"enable_bm25": bool(row[0]), "enable_rerank": bool(row[1]), "rrf_k": int(row[2])}


def _any_kb_bm25_enabled(db, kb_ids: list[str]) -> bool:
    """只要有一个 KB 启用 BM25 就启用（粗略策略，避免每个 KB 单独跑两路）。"""
    from sqlalchemy import text as sa_text
    row = db.execute(
        sa_text(
            "SELECT 1 FROM user_knowledge_bases "
            "WHERE id = ANY(CAST(:ids AS varchar[])) AND enable_bm25 = TRUE LIMIT 1"
        ),
        {"ids": kb_ids},
    ).fetchone()
    return row is not None


def _get_rrf_k(db, kb_id: str) -> int:
    from sqlalchemy import text as sa_text
    row = db.execute(
        sa_text("SELECT rrf_k FROM user_knowledge_bases WHERE id = :id"),
        {"id": kb_id},
    ).fetchone()
    return int(row[0]) if row else 60


async def _apply_rerank_if_enabled(
    query: str,
    candidates: list[dict[str, Any]],
    *,
    top_k: int,
    kb_flags: dict[str, Any],
) -> list[dict[str, Any]]:
    """命中候选 → 若 KB 启用 rerank 且配置了默认 rerank 模型，则重排取 top_k。

    rerank 服务尚未配置时直接返回候选 top_k，不报错。
    """
    if not candidates:
        return []
    if not kb_flags.get("enable_rerank", True):
        return candidates[:top_k]

    try:
        from app.db.session import SessionLocal
        from app.services.rerank_service import get_active_rerank_model, rerank_documents
    except Exception:
        return candidates[:top_k]

    db = SessionLocal()
    try:
        rerank_model = get_active_rerank_model(db)
    finally:
        db.close()

    if not rerank_model:
        return candidates[:top_k]

    docs = [c["content"] for c in candidates]
    try:
        ranked = await rerank_documents(
            query=query,
            documents=docs,
            base_url=rerank_model.base_url or "",
            api_key=rerank_model.api_key or "",
            model_name=rerank_model.model_id,
            top_n=top_k,
        )
    except Exception as exc:
        logger.warning("rerank failed, fallback to fused order: %s", exc)
        return candidates[:top_k]

    out: list[dict[str, Any]] = []
    for idx, _score in ranked:
        if 0 <= idx < len(candidates):
            out.append(candidates[idx])
    return out[:top_k] if out else candidates[:top_k]


def build_retrieval_query(state: dict[str, Any], step_code: str = "step1") -> str:
    """从 state 中构建检索 query。"""
    project_name = state.get("project_name", "")
    hint = STEP_QUERY_HINTS.get(step_code, "")
    return f"{project_name} {hint}".strip()


async def retrieve_kb_chunks_structured(
    *,
    project_id: str,
    queries: list[str],
    top_k_per_query: int = 3,
    kb_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """多 query 并行检索 + 去重合并，返回结构化 chunk 列表。

    返回: [{"id", "content", "file_name", "chunk_index", "query_source"}, ...]
    任何异常都返回空列表，不打断 step。
    """
    if not project_id or not queries:
        return []
    try:
        return await _do_structured_retrieve(
            project_id=project_id,
            queries=queries,
            top_k_per_query=top_k_per_query,
            kb_ids=kb_ids,
        )
    except Exception as exc:
        logger.warning("retrieve_kb_chunks_structured failed: %s", exc)
        return []


async def _do_structured_retrieve(
    *,
    project_id: str,
    queries: list[str],
    top_k_per_query: int,
    kb_ids: list[str] | None,
) -> list[dict[str, Any]]:
    import sys
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[4]
    sys.path.insert(0, str(backend_root))

    from sqlalchemy import text as sa_text

    from app.db.session import SessionLocal
    from app.services.embedding_service import get_active_embedding_model

    db = SessionLocal()
    try:
        if not kb_ids:
            rows = db.execute(
                sa_text(
                    "SELECT kb_id FROM project_knowledge_bases WHERE project_id = :pid AND enabled = TRUE"
                ),
                {"pid": project_id},
            ).fetchall()
            kb_ids = [r[0] for r in rows]
        if not kb_ids:
            return []

        emb_model = get_active_embedding_model(db)
        if not emb_model:
            return []

        merged: dict[int, dict[str, Any]] = {}
        for query in queries:
            query = (query or "").strip()
            if not query:
                continue
            try:
                hits = await hybrid_search(
                    db,
                    query=query,
                    kb_ids=kb_ids,
                    emb_model=emb_model,
                    candidate_pool=top_k_per_query * 4,
                )
            except Exception as exc:
                logger.warning("hybrid_search failed for query %r: %s", query, exc)
                continue
            for chunk in hits[:top_k_per_query]:
                cid = chunk["id"]
                if cid in merged:
                    existing = merged[cid]
                    if query not in existing["query_source"]:
                        existing["query_source"].append(query)
                else:
                    merged[cid] = {
                        "id": cid,
                        "content": chunk["content"],
                        "file_name": chunk["file_name"],
                        "chunk_index": chunk["chunk_index"],
                        "query_source": [query],
                    }
        return list(merged.values())
    finally:
        db.close()
