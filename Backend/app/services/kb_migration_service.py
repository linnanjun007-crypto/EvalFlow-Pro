"""KbMigrationService — 文件在知识库间迁移（移动/复制）。"""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.kb_chunk import KbChunk
from app.models.kb_document import KbDocument
from app.models.user_knowledge_base import UserKnowledgeBase
from app.services.kb_indexing_service import KB_STORAGE_ROOT, _ensure_dir

logger = logging.getLogger(__name__)


def migrate_document(
    db: Session,
    *,
    source_kb_id: str,
    doc_id: str,
    target_kb_id: str,
    user_id: str,
    mode: Literal["move", "copy"],
) -> dict[str, Any]:
    source_kb = db.get(UserKnowledgeBase, source_kb_id)
    if not source_kb or source_kb.user_id != user_id:
        raise ValueError("源知识库不存在或无权限")

    target_kb = db.get(UserKnowledgeBase, target_kb_id)
    if not target_kb or target_kb.user_id != user_id:
        raise ValueError("目标知识库不存在或无权限")

    if source_kb_id == target_kb_id:
        raise ValueError("源和目标知识库不能相同")

    doc = db.get(KbDocument, doc_id)
    if not doc or doc.kb_id != source_kb_id:
        raise ValueError("文档不存在或不属于源知识库")

    same_embedding = (
        source_kb.embedding_model_id == target_kb.embedding_model_id
        and source_kb.embedding_dim == target_kb.embedding_dim
    )

    is_promoted_file = doc.source_type == "project_file_promote"

    if mode == "move":
        new_storage_key = doc.storage_key
        if not is_promoted_file and os.path.exists(doc.storage_key):
            target_dir = os.path.join(KB_STORAGE_ROOT, target_kb_id)
            _ensure_dir(target_dir)
            base_name = os.path.basename(doc.storage_key)
            new_storage_key = os.path.join(target_dir, base_name)
            if os.path.abspath(new_storage_key) != os.path.abspath(doc.storage_key):
                shutil.move(doc.storage_key, new_storage_key)

        doc.kb_id = target_kb_id
        doc.storage_key = new_storage_key

        if same_embedding:
            db.execute(
                update(KbChunk)
                .where(KbChunk.document_id == doc.id)
                .values(kb_id=target_kb_id, embedding_model_id=target_kb.embedding_model_id)
            )
            doc.status = "indexed"
            need_reindex = False
        else:
            from sqlalchemy import delete

            db.execute(delete(KbChunk).where(KbChunk.document_id == doc.id))
            doc.chunk_count = 0
            doc.status = "pending"
            doc.error_message = None
            need_reindex = True

        db.commit()
        db.refresh(doc)
        return {
            "id": doc.id,
            "kb_id": doc.kb_id,
            "file_name": doc.file_name,
            "status": doc.status,
            "mode": "move",
            "reindex_required": need_reindex,
        }

    new_doc_id = str(uuid4())
    target_dir = os.path.join(KB_STORAGE_ROOT, target_kb_id)
    _ensure_dir(target_dir)
    base_name = os.path.basename(doc.storage_key) if doc.storage_key else doc.file_name
    new_storage_key = os.path.join(target_dir, f"{new_doc_id}_{doc.file_name}")
    if doc.storage_key and os.path.exists(doc.storage_key):
        shutil.copy2(doc.storage_key, new_storage_key)
    else:
        new_storage_key = doc.storage_key

    new_doc = KbDocument(
        id=new_doc_id,
        kb_id=target_kb_id,
        source_file_id=doc.source_file_id,
        source_type="copied",
        file_name=doc.file_name,
        file_type=doc.file_type,
        storage_key=new_storage_key,
        file_size=doc.file_size,
        status="pending",
    )
    db.add(new_doc)
    db.commit()
    db.refresh(new_doc)
    return {
        "id": new_doc.id,
        "kb_id": new_doc.kb_id,
        "file_name": new_doc.file_name,
        "status": new_doc.status,
        "mode": "copy",
        "reindex_required": True,
    }
