"""Issue persistence models."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dataing.models.base import BaseModel

if TYPE_CHECKING:
    from dataing.models.investigation import Investigation
    from dataing.models.tenant import Tenant
    from dataing.models.user import User


class IssueStatus(str, enum.Enum):
    """Issue lifecycle status."""

    OPEN = "open"
    TRIAGED = "triaged"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IssuePriority(str, enum.Enum):
    """Issue priority levels."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class IssueSeverity(str, enum.Enum):
    """Issue severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IssueAuthorType(str, enum.Enum):
    """Issue author type."""

    HUMAN = "human"
    INTEGRATION = "integration"


class Issue(BaseModel):
    """Issue model for intake, triage, and collaboration."""

    __tablename__ = "issues"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default=IssueStatus.OPEN.value)
    priority: Mapped[str | None] = mapped_column(String(10), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(nullable=True)
    dataset_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Assignment
    assignee_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    acknowledged_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    # Source/integration metadata
    author_type: Mapped[str] = mapped_column(
        String(20), default=IssueAuthorType.HUMAN.value
    )
    source_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_external_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)

    # SLA and resolution
    sla_policy_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("sla_policies.id"), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Full-text search vector (generated column in Postgres)
    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR, nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="issues")
    assignee: Mapped["User | None"] = relationship(
        "User", foreign_keys=[assignee_user_id], back_populates="assigned_issues"
    )
    acknowledged_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[acknowledged_by]
    )
    created_by_user: Mapped["User | None"] = relationship(
        "User", foreign_keys=[created_by_user_id], back_populates="created_issues"
    )
    comments: Mapped[list["IssueComment"]] = relationship(
        "IssueComment", back_populates="issue", cascade="all, delete-orphan"
    )
    events: Mapped[list["IssueEvent"]] = relationship(
        "IssueEvent", back_populates="issue", cascade="all, delete-orphan"
    )
    watchers: Mapped[list["IssueWatcher"]] = relationship(
        "IssueWatcher", back_populates="issue", cascade="all, delete-orphan"
    )
    investigation_runs: Mapped[list["IssueInvestigationRun"]] = relationship(
        "IssueInvestigationRun", back_populates="issue", cascade="all, delete-orphan"
    )
    sla_policy: Mapped["SLAPolicy | None"] = relationship("SLAPolicy", back_populates="issues")


class IssueComment(BaseModel):
    """Comment on an issue."""

    __tablename__ = "issue_comments"

    issue_id: Mapped[UUID] = mapped_column(ForeignKey("issues.id"), nullable=False)
    author_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="comments")
    author: Mapped["User"] = relationship("User")


class IssueEventType(str, enum.Enum):
    """Types of issue events."""

    CREATED = "created"
    STATUS_CHANGED = "status_changed"
    ASSIGNED = "assigned"
    ACKNOWLEDGED = "acknowledged"
    COMMENT_ADDED = "comment_added"
    LABEL_ADDED = "label_added"
    LABEL_REMOVED = "label_removed"
    PRIORITY_CHANGED = "priority_changed"
    SEVERITY_CHANGED = "severity_changed"
    RELATIONSHIP_ADDED = "relationship_added"
    INVESTIGATION_SPAWNED = "investigation_spawned"
    INVESTIGATION_COMPLETED = "investigation_completed"
    SLA_BREACH = "sla_breach"
    MERGED = "merged"
    REOPENED = "reopened"


class IssueEvent(BaseModel):
    """Immutable event in issue timeline."""

    __tablename__ = "issue_events"

    issue_id: Mapped[UUID] = mapped_column(ForeignKey("issues.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="events")
    actor: Mapped["User | None"] = relationship("User")


class IssueRelationshipType(str, enum.Enum):
    """Types of relationships between issues."""

    DUPLICATES = "duplicates"
    BLOCKS = "blocks"
    RELATES_TO = "relates_to"


class IssueRelationship(BaseModel):
    """Relationship between two issues."""

    __tablename__ = "issue_relationships"

    from_issue_id: Mapped[UUID] = mapped_column(ForeignKey("issues.id"), nullable=False)
    to_issue_id: Mapped[UUID] = mapped_column(ForeignKey("issues.id"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # Relationships
    from_issue: Mapped["Issue"] = relationship("Issue", foreign_keys=[from_issue_id])
    to_issue: Mapped["Issue"] = relationship("Issue", foreign_keys=[to_issue_id])


class IssueWatcher(BaseModel):
    """User watching an issue for updates."""

    __tablename__ = "issue_watchers"

    # Override id since this table uses composite PK
    id: Mapped[UUID] = mapped_column(primary_key=False, default=None, nullable=True)
    issue_id: Mapped[UUID] = mapped_column(
        ForeignKey("issues.id"), primary_key=True, nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id"), primary_key=True, nullable=False
    )

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="watchers")
    user: Mapped["User"] = relationship("User")


class IssueTriggerType(str, enum.Enum):
    """How an investigation was triggered from an issue."""

    HUMAN = "human"
    RULE = "rule"
    WEBHOOK = "webhook"


class IssueExecutionProfile(str, enum.Enum):
    """Execution profile for investigation runs."""

    SAFE = "safe"
    STANDARD = "standard"
    DEEP = "deep"


class IssueApprovalStatus(str, enum.Enum):
    """Approval status for investigation runs."""

    QUEUED = "queued"
    APPROVED = "approved"
    REJECTED = "rejected"


class IssueInvestigationRun(BaseModel):
    """Link between an issue and an investigation run."""

    __tablename__ = "issue_investigation_runs"

    issue_id: Mapped[UUID] = mapped_column(ForeignKey("issues.id"), nullable=False)
    investigation_id: Mapped[UUID] = mapped_column(
        ForeignKey("investigations.id"), nullable=False
    )
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    focus_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_profile: Mapped[str] = mapped_column(
        String(20), default=IssueExecutionProfile.STANDARD.value
    )
    approval_status: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Structured result fields (populated on completion)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    root_cause_tag: Mapped[str | None] = mapped_column(Text, nullable=True)
    synthesis_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="investigation_runs")
    investigation: Mapped["Investigation"] = relationship("Investigation")


# Label is handled as a simple join table, not a full model
# since it uses composite PK without an id column


class SLAType(str, enum.Enum):
    """Types of SLA timers."""

    ACKNOWLEDGE = "acknowledge"  # OPEN -> TRIAGED
    PROGRESS = "progress"  # TRIAGED -> IN_PROGRESS
    RESOLVE = "resolve"  # any -> RESOLVED


class SLAPolicy(BaseModel):
    """SLA policy defining time limits for issue resolution."""

    __tablename__ = "sla_policies"

    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    # Time limits in minutes (null = not tracked)
    time_to_acknowledge: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_to_progress: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_to_resolve: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Per severity overrides (e.g., {"critical": {"time_to_acknowledge": 15}})
    severity_overrides: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant")
    issues: Mapped[list["Issue"]] = relationship("Issue", back_populates="sla_policy")


class SLABreachNotification(BaseModel):
    """Tracks when SLA breach notifications were sent to avoid duplicates."""

    __tablename__ = "sla_breach_notifications"

    issue_id: Mapped[UUID] = mapped_column(ForeignKey("issues.id"), nullable=False)
    sla_type: Mapped[str] = mapped_column(String(20), nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)  # 50, 75, 90, 100
    notified_at: Mapped[datetime] = mapped_column(nullable=False)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue")
