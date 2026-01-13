"""End-to-end tests for investigation flow using maestro.

These tests verify the complete investigation workflow from start to finish,
using the maestro workflow engine. They help uncover interface mismatches
and integration issues between components.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from maestro import Signal, Workflow

from dataing.core.domain_types import (
    AnomalyAlert,
    Hypothesis,
    HypothesisCategory,
    MetricSpec,
)
from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.flow import (
    build_investigation_workflow,
    run_investigation,
)
from dataing.core.investigation.steps import (
    GatherContextStep,
    GenerateHypothesesStep,
)
from dataing.core.investigation.values import StepType


# =============================================================================
# Test Fixtures - Mock implementations that satisfy the step protocols
# =============================================================================


@dataclass
class MockSchema:
    """Mock schema that satisfies SchemaLike protocol."""

    tables: dict[str, Any]

    def is_empty(self) -> bool:
        """Return True if no tables."""
        return len(self.tables) == 0

    def to_dict(self) -> dict[str, Any]:
        """Return schema as dict."""
        return {"tables": self.tables}


@dataclass
class MockLineage:
    """Mock lineage that satisfies LineageLike protocol."""

    upstream: list[str]
    downstream: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return lineage as dict."""
        return {"upstream": self.upstream, "downstream": self.downstream}


@dataclass
class MockSchemaResponse:
    """Mock schema response that mimics SchemaResponse from datasource layer."""

    catalogs: list[dict[str, Any]]

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        """Return schema as dict (mimics Pydantic model_dump)."""
        return {
            "source_id": "mock-source",
            "source_type": "postgresql",
            "source_category": "database",
            "fetched_at": "2024-01-15T00:00:00",
            "catalogs": self.catalogs,
        }


@dataclass
class MockLineageContext:
    """Mock lineage context that mimics LineageContext."""

    target: str
    upstream: tuple[str, ...]
    downstream: tuple[str, ...]


@dataclass
class MockGatheredContext:
    """Mock gathered context returned by ContextEngine.gather().

    This mimics domain_types.InvestigationContext which has:
    - schema: SchemaResponse
    - lineage: LineageContext | None
    """

    schema: MockSchemaResponse
    lineage: MockLineageContext | None = None


class MockContextEngine:
    """Mock context engine that satisfies ContextEngineProtocol.

    The step protocol expects: gather(alert, adapter) -> InvestigationContext
    """

    def __init__(
        self,
        schema_tables: dict[str, Any] | None = None,
        lineage: MockLineageContext | None = None,
        should_fail: bool = False,
    ) -> None:
        """Initialize mock context engine."""
        # Use 'is None' check to allow empty dict {} to be passed explicitly
        if schema_tables is None:
            self.schema_tables = {"events": {"columns": ["id", "user_id", "timestamp"]}}
        else:
            self.schema_tables = schema_tables
        self.lineage = lineage
        self.should_fail = should_fail
        self.gather_called = False
        self.gather_args: tuple[Any, ...] = ()

    async def gather(self, alert: Any, adapter: Any) -> MockGatheredContext:
        """Gather context - matches real ContextEngine.gather() signature."""
        self.gather_called = True
        self.gather_args = (alert, adapter)

        if self.should_fail:
            raise RuntimeError("Context gathering failed")

        # Build schema in the format expected (SchemaResponse-like)
        # Empty schema_tables means no tables discovered
        tables = []
        for table_name, table_info in self.schema_tables.items():
            # Build proper Column objects with required fields
            columns = []
            for col_name in table_info.get("columns", []):
                columns.append({
                    "name": col_name,
                    "data_type": "string",
                    "native_type": "varchar",
                    "nullable": True,
                })
            tables.append({
                "name": table_name,
                "table_type": "table",
                "native_type": "TABLE",
                "native_path": f"public.{table_name}",
                "columns": columns,
            })

        schema = MockSchemaResponse(
            catalogs=[{
                "name": "default",
                "schemas": [{
                    "name": "public",
                    "tables": tables,
                }],
            }] if tables else []
        )

        return MockGatheredContext(
            schema=schema,
            lineage=self.lineage,
        )


class MockAdapter:
    """Mock adapter that satisfies BaseAdapter protocol for testing."""

    pass


class MockSynthesisResponse:
    """Mock synthesis response matching AgentClient.synthesize_findings_raw return."""

    def __init__(self, synthesis: dict[str, Any]) -> None:
        """Initialize mock synthesis response."""
        self.root_cause = synthesis.get("root_cause", "Unknown")
        self.confidence = synthesis.get("confidence", 0.5)
        self.causal_chain = synthesis.get("causal_chain", [])
        self.estimated_onset = synthesis.get("estimated_onset")
        self.affected_scope = synthesis.get("affected_scope")
        self.recommendations = synthesis.get("recommendations", [])
        self.supporting_evidence = synthesis.get("supporting_evidence", [])


