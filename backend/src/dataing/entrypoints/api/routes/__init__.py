"""API route modules."""

from fastapi import APIRouter

from dataing.entrypoints.api.routes.approvals import router as approvals_router
from dataing.entrypoints.api.routes.dashboard import router as dashboard_router
from dataing.entrypoints.api.routes.datasources import router as datasources_router
from dataing.entrypoints.api.routes.investigations import router as investigations_router
from dataing.entrypoints.api.routes.settings import router as settings_router
from dataing.entrypoints.api.routes.users import router as users_router

# Create main API router
api_router = APIRouter()

# Include all route modules
api_router.include_router(investigations_router)
api_router.include_router(datasources_router)
api_router.include_router(approvals_router)
api_router.include_router(settings_router)
api_router.include_router(users_router)
api_router.include_router(dashboard_router)

__all__ = ["api_router"]
