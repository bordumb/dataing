"""Tests for Engine determinism and state machine invariants.

These tests verify that the Engine is a pure reducer function that produces
identical results given the same inputs, with no side effects.
"""

from dataclasses import dataclass

from maestro.commands import ExecuteStep, Stop
from maestro.engine import Engine
from maestro.events import RunStarted, StepCompleted, StepFailed, StepStarted
from maestro.merge import DefaultMergeStrategy
from maestro.signals import Signal
from maestro.state import RunState


@dataclass(frozen=True)
class CounterContext:
    """Simple context for testing."""

    count: int


class TestEngineDeterminism:
    """Tests for Engine determinism - same inputs produce same outputs."""

    def test_apply_same_events_twice_identical_state(self) -> None:
        """Applying the same event twice produces identical state."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a", "step_b"],
            merge_strategy=DefaultMergeStrategy(),
        )

        initial_state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=CounterContext(count=0),
            current_step="step_a",
            seq=0,
        )

        event = StepCompleted(
            step_name="step_a",
            context_update={"_full_context": CounterContext(count=1)},
            signal=Signal.CONTINUE,
        )

        # Apply the same event twice
        state1, cmd1 = engine.apply(initial_state, event)
        state2, cmd2 = engine.apply(initial_state, event)

        # Results should be identical
        assert state1 == state2
        assert cmd1 == cmd2

    def test_apply_produces_identical_commands(self) -> None:
        """Same state + event always produces the same command."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a", "step_b", "step_c"],
            merge_strategy=DefaultMergeStrategy(),
        )

        state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=CounterContext(count=5),
            current_step="step_a",
            seq=5,
        )

        # Complete signal should produce ExecuteStep for next step
        complete_event = StepCompleted(
            step_name="step_a",
            context_update={},
            signal=Signal.CONTINUE,
        )

        _, cmd1 = engine.apply(state, complete_event)
        _, cmd2 = engine.apply(state, complete_event)

        assert cmd1 == cmd2
        assert isinstance(cmd1, ExecuteStep)
        assert cmd1.step_name == "step_b"

    def test_engine_no_side_effects(self) -> None:
        """Engine.apply() does not modify input state."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a", "step_b"],
            merge_strategy=DefaultMergeStrategy(),
        )

        initial_state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=CounterContext(count=0),
            current_step="step_a",
            seq=0,
        )

        # Store original values
        original_seq = initial_state.seq
        original_status = initial_state.status
        original_step = initial_state.current_step
        original_context = initial_state.context

        event = StepCompleted(
            step_name="step_a",
            context_update={"_full_context": CounterContext(count=10)},
            signal=Signal.CONTINUE,
        )

        # Apply should not modify the original state
        engine.apply(initial_state, event)

        # Original state should be unchanged (frozen dataclass)
        assert initial_state.seq == original_seq
        assert initial_state.status == original_status
        assert initial_state.current_step == original_step
        assert initial_state.context == original_context


class TestStateTransitionValidity:
    """Tests for valid state transitions."""

    def test_running_to_completed_valid(self) -> None:
        """Running -> completed is a valid transition."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a"],
            merge_strategy=DefaultMergeStrategy(),
        )

        state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=CounterContext(count=0),
            current_step="step_a",
            seq=0,
        )

        event = StepCompleted(
            step_name="step_a",
            context_update={},
            signal=Signal.COMPLETE,
        )

        new_state, cmd = engine.apply(state, event)

        assert new_state.status == "completed"
        assert isinstance(cmd, Stop)
        assert cmd.status == "completed"

    def test_running_to_failed_valid(self) -> None:
        """Running -> failed is a valid transition."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a"],
            merge_strategy=DefaultMergeStrategy(),
        )

        state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=CounterContext(count=0),
            current_step="step_a",
            seq=0,
        )

        event = StepFailed(step_name="step_a", error="Test error")

        new_state, cmd = engine.apply(state, event)

        assert new_state.status == "failed"
        assert isinstance(cmd, Stop)
        assert cmd.status == "failed"
        assert cmd.error == "Test error"


class TestEventSequenceMonotonicity:
    """Tests for event sequence number monotonicity."""

    def test_seq_increases_on_apply(self) -> None:
        """Sequence number increases with each apply."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a", "step_b"],
            merge_strategy=DefaultMergeStrategy(),
        )

        state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=CounterContext(count=0),
            current_step="step_a",
            seq=5,
        )

        event = StepStarted(step_name="step_a")
        new_state, _ = engine.apply(state, event)

        assert new_state.seq == 6  # seq + 1

    def test_seq_never_decreases(self) -> None:
        """Sequence number never decreases during workflow."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a", "step_b", "step_c"],
            merge_strategy=DefaultMergeStrategy(),
        )

        state, cmd, _ = engine.init("test_run", CounterContext(count=0), "step_a")
        initial_seq = state.seq

        events = [
            StepStarted(step_name="step_a"),
            StepCompleted(
                step_name="step_a",
                context_update={},
                signal=Signal.CONTINUE,
            ),
            StepStarted(step_name="step_b"),
            StepCompleted(
                step_name="step_b",
                context_update={},
                signal=Signal.COMPLETE,
            ),
        ]

        prev_seq = initial_seq
        for event in events:
            state, cmd = engine.apply(state, event)
            assert state.seq > prev_seq, f"seq should increase: {prev_seq} -> {state.seq}"
            prev_seq = state.seq


class CounterContextUpdateApplication:
    """Tests for context update delta application."""

    def test_dict_context_delta_applied(self) -> None:
        """Dict context deltas are applied correctly."""
        engine: Engine[dict[str, int]] = Engine(
            step_order=["step_a"],
            merge_strategy=DefaultMergeStrategy(),
        )

        state: RunState[dict[str, int]] = RunState(
            run_id="test_run",
            status="running",
            context={"count": 0, "name": "test"},
            current_step="step_a",
            seq=0,
        )

        event = StepCompleted(
            step_name="step_a",
            context_update={"count": 5},  # Delta, not full context
            signal=Signal.COMPLETE,
        )

        new_state, _ = engine.apply(state, event)

        # Count should be updated, name should be preserved
        assert new_state.context["count"] == 5
        assert new_state.context["name"] == "test"

    def test_dataclass_context_full_replacement(self) -> None:
        """Dataclass contexts use full replacement via _full_context."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a"],
            merge_strategy=DefaultMergeStrategy(),
        )

        state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=CounterContext(count=0),
            current_step="step_a",
            seq=0,
        )

        event = StepCompleted(
            step_name="step_a",
            context_update={"_full_context": CounterContext(count=42)},
            signal=Signal.COMPLETE,
        )

        new_state, _ = engine.apply(state, event)

        assert new_state.context == CounterContext(count=42)


class TestEngineInit:
    """Tests for Engine.init() method."""

    def test_init_returns_correct_state(self) -> None:
        """Engine.init() returns correct initial state."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a", "step_b"],
            merge_strategy=DefaultMergeStrategy(),
        )

        context = CounterContext(count=10)
        state, cmd, event = engine.init("run_123", context, "step_a")

        assert state.run_id == "run_123"
        assert state.status == "running"
        assert state.context == context
        assert state.current_step == "step_a"
        assert state.seq == 0

        assert isinstance(cmd, ExecuteStep)
        assert cmd.step_name == "step_a"

        assert isinstance(event, RunStarted)
        assert event.run_id == "run_123"
        assert event.start_step == "step_a"

    def test_init_with_input_data(self) -> None:
        """Engine.init() passes input_data in ExecuteStep command."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a"],
            merge_strategy=DefaultMergeStrategy(),
        )

        state, cmd, _ = engine.init(
            "run_123", CounterContext(count=0), "step_a", input_data={"key": "value"}
        )

        assert isinstance(cmd, ExecuteStep)
        assert cmd.input_data == {"key": "value"}
