"""Tests for AWAIT_USER pause and resume flow.

These tests verify that workflows can pause for user input and resume
correctly with the provided input data.
"""

from dataclasses import dataclass

import pytest

from maestro.commands import ExecuteStep, Stop, WaitForInput
from maestro.engine import Engine
from maestro.events import (
    InputReceived,
    InputRequested,
    StepCompleted,
    StepStarted,
)
from maestro.merge import DefaultMergeStrategy
from maestro.replay import Replayer
from maestro.signals import Signal
from maestro.state import AwaitState, RunState


@dataclass(frozen=True)
class UserInputContext:
    """Context for user input testing."""

    message: str
    user_response: str | None = None


class TestInputRequestedEvent:
    """Tests for InputRequested event handling."""

    def test_input_requested_transitions_to_paused(self) -> None:
        """InputRequested event transitions workflow to paused state."""
        engine: Engine[UserInputContext] = Engine(
            step_order=["ask_user", "process_response"],
            merge_strategy=DefaultMergeStrategy(),
        )

        state: RunState[UserInputContext] = RunState(
            run_id="test_run",
            status="running",
            context=UserInputContext(message="Hello"),
            current_step="ask_user",
            seq=0,
        )

        event = InputRequested(token="user_clarification", seq=1)

        new_state, cmd = engine.apply(state, event)

        assert new_state.status == "paused"
        assert new_state.pending_await is not None
        assert new_state.pending_await.token == "user_clarification"
        assert isinstance(cmd, WaitForInput)
        assert cmd.token == "user_clarification"

    def test_input_requested_computes_resume_step(self) -> None:
        """InputRequested event sets resume_step to the next step."""
        engine: Engine[UserInputContext] = Engine(
            step_order=["ask_user", "process_response"],
            merge_strategy=DefaultMergeStrategy(),
        )

        state: RunState[UserInputContext] = RunState(
            run_id="test_run",
            status="running",
            context=UserInputContext(message="Hello"),
            current_step="ask_user",
            seq=0,
        )

        event = InputRequested(token="token123", seq=1)

        new_state, _ = engine.apply(state, event)

        assert new_state.pending_await is not None
        # Engine computes next step for resume
        assert new_state.pending_await.resume_step == "process_response"


class TestInputReceivedEvent:
    """Tests for InputReceived event handling."""

    def test_input_received_resumes_workflow(self) -> None:
        """InputReceived event resumes workflow from paused state."""
        engine: Engine[UserInputContext] = Engine(
            step_order=["ask_user", "process_response"],
            merge_strategy=DefaultMergeStrategy(),
        )

        # State that's paused waiting for input
        paused_state: RunState[UserInputContext] = RunState(
            run_id="test_run",
            status="paused",
            context=UserInputContext(message="Hello"),
            current_step="ask_user",
            seq=5,
            pending_await=AwaitState(
                token="user_clarification",
                resume_step="process_response",
            ),
        )

        event = InputReceived(payload="User says hello", token="user_clarification", seq=6)

        new_state, cmd = engine.apply(paused_state, event)

        assert new_state.status == "running"
        assert new_state.pending_await is None
        assert isinstance(cmd, ExecuteStep)
        assert cmd.step_name == "process_response"

    def test_input_received_clears_pending_await(self) -> None:
        """InputReceived clears the pending_await state."""
        engine: Engine[UserInputContext] = Engine(
            step_order=["ask_user"],
            merge_strategy=DefaultMergeStrategy(),
        )

        paused_state: RunState[UserInputContext] = RunState(
            run_id="test_run",
            status="paused",
            context=UserInputContext(message="Hello"),
            current_step="ask_user",
            seq=5,
            pending_await=AwaitState(
                token="token123",
                resume_step="ask_user",
            ),
        )

        event = InputReceived(payload="response", token="token123", seq=6)
        new_state, _ = engine.apply(paused_state, event)

        assert new_state.pending_await is None

    def test_input_received_without_pending_await_fails(self) -> None:
        """InputReceived without pending await produces failure."""
        engine: Engine[UserInputContext] = Engine(
            step_order=["ask_user"],
            merge_strategy=DefaultMergeStrategy(),
        )

        state: RunState[UserInputContext] = RunState(
            run_id="test_run",
            status="running",
            context=UserInputContext(message="Hello"),
            current_step="ask_user",
            seq=0,
        )

        event = InputReceived(payload="data", token="token", seq=1)
        new_state, cmd = engine.apply(state, event)

        # Should produce Stop with error
        assert isinstance(cmd, Stop)
        assert cmd.status == "failed"
        assert "without pending await" in (cmd.error or "")

    def test_input_received_token_mismatch_fails(self) -> None:
        """InputReceived with wrong token produces failure."""
        engine: Engine[UserInputContext] = Engine(
            step_order=["ask_user"],
            merge_strategy=DefaultMergeStrategy(),
        )

        paused_state: RunState[UserInputContext] = RunState(
            run_id="test_run",
            status="paused",
            context=UserInputContext(message="Hello"),
            current_step="ask_user",
            seq=5,
            pending_await=AwaitState(
                token="expected_token",
                resume_step="ask_user",
            ),
        )

        event = InputReceived(payload="data", token="wrong_token", seq=6)
        new_state, cmd = engine.apply(paused_state, event)

        assert isinstance(cmd, Stop)
        assert cmd.status == "failed"
        assert "Token mismatch" in (cmd.error or "")


