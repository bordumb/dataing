# Unified Investigation Architecture Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the existing event-sourced orchestrator with a branch-based, snapshot-persisted investigation system that supports collaboration, pattern learning, and durable execution.

**Architecture:** Investigations are trees of branches, each branch containing a chain of immutable snapshots. Steps are pure functions returning signals that the orchestrator interprets. User branches enable collaborative exploration without affecting the main investigation.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0, PostgreSQL, Pydantic v2, pytest-asyncio

---

## Phase 1: Foundation (Database & Domain Models)

### Task 1.1: Create Database Migration for Core Tables

**Files:**
- Create: `dataing/migrations/013_unified_investigation.sql`

**Step 1: Write the migration file**

```sql
-- Migration: 013_unified_investigation.sql
-- Unified Investigation Architecture - Core Tables

-- Drop old investigation table if exists (we're replacing it)
-- Note: This is safe because we're pre-launch
DROP TABLE IF EXISTS investigations CASCADE;

-- =============================================================================
-- Core Tables
-- =============================================================================

-- Investigations: Root aggregate
CREATE TABLE investigations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    alert JSONB NOT NULL,
    main_branch_id UUID,  -- Set after first branch created
    outcome JSONB,        -- Final finding when complete
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    -- Denormalized status for fast queries
    status TEXT GENERATED ALWAYS AS (
        CASE
            WHEN outcome IS NOT NULL THEN 'completed'
            ELSE 'active'
        END
    ) STORED
);

CREATE INDEX idx_investigations_tenant ON investigations(tenant_id);
CREATE INDEX idx_investigations_status ON investigations(status);
CREATE INDEX idx_investigations_created ON investigations(created_at DESC);

-- Branches: Lines of exploration
CREATE TABLE investigation_branches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    branch_type TEXT NOT NULL CHECK (branch_type IN ('main', 'hypothesis', 'user', 'counter', 'pattern')),
    name TEXT NOT NULL,

    -- Lineage
    parent_branch_id UUID REFERENCES investigation_branches(id),
    forked_from_snapshot_id UUID,

    -- Ownership (for user branches)
    owner_user_id UUID REFERENCES users(id),

    -- Current state (denormalized for performance)
    head_snapshot_id UUID,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'merged', 'abandoned', 'completed')),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_branches_investigation ON investigation_branches(investigation_id);
CREATE INDEX idx_branches_owner ON investigation_branches(owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX idx_branches_status ON investigation_branches(status);

-- Snapshots: Immutable state records
CREATE TABLE investigation_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,

    -- Version
    version_major INT NOT NULL DEFAULT 0,
    version_minor INT NOT NULL DEFAULT 0,
    version_patch INT NOT NULL DEFAULT 0,

    -- Lineage
    parent_snapshot_id UUID REFERENCES investigation_snapshots(id),

    -- Workflow position
    step TEXT NOT NULL,
    step_cursor JSONB DEFAULT '{}'::jsonb,

    -- The full context (the "brain")
    context JSONB NOT NULL,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    trigger TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX idx_snapshots_branch_head ON investigation_snapshots(branch_id, created_at DESC);
CREATE INDEX idx_snapshots_investigation ON investigation_snapshots(investigation_id, created_at DESC);

-- Add foreign key for head_snapshot_id after snapshots table exists
ALTER TABLE investigation_branches
    ADD CONSTRAINT fk_branches_head_snapshot
    FOREIGN KEY (head_snapshot_id) REFERENCES investigation_snapshots(id);

-- Add foreign key for forked_from_snapshot_id
ALTER TABLE investigation_branches
    ADD CONSTRAINT fk_branches_forked_snapshot
    FOREIGN KEY (forked_from_snapshot_id) REFERENCES investigation_snapshots(id);

-- Add foreign key for main_branch_id
ALTER TABLE investigations
    ADD CONSTRAINT fk_investigations_main_branch
    FOREIGN KEY (main_branch_id) REFERENCES investigation_branches(id);

-- =============================================================================
-- Execution Control Tables
-- =============================================================================

-- Execution locks for durable processing
CREATE TABLE execution_locks (
    branch_id UUID PRIMARY KEY REFERENCES investigation_branches(id) ON DELETE CASCADE,
    locked_by TEXT NOT NULL,      -- Worker instance ID
    locked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- Collaboration Tables
-- =============================================================================

-- Chat messages linked to branches
CREATE TABLE branch_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,

    -- Link to the snapshot that resulted from this message
    resulting_snapshot_id UUID REFERENCES investigation_snapshots(id),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_branch ON branch_messages(branch_id, created_at);

-- Approval requests
CREATE TABLE approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,
    snapshot_id UUID NOT NULL REFERENCES investigation_snapshots(id),

    -- What needs approval
    action_type TEXT NOT NULL,
    action_payload JSONB NOT NULL,
    risk_reason TEXT NOT NULL,

    -- Resolution
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    decided_by UUID REFERENCES users(id),
    decided_at TIMESTAMPTZ,
    decision TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_approvals_branch ON approval_requests(branch_id);
CREATE INDEX idx_approvals_status ON approval_requests(status) WHERE status = 'pending';

-- Merge point tracking
CREATE TABLE branch_merge_points (
    parent_branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,
    child_branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,
    merge_step TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (parent_branch_id, child_branch_id)
);

-- =============================================================================
-- Pattern Learning Tables
-- =============================================================================

-- Known root cause patterns
CREATE TABLE root_cause_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Pattern definition
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    trigger_signals JSONB NOT NULL,
    typical_root_cause TEXT NOT NULL,
    resolution_steps JSONB NOT NULL,

    -- Matching criteria
    affected_datasets JSONB DEFAULT '[]'::jsonb,
    affected_metrics JSONB DEFAULT '[]'::jsonb,
    time_patterns JSONB,

    -- Statistics
    occurrence_count INT DEFAULT 0,
    last_matched_at TIMESTAMPTZ,
    false_positive_count INT DEFAULT 0,
    avg_resolution_time_minutes INT,

    -- Lifecycle
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_from_investigation_id UUID REFERENCES investigations(id)
);

CREATE INDEX idx_patterns_tenant ON root_cause_patterns(tenant_id) WHERE status = 'active';
```

**Step 2: Verify migration syntax**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing && cat migrations/013_unified_investigation.sql | head -50`
Expected: Migration file content displayed

**Step 3: Commit migration**

```bash
git add migrations/013_unified_investigation.sql
git commit -m "feat(db): add unified investigation architecture tables

Tables added:
- investigations (root aggregate)
- investigation_branches (lines of exploration)
- investigation_snapshots (immutable state)
- execution_locks (durable processing)
- branch_messages (collaboration)
- approval_requests (human-in-loop)
- branch_merge_points (parallel execution)
- root_cause_patterns (learning)"
```

---

### Task 1.2: Create Domain Value Objects

**Files:**
- Create: `dataing/src/dataing/core/investigation/values.py`
- Test: `dataing/tests/unit/core/investigation/test_values.py`

**Step 1: Create the test file with directory**

```bash
mkdir -p /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing/tests/unit/core/investigation
touch /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing/tests/unit/core/investigation/__init__.py
```

**Step 2: Write failing tests for value objects**

```python
# tests/unit/core/investigation/test_values.py
"""Tests for investigation value objects."""

