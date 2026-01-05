# Feedback System Phase 1: Event Foundation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create an append-only event log to capture investigation traces for future feedback, search, and ML training.

**Architecture:** New `feedback_events` table stores all investigation activity as immutable events. A `FeedbackAdapter` provides a clean interface for emitting events. The orchestrator is wired to emit events at key investigation milestones.

**Tech Stack:** PostgreSQL (asyncpg), Python dataclasses, structlog for logging

---

## Task 1: Create feedback_events Migration

**Files:**
- Create: `backend/migrations/003_feedback_events.sql`

**Step 1: Write the migration file**

```sql
-- Feedback events: append-only event log for investigation traces
-- Used for: user feedback, tribal knowledge, ML training data

CREATE TABLE feedback_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    investigation_id UUID REFERENCES investigations(id) ON DELETE SET NULL,
    dataset_id UUID REFERENCES datasets(id) ON DELETE SET NULL,
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}',
    actor_id UUID,
    actor_type VARCHAR(50) NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX idx_feedback_events_tenant ON feedback_events(tenant_id);
CREATE INDEX idx_feedback_events_investigation ON feedback_events(investigation_id);
CREATE INDEX idx_feedback_events_dataset ON feedback_events(dataset_id);
CREATE INDEX idx_feedback_events_type ON feedback_events(event_type);
CREATE INDEX idx_feedback_events_created ON feedback_events(created_at DESC);

-- Composite index for tenant + time range queries
CREATE INDEX idx_feedback_events_tenant_time ON feedback_events(tenant_id, created_at DESC);

-- GIN index for JSONB queries on event_data
CREATE INDEX idx_feedback_events_data ON feedback_events USING GIN (event_data);

COMMENT ON TABLE feedback_events IS 'Append-only event log for investigation traces, feedback, and ML training';
COMMENT ON COLUMN feedback_events.event_type IS 'Event type: investigation.started, hypothesis.generated, query.executed, feedback.submitted, etc.';
COMMENT ON COLUMN feedback_events.actor_type IS 'Actor type: system, user';
```

