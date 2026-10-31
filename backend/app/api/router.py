from fastapi import APIRouter

from app.api.routes import admin, audit, auth, chat, feedback, review, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(auth.router)
api_router.include_router(chat.router)
api_router.include_router(review.router)
api_router.include_router(admin.router)
api_router.include_router(audit.router)
api_router.include_router(feedback.router)
