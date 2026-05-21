from __future__ import annotations

from typing import Any


class DownloadService:
    def __init__(self, db) -> None:
        self.db = db

    def list_downloads(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "dl-1",
                "name": "项目 demo-1 导出包",
                "status": "可下载",
                "created": "2026-05-10 15:10",
                "size": "12 MB",
                "download_url": "/downloads/dl-1/file",
            },
            {
                "id": "dl-2",
                "name": "项目 demo-2 导出包",
                "status": "生成中",
                "created": "2026-05-11 09:40",
                "size": "—",
                "download_url": None,
            },
        ]