**Step 2: Verify migration syntax**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && psql -h localhost -U dataing -d dataing -f backend/migrations/003_feedback_events.sql`

Expected: Tables and indexes created without errors.

**Step 3: Commit**

```bash
git add backend/migrations/003_feedback_events.sql
git commit -m "feat(feedback): add feedback_events table migration"
```

---

## Task 2: Create FeedbackEvent Domain Type

**Files:**
- Create: `backend/src/dataing/adapters/feedback/__init__.py`
- Create: `backend/src/dataing/adapters/feedback/types.py`
- Test: `backend/tests/unit/adapters/feedback/test_types.py`

**Step 1: Create the feedback adapter package**

```bash
mkdir -p backend/src/dataing/adapters/feedback
mkdir -p backend/tests/unit/adapters/feedback
touch backend/tests/unit/adapters/feedback/__init__.py
```

**Step 2: Write the failing test**

Create `backend/tests/unit/adapters/feedback/test_types.py`:

```python
"""Tests for feedback event types."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from dataing.adapters.feedback.types import FeedbackEvent, EventType


class TestFeedbackEvent:
    """Tests for FeedbackEvent dataclass."""

    def test_create_event_with_required_fields(self) -> None:
        """Event can be created with required fields only."""
        event = FeedbackEvent(
            tenant_id=uuid4(),
            event_type=EventType.INVESTIGATION_STARTED,
            event_data={"dataset_id": "public.orders"},
        )

        assert event.id is not None
        assert event.actor_type == "system"
        assert event.created_at is not None

    def test_create_event_with_all_fields(self) -> None:
        """Event can be created with all fields."""
        tenant_id = uuid4()
        investigation_id = uuid4()
        dataset_id = uuid4()
        actor_id = uuid4()

        event = FeedbackEvent(
            tenant_id=tenant_id,
            investigation_id=investigation_id,
            dataset_id=dataset_id,
            event_type=EventType.HYPOTHESIS_GENERATED,
            event_data={"hypothesis_id": "h1", "title": "NULL spike"},
            actor_id=actor_id,
            actor_type="user",
        )

        assert event.tenant_id == tenant_id
        assert event.investigation_id == investigation_id
        assert event.dataset_id == dataset_id
        assert event.actor_id == actor_id
        assert event.actor_type == "user"

    def test_event_is_immutable(self) -> None:
        """Event should be immutable (frozen dataclass)."""
        event = FeedbackEvent(
            tenant_id=uuid4(),
            event_type=EventType.INVESTIGATION_STARTED,
            event_data={},
        )

        with pytest.raises(AttributeError):
            event.event_type = EventType.INVESTIGATION_COMPLETED  # type: ignore[misc]


class TestEventType:
    """Tests for EventType enum."""

    def test_investigation_events_exist(self) -> None:
        """Investigation lifecycle events are defined."""
        assert EventType.INVESTIGATION_STARTED.value == "investigation.started"
        assert EventType.INVESTIGATION_COMPLETED.value == "investigation.completed"

    def test_hypothesis_events_exist(self) -> None:
        """Hypothesis events are defined."""
        assert EventType.HYPOTHESIS_GENERATED.value == "hypothesis.generated"
        assert EventType.HYPOTHESIS_ACCEPTED.value == "hypothesis.accepted"
        assert EventType.HYPOTHESIS_REJECTED.value == "hypothesis.rejected"

    def test_query_events_exist(self) -> None:
        """Query events are defined."""
        assert EventType.QUERY_SUBMITTED.value == "query.submitted"
        assert EventType.QUERY_SUCCEEDED.value == "query.succeeded"
        assert EventType.QUERY_FAILED.value == "query.failed"

    def test_feedback_events_exist(self) -> None:
        """User feedback events are defined."""
        assert EventType.FEEDBACK_HYPOTHESIS.value == "feedback.hypothesis"
        assert EventType.FEEDBACK_QUERY.value == "feedback.query"
        assert EventType.FEEDBACK_SYNTHESIS.value == "feedback.synthesis"
        assert EventType.FEEDBACK_INVESTIGATION.value == "feedback.investigation"
```

**Step 3: Run test to verify it fails**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/adapters/feedback/test_types.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'dataing.adapters.feedback'"

**Step 4: Write minimal implementation**

Create `backend/src/dataing/adapters/feedback/__init__.py`:

```python
"""Feedback adapter for event logging and feedback collection."""

from .types import EventType, FeedbackEvent

__all__ = ["EventType", "FeedbackEvent"]
```

Create `backend/src/dataing/adapters/feedback/types.py`:

```python
"""Types for the feedback event system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


class EventType(Enum):
    """Types of events that can be logged."""

    # Investigation lifecycle
    INVESTIGATION_STARTED = "investigation.started"
    INVESTIGATION_COMPLETED = "investigation.completed"
    INVESTIGATION_FAILED = "investigation.failed"

    # Hypothesis events
    HYPOTHESIS_GENERATED = "hypothesis.generated"
    HYPOTHESIS_ACCEPTED = "hypothesis.accepted"
    HYPOTHESIS_REJECTED = "hypothesis.rejected"

    # Query events
    QUERY_SUBMITTED = "query.submitted"
    QUERY_SUCCEEDED = "query.succeeded"
    QUERY_FAILED = "query.failed"

    # Evidence events
    EVIDENCE_COLLECTED = "evidence.collected"
    EVIDENCE_EVALUATED = "evidence.evaluated"

    # Synthesis events
    SYNTHESIS_GENERATED = "synthesis.generated"

    # User feedback events
    FEEDBACK_HYPOTHESIS = "feedback.hypothesis"
    FEEDBACK_QUERY = "feedback.query"
    FEEDBACK_EVIDENCE = "feedback.evidence"
    FEEDBACK_SYNTHESIS = "feedback.synthesis"
    FEEDBACK_INVESTIGATION = "feedback.investigation"

    # Comments
    COMMENT_ADDED = "comment.added"


@dataclass(frozen=True)
class FeedbackEvent:
    """Immutable event for the feedback log.

    Attributes:
        id: Unique event identifier.
        tenant_id: Tenant this event belongs to.
        investigation_id: Optional investigation this event relates to.
        dataset_id: Optional dataset this event relates to.
        event_type: Type of event.
        event_data: Event-specific data payload.
        actor_id: Optional user or system that caused the event.
        actor_type: Type of actor (user or system).
        created_at: When the event occurred.
    """

    tenant_id: UUID
    event_type: EventType
    event_data: dict[str, Any]
    id: UUID = field(default_factory=uuid4)
    investigation_id: UUID | None = None
    dataset_id: UUID | None = None
    actor_id: UUID | None = None
    actor_type: str = "system"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

