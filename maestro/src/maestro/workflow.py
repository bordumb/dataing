"""Workflow engine for step-based execution.

The Workflow class orchestrates step execution in a tick loop,
handling signals to determine the next action.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from maestro.result import BranchRequest, StepResult
from maestro.signals import Signal
from maestro.step import Step

if TYPE_CHECKING:
    from maestro.handlers import SignalHandler

ContextT = TypeVar("ContextT")


class WorkflowError(Exception):
    """Exception raised when a workflow fails.

    Attributes:
        context: The context at the time of failure.
        message: Error description.

    """

    def __init__(self, message: str, context: Any = None) -> None:
        """Initialize WorkflowError.

        Args:
            message: Error description.
            context: The context at the time of failure.

        """
        super().__init__(message)
        self.context = context
        self.message = message


@dataclass(frozen=True)
class TickResult(Generic[ContextT]):
    """Result of a single tick (step execution).

    Attributes:
        context: The (possibly updated) context after the step.
        signal: The signal returned by the step.
        next_step: Name of the next step to execute (if CONTINUE).
        branch_request: Branch specifications (if BRANCH signal).
        output: Any output from the step.
        error: Error message if the tick failed.

    """

    context: ContextT
    signal: Signal
    next_step: str | None = None
    branch_request: BranchRequest | None = None
    output: Any = None
    error: str | None = None


class Workflow(Generic[ContextT]):
    """Generic workflow engine.

    Executes steps in a tick loop, handling signals to determine
    the next action. Steps are registered by name and can be
    routed explicitly via StepResult.next_step.

    Example:
        ```python
        workflow = Workflow[MyContext]()
        workflow.add_step(InitStep())
        workflow.add_step(ProcessStep())
        workflow.add_step(FinalizeStep())

        result = await workflow.run(
            initial_context=MyContext(...),
            start_step="init",
        )
        ```

    """

    def __init__(self, fail_on_cannot_execute: bool = True) -> None:
        """Initialize workflow.

        Args:
            fail_on_cannot_execute: If True, raise an error when can_execute()
                returns False. If False, skip the step and continue.

        """
        self._steps: dict[str, Step[ContextT, Any, Any]] = {}
        self._step_order: list[str] = []
        self._fail_on_cannot_execute = fail_on_cannot_execute
        self._signal_handler: SignalHandler[ContextT] | None = None

    def set_signal_handler(self, handler: SignalHandler[ContextT]) -> None:
        """Set a custom signal handler.

        The signal handler processes signals returned by steps
        to determine how the workflow should proceed.

        Args:
            handler: The signal handler to use.

        """
        self._signal_handler = handler

    def get_signal_handler(self) -> SignalHandler[ContextT] | None:
        """Get the current signal handler.

        Returns:
            The current signal handler, or None if not set.

        """
        return self._signal_handler

    def add_step(self, step: Step[ContextT, Any, Any]) -> None:
        """Register a step with the workflow.

        Steps are executed in the order they are added unless
        explicitly routed via StepResult.next_step.

        Args:
            step: The step to register.

        Raises:
            ValueError: If a step with the same name is already registered.

        """
        if step.name in self._steps:
            raise ValueError(f"Step already registered: {step.name}")
        self._steps[step.name] = step
        self._step_order.append(step.name)

    def get_step(self, name: str) -> Step[ContextT, Any, Any] | None:
        """Get a step by name.

        Args:
            name: The step name.

        Returns:
            The step, or None if not found.

        """
        return self._steps.get(name)

    async def tick(
        self,
        context: ContextT,
        step_name: str,
        input_data: Any = None,
    ) -> TickResult[ContextT]:
        """Execute a single step.

        Args:
            context: Current workflow context.
            step_name: Name of the step to execute.
            input_data: Optional input data for the step.

        Returns:
            TickResult with the execution outcome.

        """
        step = self._steps.get(step_name)
        if step is None:
            return TickResult(
                context=context,
                signal=Signal.FAIL,
                error=f"Step not found: {step_name}",
            )

        # Check preconditions
        if not step.can_execute(context):
            if self._fail_on_cannot_execute:
                return TickResult(
                    context=context,
                    signal=Signal.FAIL,
                    error=f"Step preconditions not met: {step_name}",
                )
            else:
                # Skip this step, try to get next
                skip_next = self._get_next_step(step_name)
                if skip_next is None:
                    return TickResult(
                        context=context,
                        signal=Signal.COMPLETE,
                    )
                return TickResult(
                    context=context,
                    signal=Signal.CONTINUE,
                    next_step=skip_next,
                )

        # Execute step
        try:
            result: StepResult[ContextT, Any] = await step.execute(context, input_data)
        except Exception as e:
            return TickResult(
                context=context,
                signal=Signal.FAIL,
                error=f"Step execution failed: {e}",
            )

        # Determine next step for CONTINUE signal
        next_step: str | None = None
        if result.signal == Signal.CONTINUE:
            next_step = result.next_step or self._get_next_step(step_name)

        return TickResult(
            context=result.context,
            signal=result.signal,
            next_step=next_step,
            branch_request=result.branch_request,
            output=result.output,
            error=result.error,
        )

    async def run(
        self,
        initial_context: ContextT,
        start_step: str,
        input_data: Any = None,
        max_iterations: int = 1000,
    ) -> ContextT:
        """Execute the workflow until completion or failure.

        Args:
            initial_context: The initial workflow context.
            start_step: Name of the first step to execute.
            input_data: Optional input data for the first step.
            max_iterations: Maximum number of steps to execute.

        Returns:
            The final context after COMPLETE signal.

        Raises:
            WorkflowError: If the workflow fails or hits max iterations.
            NotImplementedError: If BRANCH or MERGE signals are encountered.

        """
        context = initial_context
        current_step = start_step
        current_input = input_data

        for _ in range(max_iterations):
            tick_result = await self.tick(context, current_step, current_input)

            if tick_result.signal == Signal.COMPLETE:
                return tick_result.context

            if tick_result.signal == Signal.FAIL:
                raise WorkflowError(
                    message=tick_result.error or "Workflow failed",
                    context=tick_result.context,
                )

            if tick_result.signal == Signal.BRANCH:
                # Require signal handler for BRANCH signal
                if self._signal_handler is None:
                    raise WorkflowError(
                        message="BRANCH signal requires a signal handler. "
                        "Use set_signal_handler() to configure one.",
                        context=tick_result.context,
                    )
                # Delegate to signal handler to get branch contexts
                branch_result = await self._signal_handler.handle_branch(
                    context,
                    StepResult(
                        context=tick_result.context,
                        signal=tick_result.signal,
                        branch_request=tick_result.branch_request,
                    ),
                    self,
                )
                context = branch_result.context
                if not branch_result.should_continue:
                    return context

                # Execute each branch context
                if branch_result.branch_contexts:
                    branch_request = tick_result.branch_request
                    child_start_step = branch_result.next_step
                    merge_step = branch_request.merge_step if branch_request else None

                    if child_start_step is None:
                        raise WorkflowError(
                            message="BRANCH signal requires next_step to be set",
                            context=context,
                        )

                    for branch_ctx in branch_result.branch_contexts:
                        # Execute child workflow from child_start_step
                        # passing branch data as input
                        child_context = branch_ctx.context
                        child_step: str = child_start_step
                        child_input: Any = branch_ctx.data

                        # Run child branch until MERGE, COMPLETE, or FAIL
                        for _ in range(max_iterations):
                            child_tick = await self.tick(
                                child_context, child_step, child_input
                            )

                            if child_tick.signal == Signal.FAIL:
                                raise WorkflowError(
                                    message=child_tick.error or "Branch failed",
                                    context=child_tick.context,
                                )

                            if child_tick.signal == Signal.COMPLETE:
                                # Branch completed early
                                child_context = child_tick.context
                                break

                            if child_tick.signal == Signal.MERGE:
                                # Branch reached merge point
                                child_context = child_tick.context
                                break

                            if child_tick.signal == Signal.CONTINUE:
                                child_context = child_tick.context
                                next_child_step = child_tick.next_step
                                child_input = None
                                if next_child_step is None or next_child_step == merge_step:
                                    # Reached merge step or end
                                    break
                                child_step = next_child_step

                        # Register branch completion with handler
                        from maestro.handlers import BranchContext as HandlerBranchContext

                        if hasattr(self._signal_handler, "register_branch_completion"):
                            self._signal_handler.register_branch_completion(
                                merge_step or "",
                                HandlerBranchContext(
                                    name=branch_ctx.name,
                                    context=child_context,
                                    data=branch_ctx.data,
                                ),
                            )

                    # After all branches complete, call handle_merge to get merged context
                    if (
                        merge_step is not None
                        and self._signal_handler is not None
                        and hasattr(self._signal_handler, "handle_merge")
                    ):
                        merge_result = await self._signal_handler.handle_merge(
                            context,
                            StepResult(
                                context=context,
                                signal=Signal.MERGE,
                                next_step=merge_step,
                            ),
                            self,
                        )
                        context = merge_result.context
                        current_step = merge_step
                        current_input = None
                        continue

                next_step = branch_result.next_step or self._get_next_step(current_step)
                if next_step is None:
                    return context
                current_step = next_step
                continue

            if tick_result.signal == Signal.MERGE:
                # Require signal handler for MERGE signal
                if self._signal_handler is None:
                    raise WorkflowError(
                        message="MERGE signal requires a signal handler. "
                        "Use set_signal_handler() to configure one.",
                        context=tick_result.context,
                    )
                # Delegate to signal handler
                merge_result = await self._signal_handler.handle_merge(
                    context,
                    StepResult(
                        context=tick_result.context,
                        signal=tick_result.signal,
                    ),
                    self,
                )
                context = merge_result.context
                if not merge_result.should_continue:
                    return context
                merge_next = merge_result.next_step or self._get_next_step(current_step)
                if merge_next is None:
                    return context
                current_step = merge_next
                continue

            if tick_result.signal == Signal.CONTINUE:
                if tick_result.next_step is None:
                    # No more steps, complete
                    return tick_result.context
                context = tick_result.context
                current_step = tick_result.next_step
                current_input = None  # Only first step gets input_data

        raise WorkflowError(
            message=f"Workflow exceeded max iterations: {max_iterations}",
            context=context,
        )

    def _get_next_step(self, current_step: str) -> str | None:
        """Get the next step in sequence.

        Args:
            current_step: Current step name.

        Returns:
            Name of the next step, or None if no more steps.

        """
        try:
            idx = self._step_order.index(current_step)
            if idx + 1 < len(self._step_order):
                return self._step_order[idx + 1]
        except ValueError:
            pass
        return None
