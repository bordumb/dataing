"""Audit logging for route handlers.

`audited` records entries through `app.state.audit_repo`. Community Edition
installs the no-op `AuditRepository` below; Enterprise Edition swaps in a
repository that persists entries to the audit_logs table.
"""

from typing import Any

from dataing.adapters.audit.decorator import audited, get_client_ip
from dataing.adapters.audit.types import AuditLogCreate


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

    async def record(self, entry: AuditLogCreate) -> None:
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


__all__ = ["AuditLogCreate", "AuditRepository", "audited", "get_client_ip"]
