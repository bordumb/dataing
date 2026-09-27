"""Audit logging for route handlers.

`audited` records an entry after a handler succeeds. `record_audit` records
one explicitly, for routes the decorator can't cover.
"""

import inspect
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
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


@contextmanager
def suppress_audit_errors(action: str) -> Iterator[None]:
    """Log and swallow errors raised while auditing.

    A failure to audit must not fail the request being audited.

    Args:
        action: Action being audited, for the log line.

    Yields:
        None.
    """
    try:
        yield
    except Exception as e:
        logger.error(f"Failed to record audit log for {action}: {e}", exc_info=True)


async def record_audit(
    request: Request,
    *,
    action: str,
    tenant_id: UUID,
    actor_id: UUID | None = None,
    actor_email: str | None = None,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    resource_name: str | None = None,
    status_code: int = 200,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record an audit log entry for a request through `app.state.audit_repo`.

    Fills in the caller's IP, user agent, method and path from the request.
    Never raises.

    Args:
        request: FastAPI request object.
        action: Action identifier (e.g., "auth.login").
        tenant_id: Tenant the entry belongs to.
        actor_id: User who acted, if known.
        actor_email: Email of the user who acted.
        resource_type: Type of resource acted on.
        resource_id: ID of resource acted on.
        resource_name: Name of resource acted on.
        status_code: HTTP status code of the response.
        metadata: Extra details for the entry.
    """
    with suppress_audit_errors(action):
        audit_repo = getattr(request.app.state, "audit_repo", None)
        if audit_repo is None:
            logger.warning("Audit repository not configured, skipping audit log")
            return

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
            status_code=status_code,
            metadata=metadata,
        )
        await audit_repo.record(entry)
        logger.debug(f"Recorded audit log: {action}", resource_id=str(resource_id))


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

            with suppress_audit_errors(action):
                await _record_audit(
                    request=request,
                    action=action,
                    resource_type=resource_type,
                    result=result,
                    kwargs=dict(kwargs),
                )

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
    """Record the audit log entry for a decorated handler's result.

    Args:
        request: FastAPI request object.
        action: Action identifier.
        resource_type: Type of resource.
        result: Handler result.
        kwargs: Handler kwargs.
    """
    actor = _resolve_actor(request)
    if actor is None:
        logger.warning(f"No authenticated caller for {action}, skipping audit log")
        return

    tenant_id, actor_id = actor
    resource_id, resource_name = _extract_resource_info(result, kwargs)

    # actor_email is not available in either auth context
    await record_audit(
        request,
        action=action,
        tenant_id=tenant_id,
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
    )