class TestPauseResumeReplay:
    """Tests for replay of pause/resume sequences."""

    def test_replay_pause_resume_sequence(self) -> None:
        """Replay correctly handles pause/resume event sequence."""
        engine: Engine[UserInputContext] = Engine(
            step_order=["ask_user", "process_response"],
            merge_strategy=DefaultMergeStrategy(),
        )
        replayer: Replayer[UserInputContext] = Replayer(engine=engine)

        initial_state: RunState[UserInputContext] = RunState(
            run_id="test_run",
            status="running",
            context=UserInputContext(message="Hello"),
            current_step="ask_user",
            seq=0,
        )

        # Event sequence: start -> input requested -> input received -> complete
        events = [
            StepStarted(step_name="ask_user", seq=1),
            InputRequested(token="user_clarification", seq=2),
            InputReceived(payload="user response", token="user_clarification", seq=3),
            StepStarted(step_name="process_response", seq=4),
            StepCompleted(
                step_name="process_response",
                context_update={
                    "_full_context": UserInputContext(
                        message="Hello", user_response="user response"
                    )
                },
                signal=Signal.COMPLETE,
                seq=5,
            ),
        ]

        final_state = replayer.replay(initial_state, events)

        assert final_state.status == "completed"
        assert final_state.context.user_response == "user response"

    def test_replay_idempotent_for_pause_resume(self) -> None:
        """Multiple replays of pause/resume produce identical results."""
        engine: Engine[UserInputContext] = Engine(
            step_order=["ask_user"],
            merge_strategy=DefaultMergeStrategy(),
        )
        replayer: Replayer[UserInputContext] = Replayer(engine=engine)

        initial_state: RunState[UserInputContext] = RunState(
            run_id="test_run",
            status="running",
            context=UserInputContext(message="test"),
            current_step="ask_user",
            seq=0,
        )

        events = [
            StepStarted(step_name="ask_user", seq=1),
            InputRequested(token="token", seq=2),
            InputReceived(payload="data", token="token", seq=3),
            StepStarted(step_name="ask_user", seq=4),
            StepCompleted(
                step_name="ask_user",
                context_update={
                    "_full_context": UserInputContext(message="test", user_response="data")
                },
                signal=Signal.COMPLETE,
                seq=5,
            ),
        ]

        # Replay multiple times
        results = [replayer.replay(initial_state, events) for _ in range(3)]

        # All results should be identical
        for result in results[1:]:
            assert result == results[0]


class TestAwaitStateProperties:
    """Tests for AwaitState dataclass."""

    def test_await_state_is_frozen(self) -> None:
        """AwaitState is immutable (frozen dataclass)."""
        state = AwaitState(token="test_token", resume_step="next_step")

        with pytest.raises(AttributeError):
            state.token = "modified"  # type: ignore[misc]

    def test_await_state_equality(self) -> None:
        """AwaitState instances with same values are equal."""
        state1 = AwaitState(token="token", resume_step="step")
        state2 = AwaitState(token="token", resume_step="step")

        assert state1 == state2

    def test_await_state_hash(self) -> None:
        """AwaitState can be used in sets and as dict keys."""
        state1 = AwaitState(token="token", resume_step="step")
        state2 = AwaitState(token="token", resume_step="step")

        # Same values should hash the same
        assert hash(state1) == hash(state2)

        # Can be used in set
        state_set = {state1, state2}
        assert len(state_set) == 1


class TestMultiplePauseResumeCycles:
    """Tests for workflows with multiple pause/resume cycles."""

    def test_replay_multiple_pause_cycles(self) -> None:
        """Replay handles multiple pause/resume cycles correctly."""
        engine: Engine[UserInputContext] = Engine(
            step_order=["step_a", "step_b", "step_c"],
            merge_strategy=DefaultMergeStrategy(),
        )
        replayer: Replayer[UserInputContext] = Replayer(engine=engine)

        initial_state: RunState[UserInputContext] = RunState(
            run_id="test_run",
            status="running",
            context=UserInputContext(message="start"),
            current_step="step_a",
            seq=0,
        )

        # Two pause/resume cycles
        events = [
            # First cycle
            StepStarted(step_name="step_a", seq=1),
            InputRequested(token="token1", seq=2),
            InputReceived(payload="first", token="token1", seq=3),
            StepStarted(step_name="step_b", seq=4),
            # Second cycle
            InputRequested(token="token2", seq=5),
            InputReceived(payload="second", token="token2", seq=6),
            StepStarted(step_name="step_c", seq=7),
            StepCompleted(
                step_name="step_c",
                context_update={},
                signal=Signal.COMPLETE,
                seq=8,
            ),
        ]

        final_state = replayer.replay(initial_state, events)

        assert final_state.status == "completed"
        assert final_state.seq == 8


class TestEngineAwaitUserSignal:
    """Tests for Engine handling of AWAIT_USER signal on StepCompleted."""

    def test_await_user_signal_continues_to_next_step(self) -> None:
        """AWAIT_USER signal on StepCompleted continues to next step.

        Note: AWAIT_USER is properly handled via InputRequested event,
        not via the signal on StepCompleted. The signal just continues.
        """
        engine: Engine[UserInputContext] = Engine(
            step_order=["step_a", "step_b"],
            merge_strategy=DefaultMergeStrategy(),
        )

        state: RunState[UserInputContext] = RunState(
            run_id="test_run",
            status="running",
            context=UserInputContext(message="test"),
            current_step="step_a",
            seq=0,
        )

        # StepCompleted with AWAIT_USER signal - this just continues
        # (the actual pause happens via InputRequested event)
        event = StepCompleted(
            step_name="step_a",
            context_update={},
            signal=Signal.AWAIT_USER,
            seq=1,
        )

        new_state, cmd = engine.apply(state, event)

        # AWAIT_USER on StepCompleted continues to next step
        # (InputRequested is what actually pauses)
        assert isinstance(cmd, ExecuteStep)
        assert cmd.step_name == "step_b"
