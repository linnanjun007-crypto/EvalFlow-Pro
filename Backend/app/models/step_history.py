from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StepHistory(Base):
    __tablename__ = "step_histories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    step_output_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    content_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
