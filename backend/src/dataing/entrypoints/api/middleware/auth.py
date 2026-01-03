"""API Key authentication middleware."""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

logger = structlog.get_logger()

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass
class ApiKeyContext:
    """Context from a verified API key."""

    key_id: UUID
    tenant_id: UUID
    tenant_slug: str
    tenant_name: str
    user_id: UUID | None
    scopes: list[str]


async def verify_api_key(
    request: Request,
    api_key: str | None = Security(API_KEY_HEADER),
) -> ApiKeyContext:
    """Verify API key and return context.

    This dependency validates the API key and returns tenant/user context.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    # Hash the key to look it up
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    # Get app database from app state (not the data warehouse)
    app_db = request.app.state.app_db

    # Look up the API key
    api_key_record = await app_db.get_api_key_by_hash(key_hash)

    if not api_key_record:
        logger.warning("invalid_api_key", key_prefix=api_key[:8] if len(api_key) >= 8 else api_key)
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Check expiration
    if api_key_record.get("expires_at"):
        expires_at = api_key_record["expires_at"]
        if isinstance(expires_at, datetime) and expires_at < datetime.now(UTC):
            raise HTTPException(status_code=401, detail="API key expired")

    # Update last_used_at (fire and forget)
    try:
        await app_db.update_api_key_last_used(api_key_record["id"])
    except Exception:
        pass  # Don't fail auth if we can't update last_used

    # Parse scopes
    scopes = api_key_record.get("scopes", ["read", "write"])
    if isinstance(scopes, str):
        scopes = json.loads(scopes)

    context = ApiKeyContext(
        key_id=api_key_record["id"],
        tenant_id=api_key_record["tenant_id"],
        tenant_slug=api_key_record.get("tenant_slug", ""),
        tenant_name=api_key_record.get("tenant_name", ""),
        user_id=api_key_record.get("user_id"),
        scopes=scopes,
    )

    # Store context in request state for audit logging
    request.state.auth_context = context

    logger.debug(
        "api_key_verified",
        key_id=str(context.key_id),
        tenant_id=str(context.tenant_id),
    )

    return context


def require_scope(required_scope: str) -> Callable[..., Any]:
    """Dependency to require a specific scope.

    Usage:
        @router.post("/")
        async def create_item(
            auth: Annotated[ApiKeyContext, Depends(require_scope("write"))],
        ):
            ...
    """

    async def scope_checker(
        auth: Annotated[ApiKeyContext, Depends(verify_api_key)],
    ) -> ApiKeyContext:
        if required_scope not in auth.scopes and "*" not in auth.scopes:
            raise HTTPException(
                status_code=403,
                detail=f"Scope '{required_scope}' required",
            )
        return auth

    return scope_checker


# Optional authentication - returns None if no API key provided
async def optional_api_key(
    request: Request,
    api_key: str | None = Security(API_KEY_HEADER),
) -> ApiKeyContext | None:
    """Optionally verify API key, returning None if not provided."""
    if not api_key:
        return None

    try:
        return await verify_api_key(request, api_key)
    except HTTPException:
        return None