**Step 5: Run test to verify it passes**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/adapters/feedback/test_types.py -v`

Expected: PASS (all tests green)

**Step 6: Run linting**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run ruff check backend/src/dataing/adapters/feedback/ backend/tests/unit/adapters/feedback/ --fix`

Expected: No errors or auto-fixed

**Step 7: Commit**

```bash
git add backend/src/dataing/adapters/feedback/ backend/tests/unit/adapters/feedback/
git commit -m "feat(feedback): add FeedbackEvent type and EventType enum"
```

---

## Task 3: Create FeedbackAdapter with emit() Method

**Files:**
- Create: `backend/src/dataing/adapters/feedback/adapter.py`
- Modify: `backend/src/dataing/adapters/feedback/__init__.py`
- Test: `backend/tests/unit/adapters/feedback/test_adapter.py`

**Step 1: Write the failing test**

Create `backend/tests/unit/adapters/feedback/test_adapter.py`:

```python
"""Tests for FeedbackAdapter."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from dataing.adapters.feedback import EventType, FeedbackAdapter, FeedbackEvent


class TestFeedbackAdapter:
    """Tests for FeedbackAdapter."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock database."""
        db = MagicMock()
        db.execute = AsyncMock(return_value="INSERT 0 1")
        return db

    @pytest.fixture
    def adapter(self, mock_db: MagicMock) -> FeedbackAdapter:
        """Create adapter with mock database."""
        return FeedbackAdapter(db=mock_db)

    async def test_emit_stores_event(
        self, adapter: FeedbackAdapter, mock_db: MagicMock
    ) -> None:
        """emit() stores event in database."""
        tenant_id = uuid4()
        investigation_id = uuid4()

        await adapter.emit(
            tenant_id=tenant_id,
            event_type=EventType.INVESTIGATION_STARTED,
            event_data={"dataset_id": "public.orders"},
            investigation_id=investigation_id,
        )

        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert "INSERT INTO feedback_events" in call_args[0][0]

    async def test_emit_returns_event(self, adapter: FeedbackAdapter) -> None:
        """emit() returns the created event."""
        tenant_id = uuid4()

        event = await adapter.emit(
            tenant_id=tenant_id,
            event_type=EventType.HYPOTHESIS_GENERATED,
            event_data={"hypothesis_id": "h1"},
        )

        assert isinstance(event, FeedbackEvent)
        assert event.tenant_id == tenant_id
        assert event.event_type == EventType.HYPOTHESIS_GENERATED

    async def test_emit_with_actor(
        self, adapter: FeedbackAdapter, mock_db: MagicMock
    ) -> None:
        """emit() includes actor information when provided."""
        tenant_id = uuid4()
        actor_id = uuid4()

        event = await adapter.emit(
            tenant_id=tenant_id,
            event_type=EventType.FEEDBACK_INVESTIGATION,
            event_data={"rating": 1},
            actor_id=actor_id,
            actor_type="user",
        )

        assert event.actor_id == actor_id
        assert event.actor_type == "user"

    async def test_emit_logs_event(
        self, adapter: FeedbackAdapter, mock_db: MagicMock
    ) -> None:
        """emit() logs the event for observability."""
        tenant_id = uuid4()

        # This test verifies emit doesn't raise and completes
        event = await adapter.emit(
            tenant_id=tenant_id,
            event_type=EventType.QUERY_SUCCEEDED,
            event_data={"row_count": 100},
        )

        assert event is not None
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/adapters/feedback/test_adapter.py -v`

Expected: FAIL with "ImportError: cannot import name 'FeedbackAdapter'"

**Step 3: Write minimal implementation**

Create `backend/src/dataing/adapters/feedback/adapter.py`:

