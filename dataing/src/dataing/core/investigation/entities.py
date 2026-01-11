"""Domain entities for the investigation system.

These are the core aggregates and entities that model the investigation domain.
All entities are immutable Pydantic models.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from dataing.core.domain_types import AnomalyAlert

from .values import BranchStatus, BranchType, StepType, VersionId


class InvestigationContext(BaseModel):
    """The accumulated knowledge of an investigation.

    This is the "brain" that persists across restarts.
    Designed for serialization to JSONB.
    """

    model_config = ConfigDict(frozen=True)

    # Summary of the triggering alert
    alert_summary: str

    # Gathered context
    schema_info: dict[str, Any] | None = None
    lineage_info: dict[str, Any] | None = None
    recent_changes: list[dict[str, Any]] = Field(default_factory=list)
    matched_patterns: list[dict[str, Any]] = Field(default_factory=list)

    # Hypotheses and evidence
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)

    # Current query being executed
    current_query: str | None = None

    # Synthesis
    current_synthesis: dict[str, Any] | None = None
    counter_analysis: dict[str, Any] | None = None

    # User interaction
    chat_history: list[dict[str, Any]] = Field(default_factory=list)
    pending_approval: dict[str, Any] | None = None

    # Execution metadata
    total_tokens_used: int = 0
    total_queries_executed: int = 0
    execution_time_ms: int = 0


class Investigation(BaseModel):
    """Root aggregate for an investigation.

    An investigation is a collection of branches exploring an anomaly.
    The "main" branch is the primary investigation path.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID
    alert: AnomalyAlert
    main_branch_id: UUID | None = None
    outcome: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: UUID | None = None

    @property
    def is_active(self) -> bool:
        """Return True if investigation is still active (no outcome yet)."""
        return self.outcome is None


class Branch(BaseModel):
    """A line of investigation exploration.

    Branches enable:
    - Parallel hypothesis testing
    - User-specific refinement paths
    - Counter-analysis without polluting main findings
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    branch_type: BranchType
    name: str

    # Lineage
    parent_branch_id: UUID | None = None
    forked_from_snapshot_id: UUID | None = None

    # Ownership (for user branches)
    owner_user_id: UUID | None = None

    # Current state
    head_snapshot_id: UUID | None = None
    status: BranchStatus = BranchStatus.ACTIVE

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def can_accept_input(self) -> bool:
        """Return True if branch can accept user input."""
        return self.status in (BranchStatus.SUSPENDED, BranchStatus.COMPLETED)


class Snapshot(BaseModel):
    """Immutable point-in-time state of an investigation branch.

    Every action creates a new snapshot. Snapshots are never modified.
    This enables: undo, branching, auditing, and collaboration.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    investigation_id: UUID
    branch_id: UUID
    version: VersionId = Field(default_factory=VersionId)
    parent_snapshot_id: UUID | None = None

    # Current position in workflow
    step: StepType
    step_cursor: dict[str, Any] = Field(default_factory=dict)

    # Accumulated context (grows with each step)
    context: InvestigationContext

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: UUID | None = None
    trigger: str = "system"

    @property
    def is_terminal(self) -> bool:
        """Return True if this snapshot is in a terminal state."""
        return self.step in (StepType.COMPLETE, StepType.FAIL)
