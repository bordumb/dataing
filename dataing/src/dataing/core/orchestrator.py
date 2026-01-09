"""Investigation Orchestrator - The "Brain" of the system.

This module implements the core investigation workflow:
1. Gather Context (FAIL FAST if schema is empty)
2. Generate Hypotheses
3. Investigate Hypotheses in Parallel (Fan-Out)
4. Synthesize Findings (Fan-In)

The orchestrator coordinates all components but contains no
infrastructure-specific code - it only uses the protocol interfaces.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from dataing.adapters.investigation_feedback import EventType
from dataing.adapters.llm.response_models import InterpretationResponse, SynthesisResponse

from .domain_types import Evidence, Finding, Hypothesis, InvestigationContext
from .exceptions import CircuitBreakerTripped, SchemaDiscoveryError
from .state import Event, InvestigationState

if TYPE_CHECKING:
    from dataing.adapters.datasource.sql.base import SQLAdapter
    from dataing.adapters.training.repository import TrainingSignalRepository

    from ..safety.circuit_breaker import CircuitBreaker
    from .interfaces import ContextEngine, InvestigationFeedbackEmitter, LLMClient
    from .quality.protocol import QualityValidator

logger = structlog.get_logger()


@dataclass(frozen=True)
class OrchestratorConfig:
    """Configuration for the investigation orchestrator.

    Attributes:
        max_hypotheses: Maximum number of hypotheses to generate.
        max_queries_per_hypothesis: Maximum queries per hypothesis.
        max_retries_per_hypothesis: Maximum retry attempts per hypothesis.
        query_timeout_seconds: Timeout for individual queries.
        high_confidence_threshold: Stop early if confidence exceeds this.
        validation_enabled: Whether to validate LLM outputs.
        validation_pass_threshold: Minimum score to pass validation.
        validation_max_retries: Maximum retries on validation failure.
    """

    max_hypotheses: int = 5
    max_queries_per_hypothesis: int = 3
    max_retries_per_hypothesis: int = 2
    query_timeout_seconds: int = 30
    high_confidence_threshold: float = 0.85
    validation_enabled: bool = True
    validation_pass_threshold: float = 0.6
    validation_max_retries: int = 2


class InvestigationOrchestrator:
    """Orchestrates the investigation workflow.

    Flow: Context -> Hypothesize -> Parallel Investigation -> Synthesis

    The orchestrator is stateless - all state is passed through
    InvestigationState, which uses event sourcing.
    """

    def __init__(
        self,
        db: SQLAdapter | None,
        llm: LLMClient,
        context_engine: ContextEngine,
        circuit_breaker: CircuitBreaker,
        config: OrchestratorConfig | None = None,
        feedback: InvestigationFeedbackEmitter | None = None,
        validator: QualityValidator | None = None,
        training_repo: TrainingSignalRepository | None = None,
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
            validator: Optional quality validator for LLM outputs.
            training_repo: Optional repository for training signal capture.
        """
        self.db = db
        self.llm = llm
        self.context_engine = context_engine
        self.circuit_breaker = circuit_breaker
        self.config = config or OrchestratorConfig()
        self.feedback = feedback
        self.validator = validator
        self.training_repo = training_repo
        # Will be set per-investigation when using tenant data source
        self._current_adapter: SQLAdapter | None = None

    async def run_investigation(
        self,
        state: InvestigationState,
        data_adapter: SQLAdapter | None = None,
    ) -> Finding:
        """Execute a complete investigation.

        Args:
            state: Initial investigation state with alert.
            data_adapter: Optional adapter for tenant's data source.
                         If provided, queries run against this adapter
                         instead of the default self.db.

        Returns:
            Finding with root cause and recommendations.

        Raises:
            SchemaDiscoveryError: If no schema discovered (FAIL FAST).
            CircuitBreakerTripped: If safety limits exceeded.
        """
        start_time = time.time()

        # Use provided adapter or fall back to default
        self._current_adapter = data_adapter or self.db

        log = logger.bind(
            investigation_id=state.id,
            dataset=state.alert.dataset_id,
            metric=state.alert.metric_spec.display_name,
            using_tenant_adapter=data_adapter is not None,
        )
        log.info("Starting investigation")

        # Record start event
        state = state.append_event(
            Event(
                type="investigation_started",
                timestamp=datetime.now(UTC),
                data={"dataset_id": state.alert.dataset_id},
            )
        )

        # Emit feedback event
        if self.feedback:
            await self.feedback.emit(
                tenant_id=state.tenant_id,
                event_type=EventType.INVESTIGATION_STARTED,
                event_data={"dataset_id": state.alert.dataset_id},
                investigation_id=UUID(state.id),
            )

        try:
            # 1. Gather Context (FAIL FAST if schema empty)
            state = await self._gather_context(state)
            if state.schema_context is None:
                raise SchemaDiscoveryError("Schema context is None after gathering")
            log.info("Context gathered", tables_found=state.schema_context.table_count())

            if self.feedback:
                await self.feedback.emit(
                    tenant_id=state.tenant_id,
                    event_type=EventType.INVESTIGATION_STARTED,  # Reuse for context
                    event_data={
                        "tables_found": state.schema_context.table_count(),
                        "has_lineage": state.lineage_context is not None,
                    },
                    investigation_id=UUID(state.id),
                )

            # 2. Generate Hypotheses
            state, hypotheses = await self._generate_hypotheses(state)
            log.info("Hypotheses generated", count=len(hypotheses))

            # 3. Investigate Hypotheses (Parallel Fan-Out)
            evidence = await self._investigate_parallel(state, hypotheses)
            log.info("Investigation complete", evidence_count=len(evidence))

            # 4. Synthesize Findings (Fan-In)
            finding = await self._synthesize(state, evidence, start_time)
            log.info(
                "Synthesis complete",
                root_cause=finding.root_cause,
                confidence=finding.confidence,
            )

            if self.feedback:
                await self.feedback.emit(
                    tenant_id=state.tenant_id,
                    event_type=EventType.INVESTIGATION_COMPLETED,
                    event_data={
                        "root_cause": finding.root_cause,
                        "confidence": finding.confidence,
                        "duration_seconds": finding.duration_seconds,
                    },
                    investigation_id=UUID(state.id),
                )

            return finding

        except SchemaDiscoveryError:
            log.error("Schema discovery failed - investigation aborted")
            raise

        except CircuitBreakerTripped as e:
            log.warning("Circuit breaker tripped", reason=str(e))
            # Return a partial finding
            return Finding(
                investigation_id=state.id,
                status="failed",
                root_cause=None,
                confidence=0.0,
                evidence=[],
                recommendations=["Investigation was stopped due to safety limits"],
                duration_seconds=time.time() - start_time,
            )

        except Exception as e:
            log.exception("Investigation failed with unexpected error")
            state = state.append_event(
                Event(
                    type="investigation_failed",
                    timestamp=datetime.now(UTC),
                    data={"error": str(e)},
                )
            )
            raise

    async def _gather_context(self, state: InvestigationState) -> InvestigationState:
        """Gather context with FAIL FAST on empty schema.

        Args:
            state: Current investigation state.

        Returns:
            Updated state with context.

        Raises:
            SchemaDiscoveryError: If schema is empty.
        """
        try:
            # Pass the current adapter to context engine
            # The adapter is guaranteed to be set at this point (set in run_investigation)
            assert self._current_adapter is not None
            context = await self.context_engine.gather(
                state.alert,
                self._current_adapter,
            )
        except Exception as e:
            state = state.append_event(
                Event(
                    type="schema_discovery_failed",
                    timestamp=datetime.now(UTC),
                    data={"error": str(e)},
                )
            )
            raise SchemaDiscoveryError(f"Context gathering failed: {e}") from e

        # FAIL FAST: Empty schema means DB connectivity issue or permissions problem
        if context.schema.is_empty():
            state = state.append_event(
                Event(
                    type="schema_discovery_failed",
                    timestamp=datetime.now(UTC),
                    data={"error": "No tables discovered"},
                )
            )
            raise SchemaDiscoveryError(
                "No tables discovered - check database connectivity and permissions"
            )

        # Update state with context
        state = state.with_context(
            schema_context=context.schema,
            lineage_context=context.lineage,
        )

        state = state.append_event(
            Event(
                type="context_gathered",
                timestamp=datetime.now(UTC),
                data={
                    "tables_found": context.schema.table_count(),
                    "has_lineage": context.lineage is not None,
                },
            )
        )

        return state

    async def _generate_hypotheses(
        self,
        state: InvestigationState,
    ) -> tuple[InvestigationState, list[Hypothesis]]:
        """Generate hypotheses using LLM.

        Args:
            state: Current investigation state with context.

        Returns:
            Tuple of updated state and list of hypotheses.
        """
        # schema_context is guaranteed to be set after _gather_context
        assert state.schema_context is not None
        context = InvestigationContext(
            schema=state.schema_context,
            lineage=state.lineage_context,
        )

        hypotheses = await self.llm.generate_hypotheses(
            alert=state.alert,
            context=context,
            num_hypotheses=self.config.max_hypotheses,
        )

        for h in hypotheses:
            state = state.append_event(
                Event(
                    type="hypothesis_generated",
                    timestamp=datetime.now(UTC),
                    data={
                        "hypothesis_id": h.id,
                        "title": h.title,
                        "category": h.category.value,
                    },
                )
            )

        return state, hypotheses

    async def _investigate_parallel(
        self,
        state: InvestigationState,
        hypotheses: list[Hypothesis],
    ) -> list[Evidence]:
        """Fan-out: Investigate all hypotheses in parallel.

        Args:
            state: Current investigation state.
            hypotheses: List of hypotheses to investigate.

        Returns:
            List of all evidence collected.
        """
        tasks = [self._investigate_hypothesis(state, h) for h in hypotheses]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        evidence: list[Evidence] = []
        for result in results:
            if isinstance(result, BaseException):
                # Log but don't fail entire investigation
                logger.warning("Hypothesis investigation failed", error=str(result))
                continue
            evidence.extend(result)

        return evidence

    async def _investigate_hypothesis(
        self,
        state: InvestigationState,
        hypothesis: Hypothesis,
    ) -> list[Evidence]:
        """Investigate a single hypothesis with retry/reflexion loop.

        Args:
            state: Current investigation state.
            hypothesis: The hypothesis to investigate.

        Returns:
            List of evidence collected for this hypothesis.
        """
        # schema_context and _current_adapter are guaranteed to be set
        assert state.schema_context is not None
        assert self._current_adapter is not None

        evidence: list[Evidence] = []
        max_queries = self.config.max_queries_per_hypothesis

        log = logger.bind(hypothesis_id=hypothesis.id, title=hypothesis.title)

        for query_num in range(max_queries):
            # Check circuit breaker
            self.circuit_breaker.check(state.events, hypothesis.id)

            # Generate query (with previous error context if retrying)
            previous_error: str | None = None
            if query_num > 0:
                failed = state.get_failed_queries(hypothesis.id)
                previous_error = failed[-1] if failed else None

            query = await self.llm.generate_query(
                hypothesis=hypothesis,
                schema=state.schema_context,
                previous_error=previous_error,
            )

            # Check for duplicate query (stall detection)
            if query in state.get_all_queries(hypothesis.id):
                log.warning("Duplicate query detected - stopping hypothesis")
                break

            # Record query submission
            state = state.append_event(
                Event(
                    type="query_submitted",
                    timestamp=datetime.now(UTC),
                    data={"hypothesis_id": hypothesis.id, "query": query},
                )
            )

            try:
                result = await self._current_adapter.execute_query(
                    query,
                    timeout_seconds=self.config.query_timeout_seconds,
                )

                state = state.append_event(
                    Event(
                        type="query_succeeded",
                        timestamp=datetime.now(UTC),
                        data={"hypothesis_id": hypothesis.id, "row_count": result.row_count},
                    )
                )

                # Interpret results
                ev = await self.llm.interpret_evidence(hypothesis, query, result)

                # Validate interpretation if enabled
                if self.config.validation_enabled and self.validator:
                    ev = await self._validate_interpretation(ev, hypothesis, query, state)

                evidence.append(ev)

                log.info(
                    "Query succeeded",
                    row_count=result.row_count,
                    confidence=ev.confidence,
                )

                # If high confidence, stop early
                if ev.confidence > self.config.high_confidence_threshold:
                    log.info("High confidence reached - stopping hypothesis")
                    break

            except Exception as e:
                state = state.append_event(
                    Event(
                        type="query_failed",
                        timestamp=datetime.now(UTC),
                        data={
                            "hypothesis_id": hypothesis.id,
                            "query": query,
                            "error": str(e),
                        },
                    )
                )

                log.warning("Query failed", error=str(e))

                # Check if we should retry
                retry_count = state.get_retry_count(hypothesis.id)
                if retry_count >= self.config.max_retries_per_hypothesis:
                    log.info("Max retries reached - stopping hypothesis")
                    break

                state = state.append_event(
                    Event(
                        type="reflexion_attempted",
                        timestamp=datetime.now(UTC),
                        data={"hypothesis_id": hypothesis.id, "retry_number": retry_count + 1},
                    )
                )

        return evidence

    async def _validate_interpretation(
        self,
        evidence: Evidence,
        hypothesis: Hypothesis,
        query: str,
        state: InvestigationState,
    ) -> Evidence:
        """Validate interpretation quality and capture training signal.

        Args:
            evidence: The evidence to validate.
            hypothesis: The hypothesis being tested.
            query: The SQL query that was executed.
            state: Current investigation state.

        Returns:
            The original evidence (validation doesn't modify it).
        """
        assert self.validator is not None

        # Construct InterpretationResponse from Evidence for validation
        # Note: Some fields are approximated since Evidence doesn't store all response fields
        interpretation_response = InterpretationResponse(
            supports_hypothesis=evidence.supports_hypothesis,
            confidence=evidence.confidence,
            interpretation=evidence.interpretation,
            # Use interpretation as causal_chain since Evidence doesn't store it separately
            causal_chain=evidence.interpretation[:100] if evidence.interpretation else "",
            # Extract key findings from interpretation
            key_findings=[evidence.interpretation[:200]] if evidence.interpretation else ["N/A"],
            next_investigation_step=None,
        )

        try:
            validation_result = await self.validator.validate_interpretation(
                response=interpretation_response,
                hypothesis_title=hypothesis.title,
                query=query,
            )

            logger.info(
                f"interpretation_validated passed={validation_result.passed} "
                f"composite={validation_result.assessment.composite_score:.2f}"
            )

            # Capture training signal if repository is available
            if self.training_repo:
                await self.training_repo.record_signal(
                    signal_type="interpretation",
                    tenant_id=state.tenant_id,
                    investigation_id=UUID(state.id),
                    input_context={
                        "hypothesis_title": hypothesis.title,
                        "hypothesis_reasoning": hypothesis.reasoning,
                        "query": query,
                    },
                    output_response=interpretation_response.model_dump(),
                    automated_score=validation_result.assessment.composite_score,
                    automated_dimensions=validation_result.training_signals,
                )

        except Exception as e:
            # Log but don't fail the investigation on validation errors
            logger.warning(f"interpretation_validation_failed error={e}")

        return evidence

    async def _synthesize(
        self,
        state: InvestigationState,
        evidence: list[Evidence],
        start_time: float,
    ) -> Finding:
        """Fan-in: Synthesize all evidence into a finding.

        Args:
            state: Current investigation state.
            evidence: All collected evidence.
            start_time: Investigation start time for duration calculation.

        Returns:
            Finding with root cause and recommendations.
        """
        finding = await self.llm.synthesize_findings(
            alert=state.alert,
            evidence=evidence,
        )

        # Update finding with investigation metadata
        duration = time.time() - start_time
        finding = Finding(
            investigation_id=state.id,
            status=finding.status,
            root_cause=finding.root_cause,
            confidence=finding.confidence,
            evidence=evidence,
            recommendations=finding.recommendations,
            duration_seconds=duration,
        )

        # Validate synthesis if enabled
        if self.config.validation_enabled and self.validator:
            await self._validate_synthesis(finding, state)

        state.append_event(
            Event(
                type="synthesis_completed",
                timestamp=datetime.now(UTC),
                data={"root_cause": finding.root_cause, "confidence": finding.confidence},
            )
        )

        return finding

    async def _validate_synthesis(
        self,
        finding: Finding,
        state: InvestigationState,
    ) -> None:
        """Validate synthesis quality and capture training signal.

        Args:
            finding: The finding to validate.
            state: Current investigation state.
        """
        assert self.validator is not None

        # Construct SynthesisResponse from Finding for validation
        # Note: Some fields are approximated since Finding doesn't store all response fields
        synthesis_response = SynthesisResponse(
            root_cause=finding.root_cause,
            confidence=finding.confidence,
            # Approximate causal_chain from root_cause
            causal_chain=(
                [finding.root_cause, "observed anomaly"]
                if finding.root_cause
                else ["unknown cause", "observed anomaly"]
            ),
            # Approximate onset from alert date
            estimated_onset=state.alert.anomaly_date,
            # Approximate scope from dataset
            affected_scope=f"Table: {state.alert.dataset_id}",
            # Use evidence interpretations as supporting evidence
            supporting_evidence=[
                ev.interpretation[:200] for ev in finding.evidence if ev.interpretation
            ]
            or ["No supporting evidence captured"],
            recommendations=finding.recommendations,
        )

        # Build alert summary for validation
        alert_summary = (
            f"{state.alert.metric_spec.display_name} anomaly in {state.alert.dataset_id}: "
            f"expected {state.alert.expected_value}, actual {state.alert.actual_value} "
            f"({state.alert.deviation_pct}% deviation)"
        )

        try:
            validation_result = await self.validator.validate_synthesis(
                response=synthesis_response,
                alert_summary=alert_summary,
            )

            logger.info(
                f"synthesis_validated passed={validation_result.passed} "
                f"composite={validation_result.assessment.composite_score:.2f}"
            )

            # Capture training signal if repository is available
            if self.training_repo:
                await self.training_repo.record_signal(
                    signal_type="synthesis",
                    tenant_id=state.tenant_id,
                    investigation_id=UUID(state.id),
                    input_context={
                        "alert_summary": alert_summary,
                        "evidence_count": len(finding.evidence),
                    },
                    output_response=synthesis_response.model_dump(),
                    automated_score=validation_result.assessment.composite_score,
                    automated_dimensions=validation_result.training_signals,
                )

        except Exception as e:
            # Log but don't fail the investigation on validation errors
            logger.warning(f"synthesis_validation_failed error={e}")