import pytest

from dataing.core.investigation.values import (
    BranchStatus,
    BranchType,
    ExecutionSignal,
    StepType,
    VersionId,
)


class TestVersionId:
    """Tests for VersionId value object."""

    def test_default_version(self) -> None:
        """Default version is 0.0.0."""
        v = VersionId()
        assert v.major == 0
        assert v.minor == 0
        assert v.patch == 0

    def test_str_format(self) -> None:
        """Version string format is vX.Y.Z."""
        v = VersionId(major=1, minor=2, patch=3)
        assert str(v) == "v1.2.3"

    def test_next_major(self) -> None:
        """next_major increments major and resets minor/patch."""
        v = VersionId(major=1, minor=2, patch=3)
        next_v = v.next_major()
        assert next_v.major == 2
        assert next_v.minor == 0
        assert next_v.patch == 0

    def test_next_minor(self) -> None:
        """next_minor increments minor, keeps major, resets patch."""
        v = VersionId(major=1, minor=2, patch=3)
        next_v = v.next_minor()
        assert next_v.major == 1
        assert next_v.minor == 3
        assert next_v.patch == 0

    def test_next_patch(self) -> None:
        """next_patch increments patch only."""
        v = VersionId(major=1, minor=2, patch=3)
        next_v = v.next_patch()
        assert next_v.major == 1
        assert next_v.minor == 2
        assert next_v.patch == 4

    def test_immutable(self) -> None:
        """VersionId is immutable (frozen)."""
        v = VersionId()
        with pytest.raises(Exception):  # Pydantic raises ValidationError
            v.major = 1  # type: ignore[misc]


class TestEnums:
    """Tests for enumeration types."""

    def test_branch_type_values(self) -> None:
        """BranchType has expected values."""
        assert BranchType.MAIN == "main"
        assert BranchType.HYPOTHESIS == "hypothesis"
        assert BranchType.USER == "user"
        assert BranchType.COUNTER == "counter"
        assert BranchType.PATTERN == "pattern"

    def test_branch_status_values(self) -> None:
        """BranchStatus has expected values."""
        assert BranchStatus.ACTIVE == "active"
        assert BranchStatus.SUSPENDED == "suspended"
        assert BranchStatus.MERGED == "merged"
        assert BranchStatus.ABANDONED == "abandoned"
        assert BranchStatus.COMPLETED == "completed"

    def test_step_type_values(self) -> None:
        """StepType has all expected step types."""
        # Core investigation
        assert StepType.GATHER_CONTEXT == "gather_context"
        assert StepType.GENERATE_HYPOTHESES == "generate_hypotheses"
        assert StepType.GENERATE_QUERY == "generate_query"
        assert StepType.EXECUTE_QUERY == "execute_query"
        assert StepType.INTERPRET_EVIDENCE == "interpret_evidence"
        assert StepType.SYNTHESIZE == "synthesize"
        # Quality
        assert StepType.COUNTER_ANALYZE == "counter_analyze"
        assert StepType.CHECK_PATTERNS == "check_patterns"
        # User interaction
        assert StepType.AWAIT_USER == "await_user"
        assert StepType.CLASSIFY_INTENT == "classify_intent"
        assert StepType.EXECUTE_REFINEMENT == "execute_refinement"
        # Terminal
        assert StepType.COMPLETE == "complete"
        assert StepType.FAIL == "fail"

    def test_execution_signal_values(self) -> None:
        """ExecutionSignal has expected values."""
        assert ExecutionSignal.CONTINUE == "continue"
        assert ExecutionSignal.REQUIRE_APPROVAL == "require_approval"
        assert ExecutionSignal.AWAIT_USER == "await_user"
        assert ExecutionSignal.BRANCH == "branch"
        assert ExecutionSignal.MERGE == "merge"
        assert ExecutionSignal.COMPLETE == "complete"
        assert ExecutionSignal.FAIL == "fail"
```

**Step 3: Run tests to verify they fail**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing && uv run pytest tests/unit/core/investigation/test_values.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'dataing.core.investigation'"

**Step 4: Create the source directory and value objects**

```bash
mkdir -p /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing/src/dataing/core/investigation
touch /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing/src/dataing/core/investigation/__init__.py
```

```python
# src/dataing/core/investigation/values.py
"""Value objects for the investigation domain.

This module contains immutable value objects and enumerations
that define the vocabulary of the investigation system.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class VersionId(BaseModel):
    """Semantic versioning for investigation snapshots.

    Format: major.minor.patch
    - major: Synthesis iterations (0 = initial, 1 = first synthesis)
    - minor: Hypothesis/evidence additions within a synthesis cycle
    - patch: Refinements/corrections that don't add new evidence
    """

    model_config = ConfigDict(frozen=True)

    major: int = 0
    minor: int = 0
    patch: int = 0

    def __str__(self) -> str:
        """Return version string in vX.Y.Z format."""
        return f"v{self.major}.{self.minor}.{self.patch}"

    def next_major(self) -> VersionId:
        """Return new version with incremented major, reset minor/patch."""
        return VersionId(major=self.major + 1, minor=0, patch=0)

    def next_minor(self) -> VersionId:
        """Return new version with incremented minor, reset patch."""
        return VersionId(major=self.major, minor=self.minor + 1, patch=0)

    def next_patch(self) -> VersionId:
        """Return new version with incremented patch."""
        return VersionId(major=self.major, minor=self.minor, patch=self.patch + 1)


class BranchType(str, Enum):
    """Types of investigation branches."""

    MAIN = "main"
    HYPOTHESIS = "hypothesis"
    USER = "user"
    COUNTER = "counter"
    PATTERN = "pattern"


class BranchStatus(str, Enum):
    """Branch lifecycle states."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    MERGED = "merged"
    ABANDONED = "abandoned"
    COMPLETED = "completed"


class StepType(str, Enum):
    """Atomic operations in the investigation lifecycle."""

    # Core investigation
    GATHER_CONTEXT = "gather_context"
    GENERATE_HYPOTHESES = "generate_hypotheses"
    GENERATE_QUERY = "generate_query"
    EXECUTE_QUERY = "execute_query"
    INTERPRET_EVIDENCE = "interpret_evidence"
    SYNTHESIZE = "synthesize"

    # Quality & validation
    COUNTER_ANALYZE = "counter_analyze"
    CHECK_PATTERNS = "check_patterns"

    # User interaction
    AWAIT_USER = "await_user"
    CLASSIFY_INTENT = "classify_intent"
    EXECUTE_REFINEMENT = "execute_refinement"

    # Terminal
    COMPLETE = "complete"
    FAIL = "fail"


class ExecutionSignal(str, Enum):
    """Signals that control orchestrator flow."""

    CONTINUE = "continue"
    REQUIRE_APPROVAL = "require_approval"
    AWAIT_USER = "await_user"
    BRANCH = "branch"
    MERGE = "merge"
    COMPLETE = "complete"
    FAIL = "fail"
