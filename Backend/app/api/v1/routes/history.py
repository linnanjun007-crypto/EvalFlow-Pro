from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.history_service import HistoryService

router = APIRouter()


def get_history_service(db: Session = Depends(get_db)) -> HistoryService:
    return HistoryService(db)


@router.get("")
def list_history(keyword: str | None = None, service: HistoryService = Depends(get_history_service)) -> dict[str, list[dict[str, object]]]:
    return {"items": service.list_history(keyword=keyword)}


@router.get("/{history_id}")
def get_history(history_id: str, service: HistoryService = Depends(get_history_service)) -> dict[str, object]:
    for item in service.list_history():
        if str(item.get("project_id")) == history_id or str(item.get("title")) == history_id:
            return item
    return {"id": history_id, "status": "not_found"}
