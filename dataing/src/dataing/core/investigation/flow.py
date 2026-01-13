"""Investigation workflow using maestro engine.

This module provides a simpler, in-memory workflow engine for running
investigations. It uses maestro.Workflow for step orchestration without
the persistence complexity of the legacy orchestrator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from maestro import (
    BranchContext,
    BranchingSignalHandler,
    MergeStrategy,
    Signal,
    SignalResult,
    StepResult,
    Workflow,
)

from dataing.adapters.investigation.llm_adapter import (
    HypothesisLLMAdapter,
    InterpretEvidenceLLMAdapter,
    QueryLLMAdapter,
    SynthesisLLMAdapter,
)
from dataing.core.investigation.entities import InvestigationContext
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
from dataing.core.investigation.values import StepType

if TYPE_CHECKING:
    from dataing.agents.client import AgentClient
    from dataing.core.investigation.steps.gather_context import ContextEngineProtocol
    from dataing.core.investigation.steps.execute_query import DatabaseProtocol
    from dataing.core.investigation.pattern_extraction import PatternRepositoryProtocol


class InvestigationMergeStrategy(MergeStrategy[InvestigationContext]):
    """Merge strategy for investigation branch convergence.

    Combines evidence and hypotheses from multiple child branches
    back into the parent context.
    """

    def merge(
        self,
        parent_context: InvestigationContext,
        child_contexts: list[BranchContext[InvestigationContext]],
    ) -> InvestigationContext:
        """Merge child branch contexts into parent.

        Combines:
        - Evidence lists from all children
        - Query results and counts

        Args:
            parent_context: The context from before branching.
            child_contexts: Results from all child branches.

        Returns:
            Merged context with combined evidence.
        """
        # Collect all evidence from child branches
        merged_evidence: list[dict[str, Any]] = list(parent_context.evidence)
        total_queries = parent_context.total_queries_executed

        for child in child_contexts:
            child_ctx = child.context
            merged_evidence.extend(child_ctx.evidence)
            total_queries += child_ctx.total_queries_executed

        return parent_context.model_copy(
            update={
                "evidence": merged_evidence,
                "total_queries_executed": total_queries,
            }
        )


class InvestigationSignalHandler(BranchingSignalHandler[InvestigationContext]):
    """Signal handler for investigation workflows.

    Extends BranchingSignalHandler with investigation-specific behavior.
    """

    def __init__(self) -> None:
        """Initialize with investigation merge strategy."""
        super().__init__(InvestigationMergeStrategy())

    async def handle_await_user(
        self,
        _context: InvestigationContext,
        result: StepResult[InvestigationContext, Any],
        _workflow: Workflow[InvestigationContext],
    ) -> SignalResult[InvestigationContext]:
        """Handle AWAIT_USER signal.

        Pauses the workflow to wait for user input.
        The workflow can be resumed later with new input.
        """
        return SignalResult(
            context=result.context,
            should_continue=False,
            next_step=result.next_step,
        )


def build_investigation_workflow(
    *,
    context_engine: ContextEngineProtocol,
    llm: AgentClient,
    database: DatabaseProtocol,
    pattern_repository: PatternRepositoryProtocol,
    max_hypotheses: int = 5,
    confidence_threshold: float = 0.85,
) -> Workflow[InvestigationContext]:
    """Build a complete investigation workflow.

    Creates a maestro.Workflow configured with all investigation steps
    and appropriate signal handlers for branching/merging.

    Args:
        context_engine: Engine for gathering schema/lineage context.
        llm: AgentClient for LLM operations (wrapped with adapters internally).
        database: Database adapter for query execution.
        pattern_repository: Repository for historical pattern matching.
        max_hypotheses: Maximum hypotheses to generate (default 5).
        confidence_threshold: Minimum confidence for completion (default 0.85).

    Returns:
        Configured Workflow ready for execution.
    """
    workflow: Workflow[InvestigationContext] = Workflow()

    # Create LLM adapters that wrap AgentClient with step-compatible interfaces
    hypothesis_llm = HypothesisLLMAdapter(llm)
    query_llm = QueryLLMAdapter(llm)
    evidence_llm = InterpretEvidenceLLMAdapter(llm)
    synthesis_llm = SynthesisLLMAdapter(llm)

    # Add steps in logical order (actual routing controlled by signals)
    workflow.add_step(GatherContextStep(context_engine, database))
    workflow.add_step(CheckPatternsStep(pattern_repository))
    workflow.add_step(GenerateHypothesesStep(hypothesis_llm, max_hypotheses))
    workflow.add_step(GenerateQueryStep(query_llm))
    workflow.add_step(ExecuteQueryStep(database))
    workflow.add_step(InterpretEvidenceStep(evidence_llm))
    workflow.add_step(SynthesizeStep(synthesis_llm, confidence_threshold))
    workflow.add_step(CounterAnalyzeStep())

    # Configure signal handler for branching and merging
    workflow.set_signal_handler(InvestigationSignalHandler())

    return workflow


async def run_investigation(
    *,
    workflow: Workflow[InvestigationContext],
    initial_context: InvestigationContext,
    max_iterations: int = 100,
) -> InvestigationContext:
    """Run an investigation workflow to completion.

    Args:
        workflow: The configured investigation workflow.
        initial_context: Initial context with alert information.
        max_iterations: Maximum steps before timeout (default 100).

    Returns:
        Final investigation context with findings.

    Raises:
        WorkflowError: If workflow fails or times out.
    """
    return await workflow.run(
        initial_context=initial_context,
        start_step=StepType.GATHER_CONTEXT.value,
        max_iterations=max_iterations,
    )
