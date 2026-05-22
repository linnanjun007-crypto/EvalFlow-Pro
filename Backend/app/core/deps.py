"""共享依赖注入：用户认证、权限校验。

复用 app.api.deps.get_actor_user_id 作为底层 token 解析，
本模块在其基础上提供更高级的依赖（User 实体、管理员校验、可选用户）。
"""
from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.api.deps import get_actor_user_id
from app.core.errors import unauthorized
from app.db.session import get_db
from app.models.user import User


def get_current_user_id(user_id: str = Depends(get_actor_user_id)) -> str:
    """从 Authorization 头解析当前用户 ID。"""
    return user_id


def get_optional_user_id(authorization: str | None = Header(default=None)) -> str | None:
    """可选用户 ID — 无 token 时返回 None，不抛异常。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith("user:"):
        return None
    user_id = token.split(":", 1)[1]
    return user_id or None


def get_current_user(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> User:
    """从 Authorization 头取出 user_id，再查 DB 返回 User 实体（含 status 校验）。"""
    user = db.get(User, user_id)
    if not user:
        raise unauthorized("用户不存在")
    if user.status != "active":
        raise unauthorized("用户已被禁用")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """要求当前用户是管理员。"""
    if user.role != "admin":
        raise unauthorized("需要管理员权限")
    return user