```

**Step 5: Run tests to verify they pass**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing && uv run pytest tests/unit/core/investigation/test_values.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/dataing/core/investigation/ tests/unit/core/investigation/
git commit -m "feat(core): add investigation value objects

- VersionId: Semantic versioning for snapshots
- BranchType: main, hypothesis, user, counter, pattern
- BranchStatus: active, suspended, merged, abandoned, completed
- StepType: All step types in investigation lifecycle
- ExecutionSignal: Orchestrator flow control signals"
```

---

### Task 1.3: Create Domain Entities (Investigation, Branch, Snapshot)

**Files:**
- Create: `dataing/src/dataing/core/investigation/entities.py`
- Test: `dataing/tests/unit/core/investigation/test_entities.py`

**Step 1: Write failing tests**

```python
# tests/unit/core/investigation/test_entities.py
"""Tests for investigation domain entities."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.investigation.entities import (
    Branch,
    Investigation,
    InvestigationContext,
    Snapshot,
)
from dataing.core.investigation.values import (
    BranchStatus,
    BranchType,
    StepType,
    VersionId,
)


@pytest.fixture
def sample_alert() -> AnomalyAlert:
    """Create a sample anomaly alert for testing."""
    return AnomalyAlert(
        dataset_id="analytics.events",
        metric_spec=MetricSpec.from_column("user_id", "NULL rate"),
        anomaly_type="null_rate",
        expected_value=0.01,
        actual_value=0.15,
        deviation_pct=1400.0,
        anomaly_date="2026-01-10",
        severity="high",
    )


@pytest.fixture
def sample_context() -> InvestigationContext:
    """Create a sample investigation context."""
    return InvestigationContext(
        alert_summary="NULL rate anomaly in analytics.events",
        schema_info={"tables": ["events"], "columns": ["user_id", "event_type"]},
    )


class TestInvestigation:
    """Tests for Investigation entity."""

    def test_create_investigation(self, sample_alert: AnomalyAlert) -> None:
        """Can create investigation with alert."""
        tenant_id = uuid4()
        inv = Investigation(
            tenant_id=tenant_id,
            alert=sample_alert,
        )
        assert inv.id is not None
        assert inv.tenant_id == tenant_id
        assert inv.alert == sample_alert
        assert inv.main_branch_id is None
        assert inv.outcome is None

    def test_investigation_is_active_when_no_outcome(
        self, sample_alert: AnomalyAlert
    ) -> None:
        """Investigation is active when outcome is None."""
        inv = Investigation(tenant_id=uuid4(), alert=sample_alert)
        assert inv.is_active is True

    def test_investigation_is_not_active_when_outcome_set(
        self, sample_alert: AnomalyAlert
    ) -> None:
        """Investigation is not active when outcome is set."""
        inv = Investigation(
            tenant_id=uuid4(),
            alert=sample_alert,
            outcome={"root_cause": "ETL failure", "confidence": 0.9},
        )
        assert inv.is_active is False


class TestBranch:
    """Tests for Branch entity."""

    def test_create_main_branch(self) -> None:
        """Can create a main branch."""
        inv_id = uuid4()
        branch = Branch(
            investigation_id=inv_id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        assert branch.id is not None
        assert branch.investigation_id == inv_id
        assert branch.branch_type == BranchType.MAIN
        assert branch.status == BranchStatus.ACTIVE
        assert branch.parent_branch_id is None
        assert branch.owner_user_id is None

    def test_create_user_branch(self) -> None:
        """Can create a user branch with owner."""
        inv_id = uuid4()
        parent_id = uuid4()
        user_id = uuid4()
        branch = Branch(
            investigation_id=inv_id,
            branch_type=BranchType.USER,
            name="alice_exploration",
            parent_branch_id=parent_id,
            owner_user_id=user_id,
        )
        assert branch.branch_type == BranchType.USER
        assert branch.parent_branch_id == parent_id
        assert branch.owner_user_id == user_id

    def test_branch_can_accept_input(self) -> None:
        """Branch can accept input when suspended or completed."""
        branch = Branch(
            investigation_id=uuid4(),
            branch_type=BranchType.USER,
            name="test",
            status=BranchStatus.SUSPENDED,
        )
        assert branch.can_accept_input is True

        branch_completed = Branch(
            investigation_id=uuid4(),
            branch_type=BranchType.USER,
            name="test",
            status=BranchStatus.COMPLETED,
        )
        assert branch_completed.can_accept_input is True

        branch_active = Branch(
            investigation_id=uuid4(),
            branch_type=BranchType.USER,
            name="test",
            status=BranchStatus.ACTIVE,
        )
        assert branch_active.can_accept_input is False


class TestSnapshot:
    """Tests for Snapshot entity."""

    def test_create_snapshot(self, sample_context: InvestigationContext) -> None:
        """Can create a snapshot with context."""
        inv_id = uuid4()
        branch_id = uuid4()
        snapshot = Snapshot(
            investigation_id=inv_id,
            branch_id=branch_id,
            version=VersionId(major=1, minor=0, patch=0),
            step=StepType.GATHER_CONTEXT,
            context=sample_context,
        )
        assert snapshot.id is not None
        assert snapshot.investigation_id == inv_id
        assert snapshot.branch_id == branch_id
        assert snapshot.version.major == 1
        assert snapshot.step == StepType.GATHER_CONTEXT
        assert snapshot.parent_snapshot_id is None
        assert snapshot.trigger == "system"

    def test_snapshot_with_parent(self, sample_context: InvestigationContext) -> None:
        """Snapshot can reference parent snapshot."""
        parent_id = uuid4()
        snapshot = Snapshot(
            investigation_id=uuid4(),
            branch_id=uuid4(),
            version=VersionId(major=1, minor=0, patch=1),
            step=StepType.GENERATE_HYPOTHESES,
            context=sample_context,
            parent_snapshot_id=parent_id,
        )
        assert snapshot.parent_snapshot_id == parent_id

    def test_snapshot_is_terminal(self, sample_context: InvestigationContext) -> None:
        """Snapshot is terminal when step is COMPLETE or FAIL."""
        complete_snapshot = Snapshot(
            investigation_id=uuid4(),
            branch_id=uuid4(),
            version=VersionId(),
            step=StepType.COMPLETE,
            context=sample_context,
        )
        assert complete_snapshot.is_terminal is True

        fail_snapshot = Snapshot(
            investigation_id=uuid4(),
            branch_id=uuid4(),
            version=VersionId(),
            step=StepType.FAIL,
            context=sample_context,
        )
        assert fail_snapshot.is_terminal is True

        active_snapshot = Snapshot(
            investigation_id=uuid4(),
            branch_id=uuid4(),
            version=VersionId(),
            step=StepType.SYNTHESIZE,
            context=sample_context,
        )
        assert active_snapshot.is_terminal is False


class TestInvestigationContext:
    """Tests for InvestigationContext value object."""

    def test_create_minimal_context(self) -> None:
        """Can create context with minimal fields."""
        ctx = InvestigationContext(alert_summary="Test anomaly")
        assert ctx.alert_summary == "Test anomaly"
        assert ctx.schema_info is None
        assert ctx.hypotheses == []
        assert ctx.evidence == []

    def test_context_with_all_fields(self) -> None:
        """Can create context with all fields populated."""
        ctx = InvestigationContext(
            alert_summary="NULL rate spike",
            schema_info={"tables": ["events"]},
            lineage_info={"upstream": ["raw.events"]},
            hypotheses=[{"id": "h1", "title": "ETL bug"}],
            evidence=[{"hypothesis_id": "h1", "supports": True}],
            current_synthesis={"root_cause": "ETL bug", "confidence": 0.85},
            total_tokens_used=1500,
            total_queries_executed=3,
        )
        assert ctx.schema_info == {"tables": ["events"]}
        assert len(ctx.hypotheses) == 1
        assert ctx.total_tokens_used == 1500
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing && uv run pytest tests/unit/core/investigation/test_entities.py -v`
Expected: FAIL with import errors

