"""API route modules - Community Edition.

Note: SSO, SCIM, Audit, and Settings routes are available in Enterprise Edition.
"""

from fastapi import APIRouter

from dataing.entrypoints.api.routes.approvals import router as approvals_router
from dataing.entrypoints.api.routes.auth import router as auth_router
from dataing.entrypoints.api.routes.comment_votes import router as comment_votes_router
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
from dataing.entrypoints.api.routes.permissions import (
    investigation_permissions_router,
)
from dataing.entrypoints.api.routes.permissions import (
    router as permissions_router,
)
from dataing.entrypoints.api.routes.schema_comments import router as schema_comments_router
from dataing.entrypoints.api.routes.tags import (
    investigation_tags_router,
)
from dataing.entrypoints.api.routes.tags import (
    router as tags_router,
)
from dataing.entrypoints.api.routes.teams import router as teams_router
from dataing.entrypoints.api.routes.users import router as users_router

# Create main API router
api_router = APIRouter()

# Include all route modules
api_router.include_router(auth_router, prefix="/auth")  # Auth routes (no API key required)
api_router.include_router(investigations_router)
api_router.include_router(datasources_router)
api_router.include_router(datasources_v2_router, prefix="/v2")  # New unified adapter API
api_router.include_router(datasets_router)
api_router.include_router(approvals_router)
api_router.include_router(users_router)
api_router.include_router(dashboard_router)
api_router.include_router(lineage_router)
api_router.include_router(investigation_feedback_router)
api_router.include_router(schema_comments_router)
api_router.include_router(knowledge_comments_router)
api_router.include_router(comment_votes_router)
api_router.include_router(teams_router, prefix="/teams")

# RBAC routes
api_router.include_router(teams_router)
api_router.include_router(tags_router)
api_router.include_router(permissions_router)
api_router.include_router(investigation_tags_router)
api_router.include_router(investigation_permissions_router)

__all__ = ["api_router"]
