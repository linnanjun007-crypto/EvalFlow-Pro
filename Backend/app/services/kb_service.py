"""KbService — 用户知识库 CRUD + 项目绑定。"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.kb_chunk import KbChunk
from app.models.kb_document import KbDocument
from app.models.project_kb import ProjectKnowledgeBase
from app.models.user_knowledge_base import UserKnowledgeBase
from app.services.embedding_service import get_active_embedding_model


class KbService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_kbs(self, user_id: str) -> list[dict[str, Any]]:
        items = self.db.scalars(
            select(UserKnowledgeBase).where(UserKnowledgeBase.user_id == user_id).order_by(UserKnowledgeBase.updated_at.desc())
        ).all()
        return [self._kb_to_dict(item) for item in items]

    def create_kb(self, user_id: str, name: str, description: str = "") -> dict[str, Any]:
        emb_model = get_active_embedding_model(self.db)
        if not emb_model:
            raise ValueError("请先在管理端配置并启用默认 Embedding 模型")
        kb = UserKnowledgeBase(
            id=str(uuid4()),
            user_id=user_id,
            name=name,
            description=description or None,
            embedding_model_id=emb_model.id,
            embedding_dim=emb_model.dimensions or 1536,
        )
        self.db.add(kb)
        self.db.commit()
        self.db.refresh(kb)
        return self._kb_to_dict(kb)

    def get_kb(self, kb_id: str, user_id: str) -> dict[str, Any]:
        kb = self._get_owned(kb_id, user_id)
        doc_count = self.db.scalar(select(func.count()).where(KbDocument.kb_id == kb_id)) or 0
        chunk_count = self.db.scalar(select(func.count()).where(KbChunk.kb_id == kb_id)) or 0
        d = self._kb_to_dict(kb)
        d["doc_count"] = doc_count
        d["chunk_count"] = chunk_count
        return d

    def update_kb(self, kb_id: str, user_id: str, name: str | None = None, description: str | None = None) -> dict[str, Any]:
        kb = self._get_owned(kb_id, user_id)
        if name is not None:
            kb.name = name.strip() or kb.name
        if description is not None:
            kb.description = description or None
        self.db.commit()
        self.db.refresh(kb)
        return self._kb_to_dict(kb)

    def delete_kb(self, kb_id: str, user_id: str) -> None:
        kb = self._get_owned(kb_id, user_id)
        self.db.delete(kb)
        self.db.commit()

    def list_documents(self, kb_id: str, user_id: str) -> list[dict[str, Any]]:
        self._get_owned(kb_id, user_id)
        items = self.db.scalars(
            select(KbDocument).where(KbDocument.kb_id == kb_id).order_by(KbDocument.created_at.desc())
        ).all()
        return [self._doc_to_dict(item) for item in items]

    def delete_document(self, doc_id: str, user_id: str) -> None:
        doc = self.db.get(KbDocument, doc_id)
        if not doc:
            raise ValueError("文档不存在")
        self._get_owned(doc.kb_id, user_id)
        self.db.execute(delete(KbChunk).where(KbChunk.document_id == doc_id))
        self.db.delete(doc)
        self.db.commit()

    def get_document(self, doc_id: str, user_id: str) -> dict[str, Any]:
        doc = self.db.get(KbDocument, doc_id)
        if not doc:
            raise ValueError("文档不存在")
        self._get_owned(doc.kb_id, user_id)
        return {
            "id": doc.id,
            "kb_id": doc.kb_id,
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "file_size": doc.file_size,
            "source_type": doc.source_type,
            "chunk_count": doc.chunk_count,
            "status": doc.status,
            "error_message": doc.error_message,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "indexed_at": doc.indexed_at.isoformat() if doc.indexed_at else None,
        }

    def list_chunks(
        self, doc_id: str, user_id: str, *, offset: int = 0, limit: int = 50
    ) -> dict[str, Any]:
        doc = self.db.get(KbDocument, doc_id)
        if not doc:
            raise ValueError("文档不存在")
        self._get_owned(doc.kb_id, user_id)
        total = (
            self.db.scalar(
                select(func.count(KbChunk.id)).where(KbChunk.document_id == doc_id)
            )
            or 0
        )
        rows = self.db.scalars(
            select(KbChunk)
            .where(KbChunk.document_id == doc_id)
            .order_by(KbChunk.chunk_index)
            .offset(offset)
            .limit(limit)
        ).all()
        items = [
            {
                "id": int(c.id),
                "chunk_index": c.chunk_index,
                "content": c.content,
                "char_count": len(c.content or ""),
                "metadata": c.metadata_json,
            }
            for c in rows
        ]
        return {"items": items, "total": int(total), "offset": offset, "limit": limit}

    # --- 项目绑定 ---

    def list_project_kbs(self, project_id: str, user_id: str) -> list[dict[str, Any]]:
        bindings = self.db.scalars(
            select(ProjectKnowledgeBase).where(ProjectKnowledgeBase.project_id == project_id)
        ).all()
        kb_ids = [b.kb_id for b in bindings if b.enabled]
        if not kb_ids:
            return []
        items = self.db.scalars(
            select(UserKnowledgeBase).where(UserKnowledgeBase.id.in_(kb_ids), UserKnowledgeBase.user_id == user_id)
        ).all()
        return [self._kb_to_dict(item) for item in items]

    def set_project_kbs(self, project_id: str, user_id: str, kb_ids: list[str]) -> list[dict[str, Any]]:
        self.db.execute(delete(ProjectKnowledgeBase).where(ProjectKnowledgeBase.project_id == project_id))
        for kb_id in kb_ids:
            kb = self.db.get(UserKnowledgeBase, kb_id)
            if kb and kb.user_id == user_id:
                self.db.add(ProjectKnowledgeBase(project_id=project_id, kb_id=kb_id, enabled=True))
        self.db.commit()
        return self.list_project_kbs(project_id, user_id)

    # --- helpers ---

    def _get_owned(self, kb_id: str, user_id: str) -> UserKnowledgeBase:
        kb = self.db.get(UserKnowledgeBase, kb_id)
        if not kb or kb.user_id != user_id:
            raise ValueError("知识库不存在或无权限")
        return kb

    def _kb_to_dict(self, kb: UserKnowledgeBase) -> dict[str, Any]:
        return {
            "id": kb.id,
            "user_id": kb.user_id,
            "name": kb.name,
            "description": kb.description,
            "embedding_model_id": kb.embedding_model_id,
            "embedding_dim": kb.embedding_dim,
            "chunk_size": kb.chunk_size,
            "chunk_overlap": kb.chunk_overlap,
            "status": kb.status,
            "enable_bm25": kb.enable_bm25,
            "enable_rerank": kb.enable_rerank,
            "rrf_k": kb.rrf_k,
            "created_at": kb.created_at.isoformat() if kb.created_at else None,
            "updated_at": kb.updated_at.isoformat() if kb.updated_at else None,
        }

    def _doc_to_dict(self, doc: KbDocument) -> dict[str, Any]:
        return {
            "id": doc.id,
            "kb_id": doc.kb_id,
            "source_file_id": doc.source_file_id,
            "source_type": doc.source_type,
            "file_name": doc.file_name,
            "file_type": doc.file_type,
            "file_size": doc.file_size,
            "chunk_count": doc.chunk_count,
            "status": doc.status,
            "error_message": doc.error_message,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "indexed_at": doc.indexed_at.isoformat() if doc.indexed_at else None,
        }
