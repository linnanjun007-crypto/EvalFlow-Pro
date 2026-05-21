from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AdminStepConfig(Base):
    __tablename__ = "admin_step_configs"

    step_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    module_order: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
