"""Notification models for in-app notifications."""

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel

if TYPE_CHECKING:
    from dataing.models.tenant import Tenant
    from dataing.models.user import User


class NotificationSeverity(str, Enum):
    """Notification severity levels."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class Notification(BaseModel):
    """In-app notification broadcast to tenant users."""

    __tablename__ = "notifications"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    resource_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")

    # Override updated_at from BaseModel - notifications are immutable
    updated_at: Mapped[datetime | None] = mapped_column(default=None)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="notifications")
    reads: Mapped[list["NotificationRead"]] = relationship(
        "NotificationRead", back_populates="notification", cascade="all, delete-orphan"
    )


class NotificationRead(BaseModel):
    """Per-user read state for notifications."""

    __tablename__ = "notification_reads"

    # Override id from BaseModel - use composite primary key instead
    id: Mapped[UUID] = mapped_column(primary_key=False, default=None)

    notification_id: Mapped[UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    read_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    # Override timestamps from BaseModel - not needed for this join table
    created_at: Mapped[datetime | None] = mapped_column(default=None)
    updated_at: Mapped[datetime | None] = mapped_column(default=None)

    # Relationships
    notification: Mapped["Notification"] = relationship("Notification", back_populates="reads")
    user: Mapped["User"] = relationship("User", back_populates="notification_reads")
