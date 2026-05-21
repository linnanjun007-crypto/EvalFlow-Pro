from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import bad_request, unauthorized
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthService

router = APIRouter()


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


@router.post("/register", response_model=UserResponse)
def register(payload: LoginRequest, service: AuthService = Depends(get_auth_service)) -> dict[str, str]:
    try:
        return service.register(payload.username, payload.password)
    except ValueError as exc:
        raise bad_request(str(exc)) from exc


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, service: AuthService = Depends(get_auth_service)) -> dict[str, str]:
    try:
        return service.login(payload.username, payload.password)
    except ValueError as exc:
        raise unauthorized(str(exc)) from exc


@router.get("/me", response_model=UserResponse)
def me(authorization: str | None = Header(default=None), service: AuthService = Depends(get_auth_service)) -> dict[str, str]:
    if not authorization or not authorization.startswith("Bearer "):
        raise unauthorized("未提供有效 token")
    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith("user:"):
        raise unauthorized("无效 token")
    user_id = token.split(":", 1)[1]
    try:
        return service.me(user_id)
    except ValueError as exc:
        raise unauthorized(str(exc)) from exc


@router.get("/users")
def list_users(service: AuthService = Depends(get_auth_service)) -> dict[str, list[dict[str, str]]]:
    return {"items": service.list_users()}


@router.patch("/users/{user_id}/status")
def update_user_status(user_id: str, payload: dict, service: AuthService = Depends(get_auth_service)) -> dict[str, str]:
    try:
        return service.set_user_status(user_id, payload.get("status", "active"))
    except ValueError as exc:
        raise bad_request(str(exc)) from exc
