"""知识库管理路由 — /api/v1/kbs"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_user_id
from app.core.errors import bad_request, not_found
from app.db.session import get_db
from app.services.kb_service import KbService

router = APIRouter()


class KbCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""


class KbUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    chunk_size: int | None = Field(default=None, ge=100, le=4000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=500)
    enable_bm25: bool | None = None
    enable_rerank: bool | None = None
    rrf_k: int | None = Field(default=None, ge=1, le=200)
    pdf_enhanced_parse: bool | None = None
    processing_mode: Literal["chunk", "qa"] | None = None
    chunk_strategy: Literal["auto", "paragraph", "heading", "fixed"] | None = None
    index_title: bool | None = None
    index_image: bool | None = None
    auto_supplement_index: bool | None = None
    param_preset: Literal["default", "custom"] | None = None


class PromoteRequest(BaseModel):
    file_id: str


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class MigrateDocRequest(BaseModel):
    target_kb_id: str
    mode: Literal["move", "copy"] = "move"


class ChunkPreviewRequest(BaseModel):
    chunk_size: int = Field(default=500, ge=100, le=4000)
    chunk_overlap: int = Field(default=80, ge=0, le=500)
    chunk_strategy: Literal["auto", "paragraph", "heading", "fixed"] = "auto"


def get_kb_service(db: Session = Depends(get_db)) -> KbService:
    return KbService(db)


# ─── KB CRUD ───


@router.get("")
def list_kbs(
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> dict[str, list[dict[str, Any]]]:
    return {"items": service.list_kbs(user_id)}


@router.post("")
def create_kb(
    payload: KbCreateRequest = Body(...),
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> dict[str, Any]:
    try:
        return service.create_kb(user_id, payload.name, payload.description)
    except ValueError as exc:
        raise bad_request(str(exc)) from exc


@router.get("/{kb_id}")
def get_kb(
    kb_id: str,
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> dict[str, Any]:
    try:
        return service.get_kb(kb_id, user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.patch("/{kb_id}")
def update_kb(
    kb_id: str,
    payload: KbUpdateRequest = Body(...),
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> dict[str, Any]:
    try:
        return service.update_kb(kb_id, user_id, **payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.delete("/{kb_id}")
def delete_kb(
    kb_id: str,
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> dict[str, str]:
    try:
        service.delete_kb(kb_id, user_id)
        return {"message": "deleted"}
    except ValueError as exc:
        raise not_found(str(exc)) from exc


# ─── 文档管理 ───


@router.get("/{kb_id}/documents")
def list_kb_documents(
    kb_id: str,
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> dict[str, list[dict[str, Any]]]:
    try:
        return {"items": service.list_documents(kb_id, user_id)}
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.post("/{kb_id}/documents/upload")
async def upload_kb_document(
    kb_id: str,
    background_tasks: BackgroundTasks,
    upload: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.services.kb_indexing_service import add_document_from_upload, process_document

    safe_name = (upload.filename or "unnamed").replace("\\", "/").split("/")[-1]
    content = await upload.read()
    try:
        doc = add_document_from_upload(
            db, kb_id=kb_id, user_id=user_id, file_name=safe_name, file_content=content
        )
    except ValueError as exc:
        raise not_found(str(exc)) from exc

    background_tasks.add_task(_run_process_document, doc.id)
    return {
        "id": doc.id,
        "kb_id": doc.kb_id,
        "file_name": doc.file_name,
        "status": doc.status,
        "message": "uploaded; indexing in background",
    }


@router.post("/{kb_id}/documents/promote")
def promote_kb_document(
    kb_id: str,
    background_tasks: BackgroundTasks,
    payload: PromoteRequest = Body(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.services.kb_indexing_service import promote_project_file

    try:
        doc = promote_project_file(db, kb_id=kb_id, file_id=payload.file_id, user_id=user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc

    background_tasks.add_task(_run_process_document, doc.id)
    return {
        "id": doc.id,
        "kb_id": doc.kb_id,
        "file_name": doc.file_name,
        "status": doc.status,
        "message": "promoted; indexing in background",
    }


@router.post("/{kb_id}/documents/{doc_id}/reindex")
def reindex_kb_document(
    kb_id: str,
    doc_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> dict[str, str]:
    try:
        service._get_owned(kb_id, user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc

    background_tasks.add_task(_run_reindex_document, doc_id)
    return {"message": "reindex queued"}


@router.delete("/{kb_id}/documents/{doc_id}")
def delete_kb_document(
    kb_id: str,
    doc_id: str,
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> dict[str, str]:
    try:
        service.delete_document(doc_id, user_id)
        return {"message": "deleted"}
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.get("/{kb_id}/documents/{doc_id}")
def get_kb_document_detail(
    kb_id: str,
    doc_id: str,
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> dict[str, Any]:
    try:
        return service.get_document(doc_id, user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


@router.get("/{kb_id}/documents/{doc_id}/chunks")
def list_kb_document_chunks(
    kb_id: str,
    doc_id: str,
    offset: int = 0,
    limit: int = 50,
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> dict[str, Any]:
    try:
        return service.list_chunks(doc_id, user_id, offset=offset, limit=limit)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


# ─── 调试检索 ───


@router.post("/{kb_id}/search")
async def search_kb(
    kb_id: str,
    payload: SearchRequest = Body(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    service: KbService = Depends(get_kb_service),
) -> dict[str, Any]:
    from app.services.embedding_service import get_active_embedding_model
    from app.services.text_tokenizer import tokenize_zh
    from sqlalchemy import text as sa_text

    try:
        service._get_owned(kb_id, user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc

    emb_model = get_active_embedding_model(db)
    if not emb_model:
        raise bad_request("未配置默认 Embedding 模型")

    from app.services.embedding_service import embed_texts

    vectors = await embed_texts(
        [payload.query],
        base_url=emb_model.base_url or "",
        api_key=emb_model.api_key or "",
        model_name=emb_model.model_id,
    )
    if not vectors:
        return {"items": [], "query": payload.query, "top_k": payload.top_k}
    query_vec = vectors[0]
    vec_literal = "[" + ",".join(f"{x:.7f}" for x in query_vec) + "]"

    candidate_pool = 20

    # 向量召回
    vec_rows = db.execute(
        sa_text(
            """
            SELECT c.id
            FROM kb_chunks c
            WHERE c.kb_id = :kb_id
            ORDER BY c.embedding <=> CAST(:q AS vector)
            LIMIT :pool
            """
        ),
        {"q": vec_literal, "kb_id": kb_id, "pool": candidate_pool},
    ).fetchall()
    vec_ids = [r[0] for r in vec_rows]

    # BM25 召回
    bm25_ids: list[int] = []
    tokens = tokenize_zh(payload.query)
    if tokens.strip():
        bm25_rows = db.execute(
            sa_text(
                """
                SELECT c.id
                FROM kb_chunks c, plainto_tsquery('simple', :tokens) q
                WHERE c.kb_id = :kb_id AND c.content_tsv @@ q
                ORDER BY ts_rank_cd(c.content_tsv, q) DESC
                LIMIT :pool
                """
            ),
            {"tokens": tokens, "kb_id": kb_id, "pool": candidate_pool},
        ).fetchall()
        bm25_ids = [r[0] for r in bm25_rows]

    # RRF 融合
    score: dict[int, float] = {}
    rrf_k = 60
    for rank, cid in enumerate(vec_ids):
        score[cid] = score.get(cid, 0.0) + 0.5 / (rrf_k + rank + 1)
    for rank, cid in enumerate(bm25_ids):
        score[cid] = score.get(cid, 0.0) + 0.5 / (rrf_k + rank + 1)
    fused_ids = sorted(score, key=lambda x: score[x], reverse=True)[: payload.top_k]

    if not fused_ids:
        return {"items": [], "query": payload.query, "top_k": payload.top_k}

    rows = db.execute(
        sa_text(
            """
            SELECT c.id, c.document_id, c.chunk_index, c.content,
                   d.file_name
            FROM kb_chunks c
            JOIN kb_documents d ON d.id = c.document_id
            WHERE c.id = ANY(CAST(:ids AS bigint[]))
            """
        ),
        {"ids": fused_ids},
    ).mappings().all()

    by_id = {r["id"]: r for r in rows}
    items = []
    for cid in fused_ids:
        r = by_id.get(cid)
        if not r:
            continue
        items.append({
            "id": r["id"],
            "document_id": r["document_id"],
            "chunk_index": r["chunk_index"],
            "content": r["content"],
            "file_name": r["file_name"],
            "score": round(score[cid], 6),
        })
    return {"items": items, "query": payload.query, "top_k": payload.top_k}


# ─── 后台任务包装 ───


def _run_process_document(doc_id: str) -> None:
    """同步包装，在 BackgroundTasks 中创建独立 session 运行异步索引。"""
    import asyncio

    from app.db.session import SessionLocal
    from app.services.kb_indexing_service import process_document

    db = SessionLocal()
    try:
        asyncio.run(process_document(db, doc_id))
    finally:
        db.close()


def _run_reindex_document(doc_id: str) -> None:
    import asyncio

    from app.db.session import SessionLocal
    from app.services.kb_indexing_service import reindex_document

    db = SessionLocal()
    try:
        asyncio.run(reindex_document(db, doc_id))
    finally:
        db.close()


# ─── 文件迁移 ───


@router.post("/{kb_id}/documents/{doc_id}/migrate")
def migrate_kb_document(
    kb_id: str,
    doc_id: str,
    background_tasks: BackgroundTasks,
    payload: MigrateDocRequest = Body(...),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from app.services.kb_migration_service import migrate_document

    try:
        result = migrate_document(
            db,
            source_kb_id=kb_id,
            doc_id=doc_id,
            target_kb_id=payload.target_kb_id,
            user_id=user_id,
            mode=payload.mode,
        )
    except ValueError as exc:
        raise bad_request(str(exc)) from exc

    if result.get("reindex_required"):
        background_tasks.add_task(_run_process_document, result["id"])
    return result


# ─── 文档全文 + 分段 ───


@router.get("/{kb_id}/documents/{doc_id}/content")
def get_kb_document_content(
    kb_id: str,
    doc_id: str,
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> dict[str, Any]:
    try:
        return service.get_document_content(doc_id, user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc


# ─── 索引片段导出 ───


@router.get("/{kb_id}/documents/{doc_id}/chunks/export")
def export_kb_document_chunks(
    kb_id: str,
    doc_id: str,
    format: Literal["md", "txt"] = Query(default="md"),
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> StreamingResponse:
    try:
        doc_info = service.get_document(doc_id, user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc

    chunks_data = service.list_chunks(doc_id, user_id, offset=0, limit=100000)
    items = chunks_data.get("items", [])
    file_name = doc_info.get("file_name", "document")

    from datetime import datetime
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if format == "md":
        lines = [f"# {file_name}", "", f"> 共 {len(items)} 个片段，导出时间 {now_str}", ""]
        for item in items:
            idx = item.get("chunk_index", 0)
            content = item.get("content", "")
            lines.append(f"## 片段 #{idx}")
            lines.append("")
            lines.append(content)
            lines.append("")
            lines.append("---")
            lines.append("")
        body = "\n".join(lines)
        ext = "md"
    else:
        lines = [f"=== {file_name} ===", f"共 {len(items)} 个片段，导出时间 {now_str}", ""]
        for item in items:
            idx = item.get("chunk_index", 0)
            content = item.get("content", "")
            lines.append(f"=== 片段 #{idx} ===")
            lines.append(content)
            lines.append("")
        body = "\n".join(lines)
        ext = "txt"

    safe_name = file_name.replace("/", "_").replace("\\", "_")
    filename = f"{safe_name}.chunks.{ext}"

    def _iter():
        yield body.encode("utf-8")

    from urllib.parse import quote
    return StreamingResponse(
        _iter(),
        media_type="text/markdown" if format == "md" else "text/plain",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ─── 分段预览 ───


@router.post("/{kb_id}/documents/{doc_id}/preview-chunks")
def preview_kb_chunks(
    kb_id: str,
    doc_id: str,
    payload: ChunkPreviewRequest = Body(...),
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> dict[str, Any]:
    try:
        return service.preview_chunks(
            doc_id, user_id,
            chunk_size=payload.chunk_size,
            chunk_overlap=payload.chunk_overlap,
        )
    except ValueError as exc:
        raise not_found(str(exc)) from exc


# ─── 全库重建索引 ───


@router.post("/{kb_id}/reindex-all")
def reindex_all_kb_docs(
    kb_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    service: KbService = Depends(get_kb_service),
) -> dict[str, Any]:
    try:
        docs = service.list_documents(kb_id, user_id)
    except ValueError as exc:
        raise not_found(str(exc)) from exc

    for doc in docs:
        background_tasks.add_task(_run_reindex_document, doc["id"])
    return {"message": "reindex queued", "count": len(docs)}