**Step 3: Implement the entities**

```python
# src/dataing/core/investigation/entities.py
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
```

**Step 4: Update the investigation package init**

```python
# src/dataing/core/investigation/__init__.py
"""Investigation domain module.

This module contains the core domain model for the investigation system,
including entities, value objects, and the step abstraction.
"""

from .entities import Branch, Investigation, InvestigationContext, Snapshot
from .values import (
    BranchStatus,
    BranchType,
    ExecutionSignal,
    StepType,
    VersionId,
)

__all__ = [
    # Entities
    "Investigation",
    "Branch",
    "Snapshot",
    "InvestigationContext",
    # Value Objects
    "VersionId",
    "BranchType",
    "BranchStatus",
    "StepType",
    "ExecutionSignal",
]
```

**Step 5: Run tests to verify they pass**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing && uv run pytest tests/unit/core/investigation/test_entities.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/dataing/core/investigation/ tests/unit/core/investigation/
git commit -m "feat(core): add investigation domain entities

- Investigation: Root aggregate with alert and outcome
- Branch: Lines of exploration (main, hypothesis, user, counter, pattern)
- Snapshot: Immutable point-in-time state
- InvestigationContext: Accumulated knowledge (the 'brain')"
```

---

### Task 1.4: Create Repository Interface and Implementation

**Files:**
- Create: `dataing/src/dataing/core/investigation/repository.py`
- Create: `dataing/src/dataing/adapters/db/investigation_repository.py`
- Test: `dataing/tests/unit/core/investigation/test_repository.py`

**Step 1: Write failing tests**

```python
# tests/unit/core/investigation/test_repository.py
"""Tests for investigation repository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.investigation.entities import (
    Branch,
    Investigation,
    InvestigationContext,
    Snapshot,
)
from dataing.core.investigation.repository import InvestigationRepository
from dataing.core.investigation.values import (
    BranchStatus,
    BranchType,
    StepType,
    VersionId,
)


@pytest.fixture
def sample_alert() -> AnomalyAlert:
    """Create sample alert."""
    return AnomalyAlert(
        dataset_id="analytics.events",
        metric_spec=MetricSpec.from_column("user_id", "NULL rate"),
        anomaly_type="null_rate",
        expected_value=0.01,
        actual_value=0.15,
        deviation_pct=1400.0,
        anomaly_date="2026-01-10",
        severity="high",
    )


@pytest.fixture
def sample_context() -> InvestigationContext:
    """Create sample context."""
    return InvestigationContext(alert_summary="Test anomaly")


class TestInvestigationRepositoryProtocol:
    """Tests that verify the repository protocol shape."""

    def test_repository_has_required_methods(self) -> None:
        """Repository protocol defines required methods."""
        # This test verifies the protocol exists and has expected methods
        assert hasattr(InvestigationRepository, "create_investigation")
        assert hasattr(InvestigationRepository, "get_investigation")
        assert hasattr(InvestigationRepository, "create_branch")
        assert hasattr(InvestigationRepository, "get_branch")
        assert hasattr(InvestigationRepository, "update_branch_status")
        assert hasattr(InvestigationRepository, "update_branch_head")
        assert hasattr(InvestigationRepository, "create_snapshot")
        assert hasattr(InvestigationRepository, "get_snapshot")
        assert hasattr(InvestigationRepository, "acquire_lock")
        assert hasattr(InvestigationRepository, "release_lock")
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing && uv run pytest tests/unit/core/investigation/test_repository.py -v`
Expected: FAIL with import error

**Step 3: Implement the repository protocol**

```python
# src/dataing/core/investigation/repository.py
"""Repository protocol for investigation persistence.

This module defines the interface for persisting investigation state.
Implementations should be in the adapters layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from .entities import Branch, Investigation, InvestigationContext, Snapshot
    from .values import BranchStatus, BranchType, StepType, VersionId


class ExecutionLock:
    """Represents an acquired execution lock."""

    def __init__(self, branch_id: UUID, locked_by: str, expires_at: str) -> None:
        """Initialize the lock."""
        self.branch_id = branch_id
        self.locked_by = locked_by
        self.expires_at = expires_at


class InvestigationRepository(Protocol):
    """Protocol for investigation persistence operations.

    This defines the interface that adapters must implement.
    All methods are async to support async database drivers.
    """

    # Investigation operations
    async def create_investigation(
        self,
        tenant_id: UUID,
        alert: dict,
        created_by: UUID | None = None,
    ) -> Investigation:
        """Create a new investigation."""
        ...

    async def get_investigation(self, investigation_id: UUID) -> Investigation | None:
        """Get investigation by ID."""
        ...

    async def update_investigation_outcome(
        self,
        investigation_id: UUID,
        outcome: dict,
    ) -> None:
        """Set the final outcome of an investigation."""
        ...

    async def set_main_branch(
        self,
        investigation_id: UUID,
        branch_id: UUID,
    ) -> None:
        """Set the main branch for an investigation."""
        ...

    # Branch operations
    async def create_branch(
        self,
        investigation_id: UUID,
        branch_type: BranchType,
        name: str,
        parent_branch_id: UUID | None = None,
        forked_from_snapshot_id: UUID | None = None,
        owner_user_id: UUID | None = None,
    ) -> Branch:
        """Create a new branch."""
        ...

    async def get_branch(self, branch_id: UUID) -> Branch | None:
        """Get branch by ID."""
        ...

    async def get_user_branch(
        self,
        investigation_id: UUID,
        user_id: UUID,
    ) -> Branch | None:
        """Get user's branch for an investigation."""
        ...

    async def update_branch_status(
        self,
        branch_id: UUID,
        status: BranchStatus,
    ) -> None:
        """Update branch status."""
        ...

    async def update_branch_head(
        self,
        branch_id: UUID,
        snapshot_id: UUID,
    ) -> None:
        """Update branch head to point to new snapshot."""
        ...

    # Snapshot operations
    async def create_snapshot(
        self,
        investigation_id: UUID,
        branch_id: UUID,
        version: VersionId,
        step: StepType,
        context: InvestigationContext,
        parent_snapshot_id: UUID | None = None,
        created_by: UUID | None = None,
        trigger: str = "system",
    ) -> Snapshot:
        """Create a new snapshot."""
        ...

    async def get_snapshot(self, snapshot_id: UUID) -> Snapshot | None:
        """Get snapshot by ID."""
        ...

    # Lock operations
    async def acquire_lock(
        self,
        branch_id: UUID,
        worker_id: str,
        ttl_seconds: int = 300,
    ) -> ExecutionLock | None:
        """Try to acquire execution lock on a branch.

        Returns ExecutionLock if acquired, None if already locked.
        """
        ...

    async def release_lock(self, branch_id: UUID, worker_id: str) -> bool:
        """Release execution lock.

        Returns True if released, False if lock was not held.
        """
        ...

    async def refresh_lock(
        self,
        branch_id: UUID,
        worker_id: str,
        ttl_seconds: int = 300,
    ) -> bool:
        """Refresh lock heartbeat.

        Returns True if refreshed, False if lock expired/not held.
        """
        ...

    # Message operations
    async def add_message(
        self,
        branch_id: UUID,
        role: str,
        content: str,
        user_id: UUID | None = None,
        resulting_snapshot_id: UUID | None = None,
    ) -> UUID:
        """Add a message to a branch."""
        ...

    async def get_messages(
        self,
        branch_id: UUID,
        limit: int = 100,
    ) -> list[dict]:
        """Get messages for a branch."""
        ...

    # Merge point operations
    async def set_merge_point(
        self,
        parent_branch_id: UUID,
        child_branch_ids: list[UUID],
        merge_step: StepType,
    ) -> None:
        """Record merge point for parallel branches."""
        ...

    async def get_merge_children(
        self,
        parent_branch_id: UUID,
    ) -> list[UUID]:
        """Get child branch IDs waiting to merge."""
        ...

    async def check_merge_ready(
        self,
        parent_branch_id: UUID,
    ) -> bool:
        """Check if all children are ready to merge."""
        ...
