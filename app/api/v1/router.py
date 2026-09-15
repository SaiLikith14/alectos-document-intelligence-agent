from fastapi import APIRouter
from app.api.v1 import agents, documents, health, sessions

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(sessions.router)
api_router.include_router(documents.router)
api_router.include_router(agents.router)
