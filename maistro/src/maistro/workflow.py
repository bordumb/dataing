"""Workflow facade over Engine+Runner for step-based execution.

The Workflow class provides a high-level API for running workflows,
delegating to the Engine and Runner for actual execution.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any, Generic, TypeVar

from maistro.engine import Engine
from maistro.events import Event
from maistro.merge import DefaultMergeStrategy, MergeStrategy
from maistro.runner import Runner, RunOutcome
from maistro.step import Step

ContextT = TypeVar("ContextT")


class WorkflowError(Exception):
    """Exception raised when a workflow fails.

    Attributes
    ----------
        context: The context at the time of failure.
        message: Error description.

    """

    def __init__(self, message: str, context: Any = None) -> None:
        """Initialize WorkflowError.

        Args:
        ----
            message: Error description.
            context: The context at the time of failure.

        """
        super().__init__(message)
        self.context = context
        self.message = message


class Workflow(Generic[ContextT]):
    """High-level workflow facade over Engine+Runner.

    The Workflow class provides a simple API for building and running
    workflows. It delegates to Engine for state transitions and Runner
    for step execution.

    Example:
    -------
        ```python
        workflow = Workflow()
        workflow.add_step(InitStep(), is_start=True)
        workflow.add_step(ProcessStep())
        workflow.add_step(FinalizeStep())

        # Run to completion
        result = await workflow.run({"key": "value"})

        # Or with events
        outcome, events = await workflow.run_with_events({"key": "value"})

        # Or streaming
        async for event in workflow.run_streaming({"key": "value"}):
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
        ----
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

    def add_step(self, step: Step[ContextT, Any, Any], is_start: bool = False) -> None:
        """Register a step with the workflow.

        Steps are executed in the order they are added unless
        explicitly routed via StepResult.next_step.

        Args:
        ----
            step: The step to register.
            is_start: If True, mark this as the default start step.

        Raises:
        ------
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
        ----
            name: The step name.

        Returns:
        -------
            The step, or None if not found.

        """
        return self._steps.get(name)

    async def run(
        self,
        context: ContextT,
        start_step: str | None = None,
        *,
        input_data: Any = None,
        max_iterations: int = 1000,
    ) -> ContextT:
        """Execute the workflow until completion or failure.

        Args:
        ----
            context: The initial workflow context.
            start_step: Name of the first step to execute.
            input_data: Optional input data for the first step.
            max_iterations: Maximum number of iterations before failing.

        Returns:
        -------
            The final context after COMPLETE signal.

        Raises:
        ------
            WorkflowError: If the workflow fails or pauses.

        """
        start = start_step or self._start_step

        if start is None:
            raise WorkflowError("No start step configured", context=context)

        outcome, _ = await self.run_with_events(
            context, start, input_data=input_data, max_iterations=max_iterations
        )

        if outcome.status == "completed":
            if outcome.context is not None:
                return outcome.context
            return context

        if outcome.status == "failed":
            raise WorkflowError(
                message=outcome.error or "Workflow failed",
                context=outcome.context or context,
            )

        # Paused
        raise WorkflowError(
            message=f"Workflow paused on await_token: {outcome.await_token}",
            context=outcome.context or context,
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

        Args:
        ----
            context: Initial workflow context.
            start_step: Name of the first step to execute.
            input_data: Optional input data for the first step.
            max_iterations: Maximum number of iterations before failing.

        Returns:
        -------
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

        This is the streaming API for real-time event consumption.
        Callers can checkpoint at any event boundary.

        Args:
        ----
            context: Initial workflow context.
            start_step: Name of the first step to execute.
            input_data: Optional input data for the first step.

        Yields:
        ------
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

    def _generate_run_id(self) -> str:
        """Generate a unique run ID.

        Returns
        -------
            UUID string for the run.

        """
        return str(uuid.uuid4())