```

**Step 4: Update package init**

```python
# src/dataing/core/investigation/__init__.py
"""Investigation domain module."""

from .entities import Branch, Investigation, InvestigationContext, Snapshot
from .repository import ExecutionLock, InvestigationRepository
from .values import (
    BranchStatus,
    BranchType,
    ExecutionSignal,
    StepType,
    VersionId,
)

__all__ = [
    # Entities
    "Investigation",
    "Branch",
    "Snapshot",
    "InvestigationContext",
    # Value Objects
    "VersionId",
    "BranchType",
    "BranchStatus",
    "StepType",
    "ExecutionSignal",
    # Repository
    "InvestigationRepository",
    "ExecutionLock",
]
```

**Step 5: Run tests to verify they pass**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing && uv run pytest tests/unit/core/investigation/test_repository.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/dataing/core/investigation/
git commit -m "feat(core): add investigation repository protocol

- InvestigationRepository: Protocol for persistence operations
- ExecutionLock: Lock representation for durable execution
- Methods for CRUD on investigations, branches, snapshots
- Lock acquisition/release for branch processing
- Message and merge point operations"
```

---

## Phase 2: Step Abstraction

### Task 2.1: Create Step Protocol and StepResult

**Files:**
- Create: `dataing/src/dataing/core/investigation/steps/protocol.py`
- Test: `dataing/tests/unit/core/investigation/steps/test_protocol.py`

**Step 1: Create directory structure**

```bash
mkdir -p /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing/src/dataing/core/investigation/steps
mkdir -p /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing/tests/unit/core/investigation/steps
touch /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing/src/dataing/core/investigation/steps/__init__.py
touch /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing/tests/unit/core/investigation/steps/__init__.py
```

**Step 2: Write failing tests**

```python
# tests/unit/core/investigation/steps/test_protocol.py
"""Tests for step protocol and StepResult."""

from dataclasses import FrozenInstanceError
from typing import Any
from uuid import uuid4

import pytest

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.steps.protocol import BranchRequest, BranchSpec, StepResult
from dataing.core.investigation.values import (
    BranchType,
    ExecutionSignal,
    StepType,
)


@pytest.fixture
def sample_context() -> InvestigationContext:
    """Create sample context."""
    return InvestigationContext(alert_summary="Test anomaly")


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_create_continue_result(self, sample_context: InvestigationContext) -> None:
        """Can create a CONTINUE result."""
        result = StepResult(
            context=sample_context,
            signal=ExecutionSignal.CONTINUE,
            next_step=StepType.GENERATE_HYPOTHESES,
        )
        assert result.signal == ExecutionSignal.CONTINUE
        assert result.next_step == StepType.GENERATE_HYPOTHESES
        assert result.output is None
        assert result.branch_request is None

    def test_create_complete_result(self, sample_context: InvestigationContext) -> None:
        """Can create a COMPLETE result with output."""
        output = {"root_cause": "ETL failure", "confidence": 0.9}
        result = StepResult(
            context=sample_context,
            signal=ExecutionSignal.COMPLETE,
            output=output,
        )
        assert result.signal == ExecutionSignal.COMPLETE
        assert result.output == output
        assert result.next_step is None

    def test_create_branch_result(self, sample_context: InvestigationContext) -> None:
        """Can create a BRANCH result with branch request."""
        branch_request = BranchRequest(
            branch_type=BranchType.HYPOTHESIS,
            branches=[
                BranchSpec(name="h1", data={"hypothesis_id": "h1"}),
                BranchSpec(name="h2", data={"hypothesis_id": "h2"}),
            ],
            merge_step=StepType.SYNTHESIZE,
        )
        result = StepResult(
            context=sample_context,
            signal=ExecutionSignal.BRANCH,
            branch_request=branch_request,
        )
        assert result.signal == ExecutionSignal.BRANCH
        assert result.branch_request is not None
        assert len(result.branch_request.branches) == 2

    def test_result_is_frozen(self, sample_context: InvestigationContext) -> None:
        """StepResult is immutable."""
        result = StepResult(
            context=sample_context,
            signal=ExecutionSignal.CONTINUE,
        )
        with pytest.raises(FrozenInstanceError):
            result.signal = ExecutionSignal.FAIL  # type: ignore[misc]


class TestBranchRequest:
    """Tests for BranchRequest."""

    def test_create_branch_request(self) -> None:
        """Can create branch request with specs."""
        request = BranchRequest(
            branch_type=BranchType.HYPOTHESIS,
            branches=[
                BranchSpec(name="h1", data={}),
            ],
            merge_step=StepType.SYNTHESIZE,
        )
        assert request.branch_type == BranchType.HYPOTHESIS
        assert request.merge_step == StepType.SYNTHESIZE
        assert request.child_start_step is None

    def test_branch_request_with_start_step(self) -> None:
        """Can specify child start step."""
        request = BranchRequest(
            branch_type=BranchType.HYPOTHESIS,
            branches=[BranchSpec(name="h1", data={})],
            merge_step=StepType.SYNTHESIZE,
            child_start_step=StepType.GENERATE_QUERY,
        )
        assert request.child_start_step == StepType.GENERATE_QUERY
```

