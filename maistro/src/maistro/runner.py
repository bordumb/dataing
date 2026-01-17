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

import copy
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar

from maistro.commands import ExecuteStep, NoOp, StartBranches, Stop, WaitForInput
from maistro.engine import Engine
from maistro.events import (
    BranchCompleted,
    BranchesRequested,
    BranchStarted,
    Event,
    InputRequested,
    RunCompleted,
    RunFailed,
    StepCompleted,
    StepFailed,
    StepStarted,
)
from maistro.log import EventLog, InMemoryEventLog
from maistro.result import BranchRequest, BranchSpec
from maistro.signals import Signal
from maistro.state import RunState
from maistro.step import Step

ContextT = TypeVar("ContextT")


@dataclass(frozen=True)
class RunOutcome(Generic[ContextT]):
    """Result of a workflow run.

    Attributes
    ----------
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

    Attributes
    ----------
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
        ----
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
        ----
            run_id: Unique identifier for this workflow run.
            context: Initial workflow context.
            start_step: Name of the step to begin execution.
            input_data: Optional input data for the first step.
            max_iterations: Maximum number of iterations before failing.

        Returns:
        -------
            RunOutcome with final status, context, and all events.

        """
        events: list[Event] = []
        iteration_count = 0

        # Initialize run
        state, cmd, run_started = self._engine.init(run_id, context, start_step, input_data)
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
            if isinstance(cmd, NoOp):
                # NoOp means continue the loop - no action needed from Runner
                # This handles informational events (StepStarted) and waiting states
                continue

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

                    # NoOp from Engine means continue processing events from this step
                    # (e.g., after StepStarted, after StepCompleted with BRANCH)

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
        ----
            run_id: Unique identifier for this workflow run.
            context: Initial workflow context.
            start_step: Name of the step to begin execution.
            input_data: Optional input data for the first step.

        Yields:
        ------
            Events as they occur during execution.

        """
        # Initialize run
        state, cmd, run_started = self._engine.init(run_id, context, start_step, input_data)
        logged_event = self._log.append(run_started)
        yield logged_event

        # Main execution loop
        while True:
            if isinstance(cmd, NoOp):
                # NoOp means continue the loop - no action needed
                continue

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

                    # NoOp means continue processing events from this step

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
        ----
            state: Current run state.
            cmd: ExecuteStep command with step name.

        Yields:
        ------
            StepStarted followed by StepCompleted or StepFailed.
            For BRANCH signal, also yields BranchesRequested.
            For AWAIT_USER signal, also yields InputRequested.

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

            # Emit StepCompleted first (Engine updates context from this)
            yield StepCompleted(
                step_name=step_name,
                context_update=context_update,
                signal=result.signal,
                next_step=result.next_step,
            )

            # Handle AWAIT_USER signal - emit InputRequested to drive pause
            if result.signal == Signal.AWAIT_USER:
                if result.await_token:
                    yield InputRequested(token=result.await_token)
                return

            # Handle BRANCH signal - emit BranchesRequested with branch_request
            if result.signal == Signal.BRANCH and result.branch_request is not None:
                # Compute merge_step: use explicit next_step or default next
                merge_step = result.next_step
                if merge_step is None:
                    # Use engine's step order to find default next
                    merge_step = self._engine._default_next(step_name) or ""
                yield BranchesRequested(
                    branch_request=result.branch_request,
                    merge_step=merge_step,
                )
                return

        except Exception as e:
            yield StepFailed(step_name=step_name, error=str(e))

    async def _execute_branches(
        self, state: RunState[ContextT], branch_request: BranchRequest
    ) -> AsyncGenerator[Event, None]:
        """Execute branches sequentially and yield events in canonical order.

        Branches run one at a time in alphabetical order by name. This ensures
        deterministic execution - no concurrent side effects or race conditions.

        Event order: BranchStarted(A) → BranchCompleted(A) → BranchStarted(B) → ...

        Args:
        ----
            state: Current run state.
            branch_request: Branch specifications.

        Yields:
        ------
            For each branch in sorted order: BranchStarted, then BranchCompleted.

        """
        # Sort branches alphabetically for deterministic execution order
        sorted_branches = sorted(branch_request.branches, key=lambda s: s.name)

        # Execute branches sequentially in sorted order
        for spec in sorted_branches:
            # Emit BranchStarted
            yield BranchStarted(
                branch_name=spec.name,
                start_step=branch_request.child_start_step or "",
            )

            # Execute branch and get result
            try:
                result = await self._run_branch(
                    state, spec.name, spec, branch_request.child_start_step
                )
            except Exception as e:
                result = {"_error": str(e)}

            # Emit BranchCompleted immediately after this branch finishes
            yield BranchCompleted(
                branch_name=spec.name,
                context_update=result,
            )

    def _branch_error(
        self,
        branch_name: str,
        reason: str,
        message: str,
        step_id: str | None = None,
        exception_class: str | None = None,
    ) -> dict[str, Any]:
        """Create a structured error payload for branch failures.

        Args:
        ----
            branch_name: Name of the failed branch.
            reason: Error reason code (EXCEPTION, SIGNAL_FAIL, AWAIT_USER, etc.)
            message: Human-readable error message.
            step_id: Step where the error occurred (if applicable).
            exception_class: Exception class name (if applicable).

        Returns:
        -------
            Structured error dict with "maistro.branch_error" key.

        """
        return {
            "maistro": {
                "branch_error": {
                    "branch_name": branch_name,
                    "step_id": step_id,
                    "reason": reason,
                    "exception_class": exception_class,
                    "message": message,
                }
            }
        }

    def _compute_context_delta(self, initial_context: Any, final_context: Any) -> dict[str, Any]:
        """Compute context delta or wrap non-dict in _full_context.

        For dict contexts, returns only new/changed keys.
        For non-dict contexts, returns {"_full_context": final_context}.

        Args:
        ----
            initial_context: Context at start of branch (deep-copied from parent).
            final_context: Context at end of branch execution.

        Returns:
        -------
            Delta dict or {"_full_context": ...} wrapper.

        """
        if isinstance(final_context, dict) and isinstance(initial_context, dict):
            # Compute delta: only keys that are new or changed
            delta: dict[str, Any] = {}
            for k, v in final_context.items():
                if k not in initial_context or initial_context[k] != v:
                    delta[k] = v
            return delta
        # Non-dict contexts: wrap full context
        return {"_full_context": final_context}

    async def _run_branch(
        self,
        state: RunState[ContextT],
        branch_name: str,
        branch_spec: BranchSpec,
        child_start_step: str | None,
        max_iterations: int = 100,
    ) -> dict[str, Any]:
        """Run a single branch sub-workflow and return its context update.

        Executes steps starting at child_start_step until a termination signal.
        Branch context is deep-copied from parent for isolation.
        BranchSpec.data is passed as input_data to the first step (not merged into context).

        Args:
        ----
            state: Parent run state.
            branch_name: Name of the branch.
            branch_spec: Branch specification containing name and data.
            child_start_step: Step to start execution at, or None for workflow default.
            max_iterations: Maximum step executions before failing (default 100).

        Returns:
        -------
            Context delta (for dict contexts) or {"_full_context": ctx} (for non-dict).
            On failure, returns structured error: {"maistro": {"branch_error": {...}}}.

        """
        # Fork context from parent (deep copy for isolation)
        initial_context = copy.deepcopy(state.context)
        branch_context = initial_context

        # Resolve start step
        current_step = child_start_step
        if current_step is None:
            # Use first step in step_order as default
            if not self._engine._step_order:
                return self._branch_error(
                    branch_name=branch_name,
                    reason="NO_STEPS_REGISTERED",
                    message="Cannot start branch: no steps registered in workflow",
                )
            current_step = self._engine._step_order[0]

        # Deep copy branch_spec.data for input_data (first step only)
        input_data: Any = copy.deepcopy(branch_spec.data) if branch_spec.data else None

        # Execute steps until termination
        for _ in range(max_iterations):
            # Look up step from registry
            step = self._steps.get(current_step)
            if step is None:
                return self._branch_error(
                    branch_name=branch_name,
                    reason="STEP_NOT_FOUND",
                    message=f"Step not found in registry: {current_step}",
                    step_id=current_step,
                )

            # Execute step
            try:
                result = await step.execute(branch_context, input_data)
            except Exception as e:
                return self._branch_error(
                    branch_name=branch_name,
                    reason="EXCEPTION",
                    message=str(e),
                    step_id=current_step,
                    exception_class=type(e).__name__,
                )

            # Clear input_data for subsequent steps
            input_data = None

            # Update branch context from result
            branch_context = result.context

            # Handle signals
            signal = result.signal

            if signal == Signal.COMPLETE:
                # Branch completed successfully
                return self._compute_context_delta(initial_context, branch_context)

            if signal == Signal.FAIL:
                return self._branch_error(
                    branch_name=branch_name,
                    reason="SIGNAL_FAIL",
                    message=result.error or "Step returned FAIL signal",
                    step_id=current_step,
                )

            if signal == Signal.AWAIT_USER:
                return self._branch_error(
                    branch_name=branch_name,
                    reason="AWAIT_USER",
                    message="AWAIT_USER signal not allowed in branches",
                    step_id=current_step,
                )

            if signal == Signal.BRANCH:
                return self._branch_error(
                    branch_name=branch_name,
                    reason="NESTED_BRANCH",
                    message="Nested branching not supported",
                    step_id=current_step,
                )

            # CONTINUE or unknown signal: resolve next step
            next_step = result.next_step or self._engine._default_next(current_step)

            if next_step is None:
                # End of steps - branch completed
                return self._compute_context_delta(initial_context, branch_context)

            # Verify next step exists
            if next_step not in self._steps:
                return self._branch_error(
                    branch_name=branch_name,
                    reason="STEP_NOT_FOUND",
                    message=f"Next step not found in registry: {next_step}",
                    step_id=current_step,
                )

            current_step = next_step

        # Max iterations exceeded
        return self._branch_error(
            branch_name=branch_name,
            reason="MAX_ITERATIONS",
            message=f"Branch exceeded {max_iterations} iterations",
            step_id=current_step,
        )

    def _create_terminal_event(self, cmd: Stop, state: RunState[ContextT]) -> Event:
        """Create the appropriate terminal event based on Stop command.

        Args:
        ----
            cmd: Stop command with status.
            state: Current run state.

        Returns:
        -------
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
