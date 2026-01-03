"""API Key model for authentication."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from dataing.models.base import BaseModel


class ApiKey(BaseModel):
    """API key for programmatic access."""

    __tablename__ = "api_keys"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    key_hash = Column(String(64), nullable=False, index=True, unique=True)  # SHA-256 hash
    key_prefix = Column(String(8), nullable=False)  # First 8 chars for display
    name = Column(String(100), nullable=False)
    scopes = Column(JSONB, default=lambda: ["read", "write"])  # JSON array
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="api_keys")
    user = relationship("User", back_populates="api_keys")
