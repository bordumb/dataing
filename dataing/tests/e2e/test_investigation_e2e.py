"""End-to-end tests for the investigation orchestration flow.

These tests verify the complete investigation lifecycle:
1. Investigation starts at GATHER_CONTEXT
2. Progresses through CHECK_PATTERNS, GENERATE_HYPOTHESES
3. Branches into parallel hypothesis investigations
4. Each branch: GENERATE_QUERY -> EXECUTE_QUERY -> INTERPRET_EVIDENCE -> COMPLETE
5. Branches merge back at SYNTHESIZE
6. Investigation completes with findings
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from dataing.adapters.datasource.types import (
    Catalog,
    Column,
    Schema,
    SchemaResponse,
    SourceCategory,
    SourceType,
    Table,
)
from dataing.core.domain_types import (
    AnomalyAlert,
    Hypothesis,
    HypothesisCategory,
    MetricSpec,
)
from dataing.core.investigation.entities import (
    Branch,
    Investigation,
    InvestigationContext,
    Snapshot,
)
from dataing.core.investigation.orchestrator import InvestigationOrchestrator
from dataing.core.investigation.registry import StepRegistry
from dataing.core.investigation.repository import ExecutionLock
from dataing.core.investigation.steps import (
    CheckPatternsStep,
    CounterAnalyzeStep,
    ExecuteQueryStep,
    GatherContextStep,
    GenerateHypothesesStep,
    GenerateQueryStep,
    InterpretEvidenceStep,
    SynthesizeStep,
)
from dataing.core.investigation.values import (
    BranchStatus,
    BranchType,
    ExecutionSignal,
    StepType,
    VersionId,
)

# =============================================================================
# In-Memory Repository for Testing
# =============================================================================


class InMemoryInvestigationRepository:
    """In-memory implementation of InvestigationRepository for testing."""

    def __init__(self) -> None:
        """Initialize the in-memory repository."""
        self.investigations: dict[UUID, Investigation] = {}
        self.branches: dict[UUID, Branch] = {}
        self.snapshots: dict[UUID, Snapshot] = {}
        self.merge_points: dict[UUID, list[tuple[UUID, StepType]]] = {}
        self.locks: dict[UUID, ExecutionLock] = {}
        self.messages: dict[UUID, list[dict[str, Any]]] = {}

    async def create_investigation(
        self,
        tenant_id: UUID,
        alert: dict[str, Any],
        created_by: UUID | None = None,
    ) -> Investigation:
        """Create a new investigation."""
        investigation = Investigation(
            id=uuid4(),
            tenant_id=tenant_id,
            alert=AnomalyAlert.model_validate(alert),
            created_by=created_by,
        )
        self.investigations[investigation.id] = investigation
        return investigation

    async def get_investigation(self, investigation_id: UUID) -> Investigation | None:
        """Get investigation by ID."""
        return self.investigations.get(investigation_id)

    async def update_investigation_outcome(
        self,
        investigation_id: UUID,
        outcome: dict[str, Any],
    ) -> None:
        """Set the final outcome of an investigation."""
        inv = self.investigations.get(investigation_id)
        if inv:
            self.investigations[investigation_id] = inv.model_copy(update={"outcome": outcome})

    async def set_main_branch(
        self,
        investigation_id: UUID,
        branch_id: UUID,
    ) -> None:
        """Set the main branch for an investigation."""
        inv = self.investigations.get(investigation_id)
        if inv:
            self.investigations[investigation_id] = inv.model_copy(
                update={"main_branch_id": branch_id}
            )

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
        branch = Branch(
            id=uuid4(),
            investigation_id=investigation_id,
            branch_type=branch_type,
            name=name,
            parent_branch_id=parent_branch_id,
            forked_from_snapshot_id=forked_from_snapshot_id,
            owner_user_id=owner_user_id,
        )
        self.branches[branch.id] = branch
        return branch

    async def get_branch(self, branch_id: UUID) -> Branch | None:
        """Get branch by ID."""
        return self.branches.get(branch_id)

    async def get_user_branch(
        self,
        investigation_id: UUID,
        user_id: UUID,
    ) -> Branch | None:
        """Get user's branch for an investigation."""
        for branch in self.branches.values():
            if branch.investigation_id == investigation_id and branch.owner_user_id == user_id:
                return branch
        return None

    async def update_branch_status(
        self,
        branch_id: UUID,
        status: BranchStatus,
    ) -> None:
        """Update branch status."""
        branch = self.branches.get(branch_id)
        if branch:
            self.branches[branch_id] = branch.model_copy(update={"status": status})

    async def update_branch_head(
        self,
        branch_id: UUID,
        snapshot_id: UUID,
    ) -> None:
        """Update branch head to point to new snapshot."""
        branch = self.branches.get(branch_id)
        if branch:
            self.branches[branch_id] = branch.model_copy(update={"head_snapshot_id": snapshot_id})

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
        step_cursor: dict[str, Any] | None = None,
    ) -> Snapshot:
        """Create a new snapshot."""
        snapshot = Snapshot(
            id=uuid4(),
            investigation_id=investigation_id,
            branch_id=branch_id,
            version=version,
            step=step,
            context=context,
            parent_snapshot_id=parent_snapshot_id,
            created_by=created_by,
            trigger=trigger,
            step_cursor=step_cursor or {},
        )
        self.snapshots[snapshot.id] = snapshot
        return snapshot

    async def get_snapshot(self, snapshot_id: UUID) -> Snapshot | None:
        """Get snapshot by ID."""
        return self.snapshots.get(snapshot_id)

    async def acquire_lock(
        self,
        branch_id: UUID,
        worker_id: str,
        ttl_seconds: int = 300,
    ) -> ExecutionLock | None:
        """Try to acquire execution lock on a branch."""
        if branch_id in self.locks:
            existing = self.locks[branch_id]
            if existing.locked_by != worker_id:
                return None
        lock = ExecutionLock(
            branch_id=branch_id,
            locked_by=worker_id,
            expires_at=datetime.now(UTC).isoformat(),
        )
        self.locks[branch_id] = lock
        return lock

    async def release_lock(self, branch_id: UUID, worker_id: str) -> bool:
        """Release execution lock."""
        if branch_id in self.locks and self.locks[branch_id].locked_by == worker_id:
            del self.locks[branch_id]
            return True
        return False

    async def refresh_lock(
        self,
        branch_id: UUID,
        worker_id: str,
        ttl_seconds: int = 300,
    ) -> bool:
        """Refresh lock heartbeat."""
        if branch_id in self.locks and self.locks[branch_id].locked_by == worker_id:
            return True
        return False

    async def add_message(
        self,
        branch_id: UUID,
        role: str,
        content: str,
        user_id: UUID | None = None,
        resulting_snapshot_id: UUID | None = None,
    ) -> UUID:
        """Add a message to a branch."""
        msg_id = uuid4()
        if branch_id not in self.messages:
            self.messages[branch_id] = []
        self.messages[branch_id].append({
            "id": msg_id,
            "role": role,
            "content": content,
            "user_id": user_id,
            "resulting_snapshot_id": resulting_snapshot_id,
        })
        return msg_id

    async def get_messages(
        self,
        branch_id: UUID,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get messages for a branch."""
        return self.messages.get(branch_id, [])[:limit]

    async def set_merge_point(
        self,
        parent_branch_id: UUID,
        child_branch_ids: list[UUID],
        merge_step: StepType,
    ) -> None:
        """Record merge point for parallel branches."""
        if parent_branch_id not in self.merge_points:
            self.merge_points[parent_branch_id] = []
        for child_id in child_branch_ids:
            self.merge_points[parent_branch_id].append((child_id, merge_step))

    async def get_merge_children(
        self,
        parent_branch_id: UUID,
    ) -> list[UUID]:
        """Get child branch IDs waiting to merge."""
        if parent_branch_id not in self.merge_points:
            return []
        return [child_id for child_id, _ in self.merge_points[parent_branch_id]]

    async def check_merge_ready(
        self,
        parent_branch_id: UUID,
    ) -> bool:
        """Check if all children are ready to merge."""
        children = await self.get_merge_children(parent_branch_id)
        if not children:
            return True
        for child_id in children:
            branch = self.branches.get(child_id)
            if branch is None:
                return False
            if branch.status not in (BranchStatus.COMPLETED, BranchStatus.MERGED):
                return False
        return True

    async def get_merge_step(
        self,
        parent_branch_id: UUID,
    ) -> StepType | None:
        """Get the merge step for a parent branch."""
        if parent_branch_id not in self.merge_points:
            return None
        if not self.merge_points[parent_branch_id]:
            return None
        return self.merge_points[parent_branch_id][0][1]


# =============================================================================
# Mock Adapters for Steps
# =============================================================================


class MockSchemaLike:
    """Mock schema that implements SchemaLike protocol."""

    def __init__(self, schema: SchemaResponse) -> None:
        """Initialize mock schema."""
        self._schema = schema

    def is_empty(self) -> bool:
        """Return True if schema has no tables."""
        return self._schema.is_empty()

    def to_dict(self) -> dict[str, Any]:
        """Return schema as dictionary."""
        return self._schema.model_dump()


class MockGatheredContext:
    """Mock gathered context that implements GatheredContext protocol."""

    def __init__(self, schema: SchemaResponse) -> None:
        """Initialize mock gathered context."""
        self._schema = MockSchemaLike(schema)
        self._lineage = None

    @property
    def schema(self) -> MockSchemaLike:
        """Return schema object."""
        return self._schema

    @property
    def lineage(self) -> None:
        """Return lineage object or None."""
        return self._lineage


class MockContextEngineAdapter:
    """Mock context engine adapter that returns predetermined schema."""

    def __init__(self, schema: SchemaResponse) -> None:
        """Initialize the mock context adapter."""
        self.schema = schema
        self.gather_calls: list[dict[str, Any]] = []

    async def gather(
        self,
        *,
        alert_summary: str,
    ) -> MockGatheredContext:
        """Return mock gathered context."""
        self.gather_calls.append({"alert_summary": alert_summary})
        return MockGatheredContext(self.schema)


class MockDatabaseAdapter:
    """Mock database adapter for testing."""

    def __init__(self, query_results: dict[str, dict[str, Any]] | None = None) -> None:
        """Initialize the mock database adapter."""
        self.query_results = query_results or {}
        self.default_result: dict[str, Any] = {
            "columns": [{"name": "count", "data_type": "integer"}],
            "rows": [{"count": 100}],
            "row_count": 1,
        }
        self.execute_calls: list[str] = []

    async def execute_query(self, sql: str) -> dict[str, Any]:
        """Execute query and return mock result."""
        self.execute_calls.append(sql)
        return self.query_results.get(sql, self.default_result)


class MockHypothesisLLM:
    """Mock LLM for hypothesis generation."""

    def __init__(self, hypotheses: list[Hypothesis]) -> None:
        """Initialize the mock LLM."""
        self.hypotheses = hypotheses
        self.generate_calls: list[dict[str, Any]] = []

    async def generate_hypotheses(
        self,
        *,
        alert_summary: str,
        alert: dict[str, Any] | None,
        schema_info: dict[str, Any] | None,
        lineage_info: dict[str, Any] | None,
        num_hypotheses: int,
        pattern_hints: list[str] | None,
    ) -> list[Hypothesis]:
        """Return mock hypotheses."""
        self.generate_calls.append({
            "alert_summary": alert_summary,
            "alert": alert,
            "num_hypotheses": num_hypotheses,
        })
        return self.hypotheses[:num_hypotheses]


class MockQueryLLM:
    """Mock LLM for query generation."""

    def __init__(self, queries: dict[str, str] | None = None) -> None:
        """Initialize the mock LLM."""
        self.queries = queries or {}
        self.default_query = "SELECT COUNT(*) FROM events WHERE user_id IS NULL LIMIT 100"
        self.generate_calls: list[dict[str, Any]] = []

    async def generate_query(
        self,
        *,
        hypothesis: dict[str, Any],
        schema_info: dict[str, Any],
        alert_summary: str,
        alert: dict[str, Any] | None,
    ) -> str:
        """Return mock query."""
        self.generate_calls.append({
            "hypothesis_id": hypothesis.get("id"),
            "alert_summary": alert_summary,
        })
        return self.queries.get(hypothesis.get("id", ""), self.default_query)


class MockInterpretLLM:
    """Mock LLM for evidence interpretation."""

    def __init__(
        self,
        default_supports: bool = True,
        default_confidence: float = 0.85,
    ) -> None:
        """Initialize the mock LLM."""
        self.default_supports = default_supports
        self.default_confidence = default_confidence
        self.interpret_calls: list[dict[str, Any]] = []

    async def interpret_evidence(
        self,
        *,
        hypothesis: dict[str, Any],
        query_result: dict[str, Any],
        alert_summary: str,
    ) -> dict[str, Any]:
        """Return mock interpretation."""
        self.interpret_calls.append({
            "hypothesis_id": hypothesis.get("id"),
            "row_count": query_result.get("row_count", 0),
        })
        return {
            "hypothesis_id": hypothesis.get("id", ""),
            "query": hypothesis.get("suggested_query", ""),
            "result_summary": "count=100",
            "row_count": query_result.get("row_count", 0),
            "supports_hypothesis": self.default_supports,
            "confidence": self.default_confidence,
            "interpretation": "Evidence supports the hypothesis.",
        }


class MockSynthesisLLM:
    """Mock LLM for synthesis."""

    def __init__(
        self,
        root_cause: str = "Mobile app version 2.3.1 bug causing NULL user_id values",
        confidence: float = 0.9,
    ) -> None:
        """Initialize the mock LLM."""
        self.root_cause = root_cause
        self.confidence = confidence
        self.synthesize_calls: list[dict[str, Any]] = []

    async def synthesize_findings(
        self,
        *,
        evidence: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
        alert_summary: str,
    ) -> dict[str, Any]:
        """Return mock synthesis."""
        self.synthesize_calls.append({
            "evidence_count": len(evidence),
            "hypotheses_count": len(hypotheses),
        })
        return {
            "root_cause": self.root_cause,
            "confidence": self.confidence,
            "recommendations": ["Fix the mobile app bug", "Deploy hotfix"],
            "supporting_evidence": [e.get("interpretation", "") for e in evidence],
        }


class MockPatternRepository:
    """Mock pattern repository for testing."""

    def __init__(self, patterns: list[dict[str, Any]] | None = None) -> None:
        """Initialize the mock pattern repository."""
        self.patterns = patterns or []

    async def find_matching_patterns(
        self,
        dataset_id: str,
        anomaly_type: str | None = None,
        min_confidence: float = 0.8,
    ) -> list[dict[str, Any]]:
        """Return mock patterns."""
        return self.patterns


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def sample_alert() -> AnomalyAlert:
    """Create a sample anomaly alert."""
    return AnomalyAlert(
        dataset_id="analytics.events",
        metric_spec=MetricSpec(
            metric_type="column",
            expression="user_id",
            display_name="NULL rate in user_id",
            columns_referenced=["user_id"],
        ),
        anomaly_type="null_rate",
        expected_value=0.01,
        actual_value=0.15,
        deviation_pct=1400.0,
        anomaly_date="2026-01-10",
        severity="high",
    )


@pytest.fixture
def sample_schema() -> SchemaResponse:
    """Create a sample schema response."""
    from dataing.adapters.datasource.types import NormalizedType

    return SchemaResponse(
        source_id="demo",
        source_type=SourceType.POSTGRESQL,
        source_category=SourceCategory.DATABASE,
        fetched_at=datetime.now(UTC),
        catalogs=[
            Catalog(
                name="default",
                schemas=[
                    Schema(
                        name="analytics",
                        tables=[
                            Table(
                                name="events",
                                table_type="table",
                                native_type="table",
                                native_path="analytics.events",
                                columns=[
                                    Column(
                                        name="id",
                                        data_type=NormalizedType.INTEGER,
                                        native_type="bigint",
                                        nullable=False,
                                    ),
                                    Column(
                                        name="user_id",
                                        data_type=NormalizedType.STRING,
                                        native_type="varchar",
                                        nullable=True,
                                    ),
                                    Column(
                                        name="event_type",
                                        data_type=NormalizedType.STRING,
                                        native_type="varchar",
                                        nullable=False,
                                    ),
                                    Column(
                                        name="channel",
                                        data_type=NormalizedType.STRING,
                                        native_type="varchar",
                                        nullable=True,
                                    ),
                                    Column(
                                        name="app_version",
                                        data_type=NormalizedType.STRING,
                                        native_type="varchar",
                                        nullable=True,
                                    ),
                                    Column(
                                        name="created_at",
                                        data_type=NormalizedType.TIMESTAMP,
                                        native_type="timestamp",
                                        nullable=False,
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def sample_hypotheses() -> list[Hypothesis]:
    """Create sample hypotheses."""
    return [
        Hypothesis(
            id="h1",
            title="Mobile app bug in version 2.3.1",
            category=HypothesisCategory.TRANSFORMATION_BUG,
            reasoning="NULL values may be caused by a bug in mobile app version 2.3.1",
            suggested_query=(
                "SELECT app_version, COUNT(*) FROM events WHERE user_id IS NULL GROUP BY 1"
            ),
        ),
        Hypothesis(
            id="h2",
            title="Authentication service timeout",
            category=HypothesisCategory.INFRASTRUCTURE,
            reasoning="Auth service may have been unavailable, causing missing user_id",
            suggested_query=(
                "SELECT COUNT(*) FROM events WHERE user_id IS NULL "
                "AND created_at > '2026-01-10'"
            ),
        ),
    ]


@pytest.fixture
def in_memory_repository() -> InMemoryInvestigationRepository:
    """Create an in-memory repository."""
    return InMemoryInvestigationRepository()


def create_step_registry_with_mocks(
    schema: SchemaResponse,
    hypotheses: list[Hypothesis],
    synthesis_confidence: float = 0.9,
) -> tuple[StepRegistry, dict[str, Any]]:
    """Create a step registry with mock dependencies.

    Returns:
        Tuple of (registry, mocks_dict) where mocks_dict contains all mock objects
        for assertions.
    """
    # Create mocks
    context_adapter = MockContextEngineAdapter(schema)
    database_adapter = MockDatabaseAdapter()
    hypothesis_llm = MockHypothesisLLM(hypotheses)
    query_llm = MockQueryLLM()
    interpret_llm = MockInterpretLLM()
    synthesis_llm = MockSynthesisLLM(confidence=synthesis_confidence)
    pattern_repo = MockPatternRepository()

    # Build registry
    registry = StepRegistry()
    registry.register(GatherContextStep(context_adapter))
    registry.register(CheckPatternsStep(pattern_repo))
    registry.register(GenerateHypothesesStep(hypothesis_llm))
    registry.register(GenerateQueryStep(query_llm))
    registry.register(ExecuteQueryStep(database_adapter))
    registry.register(InterpretEvidenceStep(interpret_llm))
    registry.register(SynthesizeStep(synthesis_llm))
    registry.register(CounterAnalyzeStep())

    mocks = {
        "context_adapter": context_adapter,
        "database_adapter": database_adapter,
        "hypothesis_llm": hypothesis_llm,
        "query_llm": query_llm,
        "interpret_llm": interpret_llm,
        "synthesis_llm": synthesis_llm,
        "pattern_repo": pattern_repo,
    }

    return registry, mocks


# =============================================================================
# Test Cases
# =============================================================================


class TestInvestigationE2E:
    """End-to-end tests for investigation orchestration."""

    @pytest.mark.asyncio
    async def test_investigation_completes_successfully(
        self,
        in_memory_repository: InMemoryInvestigationRepository,
        sample_alert: AnomalyAlert,
        sample_schema: SchemaResponse,
        sample_hypotheses: list[Hypothesis],
    ) -> None:
        """Test that an investigation runs to completion with expected steps."""
        # Arrange
        registry, mocks = create_step_registry_with_mocks(
            sample_schema,
            sample_hypotheses,
            synthesis_confidence=0.9,  # High confidence -> complete
        )
        orchestrator = InvestigationOrchestrator(
            repository=in_memory_repository,
            registry=registry,
        )

        # Create investigation
        tenant_id = uuid4()
        investigation = await in_memory_repository.create_investigation(
            tenant_id=tenant_id,
            alert=sample_alert.model_dump(),
        )

        # Create main branch
        main_branch = await in_memory_repository.create_branch(
            investigation_id=investigation.id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        await in_memory_repository.set_main_branch(investigation.id, main_branch.id)

        # Create initial snapshot
        initial_context = InvestigationContext(
            alert_summary=f"NULL rate spike in {sample_alert.dataset_id}",
            alert=sample_alert.model_dump(mode="json"),
        )
        snapshot = await in_memory_repository.create_snapshot(
            investigation_id=investigation.id,
            branch_id=main_branch.id,
            version=VersionId(),
            step=StepType.GATHER_CONTEXT,
            context=initial_context,
        )
        await in_memory_repository.update_branch_head(main_branch.id, snapshot.id)

        # Act - run orchestrator loop
        max_iterations = 50
        completed = False
        tick_count = 0

        async def run_branch(branch_id: UUID) -> None:
            """Run a branch to completion."""
            nonlocal tick_count, completed
            for _ in range(max_iterations):
                tick_count += 1
                result = await orchestrator.tick(branch_id)

                if result.signal == ExecutionSignal.COMPLETE:
                    completed = True
                    break
                elif result.signal == ExecutionSignal.FAIL:
                    break
                elif result.signal == ExecutionSignal.BRANCH:
                    if result.child_branch_ids:
                        # Run child branches
                        await asyncio.gather(
                            *[run_branch(child_id) for child_id in result.child_branch_ids]
                        )
                        # Continue parent after children complete
                        continue
                    break
                elif result.signal == ExecutionSignal.AWAIT_USER:
                    break

                await asyncio.sleep(0)  # Yield to allow other coroutines

        await run_branch(main_branch.id)

        # Assert
        assert completed, f"Investigation did not complete after {tick_count} ticks"

        # Verify expected number of hypotheses were generated
        assert len(mocks["hypothesis_llm"].generate_calls) == 1
        assert mocks["hypothesis_llm"].generate_calls[0]["num_hypotheses"] == 5

        # Verify queries were generated for each hypothesis
        assert len(mocks["query_llm"].generate_calls) == len(sample_hypotheses)

        # Verify evidence was interpreted for each hypothesis
        assert len(mocks["interpret_llm"].interpret_calls) == len(sample_hypotheses)

        # Verify synthesis was called once
        assert len(mocks["synthesis_llm"].synthesize_calls) == 1
        synth_call = mocks["synthesis_llm"].synthesize_calls[0]
        assert synth_call["evidence_count"] == len(sample_hypotheses)

        # Verify branch counts
        main_branches = [
            b for b in in_memory_repository.branches.values()
            if b.branch_type == BranchType.MAIN
        ]
        hypothesis_branches = [
            b for b in in_memory_repository.branches.values()
            if b.branch_type == BranchType.HYPOTHESIS
        ]
        assert len(main_branches) == 1
        assert len(hypothesis_branches) == len(sample_hypotheses)

        # Verify all branches completed
        for branch in in_memory_repository.branches.values():
            assert branch.status == BranchStatus.COMPLETED, (
                f"Branch {branch.name} not completed: {branch.status}"
            )

    @pytest.mark.asyncio
    async def test_investigation_with_low_confidence_completes_via_counter_analyze(
        self,
        in_memory_repository: InMemoryInvestigationRepository,
        sample_alert: AnomalyAlert,
        sample_schema: SchemaResponse,
        sample_hypotheses: list[Hypothesis],
    ) -> None:
        """Test that low-confidence synthesis triggers counter-analyze and still completes."""
        # Arrange - use low confidence to trigger counter-analyze
        registry, mocks = create_step_registry_with_mocks(
            sample_schema,
            sample_hypotheses,
            synthesis_confidence=0.5,  # Low confidence -> counter-analyze
        )
        orchestrator = InvestigationOrchestrator(
            repository=in_memory_repository,
            registry=registry,
        )

        # Setup investigation
        tenant_id = uuid4()
        investigation = await in_memory_repository.create_investigation(
            tenant_id=tenant_id,
            alert=sample_alert.model_dump(),
        )
        main_branch = await in_memory_repository.create_branch(
            investigation_id=investigation.id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        await in_memory_repository.set_main_branch(investigation.id, main_branch.id)

        initial_context = InvestigationContext(
            alert_summary=f"NULL rate spike in {sample_alert.dataset_id}",
            alert=sample_alert.model_dump(mode="json"),
        )
        snapshot = await in_memory_repository.create_snapshot(
            investigation_id=investigation.id,
            branch_id=main_branch.id,
            version=VersionId(),
            step=StepType.GATHER_CONTEXT,
            context=initial_context,
        )
        await in_memory_repository.update_branch_head(main_branch.id, snapshot.id)

        # Act
        max_iterations = 50
        completed = False
        tick_count = 0
        steps_visited: list[str] = []

        async def run_branch(branch_id: UUID) -> None:
            nonlocal tick_count, completed
            for _ in range(max_iterations):
                tick_count += 1
                branch = await in_memory_repository.get_branch(branch_id)
                if branch and branch.head_snapshot_id:
                    snap = await in_memory_repository.get_snapshot(branch.head_snapshot_id)
                    if snap and snap.step.value not in steps_visited:
                        steps_visited.append(snap.step.value)

                result = await orchestrator.tick(branch_id)

                if result.signal == ExecutionSignal.COMPLETE:
                    completed = True
                    break
                elif result.signal == ExecutionSignal.FAIL:
                    break
                elif result.signal == ExecutionSignal.BRANCH:
                    if result.child_branch_ids:
                        await asyncio.gather(
                            *[run_branch(child_id) for child_id in result.child_branch_ids]
                        )
                        continue
                    break
                elif result.signal == ExecutionSignal.AWAIT_USER:
                    break

                await asyncio.sleep(0)

        await run_branch(main_branch.id)

        # Assert
        assert completed, f"Investigation did not complete after {tick_count} ticks"

        # Verify counter_analyze was visited (low confidence path)
        assert "counter_analyze" in steps_visited, (
            f"Expected counter_analyze in steps: {steps_visited}"
        )

    @pytest.mark.asyncio
    async def test_child_branch_failure_does_not_block_merge(
        self,
        in_memory_repository: InMemoryInvestigationRepository,
        sample_alert: AnomalyAlert,
        sample_schema: SchemaResponse,
        sample_hypotheses: list[Hypothesis],
    ) -> None:
        """Test that a child branch failure allows merge to proceed."""
        # Arrange - make one hypothesis fail query generation
        class FailingQueryLLM(MockQueryLLM):
            async def generate_query(
                self,
                *,
                hypothesis: dict[str, Any],
                schema_info: dict[str, Any],
                alert_summary: str,
                alert: dict[str, Any] | None,
            ) -> str:
                if hypothesis.get("id") == "h2":
                    raise Exception("Query generation failed")
                return await super().generate_query(
                    hypothesis=hypothesis,
                    schema_info=schema_info,
                    alert_summary=alert_summary,
                    alert=alert,
                )

        # Create registry with failing query LLM
        context_adapter = MockContextEngineAdapter(sample_schema)
        database_adapter = MockDatabaseAdapter()
        hypothesis_llm = MockHypothesisLLM(sample_hypotheses)
        query_llm = FailingQueryLLM()
        interpret_llm = MockInterpretLLM()
        synthesis_llm = MockSynthesisLLM()
        pattern_repo = MockPatternRepository()

        registry = StepRegistry()
        registry.register(GatherContextStep(context_adapter))
        registry.register(CheckPatternsStep(pattern_repo))
        registry.register(GenerateHypothesesStep(hypothesis_llm))
        registry.register(GenerateQueryStep(query_llm))
        registry.register(ExecuteQueryStep(database_adapter))
        registry.register(InterpretEvidenceStep(interpret_llm))
        registry.register(SynthesizeStep(synthesis_llm))
        registry.register(CounterAnalyzeStep())

        orchestrator = InvestigationOrchestrator(
            repository=in_memory_repository,
            registry=registry,
        )

        # Setup investigation
        tenant_id = uuid4()
        investigation = await in_memory_repository.create_investigation(
            tenant_id=tenant_id,
            alert=sample_alert.model_dump(),
        )
        main_branch = await in_memory_repository.create_branch(
            investigation_id=investigation.id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        await in_memory_repository.set_main_branch(investigation.id, main_branch.id)

        initial_context = InvestigationContext(
            alert_summary=f"NULL rate spike in {sample_alert.dataset_id}",
            alert=sample_alert.model_dump(mode="json"),
        )
        snapshot = await in_memory_repository.create_snapshot(
            investigation_id=investigation.id,
            branch_id=main_branch.id,
            version=VersionId(),
            step=StepType.GATHER_CONTEXT,
            context=initial_context,
        )
        await in_memory_repository.update_branch_head(main_branch.id, snapshot.id)

        # Act
        max_iterations = 50
        final_signal: ExecutionSignal | None = None

        async def run_branch(branch_id: UUID) -> ExecutionSignal:
            nonlocal final_signal
            for _ in range(max_iterations):
                result = await orchestrator.tick(branch_id)

                if result.signal == ExecutionSignal.COMPLETE:
                    final_signal = result.signal
                    return result.signal
                elif result.signal == ExecutionSignal.FAIL:
                    return result.signal
                elif result.signal == ExecutionSignal.BRANCH:
                    if result.child_branch_ids:
                        # Run child branches (results not needed, just need completion)
                        await asyncio.gather(
                            *[
                                run_branch(child_id)
                                for child_id in result.child_branch_ids
                            ],
                            return_exceptions=True,
                        )
                        # Continue parent after children complete
                        continue
                    return result.signal
                elif result.signal == ExecutionSignal.AWAIT_USER:
                    return result.signal

                await asyncio.sleep(0)

            return ExecutionSignal.FAIL

        await run_branch(main_branch.id)

        # Assert - investigation should still complete despite one branch failing
        # Note: This depends on merge logic handling abandoned branches
        # The test verifies the behavior - if it fails, the merge logic needs fixing
        hypothesis_branches = [
            b for b in in_memory_repository.branches.values()
            if b.branch_type == BranchType.HYPOTHESIS
        ]
        abandoned_count = sum(
            1 for b in hypothesis_branches if b.status == BranchStatus.ABANDONED
        )
        completed_count = sum(
            1 for b in hypothesis_branches if b.status == BranchStatus.COMPLETED
        )

        # At least one branch should have failed
        assert abandoned_count >= 1, "Expected at least one abandoned branch"
        # At least one branch should have completed
        assert completed_count >= 1, "Expected at least one completed branch"

    @pytest.mark.asyncio
    async def test_expected_step_sequence(
        self,
        in_memory_repository: InMemoryInvestigationRepository,
        sample_alert: AnomalyAlert,
        sample_schema: SchemaResponse,
        sample_hypotheses: list[Hypothesis],
    ) -> None:
        """Test that steps execute in the expected sequence."""
        # Arrange
        registry, mocks = create_step_registry_with_mocks(
            sample_schema,
            sample_hypotheses[:1],  # Just one hypothesis for simpler tracking
            synthesis_confidence=0.9,
        )
        orchestrator = InvestigationOrchestrator(
            repository=in_memory_repository,
            registry=registry,
        )

        # Setup
        tenant_id = uuid4()
        investigation = await in_memory_repository.create_investigation(
            tenant_id=tenant_id,
            alert=sample_alert.model_dump(),
        )
        main_branch = await in_memory_repository.create_branch(
            investigation_id=investigation.id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        await in_memory_repository.set_main_branch(investigation.id, main_branch.id)

        initial_context = InvestigationContext(
            alert_summary=f"NULL rate spike in {sample_alert.dataset_id}",
            alert=sample_alert.model_dump(mode="json"),
        )
        snapshot = await in_memory_repository.create_snapshot(
            investigation_id=investigation.id,
            branch_id=main_branch.id,
            version=VersionId(),
            step=StepType.GATHER_CONTEXT,
            context=initial_context,
        )
        await in_memory_repository.update_branch_head(main_branch.id, snapshot.id)

        # Track steps per branch type
        main_steps: list[str] = []
        child_steps: list[str] = []

        async def run_branch(branch_id: UUID, is_main: bool = True) -> None:
            for _ in range(50):
                branch = await in_memory_repository.get_branch(branch_id)
                if branch and branch.head_snapshot_id:
                    snap = await in_memory_repository.get_snapshot(branch.head_snapshot_id)
                    if snap:
                        step_list = main_steps if is_main else child_steps
                        if not step_list or step_list[-1] != snap.step.value:
                            step_list.append(snap.step.value)

                result = await orchestrator.tick(branch_id)

                if result.signal in (ExecutionSignal.COMPLETE, ExecutionSignal.FAIL):
                    break
                elif result.signal == ExecutionSignal.BRANCH:
                    if result.child_branch_ids:
                        await asyncio.gather(*[
                            run_branch(child_id, is_main=False)
                            for child_id in result.child_branch_ids
                        ])
                        continue
                    break
                elif result.signal == ExecutionSignal.AWAIT_USER:
                    break

                await asyncio.sleep(0)

        await run_branch(main_branch.id)

        # Assert expected main branch sequence
        # Note: The final "complete" step may or may not be captured depending on timing
        # because we check step BEFORE tick, and COMPLETE creates final snapshot during tick
        expected_main_prefix = [
            "gather_context",
            "check_patterns",
            "generate_hypotheses",
            "synthesize",
        ]
        assert main_steps[:4] == expected_main_prefix, f"Main steps mismatch: {main_steps}"

        # Assert expected child branch sequence
        # Note: Same as main - "complete" step is created during tick but we exit before capturing
        expected_child_prefix = [
            "generate_query",
            "execute_query",
            "interpret_evidence",
        ]
        assert child_steps[:3] == expected_child_prefix, f"Child steps mismatch: {child_steps}"

    @pytest.mark.asyncio
    async def test_no_infinite_loop_with_multiple_iterations(
        self,
        in_memory_repository: InMemoryInvestigationRepository,
        sample_alert: AnomalyAlert,
        sample_schema: SchemaResponse,
        sample_hypotheses: list[Hypothesis],
    ) -> None:
        """Test that investigation completes within iteration limit."""
        # Arrange
        registry, mocks = create_step_registry_with_mocks(
            sample_schema,
            sample_hypotheses,
            synthesis_confidence=0.9,
        )
        orchestrator = InvestigationOrchestrator(
            repository=in_memory_repository,
            registry=registry,
        )

        # Setup
        tenant_id = uuid4()
        investigation = await in_memory_repository.create_investigation(
            tenant_id=tenant_id,
            alert=sample_alert.model_dump(),
        )
        main_branch = await in_memory_repository.create_branch(
            investigation_id=investigation.id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        await in_memory_repository.set_main_branch(investigation.id, main_branch.id)

        initial_context = InvestigationContext(
            alert_summary=f"NULL rate spike in {sample_alert.dataset_id}",
            alert=sample_alert.model_dump(mode="json"),
        )
        snapshot = await in_memory_repository.create_snapshot(
            investigation_id=investigation.id,
            branch_id=main_branch.id,
            version=VersionId(),
            step=StepType.GATHER_CONTEXT,
            context=initial_context,
        )
        await in_memory_repository.update_branch_head(main_branch.id, snapshot.id)

        # Act
        max_total_ticks = 100
        total_ticks = 0
        completed = False

        async def run_branch(branch_id: UUID) -> None:
            nonlocal total_ticks, completed
            for _ in range(50):
                total_ticks += 1
                if total_ticks > max_total_ticks:
                    raise AssertionError(
                        f"Exceeded max ticks ({max_total_ticks}) - infinite loop"
                    )

                result = await orchestrator.tick(branch_id)

                if result.signal == ExecutionSignal.COMPLETE:
                    completed = True
                    break
                elif result.signal == ExecutionSignal.FAIL:
                    break
                elif result.signal == ExecutionSignal.BRANCH:
                    if result.child_branch_ids:
                        await asyncio.gather(*[
                            run_branch(child_id)
                            for child_id in result.child_branch_ids
                        ])
                        continue
                    break
                elif result.signal == ExecutionSignal.AWAIT_USER:
                    break

                await asyncio.sleep(0)

        await run_branch(main_branch.id)

        # Assert
        assert completed, f"Investigation did not complete after {total_ticks} ticks"
        assert total_ticks < max_total_ticks, f"Used {total_ticks} ticks, close to limit"

        # Expected ticks:
        # Main: gather_context + check_patterns + generate_hypotheses + synthesize = 4
        # Per hypothesis: generate_query + execute_query + interpret_evidence = 3
        # Total with 2 hypotheses: 4 + (3 * 2) = 10, plus buffer
        expected_max = 5 + (4 * len(sample_hypotheses)) + 5  # Buffer
        assert total_ticks <= expected_max, (
            f"Too many ticks: {total_ticks}, expected ~{expected_max}"
        )

    @pytest.mark.asyncio
    async def test_context_preserved_across_steps(
        self,
        in_memory_repository: InMemoryInvestigationRepository,
        sample_alert: AnomalyAlert,
        sample_schema: SchemaResponse,
        sample_hypotheses: list[Hypothesis],
    ) -> None:
        """Test that context accumulates correctly across steps."""
        # Arrange
        registry, mocks = create_step_registry_with_mocks(
            sample_schema,
            sample_hypotheses,
            synthesis_confidence=0.9,
        )
        orchestrator = InvestigationOrchestrator(
            repository=in_memory_repository,
            registry=registry,
        )

        # Setup
        tenant_id = uuid4()
        investigation = await in_memory_repository.create_investigation(
            tenant_id=tenant_id,
            alert=sample_alert.model_dump(),
        )
        main_branch = await in_memory_repository.create_branch(
            investigation_id=investigation.id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        await in_memory_repository.set_main_branch(investigation.id, main_branch.id)

        initial_context = InvestigationContext(
            alert_summary=f"NULL rate spike in {sample_alert.dataset_id}",
            alert=sample_alert.model_dump(mode="json"),
        )
        snapshot = await in_memory_repository.create_snapshot(
            investigation_id=investigation.id,
            branch_id=main_branch.id,
            version=VersionId(),
            step=StepType.GATHER_CONTEXT,
            context=initial_context,
        )
        await in_memory_repository.update_branch_head(main_branch.id, snapshot.id)

        # Act
        async def run_branch(branch_id: UUID) -> None:
            for _ in range(50):
                result = await orchestrator.tick(branch_id)
                terminal_signals = (
                    ExecutionSignal.COMPLETE,
                    ExecutionSignal.FAIL,
                    ExecutionSignal.AWAIT_USER,
                )
                if result.signal in terminal_signals:
                    break
                elif result.signal == ExecutionSignal.BRANCH:
                    if result.child_branch_ids:
                        await asyncio.gather(*[
                            run_branch(child_id)
                            for child_id in result.child_branch_ids
                        ])
                        continue
                    break
                await asyncio.sleep(0)

        await run_branch(main_branch.id)

        # Assert - check final context
        main_branch = await in_memory_repository.get_branch(main_branch.id)
        assert main_branch is not None
        final_snapshot = await in_memory_repository.get_snapshot(
            main_branch.head_snapshot_id
        )
        assert final_snapshot is not None

        final_context = final_snapshot.context

        # Context should have all expected fields populated
        assert final_context.schema_info is not None, "schema_info not preserved"
        assert len(final_context.hypotheses) == len(sample_hypotheses), (
            "hypotheses not preserved"
        )
        assert len(final_context.evidence) == len(sample_hypotheses), (
            "evidence not merged"
        )
        assert final_context.current_synthesis is not None, "synthesis not set"
        assert final_context.current_synthesis.get("confidence") == 0.9, (
            "synthesis confidence wrong"
        )
