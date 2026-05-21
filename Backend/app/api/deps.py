from fastapi import Header

from app.core.errors import unauthorized


def get_actor_user_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise unauthorized("未提供有效 token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith("user:"):
        raise unauthorized("无效 token")
    return token.split(":", 1)[1]