class MockLLM:
    """Mock LLM that satisfies AgentClient interface (used by LLM adapters)."""

    def __init__(
        self,
        hypotheses: list[Hypothesis] | None = None,
        query: str = "SELECT * FROM events",
        evidence: dict[str, Any] | None = None,
        synthesis: dict[str, Any] | None = None,
    ) -> None:
        """Initialize mock LLM."""
        self.hypotheses = hypotheses or [
            Hypothesis(
                id="h1",
                title="Mobile app bug causing NULL user_id",
                category=HypothesisCategory.TRANSFORMATION_BUG,
                reasoning="Recent mobile app update may have introduced a bug",
                suggested_query="SELECT COUNT(*) FROM events WHERE user_id IS NULL",
            )
        ]
        self.query = query
        self.evidence_data = evidence or {
            "finding": "50% NULL rate increase",
            "supports_hypothesis": True,
        }
        self.synthesis = synthesis or {"root_cause": "Mobile app bug", "confidence": 0.9}

    async def generate_hypotheses(
        self,
        alert: Any,
        context: Any,
        num_hypotheses: int = 5,
        handlers: Any = None,
    ) -> list[Hypothesis]:
        """Generate hypotheses - matches AgentClient interface."""
        return self.hypotheses[:num_hypotheses]

    async def generate_query(
        self,
        hypothesis: Any,
        schema: Any,
        previous_error: str | None = None,
        handlers: Any = None,
        alert: Any = None,
    ) -> str:
        """Generate SQL query - matches AgentClient interface."""
        return self.query

    async def interpret_evidence(
        self,
        hypothesis: Any,
        sql: str,
        results: Any,
    ) -> Any:
        """Interpret evidence - matches AgentClient interface."""
        from dataing.core.domain_types import Evidence

        hyp_id = hypothesis.id if hasattr(hypothesis, "id") else "h1"
        return Evidence(
            hypothesis_id=hyp_id,
            query=sql,
            result_summary=str(self.evidence_data.get("finding", "")),
            row_count=1,
            supports_hypothesis=self.evidence_data.get("supports_hypothesis", True),
            confidence=0.8,
            interpretation=self.evidence_data.get("finding", "Evidence interpreted"),
        )

    async def synthesize_findings_raw(
        self,
        alert: Any,
        evidence: list[Any],
    ) -> MockSynthesisResponse:
        """Synthesize findings - matches AgentClient interface."""
        return MockSynthesisResponse(self.synthesis)


class MockDatabase:
    """Mock database that satisfies DatabaseProtocol."""

    def __init__(
        self,
        result: dict[str, Any] | None = None,
        should_fail: bool = False,
    ) -> None:
        """Initialize mock database."""
        self.result = result or {"rows": [{"count": 1000}], "row_count": 1}
        self.should_fail = should_fail
        self.executed_queries: list[str] = []

    async def execute_query(self, query: str) -> dict[str, Any]:
        """Execute query and return results."""
        self.executed_queries.append(query)
        if self.should_fail:
            raise RuntimeError("Query execution failed")
        return self.result


class MockPatternRepository:
    """Mock pattern repository that satisfies PatternRepositoryProtocol."""

    def __init__(self, patterns: list[dict[str, Any]] | None = None) -> None:
        """Initialize mock pattern repository."""
        self.patterns = patterns or []

    async def find_matching_patterns(
        self,
        dataset_id: str | None,
        anomaly_type: str | None,
        min_confidence: float = 0.8,
    ) -> list[dict[str, Any]]:
        """Find matching historical patterns."""
        return self.patterns


@pytest.fixture
def sample_alert() -> AnomalyAlert:
    """Create a sample anomaly alert for testing."""
    return AnomalyAlert(
        dataset_id="analytics.events",
        metric_spec=MetricSpec(
            metric_type="column",
            expression="user_id",
            display_name="NULL Rate",
            columns_referenced=["user_id"],
        ),
        anomaly_type="null_spike",
        anomaly_date="2024-01-15",
        expected_value=0.01,
        actual_value=0.15,
        deviation_pct=1400.0,
        severity="high",
    )


@pytest.fixture
def initial_context(sample_alert: AnomalyAlert) -> InvestigationContext:
    """Create initial investigation context."""
    return InvestigationContext(
        alert_summary=f"NULL spike in {sample_alert.dataset_id}: 15% vs 1% expected",
        alert=sample_alert.model_dump(mode="json"),
    )


@pytest.fixture
def mock_context_engine() -> MockContextEngine:
    """Create mock context engine."""
    return MockContextEngine(
        schema_tables={
            "events": {"columns": ["id", "user_id", "event_type", "timestamp"]},
            "users": {"columns": ["id", "email", "created_at"]},
        }
    )


