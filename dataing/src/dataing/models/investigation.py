"""Investigation persistence model."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel

if TYPE_CHECKING:
    from dataing.models.data_source import DataSource
    from dataing.models.tenant import Tenant
    from dataing.models.user import User


class InvestigationStatus(str, enum.Enum):
    """Investigation status."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class Investigation(BaseModel):
    """Persisted investigation state."""

    __tablename__ = "investigations"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    data_source_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("data_sources.id"), nullable=True
    )
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Alert data (immutable)
    dataset_id: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    expected_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    deviation_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    anomaly_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    # State
    status: Mapped[str] = mapped_column(String(50), default=InvestigationStatus.PENDING.value)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)  # Event-sourced state

    # Results
    finding: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )  # Serialized Finding

    # Timestamps
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="investigations")
    data_source: Mapped["DataSource | None"] = relationship(
        "DataSource", back_populates="investigations"
    )
    created_by_user: Mapped["User | None"] = relationship("User", back_populates="investigations")
