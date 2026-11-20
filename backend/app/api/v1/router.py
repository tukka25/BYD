from fastapi import APIRouter
from app.api.v1.endpoints import auth, blocks, dashboard, data_sources, settings

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(data_sources.router, prefix="/data-sources", tags=["data-sources"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(blocks.router, prefix="/dashboard", tags=["blocks"])
