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

import structlog

from .domain_types import Evidence, Finding, Hypothesis, InvestigationContext
from .exceptions import CircuitBreakerTripped, SchemaDiscoveryError
from .state import Event, InvestigationState

if TYPE_CHECKING:
    from ..safety.circuit_breaker import CircuitBreaker
    from .interfaces import ContextEngine, DatabaseAdapter, LLMClient

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
    """

    max_hypotheses: int = 5
    max_queries_per_hypothesis: int = 3
    max_retries_per_hypothesis: int = 2
    query_timeout_seconds: int = 30
    high_confidence_threshold: float = 0.85


class InvestigationOrchestrator:
    """Orchestrates the investigation workflow.

    Flow: Context -> Hypothesize -> Parallel Investigation -> Synthesis

    The orchestrator is stateless - all state is passed through
    InvestigationState, which uses event sourcing.
    """

    def __init__(
        self,
        db: DatabaseAdapter,
        llm: LLMClient,
        context_engine: ContextEngine,
        circuit_breaker: CircuitBreaker,
        config: OrchestratorConfig | None = None,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            db: Database adapter for executing queries (fallback).
            llm: LLM client for generating hypotheses and queries.
            context_engine: Engine for gathering investigation context.
            circuit_breaker: Safety circuit breaker.
            config: Optional orchestrator configuration.
        """
        self.db = db
        self.llm = llm
        self.context_engine = context_engine
        self.circuit_breaker = circuit_breaker
        self.config = config or OrchestratorConfig()
        # Will be set per-investigation when using tenant data source
        self._current_adapter: DatabaseAdapter | None = None

    async def run_investigation(
        self,
        state: InvestigationState,
        data_adapter: DatabaseAdapter | None = None,
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
            metric=state.alert.metric_name,
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

        try:
            # 1. Gather Context (FAIL FAST if schema empty)
            state = await self._gather_context(state)
            if state.schema_context is None:
                raise SchemaDiscoveryError("Schema context is None after gathering")
            log.info("Context gathered", tables_found=len(state.schema_context.tables))

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
        if not context.schema.tables:
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
                    "tables_found": len(context.schema.tables),
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

        state.append_event(
            Event(
                type="synthesis_completed",
                timestamp=datetime.now(UTC),
                data={"root_cause": finding.root_cause, "confidence": finding.confidence},
            )
        )

        return finding
