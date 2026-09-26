"""Audit logging decorator for route handlers."""

import inspect
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar
from uuid import UUID

import structlog
from starlette.requests import Request

from dataing.adapters.audit.types import AuditLogCreate

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


def _takes_request(func: Callable[..., Any]) -> bool:
    """Check whether FastAPI will pass the handler its request.

    FastAPI injects the request into any parameter annotated with Request.
    Route modules use `from __future__ import annotations`, so an annotation
    may be the string name of the imported class.

    Args:
        func: Route handler.

    Returns:
        True if some parameter is annotated with Request.
    """
    globalns = getattr(inspect.unwrap(func), "__globals__", {})
    for param in inspect.signature(func).parameters.values():
        annotation = param.annotation
        if isinstance(annotation, str):
            annotation = globalns.get(annotation)
        if isinstance(annotation, type) and issubclass(annotation, Request):
            return True
    return False


def _find_request(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Request | None:
    """Find the Starlette request among a handler's arguments.

    Matches by type, never by parameter name: many handlers name their JSON
    body `request`.

    Args:
        args: Positional arguments passed to handler.
        kwargs: Keyword arguments passed to handler.

    Returns:
        The request, or None if the handler was not given one.
    """
    for value in (*args, *kwargs.values()):
        if isinstance(value, Request):
            return value
    return None


def _resolve_actor(request: Request) -> tuple[UUID, UUID | None] | None:
    """Resolve who made the request from the auth dependency that ran.

    verify_api_key stores an ApiKeyContext as request.state.auth_context;
    verify_jwt stores a JwtContext as request.state.user.

    Args:
        request: FastAPI request object.

    Returns:
        Tuple of (tenant_id, actor_id), or None for unauthenticated requests.
    """
    auth_context = getattr(request.state, "auth_context", None)
    if auth_context is not None:
        tenant_id: UUID = auth_context.tenant_id
        actor_id: UUID | None = auth_context.user_id
        return tenant_id, actor_id

    jwt_context = getattr(request.state, "user", None)
    if jwt_context is not None:
        return UUID(jwt_context.org_id), UUID(jwt_context.user_id)

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
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorate route handlers to record audit logs.

    Entries go to `app.state.audit_repo`. CE installs a stub repository that
    discards them; EE swaps in one that persists them.

    Args:
        action: Action identifier (e.g., "team.create").
        resource_type: Type of resource (e.g., "team").

    Returns:
        Decorated function that records audit logs.

    Raises:
        TypeError: If the handler has no Request parameter to record from.
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        """Wrap the function to record audit logs."""
        if not _takes_request(func):
            name = getattr(func, "__qualname__", repr(func))
            raise TypeError(
                f"@audited({action!r}) handler {name} needs a Request parameter "
                "(e.g. `http_request: Request`) to record the audit log"
            )

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            """Execute function and record audit log."""
            request = _find_request(args, kwargs)

            # Execute the handler
            result = await func(*args, **kwargs)

            if request is None:
                logger.warning(f"audit_decorator: no request found for {action}")
                return result

            try:
                await _record_audit(
                    request=request,
                    action=action,
                    resource_type=resource_type,
                    result=result,
                    kwargs=dict(kwargs),
                )
            except Exception as e:
                # Log but don't fail the request
                logger.error(f"Failed to record audit log: {e}", exc_info=True)

            return result

        return wrapper

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

    actor = _resolve_actor(request)
    if actor is None:
        logger.warning(f"No authenticated caller for {action}, skipping audit log")
        return

    tenant_id, actor_id = actor
    actor_email = None  # Not available in either auth context, could be added later

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
