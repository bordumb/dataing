"""Audit logging decorator for route handlers."""

from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar
from uuid import UUID

import structlog
from fastapi import Request

from dataing_ee.adapters.audit.types import AuditLogCreate

logger = structlog.get_logger()

P = ParamSpec("P")
R = TypeVar("R")


def get_client_ip(request: Request) -> str | None:
    """Extract client IP from request.

    Args:
        request: FastAPI request object.

    Returns:
        Client IP address or None.
    """
    # Check X-Forwarded-For header first (for proxied requests)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take the first IP in the chain
        return forwarded_for.split(",")[0].strip()

    # Fall back to direct client
    if request.client:
        return request.client.host

    return None


def _extract_resource_info(result: Any, kwargs: dict[str, Any]) -> tuple[UUID | None, str | None]:
    """Extract resource ID and name from result or kwargs.

    Args:
        result: Return value from handler.
        kwargs: Keyword arguments passed to handler.

    Returns:
        Tuple of (resource_id, resource_name).
    """
    resource_id: UUID | None = None
    resource_name: str | None = None

    # Try to extract from result
    if isinstance(result, dict):
        if "id" in result:
            try:
                resource_id = UUID(str(result["id"]))
            except (ValueError, TypeError):
                pass
        resource_name = result.get("name")
    elif hasattr(result, "id"):
        try:
            resource_id = UUID(str(result.id))
        except (ValueError, TypeError):
            pass
        if hasattr(result, "name"):
            resource_name = result.name

    # Try to extract from path params if not in result
    if resource_id is None:
        for key in ("team_id", "tag_id", "datasource_id", "investigation_id", "id"):
            if key in kwargs:
                try:
                    resource_id = UUID(str(kwargs[key]))
                    break
                except (ValueError, TypeError):
                    pass

    return resource_id, resource_name


def audited(
    action: str,
    resource_type: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate route handlers to record audit logs.

    Args:
        action: Action identifier (e.g., "team.create").
        resource_type: Type of resource (e.g., "team").

    Returns:
        Decorated function that records audit logs.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        """Wrap the function to record audit logs."""

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            """Execute function and record audit log."""
            # Extract request from kwargs
            request: Request | None = kwargs.get("request")  # type: ignore[assignment]
            if request is None:
                # Try positional args
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            # Execute the handler
            result = await func(*args, **kwargs)  # type: ignore[misc]

            # Record audit log if we have a request
            if request is not None:
                try:
                    logger.info(f"audit_decorator: recording {action}")
                    await _record_audit(
                        request=request,
                        action=action,
                        resource_type=resource_type,
                        result=result,
                        kwargs=dict(kwargs),
                    )
                    logger.info(f"audit_decorator: recorded {action} successfully")
                except Exception as e:
                    # Log but don't fail the request
                    logger.error(f"Failed to record audit log: {e}", exc_info=True)
            else:
                logger.warning(f"audit_decorator: no request found for {action}")

            typed_result: R = result
            return typed_result

        return wrapper  # type: ignore[return-value]

    return decorator


async def _record_audit(
    request: Request,
    action: str,
    resource_type: str | None,
    result: Any,
    kwargs: dict[str, Any],
) -> None:
    """Record an audit log entry.

    Args:
        request: FastAPI request object.
        action: Action identifier.
        resource_type: Type of resource.
        result: Handler result.
        kwargs: Handler kwargs.
    """
    # Get audit repo from app state
    audit_repo = getattr(request.app.state, "audit_repo", None)
    if audit_repo is None:
        logger.warning("Audit repository not configured, skipping audit log")
        return

    # Extract actor info from auth_context (set by auth middleware)
    auth_context = getattr(request.state, "auth_context", None)
    if auth_context is None:
        logger.warning("No auth_context in request state, skipping audit log")
        return

    tenant_id = auth_context.tenant_id
    actor_id = auth_context.user_id
    actor_email = None  # Not available in ApiKeyContext, could be added later

    # Extract resource info
    resource_id, resource_name = _extract_resource_info(result, kwargs)

    entry = AuditLogCreate(
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_email=actor_email,
        actor_ip=get_client_ip(request),
        actor_user_agent=request.headers.get("user-agent"),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        request_method=request.method,
        request_path=str(request.url.path),
        status_code=200,
    )

    await audit_repo.record(entry)
    logger.debug(f"Recorded audit log: {action}", resource_id=str(resource_id))
