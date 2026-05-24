from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    import logging

    logger = logging.getLogger(__name__)

    async def _daily_cleanup():
        from app.db.session import SessionLocal
        from app.services.project_report_service import cleanup_expired

        while True:
            await asyncio.sleep(86400)
            db = SessionLocal()
            try:
                count = cleanup_expired(db)
                if count:
                    logger.info("cleaned up %d expired reports", count)
            except Exception:  # noqa: BLE001
                logger.exception("report cleanup failed")
            finally:
                db.close()

    task = asyncio.create_task(_daily_cleanup())
    yield
    task.cancel()


app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
