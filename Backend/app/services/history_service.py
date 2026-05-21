from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.step_history import StepHistory
from app.models.step_output import StepOutput


class HistoryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_history(self, keyword: str | None = None) -> list[dict[str, Any]]:
        outputs = self.db.scalars(select(StepOutput)).all()
        histories = self.db.scalars(select(StepHistory)).all()
        history_map = {item.step_output_id: item for item in histories}
        items: list[dict[str, Any]] = []
        for output in outputs:
            record = history_map.get(output.id)
            title = output.title or output.step_code
            summary = output.content_text or (record.content_text if record else "") or ""
            row = {
                "time": datetime.utcnow().isoformat(timespec="seconds"),
                "project_id": output.project_id,
                "project": output.project_id,
                "step": output.step_code,
                "summary": summary[:120],
                "title": title,
                "content_text": summary,
            }
            if not keyword or keyword in row["project"] or keyword in row["summary"] or keyword in row["step"]:
                items.append(row)
        return items