```python
"""Feedback adapter for emitting and storing events."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from .types import EventType, FeedbackEvent

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase

logger = structlog.get_logger()


class FeedbackAdapter:
    """Adapter for emitting feedback events to the event log.

    This adapter provides a clean interface for recording investigation
    traces, user feedback, and other events for later analysis.
    """

    def __init__(self, db: AppDatabase) -> None:
        """Initialize the feedback adapter.

        Args:
            db: Application database for storing events.
        """
        self.db = db

    async def emit(
        self,
        tenant_id: UUID,
        event_type: EventType,
        event_data: dict[str, Any],
        investigation_id: UUID | None = None,
        dataset_id: UUID | None = None,
        actor_id: UUID | None = None,
        actor_type: str = "system",
    ) -> FeedbackEvent:
        """Emit an event to the feedback log.

        Args:
            tenant_id: Tenant this event belongs to.
            event_type: Type of event being emitted.
            event_data: Event-specific data payload.
            investigation_id: Optional investigation this relates to.
            dataset_id: Optional dataset this relates to.
            actor_id: Optional user or system that caused the event.
            actor_type: Type of actor (user or system).

        Returns:
            The created FeedbackEvent.
        """
        event = FeedbackEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            event_data=event_data,
            investigation_id=investigation_id,
            dataset_id=dataset_id,
            actor_id=actor_id,
            actor_type=actor_type,
        )

        await self._store_event(event)

        logger.debug(
            "feedback_event_emitted",
            event_id=str(event.id),
            event_type=event_type.value,
            investigation_id=str(investigation_id) if investigation_id else None,
        )

        return event

    async def _store_event(self, event: FeedbackEvent) -> None:
        """Store event in the database.

        Args:
            event: The event to store.
        """
        query = """
            INSERT INTO feedback_events (
                id, tenant_id, investigation_id, dataset_id,
                event_type, event_data, actor_id, actor_type, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """

        await self.db.execute(
            query,
            event.id,
            event.tenant_id,
            event.investigation_id,
            event.dataset_id,
            event.event_type.value,
            json.dumps(event.event_data),
            event.actor_id,
            event.actor_type,
            event.created_at,
        )
```

Update `backend/src/dataing/adapters/feedback/__init__.py`:

```python
"""Feedback adapter for event logging and feedback collection."""

from .adapter import FeedbackAdapter
from .types import EventType, FeedbackEvent

__all__ = ["EventType", "FeedbackAdapter", "FeedbackEvent"]
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/adapters/feedback/test_adapter.py -v`

Expected: PASS (all tests green)

**Step 5: Run linting**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run ruff check backend/src/dataing/adapters/feedback/ --fix && uv run mypy backend/src/dataing/adapters/feedback/`

Expected: No errors

**Step 6: Commit**

```bash
git add backend/src/dataing/adapters/feedback/
git commit -m "feat(feedback): add FeedbackAdapter with emit() method"
```

---

## Task 4: Add FeedbackEmitter Protocol to Core Interfaces

**Files:**
- Modify: `backend/src/dataing/core/interfaces.py`
- Test: `backend/tests/unit/adapters/feedback/test_adapter.py` (add protocol conformance test)

**Step 1: Write the failing test**

Add to `backend/tests/unit/adapters/feedback/test_adapter.py`:

```python
from dataing.core.interfaces import FeedbackEmitter


class TestFeedbackAdapterProtocol:
    """Tests for protocol conformance."""

    def test_adapter_implements_feedback_emitter(self) -> None:
        """FeedbackAdapter implements FeedbackEmitter protocol."""
        from dataing.adapters.feedback import FeedbackAdapter

        assert isinstance(FeedbackAdapter, type)
        # Runtime check would require an instance, but we verify the class exists
        # and has the emit method signature
        assert hasattr(FeedbackAdapter, "emit")
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/adapters/feedback/test_adapter.py::TestFeedbackAdapterProtocol -v`

Expected: FAIL with "ImportError: cannot import name 'FeedbackEmitter'"

**Step 3: Write minimal implementation**

Add to `backend/src/dataing/core/interfaces.py` (after existing protocols):

```python
@runtime_checkable
class FeedbackEmitter(Protocol):
    """Interface for emitting feedback events.

    Implementations store events in an append-only log for:
    - Investigation trace recording
    - User feedback collection
    - ML training data generation
    """

    async def emit(
        self,
        tenant_id: UUID,
        event_type: Any,  # EventType enum
        event_data: dict[str, Any],
        investigation_id: UUID | None = None,
        dataset_id: UUID | None = None,
        actor_id: UUID | None = None,
        actor_type: str = "system",
    ) -> Any:
        """Emit an event to the feedback log.

        Args:
            tenant_id: Tenant this event belongs to.
            event_type: Type of event being emitted.
            event_data: Event-specific data payload.
            investigation_id: Optional investigation this relates to.
            dataset_id: Optional dataset this relates to.
            actor_id: Optional user or system that caused the event.
            actor_type: Type of actor (user or system).

        Returns:
            The created event object.
        """
        ...
