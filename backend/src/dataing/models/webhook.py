"""Webhook configuration model."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from dataing.models.base import BaseModel


class Webhook(BaseModel):
    """Webhook configuration for notifications."""

    __tablename__ = "webhooks"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    url = Column(String, nullable=False)
    secret = Column(String(100), nullable=True)
    events = Column(JSONB, default=lambda: ["investigation.completed"])
    is_active = Column(Boolean, default=True)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    last_status = Column(Integer, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="webhooks")
