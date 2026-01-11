"""Integration tests for the unified investigation system.

These tests verify that all components work together correctly:
- Steps execute and produce correct signals
- Registry wires steps correctly
- Orchestrator handles signals appropriately
- Branching and merging flows work end-to-end
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from dataing.core.domain_types import Hypothesis, HypothesisCategory
from dataing.core.investigation.entities import (
    Branch,
    InvestigationContext,
    Snapshot,
)
from dataing.core.investigation.orchestrator import InvestigationOrchestrator, TickResult
from dataing.core.investigation.registry import StepRegistry
from dataing.core.investigation.repository import ExecutionLock
from dataing.core.investigation.steps import (
    CheckPatternsStep,
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
# Test Fixtures - Mock Implementations of Dependencies
# =============================================================================


class MockSchema:
    """Mock schema object for testing."""

    def __init__(self, tables: dict[str, list[str]] | None = None) -> None:
        """Initialize mock schema."""
        default_tables = {"public.orders": ["id", "user_id", "total"]}
        self._tables = tables if tables is not None else default_tables

    def is_empty(self) -> bool:
        """Return True if schema has no tables."""
        return len(self._tables) == 0

    def to_dict(self) -> dict[str, Any]:
        """Return schema as dictionary."""
        return {"tables": self._tables}


class MockLineage:
    """Mock lineage object for testing."""

    def __init__(self, target: str = "public.orders") -> None:
        """Initialize mock lineage."""
        self._target = target

    def to_dict(self) -> dict[str, Any]:
        """Return lineage as dictionary."""
        return {"target": self._target, "upstream": [], "downstream": []}


class MockGatheredContext:
    """Mock gathered context for testing."""

    def __init__(
        self,
        schema: MockSchema | None = None,
        lineage: MockLineage | None = None,
    ) -> None:
        """Initialize mock gathered context."""
        self._schema = schema or MockSchema()
        self._lineage = lineage

    @property
    def schema(self) -> MockSchema:
        """Return schema object."""
        return self._schema

    @property
    def lineage(self) -> MockLineage | None:
        """Return lineage object or None."""
        return self._lineage


class MockContextEngine:
    """Mock context engine for testing."""

    def __init__(self, gathered: MockGatheredContext | None = None) -> None:
        """Initialize mock context engine."""
        self._gathered = gathered or MockGatheredContext()

    async def gather(self, *, alert_summary: str) -> MockGatheredContext:
        """Gather schema and lineage context."""
        return self._gathered


class MockPatternRepository:
    """Mock pattern repository for testing."""

    def __init__(self, patterns: list[dict[str, Any]] | None = None) -> None:
        """Initialize mock pattern repository."""
        self._patterns = patterns or []

    async def find_matching_patterns(
        self,
        *,
        dataset_id: str,
        anomaly_type: str | None = None,
        metric_name: str | None = None,
        min_confidence: float = 0.8,
    ) -> list[dict[str, Any]]:
        """Find patterns that match the given criteria."""
        return self._patterns


class MockLLM:
    """Mock LLM client for testing."""

    def __init__(self) -> None:
        """Initialize mock LLM."""
        self._hypotheses: list[Hypothesis] = []
        self._query = "SELECT COUNT(*) FROM orders LIMIT 100"
        self._evidence: dict[str, Any] = {}
        self._synthesis: dict[str, Any] = {}

    def set_hypotheses(self, hypotheses: list[Hypothesis]) -> None:
        """Set hypotheses to return."""
        self._hypotheses = hypotheses

    def set_query(self, query: str) -> None:
        """Set query to return."""
        self._query = query

    def set_evidence(self, evidence: dict[str, Any]) -> None:
        """Set evidence to return."""
        self._evidence = evidence

    def set_synthesis(self, synthesis: dict[str, Any]) -> None:
        """Set synthesis to return."""
        self._synthesis = synthesis

    async def generate_hypotheses(
        self,
        *,
        alert_summary: str,
        schema_info: dict[str, Any] | None,
        lineage_info: dict[str, Any] | None,
        num_hypotheses: int,
        pattern_hints: list[str] | None,
    ) -> list[Hypothesis]:
        """Generate hypotheses about potential root causes."""
        return self._hypotheses

    async def generate_query(
        self,
        *,
        hypothesis: dict[str, Any],
        schema_info: dict[str, Any],
        alert_summary: str,
    ) -> str:
        """Generate a SQL query to test the hypothesis."""
        return self._query

    async def interpret_evidence(
        self,
        *,
        hypothesis: dict[str, Any],
        query_result: dict[str, Any],
        alert_summary: str,
    ) -> dict[str, Any]:
        """Interpret query results as evidence for/against hypothesis."""
        return self._evidence

    async def synthesize_findings(
        self,
        *,
        evidence: list[dict[str, Any]],
        hypotheses: list[dict[str, Any]],
        alert_summary: str,
    ) -> dict[str, Any]:
        """Synthesize evidence into root cause finding."""
        return self._synthesis


class MockDatabase:
    """Mock database adapter for testing."""

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        """Initialize mock database."""
        self._result = result or {"columns": ["count"], "rows": [{"count": 100}], "row_count": 1}

    async def execute_query(self, sql: str) -> dict[str, Any]:
        """Execute SQL query and return results."""
        return self._result


class MockInvestigationRepository:
    """In-memory mock repository for integration tests."""

    def __init__(self) -> None:
        """Initialize mock repository."""
        self._branches: dict[UUID, Branch] = {}
        self._snapshots: dict[UUID, Snapshot] = {}
        self._locks: dict[UUID, str] = {}
        self._merge_points: dict[UUID, tuple[list[UUID], StepType]] = {}
        self._investigation_outcomes: dict[UUID, dict[str, Any]] = {}

    async def get_branch(self, branch_id: UUID) -> Branch | None:
        """Get branch by ID."""
        return self._branches.get(branch_id)

    async def get_snapshot(self, snapshot_id: UUID) -> Snapshot | None:
        """Get snapshot by ID."""
        return self._snapshots.get(snapshot_id)

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
            status=BranchStatus.ACTIVE,
        )
        self._branches[branch.id] = branch
        return branch

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
        self._snapshots[snapshot.id] = snapshot
        return snapshot

    async def update_branch_head(self, branch_id: UUID, snapshot_id: UUID) -> None:
        """Update branch head to point to new snapshot."""
        if branch_id in self._branches:
            old_branch = self._branches[branch_id]
            self._branches[branch_id] = Branch(
                id=old_branch.id,
                investigation_id=old_branch.investigation_id,
                branch_type=old_branch.branch_type,
                name=old_branch.name,
                parent_branch_id=old_branch.parent_branch_id,
                forked_from_snapshot_id=old_branch.forked_from_snapshot_id,
                owner_user_id=old_branch.owner_user_id,
                head_snapshot_id=snapshot_id,
                status=old_branch.status,
                created_at=old_branch.created_at,
                updated_at=old_branch.updated_at,
            )

    async def update_branch_status(self, branch_id: UUID, status: BranchStatus) -> None:
        """Update branch status."""
        if branch_id in self._branches:
            old_branch = self._branches[branch_id]
            self._branches[branch_id] = Branch(
                id=old_branch.id,
                investigation_id=old_branch.investigation_id,
                branch_type=old_branch.branch_type,
                name=old_branch.name,
                parent_branch_id=old_branch.parent_branch_id,
                forked_from_snapshot_id=old_branch.forked_from_snapshot_id,
                owner_user_id=old_branch.owner_user_id,
                head_snapshot_id=old_branch.head_snapshot_id,
                status=status,
                created_at=old_branch.created_at,
                updated_at=old_branch.updated_at,
            )

    async def update_investigation_outcome(
        self,
        investigation_id: UUID,
        outcome: dict[str, Any],
    ) -> None:
        """Set the final outcome of an investigation."""
        self._investigation_outcomes[investigation_id] = outcome

    async def acquire_lock(
        self,
        branch_id: UUID,
        worker_id: str,
        ttl_seconds: int = 300,
    ) -> ExecutionLock | None:
        """Try to acquire execution lock on a branch."""
        if branch_id in self._locks and self._locks[branch_id] != worker_id:
            return None
        self._locks[branch_id] = worker_id
        return ExecutionLock(
            branch_id=branch_id,
            locked_by=worker_id,
            expires_at="2030-01-01T00:00:00Z",
        )

    async def release_lock(self, branch_id: UUID, worker_id: str) -> bool:
        """Release execution lock."""
        if branch_id in self._locks and self._locks[branch_id] == worker_id:
            del self._locks[branch_id]
            return True
        return False

    async def set_merge_point(
        self,
        parent_branch_id: UUID,
        child_branch_ids: list[UUID],
        merge_step: StepType,
    ) -> None:
        """Record merge point for parallel branches."""
        self._merge_points[parent_branch_id] = (child_branch_ids, merge_step)

    async def get_merge_children(self, parent_branch_id: UUID) -> list[UUID]:
        """Get child branch IDs waiting to merge."""
        if parent_branch_id in self._merge_points:
            return self._merge_points[parent_branch_id][0]
        return []

    async def check_merge_ready(self, parent_branch_id: UUID) -> bool:
        """Check if all children are ready to merge."""
        if parent_branch_id not in self._merge_points:
            return False
        child_ids = self._merge_points[parent_branch_id][0]
        for child_id in child_ids:
            branch = self._branches.get(child_id)
            if branch is None or branch.status != BranchStatus.COMPLETED:
                return False
        return True

    # Helper methods for tests
    def add_branch(self, branch: Branch) -> None:
        """Add a branch directly (for test setup)."""
        self._branches[branch.id] = branch

    def add_snapshot(self, snapshot: Snapshot) -> None:
        """Add a snapshot directly (for test setup)."""
        self._snapshots[snapshot.id] = snapshot


# =============================================================================
# Scenario 1: Simple Investigation Flow (No Branching)
# =============================================================================


class TestSimpleInvestigationFlow:
    """Test a linear flow: GatherContext -> CheckPatterns -> GenerateHypotheses."""

    @pytest.fixture
    def context_engine(self) -> MockContextEngine:
        """Create mock context engine."""
        return MockContextEngine()

    @pytest.fixture
    def pattern_repository(self) -> MockPatternRepository:
        """Create mock pattern repository with no patterns."""
        return MockPatternRepository(patterns=[])

    @pytest.fixture
    def llm(self) -> MockLLM:
        """Create mock LLM."""
        llm = MockLLM()
        llm.set_hypotheses([
            Hypothesis(
                id="h1",
                title="Upstream ETL failure",
                category=HypothesisCategory.UPSTREAM_DEPENDENCY,
                reasoning="The upstream table may have failed to load.",
                suggested_query="SELECT COUNT(*) FROM upstream LIMIT 100",
            ),
            Hypothesis(
                id="h2",
                title="Data quality issue",
                category=HypothesisCategory.DATA_QUALITY,
                reasoning="Invalid status values may be present.",
                suggested_query="SELECT COUNT(*) FROM orders WHERE status = 'invalid' LIMIT 100",
            ),
        ])
        return llm

    @pytest.fixture
    def registry(
        self,
        context_engine: MockContextEngine,
        pattern_repository: MockPatternRepository,
        llm: MockLLM,
    ) -> StepRegistry:
        """Create registry with GatherContext, CheckPatterns, GenerateHypotheses steps."""
        reg = StepRegistry()
        reg.register(GatherContextStep(context_engine))
        reg.register(CheckPatternsStep(pattern_repository))
        reg.register(GenerateHypothesesStep(llm))
        return reg

    @pytest.fixture
    def repository(self) -> MockInvestigationRepository:
        """Create mock repository."""
        return MockInvestigationRepository()

    @pytest.fixture
    def initial_context(self) -> InvestigationContext:
        """Create initial investigation context."""
        return InvestigationContext(
            alert_summary="50% row count drop in public.orders on 2024-01-15"
        )

    @pytest.mark.asyncio
    async def test_gather_context_step_continues_to_check_patterns(
        self,
        registry: StepRegistry,
        repository: MockInvestigationRepository,
        initial_context: InvestigationContext,
    ) -> None:
        """GatherContext step should continue to CheckPatterns."""
        # Setup initial state
        investigation_id = uuid4()
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(),
            step=StepType.GATHER_CONTEXT,
            context=initial_context,
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        # Execute orchestrator tick
        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=registry,
        )
        result = await orchestrator.tick(branch.id)

        # Verify CONTINUE signal with next step
        assert result.signal == ExecutionSignal.CONTINUE
        assert result.new_snapshot_id is not None

        # Verify new snapshot has CHECK_PATTERNS step
        new_snapshot = await repository.get_snapshot(result.new_snapshot_id)
        assert new_snapshot is not None
        assert new_snapshot.step == StepType.CHECK_PATTERNS

    @pytest.mark.asyncio
    async def test_check_patterns_step_continues_to_generate_hypotheses(
        self,
        registry: StepRegistry,
        repository: MockInvestigationRepository,
        initial_context: InvestigationContext,
    ) -> None:
        """CheckPatterns step should continue to GenerateHypotheses."""
        # Setup state at CHECK_PATTERNS step
        investigation_id = uuid4()
        context_with_schema = InvestigationContext(
            alert_summary=initial_context.alert_summary,
            schema_info={"tables": {"public.orders": ["id", "user_id", "total"]}},
        )
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(patch=1),
            step=StepType.CHECK_PATTERNS,
            context=context_with_schema,
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        # Execute orchestrator tick
        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=registry,
        )
        result = await orchestrator.tick(branch.id)

        # Verify CONTINUE signal with next step
        assert result.signal == ExecutionSignal.CONTINUE
        assert result.new_snapshot_id is not None

        # Verify new snapshot has GENERATE_HYPOTHESES step
        new_snapshot = await repository.get_snapshot(result.new_snapshot_id)
        assert new_snapshot is not None
        assert new_snapshot.step == StepType.GENERATE_HYPOTHESES

    @pytest.mark.asyncio
    async def test_generate_hypotheses_step_returns_branch_signal(
        self,
        registry: StepRegistry,
        repository: MockInvestigationRepository,
        initial_context: InvestigationContext,
    ) -> None:
        """GenerateHypotheses step should return BRANCH signal with child branches."""
        # Setup state at GENERATE_HYPOTHESES step
        investigation_id = uuid4()
        context_with_schema = InvestigationContext(
            alert_summary=initial_context.alert_summary,
            schema_info={"tables": {"public.orders": ["id", "user_id", "total"]}},
            matched_patterns=[],
        )
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(patch=2),
            step=StepType.GENERATE_HYPOTHESES,
            context=context_with_schema,
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        # Execute orchestrator tick
        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=registry,
        )
        result = await orchestrator.tick(branch.id)

        # Verify BRANCH signal with child branches
        assert result.signal == ExecutionSignal.BRANCH
        assert result.child_branch_ids is not None
        assert len(result.child_branch_ids) == 2  # Two hypotheses

        # Verify parent branch is suspended
        parent_branch = await repository.get_branch(branch.id)
        assert parent_branch is not None
        assert parent_branch.status == BranchStatus.SUSPENDED

        # Verify child branches were created
        for child_id in result.child_branch_ids:
            child_branch = await repository.get_branch(child_id)
            assert child_branch is not None
            assert child_branch.branch_type == BranchType.HYPOTHESIS
            assert child_branch.parent_branch_id == branch.id


# =============================================================================
# Scenario 2: Complete Hypothesis Branch
# =============================================================================


class TestHypothesisBranchFlow:
    """Test a hypothesis branch: GenerateQuery -> ExecuteQuery -> InterpretEvidence."""

    @pytest.fixture
    def llm(self) -> MockLLM:
        """Create mock LLM."""
        llm = MockLLM()
        llm.set_query("SELECT COUNT(*) FROM orders WHERE status = 'invalid' LIMIT 100")
        llm.set_evidence({
            "hypothesis_id": "h1",
            "supports_hypothesis": True,
            "confidence": 0.85,
            "interpretation": "Query shows 500 invalid status records.",
            "query": "SELECT COUNT(*) FROM orders WHERE status = 'invalid' LIMIT 100",
            "result_summary": "count=500",
            "row_count": 1,
        })
        return llm

    @pytest.fixture
    def database(self) -> MockDatabase:
        """Create mock database."""
        return MockDatabase(
            result={"columns": ["count"], "rows": [{"count": 500}], "row_count": 1}
        )

    @pytest.fixture
    def registry(self, llm: MockLLM, database: MockDatabase) -> StepRegistry:
        """Create registry with hypothesis branch steps."""
        reg = StepRegistry()
        reg.register(GenerateQueryStep(llm))
        reg.register(ExecuteQueryStep(database))
        reg.register(InterpretEvidenceStep(llm))
        return reg

    @pytest.fixture
    def repository(self) -> MockInvestigationRepository:
        """Create mock repository."""
        return MockInvestigationRepository()

    @pytest.fixture
    def hypothesis_data(self) -> dict[str, Any]:
        """Create hypothesis data for step cursor."""
        return {
            "hypothesis": {
                "id": "h1",
                "title": "Data quality issue",
                "category": "data_quality",
                "reasoning": "Invalid status values may be present.",
                "suggested_query": "SELECT COUNT(*) FROM orders WHERE status = 'invalid'",
            }
        }

    @pytest.mark.asyncio
    async def test_generate_query_step_continues_to_execute_query(
        self,
        registry: StepRegistry,
        repository: MockInvestigationRepository,
        hypothesis_data: dict[str, Any],
    ) -> None:
        """GenerateQuery step should continue to ExecuteQuery."""
        # Setup state at GENERATE_QUERY step
        investigation_id = uuid4()
        context = InvestigationContext(
            alert_summary="50% row count drop in public.orders",
            schema_info={"tables": {"public.orders": ["id", "status"]}},
        )
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.HYPOTHESIS,
            name="hypothesis_h1",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(minor=1),
            step=StepType.GENERATE_QUERY,
            context=context,
            step_cursor=hypothesis_data,
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        # Execute orchestrator tick
        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=registry,
        )
        result = await orchestrator.tick(branch.id)

        # Verify CONTINUE signal
        assert result.signal == ExecutionSignal.CONTINUE
        assert result.new_snapshot_id is not None

        # Verify new snapshot has EXECUTE_QUERY step and current_query set
        new_snapshot = await repository.get_snapshot(result.new_snapshot_id)
        assert new_snapshot is not None
        assert new_snapshot.step == StepType.EXECUTE_QUERY
        assert new_snapshot.context.current_query is not None

    @pytest.mark.asyncio
    async def test_execute_query_step_continues_to_interpret_evidence(
        self,
        registry: StepRegistry,
        repository: MockInvestigationRepository,
        hypothesis_data: dict[str, Any],
    ) -> None:
        """ExecuteQuery step should continue to InterpretEvidence."""
        # Setup state at EXECUTE_QUERY step
        investigation_id = uuid4()
        context = InvestigationContext(
            alert_summary="50% row count drop in public.orders",
            schema_info={"tables": {"public.orders": ["id", "status"]}},
            current_query="SELECT COUNT(*) FROM orders WHERE status = 'invalid' LIMIT 100",
        )
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.HYPOTHESIS,
            name="hypothesis_h1",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(minor=1, patch=1),
            step=StepType.EXECUTE_QUERY,
            context=context,
            step_cursor=hypothesis_data,
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        # Execute orchestrator tick
        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=registry,
        )
        result = await orchestrator.tick(branch.id)

        # Verify CONTINUE signal
        assert result.signal == ExecutionSignal.CONTINUE
        assert result.new_snapshot_id is not None

        # Verify new snapshot has INTERPRET_EVIDENCE step and current_query_result set
        new_snapshot = await repository.get_snapshot(result.new_snapshot_id)
        assert new_snapshot is not None
        assert new_snapshot.step == StepType.INTERPRET_EVIDENCE
        assert new_snapshot.context.current_query_result is not None

    @pytest.mark.asyncio
    async def test_interpret_evidence_step_returns_complete_signal(
        self,
        registry: StepRegistry,
        repository: MockInvestigationRepository,
        hypothesis_data: dict[str, Any],
    ) -> None:
        """InterpretEvidence step should return COMPLETE signal."""
        # Setup state at INTERPRET_EVIDENCE step
        investigation_id = uuid4()
        context = InvestigationContext(
            alert_summary="50% row count drop in public.orders",
            schema_info={"tables": {"public.orders": ["id", "status"]}},
            current_query="SELECT COUNT(*) FROM orders WHERE status = 'invalid' LIMIT 100",
            current_query_result={"columns": ["count"], "rows": [{"count": 500}], "row_count": 1},
        )
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.HYPOTHESIS,
            name="hypothesis_h1",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(minor=1, patch=2),
            step=StepType.INTERPRET_EVIDENCE,
            context=context,
            step_cursor=hypothesis_data,
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        # Execute orchestrator tick
        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=registry,
        )
        result = await orchestrator.tick(branch.id)

        # Verify COMPLETE signal
        assert result.signal == ExecutionSignal.COMPLETE
        assert result.new_snapshot_id is not None

        # Verify branch is marked as completed
        updated_branch = await repository.get_branch(branch.id)
        assert updated_branch is not None
        assert updated_branch.status == BranchStatus.COMPLETED

        # Verify evidence was added to context
        new_snapshot = await repository.get_snapshot(result.new_snapshot_id)
        assert new_snapshot is not None
        assert len(new_snapshot.context.evidence) == 1


# =============================================================================
# Scenario 3: Synthesis After Branch Merge
# =============================================================================


class TestSynthesisFlow:
    """Test synthesis step with evidence.

    High confidence -> COMPLETE, low confidence -> CONTINUE.
    """

    @pytest.fixture
    def high_confidence_llm(self) -> MockLLM:
        """Create mock LLM that returns high confidence synthesis."""
        llm = MockLLM()
        llm.set_synthesis({
            "root_cause": "Upstream ETL job failed to load user data",
            "confidence": 0.92,
            "recommendations": ["Restart ETL job", "Add monitoring"],
            "supporting_evidence": ["Evidence shows 50% drop in user records"],
        })
        return llm

    @pytest.fixture
    def low_confidence_llm(self) -> MockLLM:
        """Create mock LLM that returns low confidence synthesis."""
        llm = MockLLM()
        llm.set_synthesis({
            "root_cause": "Possible data quality issue",
            "confidence": 0.65,
            "recommendations": ["Investigate further"],
            "supporting_evidence": ["Evidence is inconclusive"],
        })
        return llm

    @pytest.fixture
    def repository(self) -> MockInvestigationRepository:
        """Create mock repository."""
        return MockInvestigationRepository()

    @pytest.fixture
    def context_with_evidence(self) -> InvestigationContext:
        """Create context with evidence for synthesis."""
        return InvestigationContext(
            alert_summary="50% row count drop in public.orders",
            schema_info={"tables": {"public.orders": ["id", "status"]}},
            hypotheses=[
                {
                    "id": "h1",
                    "title": "Upstream ETL failure",
                    "category": "upstream_dependency",
                    "reasoning": "ETL may have failed",
                    "suggested_query": "SELECT COUNT(*) FROM upstream",
                }
            ],
            evidence=[
                {
                    "hypothesis_id": "h1",
                    "supports_hypothesis": True,
                    "confidence": 0.85,
                    "interpretation": "Query confirms 50% drop",
                    "query": "SELECT COUNT(*) FROM upstream",
                    "result_summary": "count=500",
                    "row_count": 1,
                }
            ],
        )

    @pytest.mark.asyncio
    async def test_synthesis_high_confidence_returns_complete(
        self,
        high_confidence_llm: MockLLM,
        repository: MockInvestigationRepository,
        context_with_evidence: InvestigationContext,
    ) -> None:
        """SynthesizeStep with high confidence should return COMPLETE signal."""
        # Setup registry with high confidence synthesis
        reg = StepRegistry()
        reg.register(SynthesizeStep(high_confidence_llm, confidence_threshold=0.85))

        # Setup state at SYNTHESIZE step
        investigation_id = uuid4()
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(major=1),
            step=StepType.SYNTHESIZE,
            context=context_with_evidence,
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        # Execute orchestrator tick
        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=reg,
        )
        result = await orchestrator.tick(branch.id)

        # Verify COMPLETE signal
        assert result.signal == ExecutionSignal.COMPLETE
        assert result.new_snapshot_id is not None

        # Verify branch is completed
        updated_branch = await repository.get_branch(branch.id)
        assert updated_branch is not None
        assert updated_branch.status == BranchStatus.COMPLETED

        # Verify investigation outcome was set (for main branch)
        assert investigation_id in repository._investigation_outcomes

    @pytest.mark.asyncio
    async def test_synthesis_low_confidence_continues_to_counter_analyze(
        self,
        low_confidence_llm: MockLLM,
        repository: MockInvestigationRepository,
        context_with_evidence: InvestigationContext,
    ) -> None:
        """SynthesizeStep with low confidence should return CONTINUE to COUNTER_ANALYZE."""
        # Setup registry with low confidence synthesis
        reg = StepRegistry()
        reg.register(SynthesizeStep(low_confidence_llm, confidence_threshold=0.85))

        # Setup state at SYNTHESIZE step
        investigation_id = uuid4()
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(major=1),
            step=StepType.SYNTHESIZE,
            context=context_with_evidence,
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        # Execute orchestrator tick
        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=reg,
        )
        result = await orchestrator.tick(branch.id)

        # Verify CONTINUE signal with next_step=COUNTER_ANALYZE
        assert result.signal == ExecutionSignal.CONTINUE
        assert result.new_snapshot_id is not None

        # Verify new snapshot has COUNTER_ANALYZE step
        new_snapshot = await repository.get_snapshot(result.new_snapshot_id)
        assert new_snapshot is not None
        assert new_snapshot.step == StepType.COUNTER_ANALYZE

        # Verify synthesis was stored in context
        assert new_snapshot.context.current_synthesis is not None
        assert new_snapshot.context.current_synthesis["confidence"] == 0.65


# =============================================================================
# Scenario 4: Full Orchestrator Integration
# =============================================================================


class TestFullOrchestratorIntegration:
    """Test orchestrator running multiple ticks until branching."""

    @pytest.fixture
    def context_engine(self) -> MockContextEngine:
        """Create mock context engine."""
        return MockContextEngine()

    @pytest.fixture
    def pattern_repository(self) -> MockPatternRepository:
        """Create mock pattern repository."""
        return MockPatternRepository()

    @pytest.fixture
    def llm(self) -> MockLLM:
        """Create mock LLM with all capabilities."""
        llm = MockLLM()
        llm.set_hypotheses([
            Hypothesis(
                id="h1",
                title="ETL failure",
                category=HypothesisCategory.UPSTREAM_DEPENDENCY,
                reasoning="ETL may have failed",
                suggested_query="SELECT COUNT(*) FROM upstream LIMIT 100",
            ),
            Hypothesis(
                id="h2",
                title="Schema drift",
                category=HypothesisCategory.TRANSFORMATION_BUG,
                reasoning="Schema may have changed",
                suggested_query="SELECT COUNT(*) FROM orders LIMIT 100",
            ),
        ])
        return llm

    @pytest.fixture
    def registry(
        self,
        context_engine: MockContextEngine,
        pattern_repository: MockPatternRepository,
        llm: MockLLM,
    ) -> StepRegistry:
        """Create registry with all steps for main branch flow."""
        reg = StepRegistry()
        reg.register(GatherContextStep(context_engine))
        reg.register(CheckPatternsStep(pattern_repository))
        reg.register(GenerateHypothesesStep(llm))
        return reg

    @pytest.fixture
    def repository(self) -> MockInvestigationRepository:
        """Create mock repository."""
        return MockInvestigationRepository()

    @pytest.mark.asyncio
    async def test_multiple_ticks_until_branching(
        self,
        registry: StepRegistry,
        repository: MockInvestigationRepository,
    ) -> None:
        """Run multiple ticks from initial state until branching occurs."""
        # Create initial investigation and branch
        investigation_id = uuid4()
        initial_context = InvestigationContext(
            alert_summary="50% row count drop in public.orders on 2024-01-15"
        )
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(),
            step=StepType.GATHER_CONTEXT,
            context=initial_context,
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=registry,
        )

        # Track execution history
        execution_history: list[TickResult] = []
        current_branch_id = branch.id

        # Run ticks until branching or completion
        max_ticks = 10
        for _ in range(max_ticks):
            result = await orchestrator.tick(current_branch_id)
            execution_history.append(result)

            if result.signal == ExecutionSignal.BRANCH:
                break
            elif result.signal == ExecutionSignal.COMPLETE:
                break
            elif result.signal == ExecutionSignal.FAIL:
                break

        # Verify execution history
        # Steps: GATHER_CONTEXT -> CHECK_PATTERNS -> GENERATE_HYPOTHESES
        assert len(execution_history) == 3

        # Verify signals in order
        assert execution_history[0].signal == ExecutionSignal.CONTINUE
        assert execution_history[1].signal == ExecutionSignal.CONTINUE
        assert execution_history[2].signal == ExecutionSignal.BRANCH

        # Verify child branches were created
        final_result = execution_history[-1]
        assert final_result.child_branch_ids is not None
        assert len(final_result.child_branch_ids) == 2

        # Verify parent branch is suspended
        parent_branch = await repository.get_branch(branch.id)
        assert parent_branch is not None
        assert parent_branch.status == BranchStatus.SUSPENDED

        # Verify child branches exist and are at GENERATE_QUERY step
        for child_id in final_result.child_branch_ids:
            child_branch = await repository.get_branch(child_id)
            assert child_branch is not None
            assert child_branch.branch_type == BranchType.HYPOTHESIS
            assert child_branch.head_snapshot_id is not None

            child_snapshot = await repository.get_snapshot(child_branch.head_snapshot_id)
            assert child_snapshot is not None
            assert child_snapshot.step == StepType.GENERATE_QUERY

    @pytest.mark.asyncio
    async def test_child_branches_have_hypothesis_data_in_step_cursor(
        self,
        registry: StepRegistry,
        repository: MockInvestigationRepository,
    ) -> None:
        """Verify child branches have hypothesis data in step_cursor."""
        # Setup state at GENERATE_HYPOTHESES step
        investigation_id = uuid4()
        context = InvestigationContext(
            alert_summary="50% row count drop in public.orders",
            schema_info={"tables": {"public.orders": ["id", "status"]}},
            matched_patterns=[],
        )
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(patch=2),
            step=StepType.GENERATE_HYPOTHESES,
            context=context,
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=registry,
        )

        result = await orchestrator.tick(branch.id)

        # Verify child branches have hypothesis data
        assert result.child_branch_ids is not None
        for child_id in result.child_branch_ids:
            child_branch = await repository.get_branch(child_id)
            assert child_branch is not None
            assert child_branch.head_snapshot_id is not None

            child_snapshot = await repository.get_snapshot(child_branch.head_snapshot_id)
            assert child_snapshot is not None
            assert "hypothesis" in child_snapshot.step_cursor
            assert "id" in child_snapshot.step_cursor["hypothesis"]


# =============================================================================
# Additional Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def repository(self) -> MockInvestigationRepository:
        """Create mock repository."""
        return MockInvestigationRepository()

    @pytest.mark.asyncio
    async def test_gather_context_fails_on_empty_schema(
        self,
        repository: MockInvestigationRepository,
    ) -> None:
        """GatherContext should fail if schema is empty."""
        # Create context engine that returns empty schema
        empty_schema_context = MockGatheredContext(schema=MockSchema(tables={}))
        context_engine = MockContextEngine(gathered=empty_schema_context)

        reg = StepRegistry()
        reg.register(GatherContextStep(context_engine))

        # Setup state
        investigation_id = uuid4()
        context = InvestigationContext(alert_summary="Test alert")
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(),
            step=StepType.GATHER_CONTEXT,
            context=context,
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=reg,
        )
        result = await orchestrator.tick(branch.id)

        # Verify FAIL signal
        assert result.signal == ExecutionSignal.FAIL

        # Verify branch is marked as abandoned
        updated_branch = await repository.get_branch(branch.id)
        assert updated_branch is not None
        assert updated_branch.status == BranchStatus.ABANDONED

    @pytest.mark.asyncio
    async def test_generate_query_fails_without_hypothesis_in_step_cursor(
        self,
        repository: MockInvestigationRepository,
    ) -> None:
        """GenerateQuery should fail if no hypothesis in step_cursor."""
        llm = MockLLM()
        reg = StepRegistry()
        reg.register(GenerateQueryStep(llm))

        # Setup state without hypothesis in step_cursor
        investigation_id = uuid4()
        context = InvestigationContext(
            alert_summary="Test alert",
            schema_info={"tables": {"public.orders": ["id"]}},
        )
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.HYPOTHESIS,
            name="hypothesis_h1",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(minor=1),
            step=StepType.GENERATE_QUERY,
            context=context,
            step_cursor={},  # Empty - no hypothesis
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=reg,
        )
        result = await orchestrator.tick(branch.id)

        # Verify FAIL signal
        assert result.signal == ExecutionSignal.FAIL

    @pytest.mark.asyncio
    async def test_execute_query_fails_without_current_query(
        self,
        repository: MockInvestigationRepository,
    ) -> None:
        """ExecuteQuery should fail if no current_query in context."""
        database = MockDatabase()
        reg = StepRegistry()
        reg.register(ExecuteQueryStep(database))

        # Setup state without current_query
        investigation_id = uuid4()
        context = InvestigationContext(
            alert_summary="Test alert",
            schema_info={"tables": {"public.orders": ["id"]}},
            current_query=None,  # No query
        )
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.HYPOTHESIS,
            name="hypothesis_h1",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(minor=1, patch=1),
            step=StepType.EXECUTE_QUERY,
            context=context,
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=reg,
        )
        result = await orchestrator.tick(branch.id)

        # Verify FAIL signal (preconditions not met)
        assert result.signal == ExecutionSignal.FAIL

    @pytest.mark.asyncio
    async def test_synthesize_fails_without_evidence(
        self,
        repository: MockInvestigationRepository,
    ) -> None:
        """SynthesizeStep should fail if no evidence in context."""
        llm = MockLLM()
        llm.set_synthesis({"root_cause": "Test", "confidence": 0.9})
        reg = StepRegistry()
        reg.register(SynthesizeStep(llm))

        # Setup state without evidence
        investigation_id = uuid4()
        context = InvestigationContext(
            alert_summary="Test alert",
            evidence=[],  # No evidence
        )
        branch = await repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.MAIN,
            name="main",
        )
        snapshot = await repository.create_snapshot(
            investigation_id=investigation_id,
            branch_id=branch.id,
            version=VersionId(major=1),
            step=StepType.SYNTHESIZE,
            context=context,
        )
        await repository.update_branch_head(branch.id, snapshot.id)

        orchestrator = InvestigationOrchestrator(
            repository=repository,
            registry=reg,
        )
        result = await orchestrator.tick(branch.id)

        # Verify FAIL signal (preconditions not met)
        assert result.signal == ExecutionSignal.FAIL
