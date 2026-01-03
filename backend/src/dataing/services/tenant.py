"""Multi-tenancy service."""
import re
from dataclasses import dataclass
from uuid import UUID

import structlog

from dataing.adapters.db.app_db import AppDatabase

logger = structlog.get_logger()


@dataclass
class TenantInfo:
    """Tenant information."""

    id: UUID
    name: str
    slug: str
    settings: dict


class TenantService:
    """Service for multi-tenant operations."""

    def __init__(self, db: AppDatabase):
        self.db = db

    async def create_tenant(
        self,
        name: str,
        slug: str | None = None,
        settings: dict | None = None,
    ) -> TenantInfo:
        """Create a new tenant."""
        # Generate slug from name if not provided
        if not slug:
            slug = self._generate_slug(name)

        # Ensure slug is unique
        existing = await self.db.get_tenant_by_slug(slug)
        if existing:
            # Append a number to make it unique
            base_slug = slug
            counter = 1
            while existing:
                slug = f"{base_slug}-{counter}"
                existing = await self.db.get_tenant_by_slug(slug)
                counter += 1

        result = await self.db.create_tenant(
            name=name,
            slug=slug,
            settings=settings,
        )

        logger.info(
            "tenant_created",
            tenant_id=str(result["id"]),
            slug=slug,
        )

        return TenantInfo(
            id=result["id"],
            name=result["name"],
            slug=result["slug"],
            settings=result.get("settings", {}),
        )

    async def get_tenant(self, tenant_id: UUID) -> TenantInfo | None:
        """Get tenant by ID."""
        result = await self.db.get_tenant(tenant_id)
        if not result:
            return None

        return TenantInfo(
            id=result["id"],
            name=result["name"],
            slug=result["slug"],
            settings=result.get("settings", {}),
        )

    async def get_tenant_by_slug(self, slug: str) -> TenantInfo | None:
        """Get tenant by slug."""
        result = await self.db.get_tenant_by_slug(slug)
        if not result:
            return None

        return TenantInfo(
            id=result["id"],
            name=result["name"],
            slug=result["slug"],
            settings=result.get("settings", {}),
        )

    async def update_tenant_settings(
        self,
        tenant_id: UUID,
        settings: dict,
    ) -> TenantInfo | None:
        """Update tenant settings."""
        result = await self.db.execute_returning(
            """UPDATE tenants SET settings = settings || $2
               WHERE id = $1 RETURNING *""",
            tenant_id,
            settings,
        )

        if not result:
            return None

        logger.info(
            "tenant_settings_updated",
            tenant_id=str(tenant_id),
            updated_keys=list(settings.keys()),
        )

        return TenantInfo(
            id=result["id"],
            name=result["name"],
            slug=result["slug"],
            settings=result.get("settings", {}),
        )

    def _generate_slug(self, name: str) -> str:
        """Generate a URL-safe slug from a name."""
        # Convert to lowercase
        slug = name.lower()
        # Replace spaces and special chars with hyphens
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        # Remove leading/trailing hyphens
        slug = slug.strip("-")
        # Limit length
        return slug[:50]
