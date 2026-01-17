"""Investigation workflow using maistro engine.

This module provides a workflow engine for running investigations using maistro's
event-sourced architecture. It uses maistro.Workflow for step orchestration with
streaming events for checkpointing support.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

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
from maistro import (
    RunCompleted,
    RunFailed,
    Signal,
    StepCompleted,
    Workflow,
)

if TYPE_CHECKING:
    from dataing.agents.client import AgentClient
    from dataing.core.investigation.pattern_extraction import PatternRepositoryProtocol
    from dataing.core.investigation.steps.execute_query import DatabaseProtocol
    from dataing.core.investigation.steps.gather_context import ContextEngineProtocol


class InvestigationMergeStrategy:
    """Merge strategy for investigation branches.

    Combines evidence and query counters from multiple hypothesis branches
    back into the parent InvestigationContext.

    Branch payloads are expected to be either:
    - {"_full_context": InvestigationContext} for successful branches
    - {"maistro": {"branch_error": {...}}} for failed branches
    """

    def merge(
        self,
        parent_context: InvestigationContext,
        branch_contexts: dict[str, Any],
    ) -> InvestigationContext:
        """Merge branch investigation contexts into parent.

        Concatenates evidence from all successful branches and sums query counters.
        Failed branches are logged but don't contribute to merged context.

        Args:
            parent_context: The context from before branching (has hypotheses).
            branch_contexts: Map of branch_name -> branch payload.

        Returns:
            Merged InvestigationContext with combined evidence.
        """
        merged_evidence: list[dict[str, Any]] = list(parent_context.evidence)
        total_queries_delta = 0

        for branch_name in sorted(branch_contexts.keys()):
            payload = branch_contexts[branch_name]

            # Skip error payloads
            if isinstance(payload, dict):
                if "maistro" in payload and "branch_error" in payload.get("maistro", {}):
                    # Log error but continue - branch failed
                    continue

                # Unwrap _full_context
                if "_full_context" in payload:
                    branch_ctx = payload["_full_context"]
                    if isinstance(branch_ctx, InvestigationContext):
                        # Compute evidence delta (new items only)
                        parent_evidence_len = len(parent_context.evidence)
                        if len(branch_ctx.evidence) > parent_evidence_len:
                            new_evidence = branch_ctx.evidence[parent_evidence_len:]
                            merged_evidence.extend(new_evidence)

                        # Compute query counter delta
                        query_delta = max(
                            0,
                            branch_ctx.total_queries_executed
                            - parent_context.total_queries_executed,
                        )
                        total_queries_delta += query_delta

        # Create merged context
        return parent_context.model_copy(
            update={
                "evidence": merged_evidence,
                "total_queries_executed": (
                    parent_context.total_queries_executed + total_queries_delta
                ),
            }
        )


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


class InvestigationCancelled(Exception):
    """Raised when investigation is cancelled by user.

    The worker detects 'cancelling' status at a step boundary and raises
    this after checkpointing. The job will be marked as 'cancelled'.
    """

    pass


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

    Creates a maistro.Workflow configured with all investigation steps.
    The event-sourced Engine handles signals internally.

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
    # Use custom merge strategy for proper evidence aggregation
    workflow: Workflow[InvestigationContext] = Workflow(merge_strategy=InvestigationMergeStrategy())

    # Create LLM adapters that wrap AgentClient with step-compatible interfaces
    hypothesis_llm = HypothesisLLMAdapter(llm)
    query_llm = QueryLLMAdapter(llm)
    evidence_llm = InterpretEvidenceLLMAdapter(llm)
    synthesis_llm = SynthesisLLMAdapter(llm)

    # Add steps in logical order (actual routing controlled by signals)
    workflow.add_step(GatherContextStep(context_engine, database))  # type: ignore[arg-type]
    workflow.add_step(CheckPatternsStep(pattern_repository))
    workflow.add_step(GenerateHypothesesStep(hypothesis_llm, max_hypotheses))
    workflow.add_step(GenerateQueryStep(query_llm))
    workflow.add_step(ExecuteQueryStep(database))
    workflow.add_step(InterpretEvidenceStep(evidence_llm))
    workflow.add_step(SynthesizeStep(synthesis_llm, confidence_threshold))
    workflow.add_step(CounterAnalyzeStep())

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
        context=initial_context,
        start_step=StepType.GATHER_CONTEXT.value,
        max_iterations=max_iterations,
    )


async def run_with_checkpointing(
    *,
    workflow: Workflow[InvestigationContext],
    context: InvestigationContext,
    start_step: str,
    on_step_complete: Callable[
        [InvestigationContext, str | None, dict[str, Any] | None], Awaitable[None]
    ],
    shutdown_signal: asyncio.Event,
    start_cursor: dict[str, Any] | None = None,
    max_iterations: int = 100,
) -> InvestigationContext:
    """Run investigation workflow with checkpoint callbacks for durable execution.

    Uses maistro's streaming API to receive events and checkpoint after each step.
    If the worker receives a shutdown signal, it checkpoints and raises
    WorkerShutdownError to allow graceful shutdown.

    Args:
        workflow: The configured investigation workflow.
        context: Current investigation context (may be from a previous checkpoint).
        start_step: Step to start (or resume) execution from.
        on_step_complete: Async callback invoked after each step with
            (context, next_step, step_cursor). next_step indicates the resume point.
        shutdown_signal: Event that signals worker shutdown.
        start_cursor: Optional cursor data from previous checkpoint (unused in new API).
        max_iterations: Maximum steps before timeout (default 100).

    Returns:
        Final investigation context with findings.

    Raises:
        WorkerShutdownError: If shutdown signal is set during execution.
        AwaitingUserInput: If workflow pauses for user input.
        InvestigationError: If workflow fails.
        RuntimeError: If max iterations exceeded.
    """
    current_context = context
    iterations = 0

    # Stream events from the workflow
    async for event in workflow.run_streaming(
        context=context,
        start_step=start_step,
        input_data=start_cursor,
    ):
        iterations += 1
        if iterations > max_iterations:
            raise RuntimeError(f"Max iterations ({max_iterations}) exceeded")

        # Check for graceful shutdown between events
        if shutdown_signal.is_set():
            # Determine next step from current state
            next_step: str | None = None
            if isinstance(event, StepCompleted):
                next_step = event.next_step
            await on_step_complete(current_context, next_step, None)
            raise WorkerShutdownError("Worker shutting down, checkpointed")

        # Handle StepCompleted events - checkpoint after each step
        if isinstance(event, StepCompleted):
            # Extract the full context from the event
            # For non-dict contexts, Runner stores {"_full_context": context}
            ctx_update = event.context_update
            if "_full_context" in ctx_update:
                current_context = ctx_update["_full_context"]

            # Determine checkpoint info based on signal
            checkpoint_step = event.next_step
            checkpoint_cursor: dict[str, Any] | None = None

            if event.signal == Signal.FAIL:
                checkpoint_step = StepType.FAIL.value
            elif event.signal == Signal.AWAIT_USER and checkpoint_step is None:
                checkpoint_step = StepType.AWAIT_USER.value

            # Checkpoint after step completion
            await on_step_complete(current_context, checkpoint_step, checkpoint_cursor)

            # Handle terminal signals
            if event.signal == Signal.AWAIT_USER:
                raise AwaitingUserInput(event.next_step)

        # Handle terminal events
        elif isinstance(event, RunCompleted):
            return current_context

        elif isinstance(event, RunFailed):
            raise InvestigationError(event.error)

    return current_context
