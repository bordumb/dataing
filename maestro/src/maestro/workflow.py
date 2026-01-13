"""Workflow engine for step-based execution.

The Workflow class orchestrates step execution in a tick loop,
handling signals to determine the next action.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from maestro.result import BranchRequest, StepResult
from maestro.signals import Signal
from maestro.step import Step

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
                raise NotImplementedError(
                    "BRANCH signal handling not implemented. "
                    "Use fn-5.3 to add signal handlers."
                )

            if tick_result.signal == Signal.MERGE:
                raise NotImplementedError(
                    "MERGE signal handling not implemented. "
                    "Use fn-5.3 to add signal handlers."
                )

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
