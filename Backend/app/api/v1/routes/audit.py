from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.audit_service import AuditService

router = APIRouter()


def get_audit_service(db: Session = Depends(get_db)) -> AuditService:
    return AuditService(db)


@router.get("")
def list_audit_logs(
    step_code: str | None = None,
    target_type: str | None = None,
    limit: int = 100,
    service: AuditService = Depends(get_audit_service),
) -> dict[str, list[dict[str, object]]]:
    return {"items": service.list_logs(step_code=step_code, target_type=target_type, limit=limit)}
