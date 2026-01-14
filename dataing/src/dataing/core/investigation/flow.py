"""Investigation workflow using maestro engine.

This module provides a simpler, in-memory workflow engine for running
investigations. It uses maestro.Workflow for step orchestration without
the persistence complexity of the legacy orchestrator.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
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


class WorkerShutdownError(Exception):
    """Raised when worker receives shutdown signal during execution.

    The checkpoint callback will have been invoked before this is raised,
    allowing the job to be safely resumed from the last completed step.
    """

    pass


class AwaitingUserInput(Exception):
    """Raised when workflow pauses to wait for user input.

    Attributes:
        next_step: The step that should resume when user provides input.
    """

    def __init__(self, next_step: str | None) -> None:
        """Initialize with the next step to resume."""
        self.next_step = next_step
        super().__init__(f"Awaiting user input, resume at step: {next_step}")


class InvestigationError(Exception):
    """Raised when investigation workflow fails.

    Attributes:
        error: The error message from the failing step.
    """

    def __init__(self, error: str | None) -> None:
        """Initialize with error message."""
        self.error = error
        super().__init__(error or "Investigation failed")


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


async def run_with_checkpointing(
    *,
    workflow: Workflow[InvestigationContext],
    context: InvestigationContext,
    start_step: str,
    on_step_complete: Callable[[InvestigationContext, str | None], Awaitable[None]],
    shutdown_signal: asyncio.Event,
    max_iterations: int = 100,
) -> InvestigationContext:
    """Run investigation workflow with checkpoint callbacks for durable execution.

    This function enables crash recovery by invoking a checkpoint callback
    after each step completes. If the worker receives a shutdown signal,
    it checkpoints and raises WorkerShutdownError to allow graceful shutdown.

    Args:
        workflow: The configured investigation workflow.
        context: Current investigation context (may be from a previous checkpoint).
        start_step: Step to start (or resume) execution from.
        on_step_complete: Async callback invoked after each step with
            (context, next_step). Use this to persist checkpoint state.
        shutdown_signal: Event that signals worker shutdown. When set,
            the function checkpoints and raises WorkerShutdownError.
        max_iterations: Maximum steps before timeout (default 100).

    Returns:
        Final investigation context with findings.

    Raises:
        WorkerShutdownError: If shutdown signal is set during execution.
        AwaitingUserInput: If workflow pauses for user input.
        InvestigationError: If workflow fails.
        RuntimeError: If max iterations exceeded.
    """
    current_step: str | None = start_step
    iterations = 0

    while current_step:
        iterations += 1
        if iterations > max_iterations:
            raise RuntimeError(f"Max iterations ({max_iterations}) exceeded")

        # Check for graceful shutdown before executing step
        if shutdown_signal.is_set():
            await on_step_complete(context, current_step)
            raise WorkerShutdownError("Worker shutting down, checkpointed")

        # Execute step via maestro
        result = await workflow.tick(context, current_step)

        # Checkpoint after each step completes
        await on_step_complete(result.context, result.next_step)

        # Handle signals
        if result.signal == Signal.COMPLETE:
            return result.context

        if result.signal == Signal.FAIL:
            raise InvestigationError(result.error)

        if result.signal == Signal.AWAIT_USER:
            raise AwaitingUserInput(result.next_step)

        # Continue to next step
        context = result.context
        current_step = result.next_step

    return context
