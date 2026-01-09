"""Entitlements middleware decorators for API routes."""

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from fastapi import HTTPException, Request

from dataing.core.entitlements.features import Feature
from dataing.entrypoints.api.middleware.auth import ApiKeyContext

F = TypeVar("F", bound=Callable[..., Any])


def require_feature(feature: Feature) -> Callable[[F], F]:
    """Decorator to require a feature to be enabled for the org.

    Usage:
        @router.get("/sso/config")
        @require_feature(Feature.SSO_OIDC)
        async def get_sso_config(request: Request, auth: AuthDep):
            ...

    The decorator extracts org_id from auth context (tenant_id).
    Requires request: Request and auth: AuthDep parameters in the route.

    Args:
        feature: Feature that must be enabled

    Raises:
        HTTPException: 403 if feature not available
    """

    def decorator(func: F) -> F:
        """Decorate function with feature check."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract request and auth from kwargs
            request: Request | None = kwargs.get("request")
            auth: ApiKeyContext | None = kwargs.get("auth")

            if request is None or auth is None:
                # Can't check feature without request/auth - let route handle it
                return await func(*args, **kwargs)

            # Get entitlements adapter from app state
            adapter = request.app.state.entitlements_adapter
            org_id = str(auth.tenant_id)

            if not await adapter.has_feature(org_id, feature):
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "feature_not_available",
                        "feature": feature.value,
                        "message": f"The '{feature.value}' feature requires an Enterprise plan.",
                        "upgrade_url": "/settings/billing",
                        "contact_sales": True,
                    },
                )
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def require_under_limit(feature: Feature) -> Callable[[F], F]:
    """Decorator to require org is under their usage limit.

    Usage:
        @router.post("/investigations")
        @require_under_limit(Feature.MAX_INVESTIGATIONS_PER_MONTH)
        async def create_investigation(request: Request, auth: AuthDep):
            ...

    The decorator extracts org_id from auth context (tenant_id).
    Requires request: Request and auth: AuthDep parameters in the route.

    Args:
        feature: Feature limit to check

    Raises:
        HTTPException: 403 if over limit
    """

    def decorator(func: F) -> F:
        """Decorate function with limit check."""

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract request and auth from kwargs
            request: Request | None = kwargs.get("request")
            auth: ApiKeyContext | None = kwargs.get("auth")

            if request is None or auth is None:
                # Can't check limit without request/auth - let route handle it
                return await func(*args, **kwargs)

            # Get entitlements adapter from app state
            adapter = request.app.state.entitlements_adapter
            org_id = str(auth.tenant_id)

            if not await adapter.check_limit(org_id, feature):
                limit = await adapter.get_limit(org_id, feature)
                usage = await adapter.get_usage(org_id, feature)
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "limit_exceeded",
                        "feature": feature.value,
                        "limit": limit,
                        "usage": usage,
                        "message": f"You've reached your limit of {limit} for {feature.value}.",
                        "upgrade_url": "/settings/billing",
                        "contact_sales": False,
                    },
                )
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
