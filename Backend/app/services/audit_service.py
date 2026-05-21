from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.user import User


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(
        self,
        *,
        actor_user_id: str,
        action: str,
        target_type: str,
        target_id: str,
        before_data: dict[str, Any] | None = None,
        after_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = AuditLog(
            id=str(uuid4()),
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before_data=json.dumps(before_data, ensure_ascii=False) if before_data is not None else None,
            after_data=json.dumps(after_data, ensure_ascii=False) if after_data is not None else None,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(item)
        self.db.flush()
        return self._to_dict(item)

    def list_logs(
        self,
        *,
        step_code: str | None = None,
        target_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(max(1, min(limit, 500)))
        if target_type:
            stmt = stmt.where(AuditLog.target_type == target_type)
        rows = self.db.scalars(stmt).all()
        usernames = self._username_map({row.actor_user_id for row in rows})
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = self._to_dict(row)
            payload["actor_username"] = usernames.get(row.actor_user_id, row.actor_user_id)
            after = payload.get("after_data") or {}
            before = payload.get("before_data") or {}
            if step_code:
                row_step = str(after.get("step_code") or before.get("step_code") or "")
                if row_step and row_step != step_code:
                    continue
            payload["summary"] = self._build_summary(payload)
            items.append(payload)
        return items

    def _username_map(self, user_ids: set[str]) -> dict[str, str]:
        if not user_ids:
            return {}
        rows = self.db.scalars(select(User).where(User.id.in_(user_ids))).all()
        return {row.id: row.username for row in rows}

    def _build_summary(self, item: dict[str, Any]) -> str:
        action = item.get("action") or ""
        target_type = item.get("target_type") or ""
        after = item.get("after_data") or {}
        title = after.get("title") or after.get("name") or item.get("target_id")
        step_code = after.get("step_code") or (item.get("before_data") or {}).get("step_code") or ""
        prefix = f"{step_code} " if step_code else ""
        action_labels = {
            "create": "新增",
            "update": "更新",
            "delete": "删除",
            "activate": "启用",
            "publish": "发布",
            "save_config": "保存配置",
        }
        type_labels = {"prompt": "Prompt", "kb": "知识库", "step_config": "步骤配置"}
        return f"{prefix}{action_labels.get(action, action)}{type_labels.get(target_type, target_type)}：{title}"

    def _to_dict(self, item: AuditLog) -> dict[str, Any]:
        before = json.loads(item.before_data) if item.before_data else None
        after = json.loads(item.after_data) if item.after_data else None
        created_at = item.created_at.isoformat(timespec="seconds").replace("+00:00", "Z") if item.created_at else None
        return {
            "id": item.id,
            "actor_user_id": item.actor_user_id,
            "action": item.action,
            "target_type": item.target_type,
            "target_id": item.target_id,
            "before_data": before,
            "after_data": after,
            "created_at": created_at,
        }