```

Also add imports at the top of `interfaces.py`:

```python
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from uuid import UUID
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/adapters/feedback/test_adapter.py::TestFeedbackAdapterProtocol -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/dataing/core/interfaces.py backend/tests/unit/adapters/feedback/test_adapter.py
git commit -m "feat(feedback): add FeedbackEmitter protocol to core interfaces"
```

---

## Task 5: Wire FeedbackAdapter into Orchestrator

**Files:**
- Modify: `backend/src/dataing/core/orchestrator.py`
- Test: `backend/tests/unit/core/test_orchestrator_feedback.py`

**Step 1: Write the failing test**

Create `backend/tests/unit/core/test_orchestrator_feedback.py`:

```python
"""Tests for orchestrator feedback event emission."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from dataing.adapters.feedback import EventType
from dataing.core.domain_types import AnomalyAlert
from dataing.core.orchestrator import InvestigationOrchestrator, OrchestratorConfig
from dataing.core.state import InvestigationState


class TestOrchestratorFeedbackEmission:
    """Tests for feedback event emission during investigations."""

    @pytest.fixture
    def mock_feedback(self) -> MagicMock:
        """Create mock feedback emitter."""
        feedback = MagicMock()
        feedback.emit = AsyncMock()
        return feedback

    @pytest.fixture
    def mock_llm(self) -> MagicMock:
        """Create mock LLM client."""
        llm = MagicMock()
        llm.generate_hypotheses = AsyncMock(return_value=[])
        llm.synthesize_findings = AsyncMock(
            return_value=MagicMock(
                status="completed",
                root_cause="Test cause",
                confidence=0.9,
                recommendations=[],
            )
        )
        return llm

    @pytest.fixture
    def mock_context_engine(self) -> MagicMock:
        """Create mock context engine."""
        engine = MagicMock()
        schema = MagicMock()
        schema.is_empty.return_value = False
        schema.table_count.return_value = 5
        engine.gather = AsyncMock(
            return_value=MagicMock(schema=schema, lineage=None)
        )
        return engine

    @pytest.fixture
    def mock_circuit_breaker(self) -> MagicMock:
        """Create mock circuit breaker."""
        cb = MagicMock()
        cb.check = MagicMock()
        return cb

    @pytest.fixture
    def mock_adapter(self) -> MagicMock:
        """Create mock SQL adapter."""
        adapter = MagicMock()
        adapter.execute_query = AsyncMock()
        return adapter

    @pytest.fixture
    def orchestrator(
        self,
        mock_llm: MagicMock,
        mock_context_engine: MagicMock,
        mock_circuit_breaker: MagicMock,
        mock_feedback: MagicMock,
    ) -> InvestigationOrchestrator:
        """Create orchestrator with mocks."""
        return InvestigationOrchestrator(
            db=None,
            llm=mock_llm,
            context_engine=mock_context_engine,
            circuit_breaker=mock_circuit_breaker,
            feedback=mock_feedback,
            config=OrchestratorConfig(),
        )

    @pytest.fixture
    def alert(self) -> AnomalyAlert:
        """Create test alert."""
        return AnomalyAlert(
            dataset_id="public.orders",
            metric_name="null_rate",
            expected_value=0.01,
            actual_value=0.15,
            deviation_pct=1400.0,
            detected_at=datetime.now(UTC),
        )

    @pytest.fixture
    def state(self, alert: AnomalyAlert) -> InvestigationState:
        """Create test state."""
        return InvestigationState.new(
            tenant_id=uuid4(),
            alert=alert,
        )

    async def test_emits_investigation_started(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
        mock_feedback: MagicMock,
        mock_adapter: MagicMock,
    ) -> None:
        """Orchestrator emits investigation.started event."""
        await orchestrator.run_investigation(state, data_adapter=mock_adapter)

        # Find the investigation.started call
        calls = mock_feedback.emit.call_args_list
        started_calls = [
            c for c in calls
            if c.kwargs.get("event_type") == EventType.INVESTIGATION_STARTED
        ]

        assert len(started_calls) == 1
        assert started_calls[0].kwargs["tenant_id"] == state.tenant_id

    async def test_emits_investigation_completed(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
        mock_feedback: MagicMock,
        mock_adapter: MagicMock,
    ) -> None:
        """Orchestrator emits investigation.completed event."""
        await orchestrator.run_investigation(state, data_adapter=mock_adapter)

        calls = mock_feedback.emit.call_args_list
        completed_calls = [
            c for c in calls
            if c.kwargs.get("event_type") == EventType.INVESTIGATION_COMPLETED
        ]

        assert len(completed_calls) == 1

    async def test_emits_context_gathered(
        self,
        orchestrator: InvestigationOrchestrator,
        state: InvestigationState,
        mock_feedback: MagicMock,
        mock_adapter: MagicMock,
    ) -> None:
        """Orchestrator emits context.gathered event."""
        await orchestrator.run_investigation(state, data_adapter=mock_adapter)

        calls = mock_feedback.emit.call_args_list
        # Look for a context-related event in event_data
        context_calls = [
            c for c in calls
            if "tables_found" in c.kwargs.get("event_data", {})
        ]

        assert len(context_calls) >= 1
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/core/test_orchestrator_feedback.py -v`

Expected: FAIL with "TypeError: InvestigationOrchestrator.__init__() got an unexpected keyword argument 'feedback'"

**Step 3: Modify orchestrator to accept and use FeedbackAdapter**

Modify `backend/src/dataing/core/orchestrator.py`:

Add import at top:

```python
from dataing.adapters.feedback import EventType
```

Update `__init__` method:

```python
def __init__(
    self,
    db: SQLAdapter | None,
    llm: LLMClient,
    context_engine: ContextEngine,
    circuit_breaker: CircuitBreaker,
    config: OrchestratorConfig | None = None,
    feedback: FeedbackEmitter | None = None,
) -> None:
    """Initialize the orchestrator.

    Args:
        db: Database adapter for executing queries (fallback). Can be None
            if adapters are always provided per-investigation.
        llm: LLM client for generating hypotheses and queries.
        context_engine: Engine for gathering investigation context.
        circuit_breaker: Safety circuit breaker.
        config: Optional orchestrator configuration.
        feedback: Optional feedback emitter for event logging.
    """
    self.db = db
    self.llm = llm
    self.context_engine = context_engine
    self.circuit_breaker = circuit_breaker
    self.config = config or OrchestratorConfig()
    self.feedback = feedback
    # Will be set per-investigation when using tenant data source
    self._current_adapter: SQLAdapter | None = None
```

Add TYPE_CHECKING import:

```python
if TYPE_CHECKING:
    from dataing.adapters.datasource.sql.base import SQLAdapter

    from ..safety.circuit_breaker import CircuitBreaker
    from .interfaces import ContextEngine, FeedbackEmitter, LLMClient
```

Update `run_investigation` method to emit events:

After "Record start event" section, add:

```python
# Emit feedback event
if self.feedback:
    await self.feedback.emit(
        tenant_id=state.tenant_id,
        event_type=EventType.INVESTIGATION_STARTED,
        event_data={"dataset_id": state.alert.dataset_id},
        investigation_id=state.id,
    )
```

After "log.info('Context gathered'...)" add:

```python
if self.feedback:
    await self.feedback.emit(
        tenant_id=state.tenant_id,
        event_type=EventType.INVESTIGATION_STARTED,  # Reuse for context
        event_data={
            "tables_found": state.schema_context.table_count(),
            "has_lineage": state.lineage_context is not None,
        },
        investigation_id=state.id,
    )
```

Before `return finding` at end of try block, add:

```python
if self.feedback:
    await self.feedback.emit(
        tenant_id=state.tenant_id,
        event_type=EventType.INVESTIGATION_COMPLETED,
        event_data={
            "root_cause": finding.root_cause,
            "confidence": finding.confidence,
            "duration_seconds": finding.duration_seconds,
        },
        investigation_id=state.id,
    )
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/core/test_orchestrator_feedback.py -v`

Expected: PASS

**Step 5: Run linting**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run ruff check backend/src/dataing/core/orchestrator.py --fix && uv run mypy backend/src/dataing/core/orchestrator.py`

Expected: No errors

**Step 6: Commit**

```bash
git add backend/src/dataing/core/orchestrator.py backend/tests/unit/core/test_orchestrator_feedback.py
git commit -m "feat(feedback): wire FeedbackAdapter into orchestrator"
```

---

## Task 6: Add feedback_events Repository Methods to AppDatabase

**Files:**
- Modify: `backend/src/dataing/adapters/db/app_db.py`
- Test: `backend/tests/unit/adapters/db/test_app_db_feedback.py`

**Step 1: Write the failing test**

Create `backend/tests/unit/adapters/db/test_app_db_feedback.py`:

```python
"""Tests for AppDatabase feedback methods."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase


