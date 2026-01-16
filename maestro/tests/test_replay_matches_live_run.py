"""Tests for Replayer functionality and replay correctness.

These tests verify that replaying events produces identical state to live runs,
and that replay is idempotent.
"""

from dataclasses import dataclass

import pytest

from maestro.engine import Engine
from maestro.events import RunCompleted, RunStarted, StepCompleted, StepStarted
from maestro.merge import DefaultMergeStrategy
from maestro.replay import Replayer
from maestro.result import StepResult
from maestro.runner import Runner
from maestro.signals import Signal
from maestro.state import RunState


@dataclass(frozen=True)
class CounterContext:
    """Simple context for testing."""

    count: int


class IncrementStep:
    """Step that increments counter."""

    @property
    def name(self) -> str:
        """Return step name."""
        return "increment"

    async def execute(
        self, context: CounterContext, input_data: int | None = None
    ) -> StepResult[CounterContext, int]:
        """Increment the counter."""
        amount = input_data if input_data is not None else 1
        new_ctx = CounterContext(count=context.count + amount)
        return StepResult(
            context=new_ctx,
            signal=Signal.CONTINUE,
            output=new_ctx.count,
            context_update={"_full_context": new_ctx},
        )

    def can_execute(self, context: CounterContext) -> bool:
        """Return True if the step can be executed."""
        return True


class DoubleStep:
    """Step that doubles counter."""

    @property
    def name(self) -> str:
        """Return step name."""
        return "double"

    async def execute(
        self, context: CounterContext, input_data: None = None
    ) -> StepResult[CounterContext, int]:
        """Double the counter."""
        new_ctx = CounterContext(count=context.count * 2)
        return StepResult(
            context=new_ctx,
            signal=Signal.CONTINUE,
            output=new_ctx.count,
            context_update={"_full_context": new_ctx},
        )

    def can_execute(self, context: CounterContext) -> bool:
        """Return True if the step can be executed."""
        return True


class CompleteStep:
    """Step that signals completion."""

    @property
    def name(self) -> str:
        """Return step name."""
        return "complete"

    async def execute(
        self, context: CounterContext, input_data: None = None
    ) -> StepResult[CounterContext, str]:
        """Complete the workflow."""
        return StepResult(
            context=context,
            signal=Signal.COMPLETE,
            output="done",
            context_update={},
        )

    def can_execute(self, context: CounterContext) -> bool:
        """Return True if the step can be executed."""
        return True


class TestReplayCorrectness:
    """Tests for replay producing correct results."""

    @pytest.mark.asyncio
    async def test_replay_linear_workflow(self) -> None:
        """Replay of linear A->B->C workflow produces correct state."""
        # Setup
        steps = {
            "increment": IncrementStep(),
            "double": DoubleStep(),
            "complete": CompleteStep(),
        }
        step_order = ["increment", "double", "complete"]

        engine: Engine[CounterContext] = Engine(
            step_order=step_order,
            merge_strategy=DefaultMergeStrategy(),
        )
        runner: Runner[CounterContext] = Runner(engine=engine, steps=steps)
        replayer: Replayer[CounterContext] = Replayer(engine=engine)

        # Live run
        initial_context = CounterContext(count=5)
        outcome = await runner.run("test_run", initial_context, "increment")

        # Verify live run completed
        assert outcome.status == "completed"
        # 5 + 1 = 6, 6 * 2 = 12
        assert outcome.context == CounterContext(count=12)

        # Replay
        initial_state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=initial_context,
            current_step="increment",
            seq=0,
        )

        # Filter out RunStarted from events (it's handled by init)
        events_to_replay = [e for e in outcome.events if not isinstance(e, RunStarted)]
        replayed_state = replayer.replay(initial_state, events_to_replay)

        # Assert identical context
        assert replayed_state.context == outcome.context
        assert replayed_state.status == "completed"

    @pytest.mark.asyncio
    async def test_replay_produces_identical_context(self) -> None:
        """Core invariant: replay(events) produces identical context to live run."""
        steps = {
            "increment": IncrementStep(),
            "complete": CompleteStep(),
        }
        step_order = ["increment", "complete"]

        engine: Engine[CounterContext] = Engine(
            step_order=step_order,
            merge_strategy=DefaultMergeStrategy(),
        )
        runner: Runner[CounterContext] = Runner(engine=engine, steps=steps)
        replayer: Replayer[CounterContext] = Replayer(engine=engine)

        # Live run
        initial_context = CounterContext(count=0)
        outcome = await runner.run("test_run", initial_context, "increment")

        # Replay
        initial_state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=initial_context,
            current_step="increment",
            seq=0,
        )

        events_to_replay = [e for e in outcome.events if not isinstance(e, RunStarted)]
        replayed_state = replayer.replay(initial_state, events_to_replay)

        # Core invariant: contexts must be identical
        assert replayed_state.context == outcome.context


