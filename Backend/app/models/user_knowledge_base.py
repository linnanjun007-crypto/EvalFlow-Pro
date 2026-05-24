from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserKnowledgeBase(Base):
    __tablename__ = "user_knowledge_bases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model_id: Mapped[str] = mapped_column(String(36), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, default=1536, nullable=False)
    chunk_size: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    enable_bm25: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    enable_rerank: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    rrf_k: Mapped[int] = mapped_column(Integer, default=60, server_default="60", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
