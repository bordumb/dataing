"""Workflow facade over Engine+Runner for step-based execution.

The Workflow class provides a high-level API for running workflows,
delegating to the Engine and Runner for actual execution.
"""

from __future__ import annotations

import uuid
import warnings
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from maistro.engine import Engine
from maistro.events import Event
from maistro.merge import DefaultMergeStrategy, MergeStrategy
from maistro.result import BranchRequest, StepResult
from maistro.runner import Runner, RunOutcome
from maistro.signals import Signal
from maistro.step import Step

if TYPE_CHECKING:
    from maistro.handlers import SignalHandler

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

    .. deprecated::
        Use run() or run_with_events() instead of tick().

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
    """High-level workflow facade over Engine+Runner.

    The Workflow class provides a simple API for building and running
    workflows. It delegates to Engine for state transitions and Runner
    for step execution.

    Example:
        ```python
        workflow = Workflow[MyContext]()
        workflow.add_step(InitStep(), is_start=True)
        workflow.add_step(ProcessStep())
        workflow.add_step(FinalizeStep())

        # Run to completion
        result = await workflow.run(MyContext(...))

        # Or with events
        outcome, events = await workflow.run_with_events(MyContext(...))

        # Or streaming
        async for event in workflow.run_streaming(MyContext(...)):
            print(event)
        ```

    """

    def __init__(
        self,
        fail_on_cannot_execute: bool = True,
        merge_strategy: MergeStrategy | None = None,
    ) -> None:
        """Initialize workflow.

        Args:
            fail_on_cannot_execute: If True, raise an error when can_execute()
                returns False. If False, skip the step and continue.
            merge_strategy: Strategy for merging branch contexts.
                Defaults to DefaultMergeStrategy.

        """
        self._steps: dict[str, Step[ContextT, Any, Any]] = {}
        self._step_order: list[str] = []
        self._start_step: str | None = None
        self._fail_on_cannot_execute = fail_on_cannot_execute
        self._merge_strategy: MergeStrategy = merge_strategy or DefaultMergeStrategy()
        self._signal_handler: SignalHandler[ContextT] | None = None

    @property
    def steps(self) -> dict[str, Step[ContextT, Any, Any]]:
        """Get the registered steps."""
        return self._steps

    @property
    def step_order(self) -> list[str]:
        """Get the step execution order."""
        return self._step_order

    @property
    def start_step(self) -> str | None:
        """Get the configured start step."""
        return self._start_step

    def set_signal_handler(self, handler: SignalHandler[ContextT]) -> None:
        """Set a custom signal handler.

        .. deprecated::
            Signal handlers are deprecated. The Engine handles signals internally.

        Args:
            handler: The signal handler to use.

        """
        warnings.warn(
            "Signal handlers are deprecated. The Engine handles signals internally.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._signal_handler = handler

    def get_signal_handler(self) -> SignalHandler[ContextT] | None:
        """Get the current signal handler.

        .. deprecated::
            Signal handlers are deprecated.

        Returns:
            The current signal handler, or None if not set.

        """
        return self._signal_handler

    def add_step(
        self, step: Step[ContextT, Any, Any], is_start: bool = False
    ) -> None:
        """Register a step with the workflow.

        Steps are executed in the order they are added unless
        explicitly routed via StepResult.next_step.

        Args:
            step: The step to register.
            is_start: If True, mark this as the default start step.

        Raises:
            ValueError: If a step with the same name is already registered.

        """
        if step.name in self._steps:
            raise ValueError(f"Step already registered: {step.name}")
        self._steps[step.name] = step
        self._step_order.append(step.name)
        if is_start or self._start_step is None:
            self._start_step = step.name

    def get_step(self, name: str) -> Step[ContextT, Any, Any] | None:
        """Get a step by name.

        Args:
            name: The step name.

        Returns:
            The step, or None if not found.

        """
        return self._steps.get(name)

    async def run(
        self,
        context: ContextT,
        start_step: str | None = None,
        *,
        initial_context: ContextT | None = None,
        input_data: Any = None,
        max_iterations: int = 1000,
    ) -> ContextT:
        """Execute the workflow until completion or failure.

        This method is backward compatible with the original API.
        It delegates to run_with_events() internally.

        Args:
            context: The initial workflow context (preferred).
            start_step: Name of the first step to execute.
            initial_context: Alias for context (deprecated).
            input_data: Optional input data for the first step.
            max_iterations: Maximum number of iterations before failing.

        Returns:
            The final context after COMPLETE signal.

        Raises:
            WorkflowError: If the workflow fails or pauses.

        """
        # Handle legacy parameter name
        ctx = initial_context if initial_context is not None else context
        start = start_step or self._start_step

        if start is None:
            raise WorkflowError("No start step configured", context=ctx)

        outcome, _ = await self.run_with_events(
            ctx, start, input_data=input_data, max_iterations=max_iterations
        )

        if outcome.status == "completed":
            if outcome.context is not None:
                return outcome.context
            return ctx

        if outcome.status == "failed":
            raise WorkflowError(
                message=outcome.error or "Workflow failed",
                context=outcome.context or ctx,
            )

        # Paused
        raise WorkflowError(
            message=f"Workflow paused on await_token: {outcome.await_token}",
            context=outcome.context or ctx,
        )

    async def run_with_events(
        self,
        context: ContextT,
        start_step: str | None = None,
        *,
        input_data: Any = None,
        max_iterations: int = 1000,
    ) -> tuple[RunOutcome[ContextT], list[Event]]:
        """Run workflow and return outcome with events.

        This is the new API for accessing workflow events.

        Args:
            context: Initial workflow context.
            start_step: Name of the first step to execute.
            input_data: Optional input data for the first step.
            max_iterations: Maximum number of iterations before failing.

        Returns:
            Tuple of (RunOutcome, list of events).

        """
        start = start_step or self._start_step
        if start is None:
            raise WorkflowError("No start step configured", context=context)

        engine: Engine[ContextT] = Engine(
            step_order=self._step_order,
            merge_strategy=self._merge_strategy,
        )
        runner: Runner[ContextT] = Runner(
            engine=engine,
            steps=self._steps,
        )

        outcome = await runner.run(
            run_id=self._generate_run_id(),
            context=context,
            start_step=start,
            input_data=input_data,
            max_iterations=max_iterations,
        )
        return outcome, outcome.events

    async def run_streaming(
        self,
        context: ContextT,
        start_step: str | None = None,
        *,
        input_data: Any = None,
    ) -> AsyncGenerator[Event, None]:
        """Yield events as they occur during workflow execution.

        This is the new streaming API for real-time event consumption.
        Callers can checkpoint at any event boundary.

        Args:
            context: Initial workflow context.
            start_step: Name of the first step to execute.
            input_data: Optional input data for the first step.

        Yields:
            Events as they occur during execution.

        """
        start = start_step or self._start_step
        if start is None:
            raise WorkflowError("No start step configured", context=context)

        engine: Engine[ContextT] = Engine(
            step_order=self._step_order,
            merge_strategy=self._merge_strategy,
        )
        runner: Runner[ContextT] = Runner(
            engine=engine,
            steps=self._steps,
        )

        async for event in runner.run_streaming(
            run_id=self._generate_run_id(),
            context=context,
            start_step=start,
            input_data=input_data,
        ):
            yield event

    async def tick(
        self,
        context: ContextT,
        step_name: str,
        input_data: Any = None,
    ) -> TickResult[ContextT]:
        """Execute a single step.

        .. deprecated::
            Use run() or run_with_events() instead.

        Args:
            context: Current workflow context.
            step_name: Name of the step to execute.
            input_data: Optional input data for the step.

        Returns:
            TickResult with the execution outcome.

        """
        warnings.warn(
            "tick() is deprecated. Use run() or run_with_events() instead.",
            DeprecationWarning,
            stacklevel=2,
        )

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

    def _generate_run_id(self) -> str:
        """Generate a unique run ID.

        Returns:
            UUID string for the run.

        """
        return str(uuid.uuid4())
