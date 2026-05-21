from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.download_service import DownloadService

router = APIRouter()


def get_download_service(db: Session = Depends(get_db)) -> DownloadService:
    return DownloadService(db)


@router.get("")
def list_downloads(service: DownloadService = Depends(get_download_service)) -> dict[str, list[dict[str, object]]]:
    return {"items": service.list_downloads()}


@router.get("/{download_id}")
def get_download(download_id: str, service: DownloadService = Depends(get_download_service)) -> dict[str, object]:
    items = service.list_downloads()
    for item in items:
        if str(item.get("id")) == download_id:
            return item
    return {"id": download_id, "name": "unknown", "status": "not_found", "created": "", "size": "—", "download_url": None}
