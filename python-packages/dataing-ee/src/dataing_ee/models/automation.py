"""Automation rules models."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel


class RuleExecutionStatus:
    """Execution status constants."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class TriggerEvent:
    """Trigger event constants."""

    ISSUE_CREATED = "issue_created"
    ISSUE_UPDATED = "issue_updated"
    ISSUE_STATUS_CHANGED = "issue_status_changed"
    ISSUE_PRIORITY_CHANGED = "issue_priority_changed"
    ISSUE_ASSIGNED = "issue_assigned"


class ConditionOperator:
    """Condition operator constants."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"


class ActionType:
    """Action type constants."""

    SPAWN_INVESTIGATION = "spawn_investigation"
    SET_PRIORITY = "set_priority"
    SET_SEVERITY = "set_severity"
    SET_STATUS = "set_status"
    ADD_LABEL = "add_label"
    REMOVE_LABEL = "remove_label"
    ASSIGN_TO = "assign_to"
    NOTIFY = "notify"
    ADD_COMMENT = "add_comment"


class AutomationRule(BaseModel):
    """Automation rule configuration."""

    __tablename__ = "automation_rules"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Rule definition (JSON DSL)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)

    # Rate limiting
    rate_limit_per_hour: Mapped[int] = mapped_column(Integer, default=100)
    rate_limit_window_start: Mapped[datetime | None] = mapped_column(nullable=True)
    rate_limit_count: Mapped[int] = mapped_column(Integer, default=0)

    # Circuit breaker
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    circuit_breaker_tripped: Mapped[bool] = mapped_column(Boolean, default=False)
    circuit_breaker_tripped_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Statistics
    total_executions: Mapped[int] = mapped_column(Integer, default=0)
    successful_executions: Mapped[int] = mapped_column(Integer, default=0)
    failed_executions: Mapped[int] = mapped_column(Integer, default=0)
    last_executed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Creator
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Relationships
    executions: Mapped[list["RuleExecution"]] = relationship(
        "RuleExecution", back_populates="rule", cascade="all, delete-orphan"
    )


class RuleExecution(BaseModel):
    """Audit log for rule executions."""

    __tablename__ = "rule_executions"

    rule_id: Mapped[UUID] = mapped_column(ForeignKey("automation_rules.id"), nullable=False)
    issue_id: Mapped[UUID] = mapped_column(ForeignKey("issues.id"), nullable=False)

    # Execution context
    trigger_event: Mapped[str] = mapped_column(String(50), nullable=False)
    matched_conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Results
    status: Mapped[str] = mapped_column(String(20), default=RuleExecutionStatus.PENDING)
    actions_executed: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timing
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    rule: Mapped["AutomationRule"] = relationship("AutomationRule", back_populates="executions")
