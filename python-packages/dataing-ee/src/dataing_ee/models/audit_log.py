"""Immutable audit log for compliance."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from dataing.models.base import BaseModel


class AuditLog(BaseModel):
    """Immutable audit log entry."""

    __tablename__ = "audit_logs"

    # Who
    tenant_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    user_id: Mapped[UUID | None] = mapped_column(nullable=True)  # Null for system actions
    api_key_id: Mapped[UUID | None] = mapped_column(nullable=True)

    # What
    action: Mapped[str] = mapped_column(String(50), nullable=False)  # "investigation.created"
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "investigation"
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Details
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # Correlation ID
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    request_body: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # Sanitized request
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # When
    timestamp: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), index=True
    )
