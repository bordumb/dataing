"""Pure reducer Engine for the event-sourced workflow state machine.

The Engine is the heart of the workflow system. It is a pure function that
takes the current state and an event, and returns the new state and a command.

Key principles:
- Engine.apply() takes Events only - never raw exceptions or StepResults
- Engine never performs I/O, logging, or side effects
- Engine computes resume_step for AWAIT_USER (Steps don't decide routing)
- All state changes use dataclasses.replace() for immutability
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Generic, TypeVar

from maestro.commands import Command, ExecuteStep, Stop, WaitForInput
from maestro.events import (
    BranchCompleted,
    BranchStarted,
    Event,
    InputReceived,
    InputRequested,
    RunCompleted,
    RunFailed,
    RunPaused,
    RunResumed,
    RunStarted,
    StepCompleted,
    StepFailed,
    StepStarted,
)
from maestro.merge import MergeStrategy
from maestro.signals import Signal
from maestro.state import AwaitState, RunState

ContextT = TypeVar("ContextT")


class Engine(Generic[ContextT]):
    """Deterministic workflow engine using pure reducer pattern.

    The Engine processes events and produces new state plus commands. It is
    completely stateless and deterministic - the same sequence of events always
    produces the same state.

    Attributes:
        _step_order: Ordered list of step names for default routing.
        _merge: Strategy for merging branch contexts.

    """

    def __init__(self, step_order: list[str], merge_strategy: MergeStrategy) -> None:
        """Initialize the Engine with step ordering and merge strategy.

        Args:
            step_order: Ordered list of step names for default routing.
            merge_strategy: Strategy for merging branch contexts.

        """
        self._step_order = step_order
        self._merge = merge_strategy

    def init(
        self, run_id: str, context: ContextT, start_step: str
    ) -> tuple[RunState[ContextT], Command, Event]:
        """Initialize a new workflow run.

        Creates the initial state and returns the first command to execute
        along with the RunStarted event.

        Args:
            run_id: Unique identifier for this workflow run.
            context: Initial workflow context.
            start_step: Name of the step to begin execution.

        Returns:
            Tuple of (initial_state, first_command, RunStarted_event).

        """
        initial_state: RunState[ContextT] = RunState(
            run_id=run_id,
            status="running",
            context=context,
            current_step=start_step,
            seq=0,
        )
        command: Command = ExecuteStep(step_name=start_step)
        event: Event = RunStarted(run_id=run_id, start_step=start_step)
        return initial_state, command, event

    def apply(
        self, state: RunState[ContextT], event: Event
    ) -> tuple[RunState[ContextT], Command]:
        """Apply an event to state, returning new state and next command.

        This is the pure reducer function at the heart of the event-sourced
        state machine. It takes the current state and an event, and returns
        the new state and the command to execute next.

        The function is completely pure - no I/O, no logging, no side effects.
        Given the same state and event, it always produces the same result.

        Args:
            state: Current workflow run state.
            event: Event to apply.

        Returns:
            Tuple of (new_state, command_to_execute).

        """
        # Increment sequence number
        new_state = replace(state, seq=state.seq + 1)

        # Dispatch to appropriate handler based on event type
        if isinstance(event, RunStarted):
            return self._handle_run_started(new_state, event)
        if isinstance(event, StepStarted):
            return self._handle_step_started(new_state, event)
        if isinstance(event, StepCompleted):
            return self._handle_step_completed(new_state, event)
        if isinstance(event, StepFailed):
            return self._handle_step_failed(new_state, event)
        if isinstance(event, BranchStarted):
            return self._handle_branch_started(new_state, event)
        if isinstance(event, BranchCompleted):
            return self._handle_branch_completed(new_state, event)
        if isinstance(event, InputRequested):
            return self._handle_input_requested(new_state, event)
        if isinstance(event, InputReceived):
            return self._handle_input_received(new_state, event)
        if isinstance(event, RunPaused):
            return self._handle_run_paused(new_state, event)
        if isinstance(event, RunResumed):
            return self._handle_run_resumed(new_state, event)
        if isinstance(event, RunCompleted):
            return self._handle_run_completed(new_state, event)
        if isinstance(event, RunFailed):
            return self._handle_run_failed(new_state, event)

        # Unknown event type - should not happen with proper typing
        return new_state, Stop(status="failed", error=f"Unknown event type: {type(event)}")

    def _handle_run_started(
        self, state: RunState[ContextT], event: RunStarted
    ) -> tuple[RunState[ContextT], Command]:
        """Handle RunStarted event."""
        new_state = replace(state, current_step=event.start_step, status="running")
        return new_state, ExecuteStep(step_name=event.start_step)

    def _handle_step_started(
        self, state: RunState[ContextT], event: StepStarted
    ) -> tuple[RunState[ContextT], Command]:
        """Handle StepStarted event (informational, no state change)."""
        # StepStarted is informational - used for UI updates and stuck detection
        # Continue with executing the current step
        return state, ExecuteStep(step_name=event.step_name)

    def _handle_step_completed(
        self, state: RunState[ContextT], event: StepCompleted
    ) -> tuple[RunState[ContextT], Command]:
        """Handle StepCompleted event."""
        # Apply context update as delta
        new_context = self._apply_context_update(state.context, event.context_update)
        new_state = replace(state, context=new_context)

        # Handle based on signal
        signal = event.signal

        if signal == Signal.COMPLETE:
            final_state = replace(new_state, status="completed", current_step=None)
            return final_state, Stop(status="completed", final_context=new_context)

        if signal == Signal.FAIL:
            failed_state = replace(new_state, status="failed", current_step=None)
            return failed_state, Stop(status="failed")

        if signal == Signal.CONTINUE:
            next_step = self._default_next(event.step_name)
            if next_step is None:
                # No more steps - workflow is complete
                final_state = replace(new_state, status="completed", current_step=None)
                return final_state, Stop(status="completed", final_context=new_context)
            continued_state = replace(new_state, current_step=next_step)
            return continued_state, ExecuteStep(step_name=next_step)

        # BRANCH, MERGE, AWAIT_USER are handled via their own events
        # For now, just continue to next step
        next_step = self._default_next(event.step_name)
        if next_step is None:
            final_state = replace(new_state, status="completed", current_step=None)
            return final_state, Stop(status="completed", final_context=new_context)
        continued_state = replace(new_state, current_step=next_step)
        return continued_state, ExecuteStep(step_name=next_step)

    def _handle_step_failed(
        self, state: RunState[ContextT], event: StepFailed
    ) -> tuple[RunState[ContextT], Command]:
        """Handle StepFailed event."""
        failed_state = replace(state, status="failed", current_step=None)
        return failed_state, Stop(status="failed", error=event.error)

    def _handle_branch_started(
        self, state: RunState[ContextT], event: BranchStarted
    ) -> tuple[RunState[ContextT], Command]:
        """Handle BranchStarted event (informational)."""
        # BranchStarted is informational - the branch will execute its steps
        return state, ExecuteStep(step_name=event.start_step)

    def _handle_branch_completed(
        self, state: RunState[ContextT], event: BranchCompleted
    ) -> tuple[RunState[ContextT], Command]:
        """Handle BranchCompleted event."""
        if state.pending_branches is None:
            # No pending branches - this is an error
            return state, Stop(
                status="failed", error="BranchCompleted without pending branches"
            )

        # Add this branch to completed
        new_completed = dict(state.pending_branches.completed)
        new_completed[event.branch_name] = event.context_update

        new_branch_state = replace(state.pending_branches, completed=new_completed)
        new_state = replace(state, pending_branches=new_branch_state)

        # Check if all branches are complete
        if new_branch_state.is_complete():
            # Merge branch contexts
            merged_context = self._merge.merge(
                state.context, new_branch_state.completed
            )
            final_state = replace(
                new_state,
                context=merged_context,
                pending_branches=None,
                current_step=new_branch_state.merge_step,
            )
            return final_state, ExecuteStep(step_name=new_branch_state.merge_step)

        # More branches pending - wait (no command to issue from Engine)
        # Runner will continue executing other branches
        return new_state, WaitForInput(token="__branch_wait__")

    def _handle_input_requested(
        self, state: RunState[ContextT], event: InputRequested
    ) -> tuple[RunState[ContextT], Command]:
        """Handle InputRequested event (AWAIT_USER triggered)."""
        # Engine computes resume_step - Steps don't decide routing
        resume_step = self._default_next(state.current_step)
        if resume_step is None:
            # Use current step if no next step
            resume_step = state.current_step or ""

        await_state = AwaitState(token=event.token, resume_step=resume_step)
        paused_state = replace(state, pending_await=await_state, status="paused")
        return paused_state, WaitForInput(token=event.token)

    def _handle_input_received(
        self, state: RunState[ContextT], event: InputReceived
    ) -> tuple[RunState[ContextT], Command]:
        """Handle InputReceived event (external input provided)."""
        if state.pending_await is None:
            return state, Stop(
                status="failed", error="InputReceived without pending await"
            )

        # Validate token matches
        if state.pending_await.token != event.token:
            return state, Stop(
                status="failed",
                error=f"Token mismatch: expected {state.pending_await.token}, got {event.token}",
            )

        resume_step = state.pending_await.resume_step
        resumed_state = replace(
            state,
            pending_await=None,
            status="running",
            current_step=resume_step,
        )
        return resumed_state, ExecuteStep(step_name=resume_step)

    def _handle_run_paused(
        self, state: RunState[ContextT], event: RunPaused
    ) -> tuple[RunState[ContextT], Command]:
        """Handle RunPaused event."""
        paused_state = replace(state, status="paused")
        return paused_state, WaitForInput(token=f"__paused_{event.reason}__")

    def _handle_run_resumed(
        self, state: RunState[ContextT], event: RunResumed
    ) -> tuple[RunState[ContextT], Command]:
        """Handle RunResumed event."""
        if state.pending_await is not None:
            resume_step = state.pending_await.resume_step
            resumed_state = replace(
                state,
                pending_await=None,
                status="running",
                current_step=resume_step,
            )
            return resumed_state, ExecuteStep(step_name=resume_step)

        # No pending await - resume current step
        current = state.current_step or self._step_order[0] if self._step_order else ""
        resumed_state = replace(state, status="running")
        return resumed_state, ExecuteStep(step_name=current)

    def _handle_run_completed(
        self, state: RunState[ContextT], event: RunCompleted
    ) -> tuple[RunState[ContextT], Command]:
        """Handle RunCompleted event."""
        completed_state = replace(state, status="completed", current_step=None)
        return completed_state, Stop(status="completed", final_context=event.final_context)

    def _handle_run_failed(
        self, state: RunState[ContextT], event: RunFailed
    ) -> tuple[RunState[ContextT], Command]:
        """Handle RunFailed event."""
        failed_state = replace(state, status="failed", current_step=None)
        return failed_state, Stop(status="failed", error=event.error)

    def _default_next(self, current_step: str | None) -> str | None:
        """Get the next step in the default step order.

        Args:
            current_step: Current step name.

        Returns:
            Next step name, or None if at end of workflow.

        """
        if current_step is None:
            return None
        try:
            idx = self._step_order.index(current_step)
            if idx + 1 < len(self._step_order):
                return self._step_order[idx + 1]
            return None
        except ValueError:
            # Step not in order - no default next
            return None

    def _apply_context_update(
        self, context: ContextT, update: dict[str, Any]
    ) -> ContextT:
        """Apply a context update delta to the current context.

        Args:
            context: Current context.
            update: Delta to apply.

        Returns:
            Updated context.

        """
        if isinstance(context, dict):
            return {**context, **update}  # type: ignore[return-value]
        # For non-dict contexts, return update if context can't be merged
        return context
