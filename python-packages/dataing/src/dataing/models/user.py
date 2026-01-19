"""User model."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel

if TYPE_CHECKING:
    from dataing.models.api_key import ApiKey
    from dataing.models.credentials import UserDatasourceCredentials
    from dataing.models.investigation import Investigation
    from dataing.models.issue import Issue
    from dataing.models.notification import NotificationRead
    from dataing.models.tenant import Tenant


class User(BaseModel):
    """A user in the system."""

    __tablename__ = "users"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(50), default="member")  # admin, member, viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="users")
    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey", back_populates="user", cascade="all, delete-orphan"
    )
    investigations: Mapped[list["Investigation"]] = relationship(
        "Investigation", back_populates="created_by_user"
    )
    notification_reads: Mapped[list["NotificationRead"]] = relationship(
        "NotificationRead", back_populates="user", cascade="all, delete-orphan"
    )
    assigned_issues: Mapped[list["Issue"]] = relationship(
        "Issue", foreign_keys="Issue.assignee_user_id", back_populates="assignee"
    )
    created_issues: Mapped[list["Issue"]] = relationship(
        "Issue", foreign_keys="Issue.created_by_user_id", back_populates="created_by_user"
    )
    datasource_credentials: Mapped[list["UserDatasourceCredentials"]] = relationship(
        "UserDatasourceCredentials", back_populates="user", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # Unique constraint on tenant_id + email
        {"sqlite_autoincrement": True},
    )