class TestReplayIdempotence:
    """Tests for replay idempotence."""

    def test_replay_idempotence(self) -> None:
        """Invariant: replay(replay(events)) == replay(events)."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a", "step_b"],
            merge_strategy=DefaultMergeStrategy(),
        )
        replayer: Replayer[CounterContext] = Replayer(engine=engine)

        initial_state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=CounterContext(count=0),
            current_step="step_a",
            seq=0,
        )

        events = [
            StepStarted(step_name="step_a", seq=1),
            StepCompleted(
                step_name="step_a",
                context_update={"_full_context": CounterContext(count=5)},
                signal=Signal.CONTINUE,
                seq=2,
            ),
            StepStarted(step_name="step_b", seq=3),
            StepCompleted(
                step_name="step_b",
                context_update={"_full_context": CounterContext(count=10)},
                signal=Signal.COMPLETE,
                seq=4,
            ),
        ]

        # First replay
        first_replay = replayer.replay(initial_state, events)

        # Second replay (same initial state and events)
        second_replay = replayer.replay(initial_state, events)

        # Idempotence: results must be identical
        assert first_replay == second_replay
        assert first_replay.context == second_replay.context
        assert first_replay.status == second_replay.status
        assert first_replay.seq == second_replay.seq

    def test_replay_multiple_times_same_result(self) -> None:
        """Multiple replays produce identical results."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a"],
            merge_strategy=DefaultMergeStrategy(),
        )
        replayer: Replayer[CounterContext] = Replayer(engine=engine)

        initial_state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=CounterContext(count=0),
            current_step="step_a",
            seq=0,
        )

        events = [
            StepStarted(step_name="step_a", seq=1),
            StepCompleted(
                step_name="step_a",
                context_update={"_full_context": CounterContext(count=42)},
                signal=Signal.COMPLETE,
                seq=2,
            ),
        ]

        # Replay 5 times
        results = [replayer.replay(initial_state, events) for _ in range(5)]

        # All results should be identical
        for i, result in enumerate(results[1:], 1):
            assert result == results[0], f"Replay {i} differs from first replay"


class TestReplayerEvents:
    """Tests for Replayer handling of different event types."""

    def test_replay_handles_step_started(self) -> None:
        """Replayer handles StepStarted events."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a"],
            merge_strategy=DefaultMergeStrategy(),
        )
        replayer: Replayer[CounterContext] = Replayer(engine=engine)

        initial_state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=CounterContext(count=0),
            current_step="step_a",
            seq=0,
        )

        events = [StepStarted(step_name="step_a", seq=1)]

        result = replayer.replay(initial_state, events)

        # StepStarted is informational, state should still be running
        assert result.status == "running"
        assert result.seq == 1

    def test_replay_handles_step_completed(self) -> None:
        """Replayer handles StepCompleted events."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a", "step_b"],
            merge_strategy=DefaultMergeStrategy(),
        )
        replayer: Replayer[CounterContext] = Replayer(engine=engine)

        initial_state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=CounterContext(count=0),
            current_step="step_a",
            seq=0,
        )

        events = [
            StepCompleted(
                step_name="step_a",
                context_update={"_full_context": CounterContext(count=5)},
                signal=Signal.CONTINUE,
                seq=1,
            ),
        ]

        result = replayer.replay(initial_state, events)

        assert result.status == "running"
        assert result.context == CounterContext(count=5)
        assert result.current_step == "step_b"

    def test_replay_handles_run_completed(self) -> None:
        """Replayer handles RunCompleted events."""
        engine: Engine[CounterContext] = Engine(
            step_order=["step_a"],
            merge_strategy=DefaultMergeStrategy(),
        )
        replayer: Replayer[CounterContext] = Replayer(engine=engine)

        initial_state: RunState[CounterContext] = RunState(
            run_id="test_run",
            status="running",
            context=CounterContext(count=0),
            current_step="step_a",
            seq=0,
        )

        events = [
            StepCompleted(
                step_name="step_a",
                context_update={"_full_context": CounterContext(count=5)},
                signal=Signal.COMPLETE,
                seq=1,
            ),
            RunCompleted(final_context={"count": 5}, seq=2),
        ]

        result = replayer.replay(initial_state, events)

        assert result.status == "completed"
