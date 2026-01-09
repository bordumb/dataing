"""Audit logging stubs for Community Edition.

The full audit logging implementation is available in Enterprise Edition.
These stubs provide no-op implementations to maintain API compatibility.
"""

from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def audited(
    action: str,
    resource_type: str | None = None,
) -> Callable[[F], F]:
    """No-op audit decorator for Community Edition.

    In CE, this decorator simply passes through without recording audit logs.
    The full audit logging implementation is available in Enterprise Edition.

    Args:
        action: Action identifier (ignored in CE).
        resource_type: Type of resource (ignored in CE).

    Returns:
        The original function unchanged.
    """
    del action, resource_type  # Unused in CE

    def decorator(func: F) -> F:
        """Return function unchanged."""
        return func

    return decorator


class AuditRepository:
    """Stub audit repository for Community Edition.

    This is a no-op implementation. The full audit logging
    implementation is available in Enterprise Edition.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize stub repository.

        Args:
            **kwargs: Ignored arguments for API compatibility with EE.
        """
        pass

    async def record(self, entry: Any) -> None:
        """No-op record method.

        Args:
            entry: Audit log entry (ignored in CE).
        """
        pass

    async def list_logs(self, *args: Any, **kwargs: Any) -> list[Any]:
        """No-op list method.

        Returns:
            Empty list.
        """
        return []


__all__ = ["audited", "AuditRepository"]
