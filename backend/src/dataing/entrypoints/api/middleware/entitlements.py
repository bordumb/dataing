"""Entitlements middleware decorators for API routes."""

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from fastapi import HTTPException

from dataing.core.entitlements import Feature, get_entitlements_adapter

F = TypeVar("F", bound=Callable[..., Any])


def require_feature(feature: Feature) -> Callable[[F], F]:
    """Decorator to require a feature to be enabled for the org.

    Usage:
        @router.get("/sso/config")
        @require_feature(Feature.SSO_OIDC)
        async def get_sso_config(org_id: str):
            ...

    Args:
        feature: Feature that must be enabled

    Raises:
        HTTPException: 403 if feature not available
    """

    def decorator(func: F) -> F:
        """Decorate function with feature check."""

        @wraps(func)
        async def wrapper(*args: Any, org_id: str, **kwargs: Any) -> Any:
            adapter = get_entitlements_adapter()
            if not await adapter.has_feature(org_id, feature):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "feature_not_available",
                        "feature": feature.value,
                        "upgrade_url": "/settings/billing",
                    },
                )
            return await func(*args, org_id=org_id, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def require_under_limit(feature: Feature) -> Callable[[F], F]:
    """Decorator to require org is under their usage limit.

    Usage:
        @router.post("/investigations")
        @require_under_limit(Feature.MAX_INVESTIGATIONS_PER_MONTH)
        async def create_investigation(org_id: str):
            ...

    Args:
        feature: Feature limit to check

    Raises:
        HTTPException: 403 if over limit
    """

    def decorator(func: F) -> F:
        """Decorate function with limit check."""

        @wraps(func)
        async def wrapper(*args: Any, org_id: str, **kwargs: Any) -> Any:
            adapter = get_entitlements_adapter()
            if not await adapter.check_limit(org_id, feature):
                limit = await adapter.get_limit(org_id, feature)
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "limit_exceeded",
                        "feature": feature.value,
                        "limit": limit,
                        "upgrade_url": "/settings/billing",
                    },
                )
            return await func(*args, org_id=org_id, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