@pytest.fixture
def mock_llm() -> MockLLM:
    """Create mock LLM."""
    return MockLLM()


@pytest.fixture
def mock_database() -> MockDatabase:
    """Create mock database."""
    return MockDatabase()


@pytest.fixture
def mock_pattern_repo() -> MockPatternRepository:
    """Create mock pattern repository."""
    return MockPatternRepository()


@pytest.fixture
def mock_adapter() -> MockAdapter:
    """Create mock adapter."""
    return MockAdapter()


# =============================================================================
# Test Cases
# =============================================================================


class TestGatherContextStep:
    """Tests for GatherContextStep in isolation."""

    @pytest.mark.asyncio
    async def test_gather_context_calls_engine_with_alert_and_adapter(
        self,
        initial_context: InvestigationContext,
        mock_context_engine: MockContextEngine,
        mock_adapter: MockAdapter,
    ) -> None:
        """Test that GatherContextStep calls context engine with alert and adapter."""
        step = GatherContextStep(mock_context_engine, mock_adapter)

        result = await step.execute(initial_context)

        # Verify context engine was called correctly
        assert mock_context_engine.gather_called
        assert len(mock_context_engine.gather_args) == 2
        # First arg should be an AnomalyAlert (converted from context.alert dict)
        assert mock_context_engine.gather_args[0] is not None
        # Second arg should be the adapter
        assert mock_context_engine.gather_args[1] is mock_adapter

    @pytest.mark.asyncio
    async def test_gather_context_returns_continue_signal(
        self,
        initial_context: InvestigationContext,
        mock_context_engine: MockContextEngine,
        mock_adapter: MockAdapter,
    ) -> None:
        """Test that successful context gathering returns CONTINUE signal."""
        step = GatherContextStep(mock_context_engine, mock_adapter)

        result = await step.execute(initial_context)

        assert result.signal == Signal.CONTINUE
        assert result.context.schema_info is not None

    @pytest.mark.asyncio
    async def test_gather_context_returns_fail_on_empty_schema(
        self,
        initial_context: InvestigationContext,
        mock_adapter: MockAdapter,
    ) -> None:
        """Test that empty schema returns FAIL signal."""
        engine = MockContextEngine(schema_tables={})  # Empty schema
        step = GatherContextStep(engine, mock_adapter)

        result = await step.execute(initial_context)

        assert result.signal == Signal.FAIL
        assert result.error is not None
        assert "Empty schema" in result.error

    @pytest.mark.asyncio
    async def test_gather_context_returns_fail_on_exception(
        self,
        initial_context: InvestigationContext,
        mock_adapter: MockAdapter,
    ) -> None:
        """Test that exception returns FAIL signal with error message."""
        engine = MockContextEngine(should_fail=True)
        step = GatherContextStep(engine, mock_adapter)

        result = await step.execute(initial_context)

        assert result.signal == Signal.FAIL
        assert result.error is not None
        assert "Context gathering failed" in result.error


class TestBuildInvestigationWorkflow:
    """Tests for workflow construction."""

    def test_workflow_has_all_required_steps(
        self,
        mock_context_engine: MockContextEngine,
        mock_llm: MockLLM,
        mock_database: MockDatabase,
        mock_pattern_repo: MockPatternRepository,
    ) -> None:
        """Test that workflow includes all investigation steps."""
        workflow = build_investigation_workflow(
            context_engine=mock_context_engine,
            llm=mock_llm,
            database=mock_database,
            pattern_repository=mock_pattern_repo,
        )

        # Check workflow has steps registered
        assert len(workflow._steps) > 0

        # Check key steps are present
        step_names = list(workflow._steps.keys())
        assert StepType.GATHER_CONTEXT.value in step_names
        assert StepType.CHECK_PATTERNS.value in step_names
        assert StepType.GENERATE_HYPOTHESES.value in step_names

    def test_workflow_has_signal_handler(
        self,
        mock_context_engine: MockContextEngine,
        mock_llm: MockLLM,
        mock_database: MockDatabase,
        mock_pattern_repo: MockPatternRepository,
    ) -> None:
        """Test that workflow has InvestigationSignalHandler configured."""
        workflow = build_investigation_workflow(
            context_engine=mock_context_engine,
            llm=mock_llm,
            database=mock_database,
            pattern_repository=mock_pattern_repo,
        )

        assert workflow._signal_handler is not None


