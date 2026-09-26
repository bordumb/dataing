"""Audit logging adapters - Enterprise Edition.

Route handlers use the CE `dataing.adapters.audit.audited` decorator. EE
persists what it records by installing this AuditRepository as
`app.state.audit_repo`.
"""

from dataing_ee.adapters.audit.repository import AuditRepository
from dataing_ee.adapters.audit.types import AuditLogEntry

__all__ = [
    "AuditLogEntry",
    "AuditRepository",
]