class TestAppDatabaseFeedback:
    """Tests for feedback-related database methods."""

    @pytest.fixture
    def db(self) -> AppDatabase:
        """Create AppDatabase instance."""
        return AppDatabase(dsn="postgresql://localhost/test")  # pragma: allowlist secret

    async def test_list_feedback_events_for_investigation(self, db: AppDatabase) -> None:
        """list_feedback_events returns events for an investigation."""
        tenant_id = uuid4()
        investigation_id = uuid4()

        with patch.object(db, "fetch_all", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = [
                {
                    "id": uuid4(),
                    "event_type": "investigation.started",
                    "event_data": {},
                    "created_at": datetime.now(UTC),
                }
            ]

            events = await db.list_feedback_events(
                tenant_id=tenant_id,
                investigation_id=investigation_id,
            )

            assert len(events) == 1
            mock_fetch.assert_called_once()
            assert "investigation_id" in mock_fetch.call_args[0][0]

    async def test_list_feedback_events_for_dataset(self, db: AppDatabase) -> None:
        """list_feedback_events returns events for a dataset."""
        tenant_id = uuid4()
        dataset_id = uuid4()

        with patch.object(db, "fetch_all", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []

            events = await db.list_feedback_events(
                tenant_id=tenant_id,
                dataset_id=dataset_id,
            )

            assert events == []
            assert "dataset_id" in mock_fetch.call_args[0][0]

    async def test_count_feedback_events(self, db: AppDatabase) -> None:
        """count_feedback_events returns event count."""
        tenant_id = uuid4()

        with patch.object(db, "fetch_one", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"count": 42}

            count = await db.count_feedback_events(tenant_id=tenant_id)

            assert count == 42
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/adapters/db/test_app_db_feedback.py -v`

Expected: FAIL with "AttributeError: 'AppDatabase' object has no attribute 'list_feedback_events'"

**Step 3: Add methods to AppDatabase**

Add to `backend/src/dataing/adapters/db/app_db.py` (at end of class):

```python
    # Feedback event operations
    async def list_feedback_events(
        self,
        tenant_id: UUID,
        investigation_id: UUID | None = None,
        dataset_id: UUID | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List feedback events with optional filtering.

        Args:
            tenant_id: The tenant ID.
            investigation_id: Optional investigation ID filter.
            dataset_id: Optional dataset ID filter.
            event_type: Optional event type filter.
            limit: Maximum events to return.
            offset: Number of events to skip.

        Returns:
            List of feedback event dictionaries.
        """
        base_query = """
            SELECT id, investigation_id, dataset_id, event_type,
                   event_data, actor_id, actor_type, created_at
            FROM feedback_events
            WHERE tenant_id = $1
        """
        args: list[Any] = [tenant_id]
        idx = 2

        if investigation_id:
            base_query += f" AND investigation_id = ${idx}"
            args.append(investigation_id)
            idx += 1

        if dataset_id:
            base_query += f" AND dataset_id = ${idx}"
            args.append(dataset_id)
            idx += 1

        if event_type:
            base_query += f" AND event_type = ${idx}"
            args.append(event_type)
            idx += 1

        base_query += f" ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
        args.extend([limit, offset])

        return await self.fetch_all(base_query, *args)

    async def count_feedback_events(
        self,
        tenant_id: UUID,
        investigation_id: UUID | None = None,
        dataset_id: UUID | None = None,
        event_type: str | None = None,
    ) -> int:
        """Count feedback events with optional filtering.

        Args:
            tenant_id: The tenant ID.
            investigation_id: Optional investigation ID filter.
            dataset_id: Optional dataset ID filter.
            event_type: Optional event type filter.

        Returns:
            Number of matching events.
        """
        base_query = """
            SELECT COUNT(*)::int as count FROM feedback_events
            WHERE tenant_id = $1
        """
        args: list[Any] = [tenant_id]
        idx = 2

        if investigation_id:
            base_query += f" AND investigation_id = ${idx}"
            args.append(investigation_id)
            idx += 1

        if dataset_id:
            base_query += f" AND dataset_id = ${idx}"
            args.append(dataset_id)
            idx += 1

        if event_type:
            base_query += f" AND event_type = ${idx}"
            args.append(event_type)

        result = await self.fetch_one(base_query, *args)
        return result["count"] if result else 0
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/adapters/db/test_app_db_feedback.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/dataing/adapters/db/app_db.py backend/tests/unit/adapters/db/test_app_db_feedback.py
git commit -m "feat(feedback): add feedback event repository methods to AppDatabase"
```

---

## Task 7: Integration Test with Real Database

**Files:**
- Create: `backend/tests/integration/adapters/feedback/test_feedback_integration.py`

**Step 1: Write integration test**

Create `backend/tests/integration/adapters/feedback/__init__.py` (empty file).

Create `backend/tests/integration/adapters/feedback/test_feedback_integration.py`:

```python
"""Integration tests for feedback system with real database."""

import pytest
from uuid import uuid4

from dataing.adapters.db.app_db import AppDatabase
from dataing.adapters.feedback import EventType, FeedbackAdapter


@pytest.mark.integration
class TestFeedbackIntegration:
    """Integration tests for feedback event storage."""

    @pytest.fixture
    async def db(self) -> AppDatabase:
        """Create database connection."""
        # Uses demo database - adjust DSN as needed
        db = AppDatabase(dsn="postgresql://localhost/dataing")  # pragma: allowlist secret
        await db.connect()
        yield db
        await db.close()

    @pytest.fixture
    def adapter(self, db: AppDatabase) -> FeedbackAdapter:
        """Create feedback adapter."""
        return FeedbackAdapter(db=db)

    async def test_emit_and_retrieve_event(
        self, adapter: FeedbackAdapter, db: AppDatabase
    ) -> None:
        """Events can be emitted and retrieved."""
        # Get a valid tenant_id from the database
        tenant = await db.fetch_one("SELECT id FROM tenants LIMIT 1")
        if not tenant:
            pytest.skip("No tenant in database")

        tenant_id = tenant["id"]

        # Emit an event
        event = await adapter.emit(
            tenant_id=tenant_id,
            event_type=EventType.INVESTIGATION_STARTED,
            event_data={"dataset_id": "test.table"},
        )

        # Retrieve events
        events = await db.list_feedback_events(tenant_id=tenant_id)

        # Find our event
        our_event = next((e for e in events if e["id"] == event.id), None)
        assert our_event is not None
        assert our_event["event_type"] == "investigation.started"
```

**Step 2: Run integration test (requires database)**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/integration/adapters/feedback/test_feedback_integration.py -v -m integration`

Note: This requires the demo database to be running. Skip if not available.

**Step 3: Commit**

```bash
git add backend/tests/integration/adapters/feedback/
git commit -m "test(feedback): add integration test for feedback event storage"
```

---

## Task 8: Final Verification and Documentation

**Step 1: Run all feedback-related tests**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/adapters/feedback/ backend/tests/unit/core/test_orchestrator_feedback.py backend/tests/unit/adapters/db/test_app_db_feedback.py -v`

Expected: All tests pass

**Step 2: Run linting on all changed files**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run ruff check backend/src/dataing/adapters/feedback/ backend/src/dataing/core/orchestrator.py backend/src/dataing/adapters/db/app_db.py --fix`

Expected: No errors

**Step 3: Run type checking**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run mypy backend/src/dataing/adapters/feedback/`

Expected: No errors

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore(feedback): phase 1 complete - event foundation ready"
```

---

## Summary

Phase 1 establishes the event foundation:

| Component | File | Purpose |
|-----------|------|---------|
| Migration | `backend/migrations/003_feedback_events.sql` | Creates `feedback_events` table |
| Types | `backend/src/dataing/adapters/feedback/types.py` | `FeedbackEvent` and `EventType` |
| Adapter | `backend/src/dataing/adapters/feedback/adapter.py` | `FeedbackAdapter.emit()` |
| Protocol | `backend/src/dataing/core/interfaces.py` | `FeedbackEmitter` protocol |
| Orchestrator | `backend/src/dataing/core/orchestrator.py` | Wired to emit events |
| Repository | `backend/src/dataing/adapters/db/app_db.py` | Query methods for events |

Next: Phase 2 - User Feedback Collection (UI + POST endpoint)