**Step 3: Run tests to verify they fail**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing && uv run pytest tests/unit/core/investigation/steps/test_protocol.py -v`
Expected: FAIL with import error

**Step 4: Implement the protocol**

```python
# src/dataing/core/investigation/steps/protocol.py
"""Step protocol and result types.

Steps are pure functions: (Context, Input) -> StepResult
They don't know about persistence, locking, or orchestration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import BranchType, ExecutionSignal, StepType

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


@dataclass(frozen=True)
class BranchSpec:
    """Specification for a child branch to create."""

    name: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BranchRequest:
    """Request to create child branches.

    Used when a step needs to fork execution into parallel paths.
    """

    branch_type: BranchType
    branches: list[BranchSpec]
    merge_step: StepType
    child_start_step: StepType | None = None


@dataclass(frozen=True)
class StepResult(Generic[OutputT]):
    """Immutable result of executing a step.

    Contains:
    - context: Updated investigation context
    - signal: What the orchestrator should do next
    - output: Step-specific output (optional)
    - next_step: Explicit next step (when signal=CONTINUE)
    - branch_request: Branch specs (when signal=BRANCH)
    """

    context: InvestigationContext
    signal: ExecutionSignal
    output: OutputT | None = None
    next_step: StepType | None = None
    branch_request: BranchRequest | None = None


class Step(ABC, Generic[InputT, OutputT]):
    """Base class for all investigation steps.

    Steps are:
    - Stateless: All state comes from context
    - Pure: Same input -> same output (modulo LLM stochasticity)
    - Composable: Can be chained, branched, merged
    """

    step_type: StepType

    @abstractmethod
    async def execute(
        self,
        context: InvestigationContext,
        input_data: InputT | None = None,
    ) -> StepResult[OutputT]:
        """Execute the step logic.

        Args:
            context: Current investigation state
            input_data: Step-specific input (e.g., user message)

        Returns:
            StepResult with updated context and execution signal
        """
        ...

    def can_execute(self, context: InvestigationContext) -> bool:
        """Check if prerequisites are met.

        Override in subclasses to add precondition checks.
        """
        return True
```

**Step 5: Create steps package init**

```python
# src/dataing/core/investigation/steps/__init__.py
"""Investigation steps module.

Steps are pure functions that transform context.
The orchestrator handles persistence, locking, and flow control.
"""

from .protocol import BranchRequest, BranchSpec, Step, StepResult

__all__ = [
    "Step",
    "StepResult",
    "BranchRequest",
    "BranchSpec",
]
```

**Step 6: Run tests to verify they pass**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing && uv run pytest tests/unit/core/investigation/steps/test_protocol.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add src/dataing/core/investigation/steps/ tests/unit/core/investigation/steps/
git commit -m "feat(core): add step protocol and StepResult

- Step: Abstract base class for investigation steps
- StepResult: Immutable result with context, signal, output
- BranchRequest: Specification for forking execution
- BranchSpec: Individual branch configuration"
```

---

### Task 2.2: Implement GatherContextStep

**Files:**
- Create: `dataing/src/dataing/core/investigation/steps/gather_context.py`
- Test: `dataing/tests/unit/core/investigation/steps/test_gather_context.py`

**Step 1: Write failing tests**

```python
# tests/unit/core/investigation/steps/test_gather_context.py
"""Tests for GatherContextStep."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.steps.gather_context import GatherContextStep
from dataing.core.investigation.values import ExecutionSignal, StepType


@pytest.fixture
def sample_alert() -> AnomalyAlert:
    """Create sample alert."""
    return AnomalyAlert(
        dataset_id="analytics.events",
        metric_spec=MetricSpec.from_column("user_id", "NULL rate"),
        anomaly_type="null_rate",
        expected_value=0.01,
        actual_value=0.15,
        deviation_pct=1400.0,
        anomaly_date="2026-01-10",
        severity="high",
    )


@pytest.fixture
def sample_context(sample_alert: AnomalyAlert) -> InvestigationContext:
    """Create context with alert summary."""
    return InvestigationContext(
        alert_summary=f"{sample_alert.anomaly_type} in {sample_alert.dataset_id}"
    )


@pytest.fixture
def mock_context_engine() -> AsyncMock:
    """Create mock context engine."""
    engine = AsyncMock()
    engine.gather.return_value = MagicMock(
        schema=MagicMock(
            is_empty=MagicMock(return_value=False),
            table_count=MagicMock(return_value=3),
            to_dict=MagicMock(return_value={"tables": ["events", "users", "orders"]}),
        ),
        lineage=MagicMock(
            to_dict=MagicMock(return_value={"upstream": ["raw.events"]})
        ),
    )
    return engine