class TestInvestigationE2E:
    """End-to-end tests for complete investigation flow."""

    @pytest.mark.asyncio
    async def test_investigation_completes_with_high_confidence(
        self,
        initial_context: InvestigationContext,
        mock_context_engine: MockContextEngine,
        mock_llm: MockLLM,
        mock_database: MockDatabase,
        mock_pattern_repo: MockPatternRepository,
    ) -> None:
        """Test that investigation completes when synthesis has high confidence."""
        # Configure LLM to return high confidence synthesis
        mock_llm.synthesis = {"root_cause": "Mobile app bug", "confidence": 0.95}

        workflow = build_investigation_workflow(
            context_engine=mock_context_engine,
            llm=mock_llm,
            database=mock_database,
            pattern_repository=mock_pattern_repo,
        )

        final_context = await run_investigation(
            workflow=workflow,
            initial_context=initial_context,
            max_iterations=50,
        )

        # Verify investigation completed
        assert final_context.current_synthesis is not None
        assert final_context.current_synthesis.get("confidence", 0) >= 0.85

    @pytest.mark.asyncio
    async def test_investigation_fails_on_context_gathering_error(
        self,
        initial_context: InvestigationContext,
        mock_llm: MockLLM,
        mock_database: MockDatabase,
        mock_pattern_repo: MockPatternRepository,
    ) -> None:
        """Test that investigation fails gracefully on context gathering error."""
        from maestro import WorkflowError

        # Configure context engine to fail
        failing_engine = MockContextEngine(should_fail=True)

        workflow = build_investigation_workflow(
            context_engine=failing_engine,
            llm=mock_llm,
            database=mock_database,
            pattern_repository=mock_pattern_repo,
        )

        with pytest.raises(WorkflowError) as exc_info:
            await run_investigation(
                workflow=workflow,
                initial_context=initial_context,
            )

        assert "Context gathering failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_investigation_fails_on_empty_schema(
        self,
        initial_context: InvestigationContext,
        mock_llm: MockLLM,
        mock_database: MockDatabase,
        mock_pattern_repo: MockPatternRepository,
    ) -> None:
        """Test that investigation fails when schema is empty."""
        from maestro import WorkflowError

        # Configure context engine to return empty schema
        empty_schema_engine = MockContextEngine(schema_tables={})

        workflow = build_investigation_workflow(
            context_engine=empty_schema_engine,
            llm=mock_llm,
            database=mock_database,
            pattern_repository=mock_pattern_repo,
        )

        with pytest.raises(WorkflowError) as exc_info:
            await run_investigation(
                workflow=workflow,
                initial_context=initial_context,
            )

        assert "Empty schema" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_investigation_gathers_context_first(
        self,
        initial_context: InvestigationContext,
        mock_context_engine: MockContextEngine,
        mock_llm: MockLLM,
        mock_database: MockDatabase,
        mock_pattern_repo: MockPatternRepository,
    ) -> None:
        """Test that context gathering is the first step."""
        workflow = build_investigation_workflow(
            context_engine=mock_context_engine,
            llm=mock_llm,
            database=mock_database,
            pattern_repository=mock_pattern_repo,
        )

        # Run just one tick to verify first step
        tick_result = await workflow.tick(
            initial_context,
            StepType.GATHER_CONTEXT.value,
        )

        # Verify context engine was called
        assert mock_context_engine.gather_called

        # Verify we got CONTINUE to next step
        assert tick_result.signal == Signal.CONTINUE
        assert tick_result.next_step == StepType.CHECK_PATTERNS.value


class TestWorkflowStepOrdering:
    """Tests for correct step ordering and transitions."""

    @pytest.mark.asyncio
    async def test_gather_context_transitions_to_check_patterns(
        self,
        initial_context: InvestigationContext,
        mock_context_engine: MockContextEngine,
        mock_llm: MockLLM,
        mock_database: MockDatabase,
        mock_pattern_repo: MockPatternRepository,
    ) -> None:
        """Test that gather_context transitions to check_patterns."""
        workflow = build_investigation_workflow(
            context_engine=mock_context_engine,
            llm=mock_llm,
            database=mock_database,
            pattern_repository=mock_pattern_repo,
        )

        result = await workflow.tick(initial_context, StepType.GATHER_CONTEXT.value)

        assert result.signal == Signal.CONTINUE
        assert result.next_step == StepType.CHECK_PATTERNS.value

    @pytest.mark.asyncio
    async def test_check_patterns_transitions_to_generate_hypotheses(
        self,
        mock_context_engine: MockContextEngine,
        mock_llm: MockLLM,
        mock_database: MockDatabase,
        mock_pattern_repo: MockPatternRepository,
    ) -> None:
        """Test that check_patterns transitions to generate_hypotheses."""
        # Create context that has passed gather_context
        context_with_schema = InvestigationContext(
            alert_summary="NULL spike test",
            schema_info={"tables": {"events": {}}},
        )

        workflow = build_investigation_workflow(
            context_engine=mock_context_engine,
            llm=mock_llm,
            database=mock_database,
            pattern_repository=mock_pattern_repo,
        )

        result = await workflow.tick(context_with_schema, StepType.CHECK_PATTERNS.value)

        assert result.signal == Signal.CONTINUE
        assert result.next_step == StepType.GENERATE_HYPOTHESES.value
