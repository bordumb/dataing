"""Immutable audit log for compliance."""
from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

from dataing.models.base import BaseModel


class AuditLog(BaseModel):
    """Immutable audit log entry."""

    __tablename__ = "audit_logs"

    # Who
    tenant_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=True)  # Null for system actions
    api_key_id = Column(UUID(as_uuid=True), nullable=True)

    # What
    action = Column(String(50), nullable=False)  # "investigation.created"
    resource_type = Column(String(50), nullable=True)  # "investigation"
    resource_id = Column(String(100), nullable=True)

    # Details
    request_id = Column(String(36), nullable=True)  # Correlation ID
    ip_address = Column(INET, nullable=True)
    user_agent = Column(String(500), nullable=True)
    request_body = Column(JSONB, nullable=True)  # Sanitized request
    response_status = Column(Integer, nullable=True)

    # When
    timestamp = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
