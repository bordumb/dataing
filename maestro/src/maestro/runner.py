"""Async Runner for executing workflow commands and emitting events.

The Runner is the effectful counterpart to the pure Engine. It executes
commands from the Engine, performs I/O (calling steps), and translates
runtime facts into Events.

Key principles:
- Runner translates runtime facts into Events (Engine never sees raw exceptions)
- Branch completion events emitted in canonical alphabetical order for determinism
- Runner can be an async generator yielding events for streaming
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

from maestro.commands import ExecuteStep, StartBranches, Stop, WaitForInput
from maestro.engine import Engine
from maestro.events import (
    BranchCompleted,
    BranchStarted,
    Event,
    InputRequested,
    RunCompleted,
    RunFailed,
    StepCompleted,
    StepFailed,
    StepStarted,
)
from maestro.log import EventLog, InMemoryEventLog
from maestro.result import BranchRequest
from maestro.signals import Signal
from maestro.state import RunState
from maestro.step import Step

ContextT = TypeVar("ContextT")


@dataclass(frozen=True)
class RunOutcome(Generic[ContextT]):
    """Result of a workflow run.

    Attributes:
        status: Terminal status of the run.
        context: Final workflow context (if completed).
        error: Error message (if failed).
        await_token: Token being awaited (if paused on AWAIT_USER).
        events: List of all events emitted during the run.

    """

    status: Literal["completed", "failed", "paused"]
    context: ContextT | None = None
    error: str | None = None
    await_token: str | None = None
    events: list[Event] = field(default_factory=list)


class Runner(Generic[ContextT]):
    """Async workflow runner that executes commands and emits events.

    The Runner is responsible for:
    - Executing step commands by calling step.execute()
    - Converting exceptions to StepFailed events
    - Emitting StepStarted events before each step
    - Running branches in parallel with canonical completion ordering
    - Maintaining an event log for replay

    Attributes:
        _engine: The pure Engine for state transitions.
        _steps: Map of step name to Step instance.
        _log: Event log for storing events.

    """

    def __init__(
        self,
        engine: Engine[ContextT],
        steps: dict[str, Step[Any, Any, Any]],
        log: EventLog | None = None,
    ) -> None:
        """Initialize the Runner.

        Args:
            engine: The pure Engine for state transitions.
            steps: Map of step name to Step instance.
            log: Optional event log. Defaults to InMemoryEventLog.

        """
        self._engine = engine
        self._steps = steps
        self._log: EventLog = log if log is not None else InMemoryEventLog()

    async def run(
        self,
        run_id: str,
        context: ContextT,
        start_step: str,
        input_data: Any | None = None,
        max_iterations: int = 1000,
    ) -> RunOutcome[ContextT]:
        """Run workflow to completion, failure, or pause.

        Collects all events and returns a RunOutcome with the properly-typed
        context from the final state.

        Args:
            run_id: Unique identifier for this workflow run.
            context: Initial workflow context.
            start_step: Name of the step to begin execution.
            input_data: Optional input data for the first step.
            max_iterations: Maximum number of iterations before failing.

        Returns:
            RunOutcome with final status, context, and all events.

        """
        events: list[Event] = []
        iteration_count = 0

        # Initialize run
        state, cmd, run_started = self._engine.init(
            run_id, context, start_step, input_data
        )
        logged_event = self._log.append(run_started)
        events.append(logged_event)

        # Main execution loop
        while True:
            # Check iteration limit
            iteration_count += 1
            if iteration_count > max_iterations:
                error_event = RunFailed(error="Exceeded max iterations")
                logged_error = self._log.append(error_event)
                events.append(logged_error)
                return RunOutcome(
                    status="failed",
                    context=state.context,
                    error="Exceeded max iterations",
                    events=events,
                )
            if isinstance(cmd, ExecuteStep):
                async for event in self._execute_step(state, cmd):
                    logged_event = self._log.append(event)
                    events.append(logged_event)
                    state, cmd = self._engine.apply(state, logged_event)

                    if isinstance(cmd, Stop):
                        terminal_event = self._create_terminal_event(cmd, state)
                        logged_terminal = self._log.append(terminal_event)
                        events.append(logged_terminal)

                        if cmd.status == "completed":
                            return RunOutcome(
                                status="completed",
                                context=state.context,
                                events=events,
                            )
                        return RunOutcome(
                            status="failed",
                            context=state.context,
                            error=cmd.error,
                            events=events,
                        )

                    if isinstance(cmd, WaitForInput):
                        return RunOutcome(
                            status="paused",
                            context=state.context,
                            await_token=cmd.token,
                            events=events,
                        )

            elif isinstance(cmd, StartBranches):
                async for event in self._execute_branches(state, cmd.branch_request):
                    logged_event = self._log.append(event)
                    events.append(logged_event)
                    state, cmd = self._engine.apply(state, logged_event)

                    if isinstance(cmd, Stop):
                        terminal_event = self._create_terminal_event(cmd, state)
                        logged_terminal = self._log.append(terminal_event)
                        events.append(logged_terminal)
                        return RunOutcome(
                            status="completed" if cmd.status == "completed" else "failed",
                            context=state.context,
                            error=cmd.error if cmd.status == "failed" else None,
                            events=events,
                        )

            elif isinstance(cmd, WaitForInput):
                return RunOutcome(
                    status="paused",
                    context=state.context,
                    await_token=cmd.token,
                    events=events,
                )

            elif isinstance(cmd, Stop):
                terminal_event = self._create_terminal_event(cmd, state)
                logged_terminal = self._log.append(terminal_event)
                events.append(logged_terminal)
                return RunOutcome(
                    status="completed" if cmd.status == "completed" else "failed",
                    context=state.context,
                    error=cmd.error if cmd.status == "failed" else None,
                    events=events,
                )

    async def run_streaming(
        self,
        run_id: str,
        context: ContextT,
        start_step: str,
        input_data: Any | None = None,
    ) -> AsyncGenerator[Event, None]:
        """Yield events as they occur during workflow execution.

        This is an async generator that yields events in real-time,
        allowing callers to persist at any event boundary.

        Args:
            run_id: Unique identifier for this workflow run.
            context: Initial workflow context.
            start_step: Name of the step to begin execution.
            input_data: Optional input data for the first step.

        Yields:
            Events as they occur during execution.

        """
        # Initialize run
        state, cmd, run_started = self._engine.init(
            run_id, context, start_step, input_data
        )
        logged_event = self._log.append(run_started)
        yield logged_event

        # Main execution loop
        while True:
            if isinstance(cmd, ExecuteStep):
                async for event in self._execute_step(state, cmd):
                    logged_event = self._log.append(event)
                    yield logged_event
                    state, cmd = self._engine.apply(state, logged_event)

                    # Check for terminal commands
                    if isinstance(cmd, Stop):
                        terminal_event = self._create_terminal_event(cmd, state)
                        logged_terminal = self._log.append(terminal_event)
                        yield logged_terminal
                        return

                    if isinstance(cmd, WaitForInput):
                        # Paused on AWAIT_USER
                        return

            elif isinstance(cmd, StartBranches):
                async for event in self._execute_branches(state, cmd.branch_request):
                    logged_event = self._log.append(event)
                    yield logged_event
                    state, cmd = self._engine.apply(state, logged_event)

                    if isinstance(cmd, Stop):
                        terminal_event = self._create_terminal_event(cmd, state)
                        logged_terminal = self._log.append(terminal_event)
                        yield logged_terminal
                        return

            elif isinstance(cmd, WaitForInput):
                # Waiting for external input
                return

            elif isinstance(cmd, Stop):
                terminal_event = self._create_terminal_event(cmd, state)
                logged_event = self._log.append(terminal_event)
                yield logged_event
                return

    async def _execute_step(
        self, state: RunState[ContextT], cmd: ExecuteStep
    ) -> AsyncGenerator[Event, None]:
        """Execute a single step and yield events.

        Args:
            state: Current run state.
            cmd: ExecuteStep command with step name.

        Yields:
            StepStarted followed by StepCompleted or StepFailed.

        """
        step_name = cmd.step_name

        # Emit StepStarted before execution
        yield StepStarted(step_name=step_name)

        # Get the step
        step = self._steps.get(step_name)
        if step is None:
            yield StepFailed(step_name=step_name, error=f"Step not found: {step_name}")
            return

        # Execute the step
        try:
            result = await step.execute(state.context, cmd.input_data)

            # Extract context_update from result
            context_update: dict[str, Any] = {}
            if result.context_update is not None:
                context_update = result.context_update
            elif isinstance(result.context, dict) and isinstance(state.context, dict):
                # Compute delta if not provided for dict contexts
                context_update = {
                    k: v for k, v in result.context.items() if state.context.get(k) != v
                }
            elif not isinstance(result.context, dict):
                # For non-dict contexts (like dataclasses), store full context
                # using a special key that the Engine recognizes
                context_update = {"_full_context": result.context}

            # Handle AWAIT_USER signal
            if result.signal == Signal.AWAIT_USER:
                yield StepCompleted(
                    step_name=step_name,
                    context_update=context_update,
                    signal=result.signal,
                    next_step=result.next_step,
                )
                if result.await_token:
                    yield InputRequested(token=result.await_token)
                return

            yield StepCompleted(
                step_name=step_name,
                context_update=context_update,
                signal=result.signal,
                next_step=result.next_step,
            )

        except Exception as e:
            yield StepFailed(step_name=step_name, error=str(e))

    async def _execute_branches(
        self, state: RunState[ContextT], branch_request: BranchRequest
    ) -> AsyncGenerator[Event, None]:
        """Execute branches in parallel and yield events in canonical order.

        Args:
            state: Current run state.
            branch_request: Branch specifications.

        Yields:
            BranchStarted for each branch, then BranchCompleted in alphabetical order.

        """
        # Create tasks for each branch
        tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
        for spec in branch_request.branches:
            # Emit BranchStarted
            yield BranchStarted(
                branch_name=spec.name,
                start_step=branch_request.child_start_step or "",
            )
            # Create task for branch execution
            task = asyncio.create_task(self._run_branch(state, spec.name, spec.data))
            tasks[spec.name] = task

        # Wait for all branches
        results: dict[str, dict[str, Any]] = {}
        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception as e:
                results[name] = {"_error": str(e)}

        # Emit BranchCompleted events in CANONICAL ORDER (alphabetical)
        for branch_name in sorted(results.keys()):
            yield BranchCompleted(
                branch_name=branch_name,
                context_update=results[branch_name],
            )

    async def _run_branch(
        self, state: RunState[ContextT], branch_name: str, branch_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Run a single branch and return its context update.

        Args:
            state: Parent run state.
            branch_name: Name of the branch.
            branch_data: Data passed to the branch.

        Returns:
            Context update from the branch execution.

        """
        # Simple implementation - just return branch data as context update
        # A real implementation would run a sub-workflow
        return branch_data

    def _create_terminal_event(
        self, cmd: Stop, state: RunState[ContextT]
    ) -> Event:
        """Create the appropriate terminal event based on Stop command.

        Args:
            cmd: Stop command with status.
            state: Current run state.

        Returns:
            RunCompleted or RunFailed event.

        """
        if cmd.status == "completed":
            final_context: dict[str, Any] = {}
            if isinstance(state.context, dict):
                final_context = dict(state.context)
            elif cmd.final_context is not None and isinstance(cmd.final_context, dict):
                final_context = cmd.final_context
            return RunCompleted(final_context=final_context)
        return RunFailed(error=cmd.error or "Workflow failed")
