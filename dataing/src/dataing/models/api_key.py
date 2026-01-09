"""API Key model for authentication."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel

if TYPE_CHECKING:
    from dataing.models.tenant import Tenant
    from dataing.models.user import User


class ApiKey(BaseModel):
    """API key for programmatic access."""

    __tablename__ = "api_keys"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    key_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, unique=True
    )  # SHA-256 hash
    key_prefix: Mapped[str] = mapped_column(String(8), nullable=False)  # First 8 chars for display
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        JSONB, default=lambda: ["read", "write"]
    )  # JSON array
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="api_keys")
    user: Mapped["User | None"] = relationship("User", back_populates="api_keys")