class TestGatherContextStep:
    """Tests for GatherContextStep."""

    def test_step_type(self) -> None:
        """Step has correct type."""
        step = GatherContextStep(context_engine=AsyncMock())
        assert step.step_type == StepType.GATHER_CONTEXT

    @pytest.mark.asyncio
    async def test_execute_gathers_schema(
        self,
        sample_context: InvestigationContext,
        mock_context_engine: AsyncMock,
    ) -> None:
        """Execute gathers schema from context engine."""
        step = GatherContextStep(context_engine=mock_context_engine)

        result = await step.execute(sample_context)

        assert result.signal == ExecutionSignal.CONTINUE
        assert result.next_step == StepType.CHECK_PATTERNS
        assert result.context.schema_info is not None
        assert result.context.schema_info["tables"] == ["events", "users", "orders"]

    @pytest.mark.asyncio
    async def test_execute_gathers_lineage(
        self,
        sample_context: InvestigationContext,
        mock_context_engine: AsyncMock,
    ) -> None:
        """Execute gathers lineage from context engine."""
        step = GatherContextStep(context_engine=mock_context_engine)

        result = await step.execute(sample_context)

        assert result.context.lineage_info is not None
        assert result.context.lineage_info["upstream"] == ["raw.events"]

    @pytest.mark.asyncio
    async def test_execute_fails_on_empty_schema(
        self,
        sample_context: InvestigationContext,
    ) -> None:
        """Execute returns FAIL signal when schema is empty."""
        engine = AsyncMock()
        engine.gather.return_value = MagicMock(
            schema=MagicMock(
                is_empty=MagicMock(return_value=True),
            ),
        )
        step = GatherContextStep(context_engine=engine)

        result = await step.execute(sample_context)

        assert result.signal == ExecutionSignal.FAIL
        assert "empty schema" in str(result.output).lower()
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing && uv run pytest tests/unit/core/investigation/steps/test_gather_context.py -v`
Expected: FAIL with import error

**Step 3: Implement the step**

```python
# src/dataing/core/investigation/steps/gather_context.py
"""GatherContext step implementation.

This step gathers schema and lineage context from the data source.
It's the first step in any investigation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import ExecutionSignal, StepType

from .protocol import Step, StepResult

if TYPE_CHECKING:
    from dataing.core.interfaces import ContextEngine


class ContextBundle:
    """Bundle of gathered context."""

    def __init__(
        self,
        schema_info: dict[str, Any],
        lineage_info: dict[str, Any] | None = None,
    ) -> None:
        """Initialize context bundle."""
        self.schema_info = schema_info
        self.lineage_info = lineage_info


class GatherContextStep(Step[None, ContextBundle]):
    """Gather schema, lineage, and recent changes.

    This is the first step in an investigation. It fails fast
    if no schema can be discovered (connectivity/permissions issue).
    """

    step_type = StepType.GATHER_CONTEXT

    def __init__(self, context_engine: ContextEngine) -> None:
        """Initialize the step.

        Args:
            context_engine: Engine for gathering context from data source.
        """
        self.context_engine = context_engine

    async def execute(
        self,
        context: InvestigationContext,
        input_data: None = None,
    ) -> StepResult[ContextBundle]:
        """Gather context from data source.

        Args:
            context: Current investigation context.
            input_data: Not used for this step.

        Returns:
            StepResult with updated context containing schema/lineage.
        """
        try:
            gathered = await self.context_engine.gather(
                alert_summary=context.alert_summary,
            )
        except Exception as e:
            return StepResult(
                context=context,
                signal=ExecutionSignal.FAIL,
                output=ContextBundle(
                    schema_info={"error": f"Context gathering failed: {e}"}
                ),
            )

        # Fail fast on empty schema
        if gathered.schema.is_empty():
            return StepResult(
                context=context,
                signal=ExecutionSignal.FAIL,
                output=ContextBundle(
                    schema_info={"error": "Empty schema - check connectivity/permissions"}
                ),
            )

        # Build updated context
        schema_info = gathered.schema.to_dict()
        lineage_info = gathered.lineage.to_dict() if gathered.lineage else None

        # Create new context with gathered info
        # Note: We need to create a new dict since InvestigationContext is frozen
        new_context = InvestigationContext(
            alert_summary=context.alert_summary,
            schema_info=schema_info,
            lineage_info=lineage_info,
            recent_changes=context.recent_changes,
            matched_patterns=context.matched_patterns,
            hypotheses=context.hypotheses,
            evidence=context.evidence,
            current_synthesis=context.current_synthesis,
            counter_analysis=context.counter_analysis,
            chat_history=context.chat_history,
            pending_approval=context.pending_approval,
            total_tokens_used=context.total_tokens_used,
            total_queries_executed=context.total_queries_executed,
            execution_time_ms=context.execution_time_ms,
        )

        return StepResult(
            context=new_context,
            signal=ExecutionSignal.CONTINUE,
            output=ContextBundle(schema_info=schema_info, lineage_info=lineage_info),
            next_step=StepType.CHECK_PATTERNS,
        )
```

**Step 4: Update steps package init**

```python
# src/dataing/core/investigation/steps/__init__.py
"""Investigation steps module."""

from .gather_context import ContextBundle, GatherContextStep
from .protocol import BranchRequest, BranchSpec, Step, StepResult

__all__ = [
    "Step",
    "StepResult",
    "BranchRequest",
    "BranchSpec",
    "GatherContextStep",
    "ContextBundle",
]
```

**Step 5: Run tests to verify they pass**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing && uv run pytest tests/unit/core/investigation/steps/test_gather_context.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/dataing/core/investigation/steps/ tests/unit/core/investigation/steps/
git commit -m "feat(steps): add GatherContextStep

- Gathers schema and lineage from context engine
- Fails fast on empty schema (connectivity/permissions issue)
- Returns CONTINUE signal with next_step=CHECK_PATTERNS"
```

---

### Task 2.3: Implement GenerateHypothesesStep

**Files:**
- Create: `dataing/src/dataing/core/investigation/steps/generate_hypotheses.py`
- Test: `dataing/tests/unit/core/investigation/steps/test_generate_hypotheses.py`

**Step 1: Write failing tests**

```python
# tests/unit/core/investigation/steps/test_generate_hypotheses.py
"""Tests for GenerateHypothesesStep."""

from unittest.mock import AsyncMock

import pytest

from dataing.core.domain_types import Hypothesis, HypothesisCategory
from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.steps.generate_hypotheses import GenerateHypothesesStep
from dataing.core.investigation.values import BranchType, ExecutionSignal, StepType


@pytest.fixture
def sample_context() -> InvestigationContext:
    """Create context with schema info."""
    return InvestigationContext(
        alert_summary="NULL rate spike in analytics.events",
        schema_info={"tables": ["events", "users"]},
    )


@pytest.fixture
def sample_hypotheses() -> list[Hypothesis]:
    """Create sample hypotheses."""
    return [
        Hypothesis(
            id="h1",
            title="Upstream ETL failure",
            category=HypothesisCategory.UPSTREAM_DEPENDENCY,
            reasoning="ETL job may have failed",
            suggested_query="SELECT * FROM events WHERE user_id IS NULL",
        ),
        Hypothesis(
            id="h2",
            title="Mobile app bug",
            category=HypothesisCategory.DATA_QUALITY,
            reasoning="Mobile app may not be sending user_id",
            suggested_query="SELECT platform, COUNT(*) FROM events GROUP BY platform",
        ),
    ]


@pytest.fixture
def mock_llm(sample_hypotheses: list[Hypothesis]) -> AsyncMock:
    """Create mock LLM client."""
    llm = AsyncMock()
    llm.generate_hypotheses.return_value = sample_hypotheses
    return llm


class TestGenerateHypothesesStep:
    """Tests for GenerateHypothesesStep."""

    def test_step_type(self) -> None:
        """Step has correct type."""
        step = GenerateHypothesesStep(llm=AsyncMock())
        assert step.step_type == StepType.GENERATE_HYPOTHESES

    @pytest.mark.asyncio
    async def test_execute_generates_hypotheses(
        self,
        sample_context: InvestigationContext,
        mock_llm: AsyncMock,
        sample_hypotheses: list[Hypothesis],
    ) -> None:
        """Execute generates hypotheses via LLM."""
        step = GenerateHypothesesStep(llm=mock_llm)

        result = await step.execute(sample_context)

        assert result.signal == ExecutionSignal.BRANCH
        assert result.branch_request is not None
        assert len(result.branch_request.branches) == 2

    @pytest.mark.asyncio
    async def test_execute_returns_branch_request(
        self,
        sample_context: InvestigationContext,
        mock_llm: AsyncMock,
    ) -> None:
        """Execute returns BRANCH signal with branch request."""
        step = GenerateHypothesesStep(llm=mock_llm)

        result = await step.execute(sample_context)

        assert result.signal == ExecutionSignal.BRANCH
        assert result.branch_request.branch_type == BranchType.HYPOTHESIS
        assert result.branch_request.merge_step == StepType.SYNTHESIZE
        assert result.branch_request.child_start_step == StepType.GENERATE_QUERY

    @pytest.mark.asyncio
    async def test_execute_updates_context_with_hypotheses(
        self,
        sample_context: InvestigationContext,
        mock_llm: AsyncMock,
        sample_hypotheses: list[Hypothesis],
    ) -> None:
        """Execute adds hypotheses to context."""
        step = GenerateHypothesesStep(llm=mock_llm)

        result = await step.execute(sample_context)

        assert len(result.context.hypotheses) == 2
        assert result.context.hypotheses[0]["id"] == "h1"

    @pytest.mark.asyncio
    async def test_execute_includes_pattern_hints(
        self,
        mock_llm: AsyncMock,
    ) -> None:
        """Execute passes pattern hints to LLM."""
        context = InvestigationContext(
            alert_summary="NULL rate spike",
            schema_info={"tables": ["events"]},
            matched_patterns=[
                {"name": "ETL failure pattern", "description": "Common ETL issue"}
            ],
        )
        step = GenerateHypothesesStep(llm=mock_llm)

        await step.execute(context)

        # Verify LLM was called with pattern hints
        call_kwargs = mock_llm.generate_hypotheses.call_args.kwargs
        assert "pattern_hints" in call_kwargs
        assert len(call_kwargs["pattern_hints"]) == 1

    def test_can_execute_requires_schema(self) -> None:
        """can_execute returns False if no schema info."""
        step = GenerateHypothesesStep(llm=AsyncMock())
        context_no_schema = InvestigationContext(alert_summary="Test")
        context_with_schema = InvestigationContext(
            alert_summary="Test",
            schema_info={"tables": ["events"]},
        )

        assert step.can_execute(context_no_schema) is False
        assert step.can_execute(context_with_schema) is True
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing && uv run pytest tests/unit/core/investigation/steps/test_generate_hypotheses.py -v`
Expected: FAIL with import error

**Step 3: Implement the step**

```python
# src/dataing/core/investigation/steps/generate_hypotheses.py
"""GenerateHypotheses step implementation.

