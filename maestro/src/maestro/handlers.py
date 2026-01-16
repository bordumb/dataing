"""Signal handlers for workflow execution.

Signal handlers process the signals returned by steps and determine
how the workflow should proceed. They can be customized to implement
domain-specific branching, merging, and completion logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Protocol, TypeVar, runtime_checkable

from maestro.result import StepResult
from maestro.signals import Signal

if TYPE_CHECKING:
    from maestro.workflow import Workflow

ContextT = TypeVar("ContextT")


class SignalHandlerError(Exception):
    """Exception raised when signal handling fails."""

    pass


@dataclass(frozen=True)
class BranchContext(Generic[ContextT]):
    """Context for a child branch.

    Attributes:
        name: Unique name for this branch.
        context: The context for this branch.
        data: Additional data passed from BranchSpec.

    """

    name: str
    context: ContextT
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SignalResult(Generic[ContextT]):
    """Result of handling a signal.

    Attributes:
        context: The (possibly updated) context.
        should_continue: Whether the workflow should continue.
        next_step: Next step name (for CONTINUE).
        branch_contexts: Child branch contexts (for BRANCH).
        error: Error message (for FAIL).

    """

    context: ContextT
    should_continue: bool = True
    next_step: str | None = None
    branch_contexts: list[BranchContext[ContextT]] | None = None
    error: str | None = None


@runtime_checkable
class MergeStrategy(Protocol[ContextT]):
    """Protocol for merging branch contexts.

    Implementations define how to combine results from multiple
    child branches back into a parent context.
    """

    def merge(
        self,
        parent_context: ContextT,
        child_contexts: list[BranchContext[ContextT]],
    ) -> ContextT:
        """Merge child branch contexts into parent.

        Args:
            parent_context: The context from before branching.
            child_contexts: Results from all child branches.

        Returns:
            Merged context to continue with.

        """
        ...


class SignalHandler(ABC, Generic[ContextT]):
    """Abstract base class for signal handlers.

    Signal handlers process signals from step execution and determine
    how the workflow should proceed. Override specific handle_* methods
    to customize behavior.
    """

    async def handle(
        self,
        signal: Signal,
        context: ContextT,
        result: StepResult[ContextT, Any],
        workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Handle a signal from step execution.

        Routes to specific handler methods based on signal type.

        Args:
            signal: The signal to handle.
            context: Current workflow context.
            result: The StepResult from step execution.
            workflow: The workflow instance (for step access).

        Returns:
            SignalResult indicating how to proceed.

        """
        if signal == Signal.CONTINUE:
            return await self.handle_continue(context, result, workflow)
        elif signal == Signal.COMPLETE:
            return await self.handle_complete(context, result, workflow)
        elif signal == Signal.FAIL:
            return await self.handle_fail(context, result, workflow)
        elif signal == Signal.BRANCH:
            return await self.handle_branch(context, result, workflow)
        elif signal == Signal.MERGE:
            return await self.handle_merge(context, result, workflow)
        elif signal == Signal.AWAIT_USER:
            return await self.handle_await_user(context, result, workflow)
        else:
            raise SignalHandlerError(f"Unknown signal: {signal}")

    @abstractmethod
    async def handle_continue(
        self,
        context: ContextT,
        result: StepResult[ContextT, Any],
        workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Handle CONTINUE signal.

        Args:
            context: Current workflow context.
            result: The StepResult from step execution.
            workflow: The workflow instance.

        Returns:
            SignalResult with next_step set.

        """
        ...

    @abstractmethod
    async def handle_complete(
        self,
        context: ContextT,
        result: StepResult[ContextT, Any],
        workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Handle COMPLETE signal.

        Args:
            context: Current workflow context.
            result: The StepResult from step execution.
            workflow: The workflow instance.

        Returns:
            SignalResult with should_continue=False.

        """
        ...

    @abstractmethod
    async def handle_fail(
        self,
        context: ContextT,
        result: StepResult[ContextT, Any],
        workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Handle FAIL signal.

        Args:
            context: Current workflow context.
            result: The StepResult from step execution.
            workflow: The workflow instance.

        Returns:
            SignalResult with should_continue=False and error set.

        """
        ...

    @abstractmethod
    async def handle_branch(
        self,
        context: ContextT,
        result: StepResult[ContextT, Any],
        workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Handle BRANCH signal.

        Args:
            context: Current workflow context.
            result: The StepResult with branch_request.
            workflow: The workflow instance.

        Returns:
            SignalResult with branch_contexts set.

        """
        ...

    @abstractmethod
    async def handle_merge(
        self,
        context: ContextT,
        result: StepResult[ContextT, Any],
        workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Handle MERGE signal.

        Args:
            context: Current workflow context.
            result: The StepResult from step execution.
            workflow: The workflow instance.

        Returns:
            SignalResult with merged context.

        """
        ...

    @abstractmethod
    async def handle_await_user(
        self,
        context: ContextT,
        result: StepResult[ContextT, Any],
        workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Handle AWAIT_USER signal.

        Pauses the workflow to wait for external user input.

        Args:
            context: Current workflow context.
            result: The StepResult from step execution.
            workflow: The workflow instance.

        Returns:
            SignalResult with should_continue=False (workflow pauses).

        """
        ...


class DefaultSignalHandler(SignalHandler[ContextT]):
    """Default signal handler with basic implementations.

    Handles CONTINUE, COMPLETE, FAIL, and AWAIT_USER signals.
    BRANCH and MERGE raise NotImplementedError.
    """

    async def handle_continue(
        self,
        _context: ContextT,
        result: StepResult[ContextT, Any],
        _workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Continue to next step.

        Uses explicit next_step from result or falls back to
        workflow's sequential ordering.
        """
        return SignalResult(
            context=result.context,
            should_continue=True,
            next_step=result.next_step,
        )

    async def handle_complete(
        self,
        _context: ContextT,
        result: StepResult[ContextT, Any],
        _workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Complete the workflow."""
        return SignalResult(
            context=result.context,
            should_continue=False,
        )

    async def handle_fail(
        self,
        _context: ContextT,
        result: StepResult[ContextT, Any],
        _workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Fail the workflow."""
        return SignalResult(
            context=result.context,
            should_continue=False,
            error="Workflow failed",
        )

    async def handle_await_user(
        self,
        _context: ContextT,
        result: StepResult[ContextT, Any],
        _workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Pause workflow for user input."""
        return SignalResult(
            context=result.context,
            should_continue=False,
            next_step=result.next_step,
        )

    async def handle_branch(
        self,
        _context: ContextT,
        _result: StepResult[ContextT, Any],
        _workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Handle BRANCH - not implemented in default handler."""
        raise NotImplementedError(
            "BRANCH signal not supported by DefaultSignalHandler. "
            "Use BranchingSignalHandler for branch/merge support."
        )

    async def handle_merge(
        self,
        _context: ContextT,
        _result: StepResult[ContextT, Any],
        _workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Handle MERGE - not implemented in default handler."""
        raise NotImplementedError(
            "MERGE signal not supported by DefaultSignalHandler. "
            "Use BranchingSignalHandler for branch/merge support."
        )


class BranchingSignalHandler(DefaultSignalHandler[ContextT]):
    """Signal handler with branch and merge support.

    Extends DefaultSignalHandler to handle BRANCH and MERGE signals.
    Requires a MergeStrategy for combining branch results.

    Attributes:
        merge_strategy: Strategy for merging branch contexts.
        pending_branches: Branches awaiting completion for merge.

    """

    def __init__(self, merge_strategy: MergeStrategy[ContextT]) -> None:
        """Initialize with merge strategy.

        Args:
            merge_strategy: Strategy for merging branch contexts.

        """
        self._merge_strategy = merge_strategy
        self._pending_branches: dict[str, list[BranchContext[ContextT]]] = {}
        self._parent_contexts: dict[str, ContextT] = {}
        self._expected_counts: dict[str, int] = {}

    async def handle_branch(
        self,
        _context: ContextT,
        result: StepResult[ContextT, Any],
        _workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Create child branch contexts from BranchRequest.

        The workflow should execute each child context and collect
        results for later merge.
        """
        if result.branch_request is None:
            raise SignalHandlerError("BRANCH signal without branch_request")

        branch_request = result.branch_request
        branch_contexts: list[BranchContext[ContextT]] = []

        for spec in branch_request.branches:
            # Create context for each child branch
            # The actual context modification is domain-specific;
            # here we just copy the parent context
            branch_ctx = BranchContext(
                name=spec.name,
                context=result.context,
                data=spec.data,
            )
            branch_contexts.append(branch_ctx)

        # Store parent context and expected count for later merge
        merge_key = branch_request.merge_step
        self._parent_contexts[merge_key] = result.context
        self._expected_counts[merge_key] = len(branch_contexts)
        self._pending_branches[merge_key] = []

        return SignalResult(
            context=result.context,
            should_continue=True,
            next_step=branch_request.child_start_step,
            branch_contexts=branch_contexts,
        )

    def register_branch_completion(
        self,
        merge_step: str,
        branch_context: BranchContext[ContextT],
    ) -> bool:
        """Register a completed branch and check if all are done.

        Args:
            merge_step: The merge step waiting for this branch.
            branch_context: The completed branch context.

        Returns:
            True if all branches are complete and ready for merge.

        """
        if merge_step not in self._pending_branches:
            self._pending_branches[merge_step] = []

        self._pending_branches[merge_step].append(branch_context)

        expected = self._expected_counts.get(merge_step, 0)
        return len(self._pending_branches[merge_step]) >= expected

    async def handle_merge(
        self,
        _context: ContextT,
        result: StepResult[ContextT, Any],
        _workflow: Workflow[ContextT],
    ) -> SignalResult[ContextT]:
        """Merge completed branch contexts.

        Uses the configured MergeStrategy to combine all child
        branch results back into a single context.
        """
        # Find pending branches that have this step as merge point
        step_name = result.next_step or "merge"

        if step_name not in self._pending_branches:
            raise SignalHandlerError(
                f"No pending branches for merge step: {step_name}"
            )

        pending = self._pending_branches.pop(step_name)
        parent_ctx = self._parent_contexts.pop(step_name, result.context)
        self._expected_counts.pop(step_name, None)

        if not pending:
            raise SignalHandlerError("No child contexts to merge")

        merged_context = self._merge_strategy.merge(parent_ctx, pending)

        return SignalResult(
            context=merged_context,
            should_continue=True,
            next_step=result.next_step,
        )
