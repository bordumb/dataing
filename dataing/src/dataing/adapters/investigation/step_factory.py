"""Step factory for creating investigation steps with real dependencies.

This module provides a factory that creates step registries wired with
production dependencies. The registry is created per-investigation
since some steps require investigation-specific dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from dataing.adapters.investigation.context_adapter import ContextEngineAdapter
from dataing.adapters.investigation.database_adapter import DatabaseAdapter
from dataing.adapters.investigation.llm_adapter import (
    HypothesisLLMAdapter,
    InterpretEvidenceLLMAdapter,
    QueryLLMAdapter,
    SynthesisLLMAdapter,
)
from dataing.adapters.investigation.pattern_adapter import InMemoryPatternRepository
from dataing.core.investigation.registry import StepRegistry
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

if TYPE_CHECKING:
    from dataing.adapters.context.engine import ContextEngine
    from dataing.adapters.datasource.base import BaseAdapter
    from dataing.agents.client import AgentClient
    from dataing.core.domain_types import AnomalyAlert
    from dataing.services.usage import UsageTracker


def create_step_registry(
    *,
    agent_client: AgentClient,
    context_engine: ContextEngine,
    alert: AnomalyAlert,
    data_adapter: BaseAdapter,
    pattern_repository: InMemoryPatternRepository | None = None,
    usage_tracker: UsageTracker | None = None,
    tenant_id: UUID | None = None,
    investigation_id: UUID | None = None,
    model: str = "claude-sonnet-4-20250514",
) -> StepRegistry:
    """Create a step registry with real production dependencies.

    This factory creates all the steps wired with real implementations.
    It should be called when starting a new investigation, when the
    investigation-specific dependencies are known.

    Args:
        agent_client: The LLM client for AI operations.
        context_engine: Engine for gathering context from data sources.
        alert: The anomaly alert being investigated.
        data_adapter: Connected adapter for the data source.
        pattern_repository: Optional pattern repository (creates in-memory if None).
        usage_tracker: Optional usage tracker for recording usage metrics.
        tenant_id: Tenant ID for usage tracking.
        investigation_id: Investigation ID for usage tracking.
        model: Model name for usage tracking.

    Returns:
        StepRegistry with configured step instances.
    """
    # Use provided pattern repository or create a new one
    if pattern_repository is None:
        pattern_repository = InMemoryPatternRepository()

    # Create adapters with usage tracking
    context_adapter = ContextEngineAdapter(context_engine, alert, data_adapter)
    database_adapter = DatabaseAdapter(
        data_adapter,
        usage_tracker=usage_tracker,
        tenant_id=tenant_id,
        investigation_id=investigation_id,
    )
    hypothesis_llm = HypothesisLLMAdapter(
        agent_client,
        usage_tracker=usage_tracker,
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        model=model,
    )
    interpret_llm = InterpretEvidenceLLMAdapter(
        agent_client,
        usage_tracker=usage_tracker,
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        model=model,
    )
    synthesis_llm = SynthesisLLMAdapter(
        agent_client,
        usage_tracker=usage_tracker,
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        model=model,
    )
    query_llm = QueryLLMAdapter(
        agent_client,
        usage_tracker=usage_tracker,
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        model=model,
    )

    # Build registry with all steps
    registry = StepRegistry()
    registry.register(GatherContextStep(context_adapter))
    registry.register(CheckPatternsStep(pattern_repository))
    registry.register(GenerateHypothesesStep(hypothesis_llm))
    registry.register(GenerateQueryStep(query_llm))
    registry.register(ExecuteQueryStep(database_adapter))
    registry.register(InterpretEvidenceStep(interpret_llm))
    registry.register(SynthesizeStep(synthesis_llm))
    registry.register(CounterAnalyzeStep())

    return registry