This step uses the LLM to generate hypotheses about potential root causes.
It returns a BRANCH signal to investigate each hypothesis in parallel.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dataing.core.domain_types import Hypothesis
from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import BranchType, ExecutionSignal, StepType

from .protocol import BranchRequest, BranchSpec, Step, StepResult

if TYPE_CHECKING:
    from dataing.core.interfaces import LLMClient


class GenerateHypothesesStep(Step[None, list[Hypothesis]]):
    """Generate hypotheses about potential root causes.

    This step:
    1. Calls LLM with alert, schema, and pattern hints
    2. Returns BRANCH signal to investigate each hypothesis in parallel
    """

    step_type = StepType.GENERATE_HYPOTHESES

    def __init__(
        self,
        llm: LLMClient,
        max_hypotheses: int = 5,
    ) -> None:
        """Initialize the step.

        Args:
            llm: LLM client for generating hypotheses.
            max_hypotheses: Maximum number of hypotheses to generate.
        """
        self.llm = llm
        self.max_hypotheses = max_hypotheses

    def can_execute(self, context: InvestigationContext) -> bool:
        """Check if schema info is available."""
        return context.schema_info is not None

    async def execute(
        self,
        context: InvestigationContext,
        input_data: None = None,
    ) -> StepResult[list[Hypothesis]]:
        """Generate hypotheses via LLM.

        Args:
            context: Current investigation context with schema.
            input_data: Not used for this step.

        Returns:
            StepResult with BRANCH signal and hypothesis branches.
        """
        # Extract pattern hints if any patterns matched
        pattern_hints = [
            p.get("description", p.get("name", ""))
            for p in context.matched_patterns
        ]

        # Generate hypotheses
        hypotheses = await self.llm.generate_hypotheses(
            alert_summary=context.alert_summary,
            schema_info=context.schema_info,
            lineage_info=context.lineage_info,
            num_hypotheses=self.max_hypotheses,
            pattern_hints=pattern_hints if pattern_hints else None,
        )

        # Convert hypotheses to dicts for context storage
        hypotheses_dicts = [h.model_dump() for h in hypotheses]

        # Create branch specs for each hypothesis
        branch_specs = [
            BranchSpec(
                name=f"hypothesis_{h.id}",
                data={"hypothesis": h.model_dump()},
            )
            for h in hypotheses
        ]

        # Update context with hypotheses
        new_context = InvestigationContext(
            alert_summary=context.alert_summary,
            schema_info=context.schema_info,
            lineage_info=context.lineage_info,
            recent_changes=context.recent_changes,
            matched_patterns=context.matched_patterns,
            hypotheses=hypotheses_dicts,
            evidence=context.evidence,
            current_synthesis=context.current_synthesis,
            counter_analysis=context.counter_analysis,
            chat_history=context.chat_history,
            pending_approval=context.pending_approval,
            total_tokens_used=context.total_tokens_used,
            total_queries_executed=context.total_queries_executed,
            execution_time_ms=context.execution_time_ms,
        )

        return StepResult(
            context=new_context,
            signal=ExecutionSignal.BRANCH,
            output=hypotheses,
            branch_request=BranchRequest(
                branch_type=BranchType.HYPOTHESIS,
                branches=branch_specs,
                merge_step=StepType.SYNTHESIZE,
                child_start_step=StepType.GENERATE_QUERY,
            ),
        )
```

**Step 4: Update steps package init**

```python
# src/dataing/core/investigation/steps/__init__.py
"""Investigation steps module."""

from .gather_context import ContextBundle, GatherContextStep
from .generate_hypotheses import GenerateHypothesesStep
from .protocol import BranchRequest, BranchSpec, Step, StepResult

__all__ = [
    "Step",
    "StepResult",
    "BranchRequest",
    "BranchSpec",
    "GatherContextStep",
    "ContextBundle",
    "GenerateHypothesesStep",
]
```

**Step 5: Run tests to verify they pass**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/unified-investigation/dataing && uv run pytest tests/unit/core/investigation/steps/test_generate_hypotheses.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add src/dataing/core/investigation/steps/ tests/unit/core/investigation/steps/
git commit -m "feat(steps): add GenerateHypothesesStep

- Generates hypotheses via LLM
- Includes pattern hints from matched patterns
- Returns BRANCH signal with one branch per hypothesis
- Child branches start at GENERATE_QUERY, merge at SYNTHESIZE"
```

---

## Phase 3: Orchestrator (Tasks 3.1-3.4)

*Continue with similar detailed task structure for:*
- Task 3.1: Create StepRegistry
- Task 3.2: Implement Orchestrator.tick() with CONTINUE/COMPLETE
- Task 3.3: Add lock acquisition and crash recovery
- Task 3.4: Implement BRANCH signal handling

---

## Phase 4: Remaining Steps and Integration (Tasks 4.1-4.6)

*Continue with:*
- Task 4.1: GenerateQueryStep
- Task 4.2: ExecuteQueryStep
- Task 4.3: InterpretEvidenceStep
- Task 4.4: SynthesizeStep
- Task 4.5: CheckPatternsStep
- Task 4.6: Integration tests

---

## Summary

This plan covers Phase 1 (Foundation) and Phase 2 (Step Abstraction) in full detail. The remaining phases follow the same pattern:

| Phase | Tasks | Key Deliverables |
|-------|-------|------------------|
| 1. Foundation | 1.1-1.4 | Migration, value objects, entities, repository |
| 2. Step Abstraction | 2.1-2.3 | Step protocol, GatherContext, GenerateHypotheses |
| 3. Orchestrator | 3.1-3.4 | StepRegistry, tick loop, locking, branching |
| 4. Remaining Steps | 4.1-4.6 | Query, Evidence, Synthesis steps, integration |
| 5. Collaboration | 5.1-5.3 | User branches, ClassifyIntent, messages |
| 6. Patterns | 6.1-6.2 | CheckPatterns, pattern extraction |
| 7. API | 7.1-7.3 | Endpoints, SSE streaming, frontend updates |

Each task follows TDD: write failing test, run to verify failure, implement, verify pass, commit.
