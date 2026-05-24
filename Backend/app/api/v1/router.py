from fastapi import APIRouter

from app.api.v1.routes import admin, agent, auth, chat, conversations, downloads, exports, files, health, history, kbs, projects, steps, audit, usage

api_router = APIRouter()
api_router.include_router(health.router, tags=["system"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(files.router, prefix="/files", tags=["files"])
api_router.include_router(steps.router, prefix="/steps", tags=["steps"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(conversations.router, prefix="/conversations", tags=["conversations"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(agent.router, prefix="/agent", tags=["agent"])
api_router.include_router(history.router, prefix="/history", tags=["history"])
api_router.include_router(downloads.router, prefix="/downloads", tags=["downloads"])
api_router.include_router(exports.router, prefix="/exports", tags=["exports"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(usage.router, prefix="/usage", tags=["usage"])
api_router.include_router(kbs.router, prefix="/kbs", tags=["kbs"])
