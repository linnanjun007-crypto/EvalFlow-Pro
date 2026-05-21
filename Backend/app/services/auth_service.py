from __future__ import annotations

from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _hash_password(self, password: str) -> str:
        return sha256(password.encode("utf-8")).hexdigest()

    def register(self, username: str, password: str) -> dict[str, Any]:
        exists = self.db.scalar(select(User).where(User.username == username))
        if exists:
            raise ValueError("用户名已存在")

        user = User(
            id=str(uuid4()),
            username=username,
            password_hash=self._hash_password(password),
            role="user",
            status="active",
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return {
            "id": user.id,
            "username": user.username,
            "role": user.role,
        }

    def login(self, username: str, password: str) -> dict[str, str]:
        user = self.db.scalar(select(User).where(User.username == username))
        if not user or user.password_hash != self._hash_password(password):
            raise ValueError("用户名或密码错误")
        if user.status != "active":
            raise ValueError("用户已被禁用")

        return {
            "access_token": f"user:{user.id}",
            "token_type": "bearer",
        }

    def me(self, user_id: str) -> dict[str, str]:
        user = self.db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")
        return {
            "id": user.id,
            "username": user.username,
            "role": user.role,
        }

    def list_users(self) -> list[dict[str, Any]]:
        items = self.db.scalars(select(User)).all()
        return [{"id": u.id, "username": u.username, "role": u.role, "status": u.status} for u in items]

    def set_user_status(self, user_id: str, status: str) -> dict[str, str]:
        user = self.db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")
        user.status = status
        self.db.commit()
        return {"message": "updated"}
