"""Investigation persistence model."""
import enum

from sqlalchemy import Column, DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from dataing.models.base import BaseModel


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

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    data_source_id = Column(UUID(as_uuid=True), ForeignKey("data_sources.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Alert data (immutable)
    dataset_id = Column(String(255), nullable=False)
    metric_name = Column(String(100), nullable=False)
    expected_value = Column(Float, nullable=True)
    actual_value = Column(Float, nullable=True)
    deviation_pct = Column(Float, nullable=True)
    anomaly_date = Column(String(20), nullable=True)
    severity = Column(String(20), nullable=True)
    extra_metadata = Column("metadata", JSONB, default=dict)

    # State
    status = Column(String(50), default=InvestigationStatus.PENDING.value)
    events = Column(JSONB, default=list)  # Event-sourced state

    # Results
    finding = Column(JSONB, nullable=True)  # Serialized Finding

    # Timestamps
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="investigations")
    data_source = relationship("DataSource", back_populates="investigations")
    created_by_user = relationship("User", back_populates="investigations")
