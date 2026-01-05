"""API route modules."""

from fastapi import APIRouter

from dataing.entrypoints.api.routes.approvals import router as approvals_router
from dataing.entrypoints.api.routes.dashboard import router as dashboard_router
from dataing.entrypoints.api.routes.datasets import router as datasets_router
from dataing.entrypoints.api.routes.datasources import router as datasources_router
from dataing.entrypoints.api.routes.datasources import router as datasources_v2_router
from dataing.entrypoints.api.routes.investigation_feedback import (
    router as investigation_feedback_router,
)
from dataing.entrypoints.api.routes.investigations import router as investigations_router
from dataing.entrypoints.api.routes.knowledge_comments import (
    router as knowledge_comments_router,
)
from dataing.entrypoints.api.routes.lineage import router as lineage_router
from dataing.entrypoints.api.routes.schema_comments import router as schema_comments_router
from dataing.entrypoints.api.routes.settings import router as settings_router
from dataing.entrypoints.api.routes.users import router as users_router

# Create main API router
api_router = APIRouter()

# Include all route modules
api_router.include_router(investigations_router)
api_router.include_router(datasources_router)
api_router.include_router(datasources_v2_router, prefix="/v2")  # New unified adapter API
api_router.include_router(datasets_router)
api_router.include_router(approvals_router)
api_router.include_router(settings_router)
api_router.include_router(users_router)
api_router.include_router(dashboard_router)
api_router.include_router(lineage_router)
api_router.include_router(investigation_feedback_router)
api_router.include_router(schema_comments_router)
api_router.include_router(knowledge_comments_router)

__all__ = ["api_router"]
