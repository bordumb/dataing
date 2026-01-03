"""Authentication service."""
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog

from dataing.adapters.db.app_db import AppDatabase

logger = structlog.get_logger()


@dataclass
class ApiKeyResult:
    """Result of API key creation."""

    id: UUID
    key: str  # Full key (only returned once)
    key_prefix: str
    name: str
    scopes: list[str]
    expires_at: datetime | None


class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: AppDatabase):
        self.db = db

    async def create_api_key(
        self,
        tenant_id: UUID,
        name: str,
        scopes: list[str] | None = None,
        user_id: UUID | None = None,
        expires_in_days: int | None = None,
    ) -> ApiKeyResult:
        """Create a new API key.

        Returns the full key only once - it cannot be retrieved later.
        """
        # Generate a secure random key
        key = f"ddr_{secrets.token_urlsafe(32)}"
        key_prefix = key[:8]
        key_hash = hashlib.sha256(key.encode()).hexdigest()

        scopes = scopes or ["read", "write"]

        expires_at = None
        if expires_in_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        result = await self.db.create_api_key(
            tenant_id=tenant_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            scopes=scopes,
            user_id=user_id,
            expires_at=expires_at,
        )

        logger.info(
            "api_key_created",
            key_id=str(result["id"]),
            tenant_id=str(tenant_id),
            name=name,
        )

        return ApiKeyResult(
            id=result["id"],
            key=key,
            key_prefix=key_prefix,
            name=name,
            scopes=scopes,
            expires_at=expires_at,
        )

    async def list_api_keys(self, tenant_id: UUID) -> list[dict]:
        """List all API keys for a tenant (without revealing key values)."""
        return await self.db.list_api_keys(tenant_id)

    async def revoke_api_key(self, key_id: UUID, tenant_id: UUID) -> bool:
        """Revoke an API key."""
        success = await self.db.revoke_api_key(key_id, tenant_id)

        if success:
            logger.info(
                "api_key_revoked",
                key_id=str(key_id),
                tenant_id=str(tenant_id),
            )

        return success

    async def rotate_api_key(
        self,
        key_id: UUID,
        tenant_id: UUID,
    ) -> ApiKeyResult | None:
        """Rotate an API key (revoke old, create new with same settings)."""
        # Get existing key info
        keys = await self.db.list_api_keys(tenant_id)
        old_key = next((k for k in keys if k["id"] == key_id), None)

        if not old_key:
            return None

        # Revoke old key
        await self.revoke_api_key(key_id, tenant_id)

        # Create new key with same settings
        return await self.create_api_key(
            tenant_id=tenant_id,
            name=f"{old_key['name']} (rotated)",
            scopes=old_key.get("scopes", ["read", "write"]),
            user_id=None,
        )
