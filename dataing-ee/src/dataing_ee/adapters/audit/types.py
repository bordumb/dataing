"""Audit log types."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogCreate(BaseModel):
    """Request to create an audit log entry."""

    model_config = ConfigDict(frozen=True)

    tenant_id: UUID
    actor_id: UUID | None = None
    actor_email: str | None = None
    actor_ip: str | None = None
    actor_user_agent: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: UUID | None = None
    resource_name: str | None = None
    request_method: str | None = None
    request_path: str | None = None
    status_code: int | None = None
    changes: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class AuditLogEntry(BaseModel):
    """Audit log entry from database."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    timestamp: datetime
    tenant_id: UUID
    actor_id: UUID | None = None
    actor_email: str | None = None
    actor_ip: str | None = None
    actor_user_agent: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: UUID | None = None
    resource_name: str | None = None
    request_method: str | None = None
    request_path: str | None = None
    status_code: int | None = None
    changes: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
