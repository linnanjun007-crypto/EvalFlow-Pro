"""KbIndexingService — 文件解析 → chunk → embed → 入库。"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import func as sa_func

from app.models.kb_chunk import KbChunk
from app.models.kb_document import KbDocument
from app.models.user_knowledge_base import UserKnowledgeBase
from app.services.chunking_service import chunk_document
from app.services.embedding_service import embed_texts, get_active_embedding_model
from app.services.file_parser import parse_file_full
from app.services.text_tokenizer import tokenize_zh

logger = logging.getLogger(__name__)

KB_STORAGE_ROOT = os.environ.get("KB_STORAGE_ROOT", "storage/kbs")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


async def process_document(db: Session, document_id: str) -> None:
    """后台任务入口：解析 → chunk → embed → 写入 kb_chunks。"""

    doc = db.get(KbDocument, document_id)
    if not doc:
        logger.warning("process_document: doc %s not found", document_id)
        return

    doc.status = "processing"
    db.commit()

    try:
        kb = db.get(UserKnowledgeBase, doc.kb_id)
        if not kb:
            raise RuntimeError("知识库不存在")

        # 1. 解析全文
        text, file_type = parse_file_full(doc.storage_key)
        if not text.strip():
            raise RuntimeError("文件解析结果为空")

        # 2. 切 chunk
        chunks = chunk_document(
            text,
            file_type=file_type,
            chunk_size=kb.chunk_size,
            chunk_overlap=kb.chunk_overlap,
        )
        if not chunks:
            raise RuntimeError("切分结果为空")

        # 3. 获取 embedding 模型
        emb_model = get_active_embedding_model(db)
        if not emb_model:
            raise RuntimeError("未配置默认 Embedding 模型")

        # 4. 批量 embed
        contents = [c["content"] for c in chunks]
        vectors = await embed_texts(
            contents,
            base_url=emb_model.base_url or "",
            api_key=emb_model.api_key or "",
            model_name=emb_model.model_id,
        )

        # 5. 写入 kb_chunks（同步写入 content_tsv 用于 BM25 召回）
        for chunk_meta, vector in zip(chunks, vectors, strict=False):
            content_text = str(chunk_meta["content"])
            tokens = tokenize_zh(content_text)
            chunk_row = KbChunk(
                kb_id=doc.kb_id,
                document_id=doc.id,
                chunk_index=int(chunk_meta["chunk_index"]),
                content=content_text,
                embedding=vector,
                embedding_model_id=emb_model.id,
                metadata_json=chunk_meta.get("metadata"),
                content_tsv=sa_func.to_tsvector("simple", tokens),
            )
            db.add(chunk_row)

        doc.chunk_count = len(chunks)
        doc.status = "indexed"
        doc.indexed_at = datetime.now(timezone.utc)
        db.commit()
        logger.info("process_document: doc %s indexed, %d chunks", document_id, len(chunks))

    except Exception as exc:  # noqa: BLE001
        db.rollback()
        doc = db.get(KbDocument, document_id)
        if doc:
            doc.status = "failed"
            doc.error_message = str(exc)[:1000]
            db.commit()
        logger.exception("process_document failed: doc=%s", document_id)


def add_document_from_upload(
    db: Session,
    *,
    kb_id: str,
    user_id: str,
    file_name: str,
    file_content: bytes,
) -> KbDocument:
    """保存上传文件到磁盘，创建 kb_documents 行（status=pending）。"""

    kb = db.get(UserKnowledgeBase, kb_id)
    if not kb or kb.user_id != user_id:
        raise ValueError("知识库不存在或无权限")

    ext = Path(file_name).suffix.lower().lstrip(".")
    doc_id = str(uuid4())
    storage_dir = os.path.join(KB_STORAGE_ROOT, kb_id)
    _ensure_dir(storage_dir)
    storage_key = os.path.join(storage_dir, f"{doc_id}_{file_name}")

    with open(storage_key, "wb") as f:
        f.write(file_content)

    doc = KbDocument(
        id=doc_id,
        kb_id=kb_id,
        source_type="upload",
        file_name=file_name,
        file_type=ext,
        storage_key=storage_key,
        file_size=len(file_content),
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def promote_project_file(
    db: Session,
    *,
    kb_id: str,
    file_id: str,
    user_id: str,
) -> KbDocument:
    """把项目文件提升到知识库（不复制文件，复用 storage_key）。"""

    from app.models.file import File

    kb = db.get(UserKnowledgeBase, kb_id)
    if not kb or kb.user_id != user_id:
        raise ValueError("知识库不存在或无权限")

    file_row = db.get(File, file_id)
    if not file_row or file_row.user_id != user_id:
        raise ValueError("文件不存在或无权限")

    ext = Path(file_row.file_name).suffix.lower().lstrip(".")
    doc_id = str(uuid4())
    doc = KbDocument(
        id=doc_id,
        kb_id=kb_id,
        source_file_id=file_id,
        source_type="project_file_promote",
        file_name=file_row.file_name,
        file_type=ext,
        storage_key=file_row.storage_key,
        file_size=file_row.file_size,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


async def reindex_document(db: Session, document_id: str) -> None:
    """删除旧 chunk 后重新索引。"""
    from sqlalchemy import delete

    db.execute(delete(KbChunk).where(KbChunk.document_id == document_id))
    doc = db.get(KbDocument, document_id)
    if doc:
        doc.chunk_count = 0
        doc.status = "pending"
        doc.error_message = None
        db.commit()
    await process_document(db, document_id)
