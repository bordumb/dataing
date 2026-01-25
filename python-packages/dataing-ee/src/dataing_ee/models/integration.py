"""Integration models for external webhook providers."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel


class IntegrationProvider:
    """Known integration providers."""

    JIRA = "jira"
    LINEAR = "linear"
    PAGERDUTY = "pagerduty"
    OPSGENIE = "opsgenie"
    MONTE_CARLO = "monte_carlo"
    GREAT_EXPECTATIONS = "great_expectations"
    SODA = "soda"
    DBT = "dbt"
    SLACK = "slack"
    CUSTOM = "custom"

    @classmethod
    def all(cls) -> list[str]:
        """Get all provider names."""
        return [
            cls.JIRA,
            cls.LINEAR,
            cls.PAGERDUTY,
            cls.OPSGENIE,
            cls.MONTE_CARLO,
            cls.GREAT_EXPECTATIONS,
            cls.SODA,
            cls.DBT,
            cls.SLACK,
            cls.CUSTOM,
        ]


class IntegrationEventStatus:
    """Processing status for integration events."""

    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
    SKIPPED = "skipped"


class Integration(BaseModel):
    """External integration configuration."""

    __tablename__ = "integrations"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Provider-specific configuration (encrypted in storage)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Signing secret for webhook verification
    signing_secret: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Rate limiting
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=60)

    # Statistics
    last_webhook_at: Mapped[datetime | None] = mapped_column(nullable=True)
    webhook_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    events: Mapped[list["IntegrationEvent"]] = relationship(
        "IntegrationEvent", back_populates="integration", cascade="all, delete-orphan"
    )
    field_mappings: Mapped[list["IntegrationFieldMapping"]] = relationship(
        "IntegrationFieldMapping",
        back_populates="integration",
        cascade="all, delete-orphan",
    )


class IntegrationEvent(BaseModel):
    """Webhook event received from integration for idempotency tracking."""

    __tablename__ = "integration_events"

    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Processing status
    status: Mapped[str] = mapped_column(String(20), default=IntegrationEventStatus.PENDING)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Result
    issue_id: Mapped[UUID | None] = mapped_column(ForeignKey("issues.id"), nullable=True)

    # Timestamps
    received_at: Mapped[datetime] = mapped_column(nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    integration: Mapped["Integration"] = relationship("Integration", back_populates="events")


class IntegrationFieldMapping(BaseModel):
    """Custom field mapping for provider payloads."""

    __tablename__ = "integration_field_mappings"

    integration_id: Mapped[UUID] = mapped_column(ForeignKey("integrations.id"), nullable=False)
    source_field: Mapped[str] = mapped_column(Text, nullable=False)
    target_field: Mapped[str] = mapped_column(String(50), nullable=False)
    transform: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    integration: Mapped["Integration"] = relationship(
        "Integration", back_populates="field_mappings"
    )
