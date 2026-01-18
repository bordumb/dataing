"""User datasource credentials and query audit log models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ARRAY, ForeignKey, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel

if TYPE_CHECKING:
    from dataing.models.data_source import DataSource
    from dataing.models.user import User


class UserDatasourceCredentials(BaseModel):
    """User-specific credentials for a datasource.

    Each user stores their own database credentials. The warehouse
    enforces permissions, not Dataing.
    """

    __tablename__ = "user_datasource_credentials"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    datasource_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_sources.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Encrypted credential blob (JSON with username, password, role, etc.)
    credentials_encrypted: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
    )

    # Metadata (not sensitive, for display only)
    db_username: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Last used timestamp
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="datasource_credentials")
    datasource: Mapped[DataSource] = relationship(
        "DataSource", back_populates="user_credentials"
    )


class QueryAuditLog(BaseModel):
    """Audit log for query execution.

    Every query is logged with who/what/when for compliance and debugging.
    """

    __tablename__ = "query_audit_log"

    # Who
    tenant_id: Mapped[UUID] = mapped_column(nullable=False)
    user_id: Mapped[UUID] = mapped_column(nullable=False)

    # What
    datasource_id: Mapped[UUID] = mapped_column(nullable=False)
    sql_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sql_text: Mapped[str | None] = mapped_column(nullable=True)
    tables_accessed: Mapped[list[str] | None] = mapped_column(
        ARRAY(String),
        nullable=True,
    )

    # When
    executed_at: Mapped[datetime] = mapped_column(nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)

    # Result
    row_count: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(nullable=True)

    # Context
    investigation_id: Mapped[UUID | None] = mapped_column(nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
