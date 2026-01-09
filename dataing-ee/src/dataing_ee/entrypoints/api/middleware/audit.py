"""Audit logging middleware."""

import asyncio
import json
import uuid
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = structlog.get_logger()

# Fields to redact from request bodies
SENSITIVE_FIELDS = {"password", "api_key", "secret", "token", "credential", "key"}


class AuditMiddleware(BaseHTTPMiddleware):
    """Log all API requests for audit trail."""

    def __init__(self, app: ASGIApp, enabled: bool = True) -> None:
        """Initialize audit middleware.

        Args:
            app: The ASGI application.
            enabled: Whether audit logging is enabled.
        """
        super().__init__(app)
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request and log audit entry."""
        # Generate request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Skip audit for health checks and OPTIONS
        if request.url.path in ["/health", "/healthz", "/ready"] or request.method == "OPTIONS":
            return await call_next(request)

        if not self.enabled:
            return await call_next(request)

        # Capture request body for POST/PUT/PATCH
        body = None
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                # Reset the body stream for downstream handlers
                request._body = body
            except Exception:
                pass

        # Process the request
        response = await call_next(request)

        # Log asynchronously (fire and forget)
        asyncio.create_task(
            self._log_request(
                request=request,
                request_id=request_id,
                body=body,
                status_code=response.status_code,
            )
        )

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response

    async def _log_request(
        self,
        request: Request,
        request_id: str,
        body: bytes | None,
        status_code: int,
    ) -> None:
        """Log the request to audit log."""
        try:
            # Get auth context if available
            auth_context = getattr(request.state, "auth_context", None)

            tenant_id = None
            actor_id = None

            if auth_context:
                tenant_id = auth_context.tenant_id
                actor_id = auth_context.user_id

            # Determine action from method and path
            action = self._get_action(request.method, request.url.path)

            # Get resource info from path
            resource_type, resource_id_str = self._parse_resource(request.url.path)

            # Try to parse resource_id as UUID
            resource_id = None
            if resource_id_str:
                try:
                    resource_id = uuid.UUID(resource_id_str)
                except ValueError:
                    pass  # Not a valid UUID, leave as None

            # Get client info
            actor_ip = request.client.host if request.client else None
            actor_user_agent = request.headers.get("user-agent", "")[:500]

            # Get request details
            request_method = request.method
            request_path = str(request.url.path)

            # Sanitize body
            sanitized_body = self._sanitize_body(body)

            # Get database from app state
            db = getattr(request.app.state, "app_db", None)

            if db and tenant_id:
                await db.create_audit_log(
                    tenant_id=tenant_id,
                    action=action,
                    actor_id=actor_id,
                    actor_ip=actor_ip,
                    actor_user_agent=actor_user_agent,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    request_method=request_method,
                    request_path=request_path,
                    status_code=status_code,
                    changes=sanitized_body,
                    metadata={"request_id": request_id},
                )
            else:
                # Just log to structlog if no DB or no tenant
                logger.info(
                    "audit_log",
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id_str,
                    request_id=request_id,
                    status_code=status_code,
                    ip=actor_ip,
                )

        except Exception as e:
            logger.error("audit_log_failed", error=str(e))

    def _get_action(self, method: str, path: str) -> str:
        """Determine action from HTTP method and path."""
        # Extract resource from path
        parts = [p for p in path.split("/") if p and p != "api" and p != "v1"]

        if not parts:
            return f"{method.lower()}.root"

        resource = parts[0]

        method_actions = {
            "GET": "read",
            "POST": "created",
            "PUT": "updated",
            "PATCH": "updated",
            "DELETE": "deleted",
        }

        action = method_actions.get(method, method.lower())

        return f"{resource}.{action}"

    def _parse_resource(self, path: str) -> tuple[str | None, str | None]:
        """Parse resource type and ID from path."""
        parts = [p for p in path.split("/") if p and p != "api" and p != "v1"]

        if not parts:
            return None, None

        resource_type = parts[0]
        resource_id = parts[1] if len(parts) > 1 else None

        return resource_type, resource_id

    def _sanitize_body(self, body: bytes | None) -> dict[str, Any] | None:
        """Remove sensitive fields from request body."""
        if not body:
            return None

        try:
            data = json.loads(body.decode())

            if isinstance(data, dict):
                return self._redact_dict(data)

            return None

        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _redact_dict(self, data: dict[str, Any], depth: int = 0) -> dict[str, Any]:
        """Recursively redact sensitive fields."""
        if depth > 5:  # Prevent infinite recursion
            return {"_redacted": True}

        result: dict[str, Any] = {}
        for key, value in data.items():
            key_lower = key.lower()

            if any(field in key_lower for field in SENSITIVE_FIELDS):
                result[key] = "[REDACTED]"
            elif isinstance(value, dict):
                result[key] = self._redact_dict(value, depth + 1)
            elif isinstance(value, list):
                result[key] = [
                    self._redact_dict(item, depth + 1) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                result[key] = value

        return result
