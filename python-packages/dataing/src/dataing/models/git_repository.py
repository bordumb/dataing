"""Git repository connection model."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ARRAY, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel

if TYPE_CHECKING:
    from dataing.models.code_change import CodeChange
    from dataing.models.tenant import Tenant


class GitRepository(BaseModel):
    """A connected git repository for pipeline change detection."""

    __tablename__ = "git_repositories"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    tracked_paths: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    default_branch: Mapped[str] = mapped_column(Text, default="main")
    last_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="pending")
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    code_changes: Mapped[list["CodeChange"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
