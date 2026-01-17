"""Tests for branch execution in maistro Runner.

This file tests _run_branch and _execute_branches behavior including:
- Context forking and isolation
- Sequential execution order
- Event ordering
- Error handling (fn-16.3)
- Full sub-workflow execution (fn-16.2)
"""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import AsyncMock

import pytest

from maistro.engine import Engine
from maistro.events import BranchCompleted, BranchStarted
from maistro.log import InMemoryEventLog
from maistro.merge import DefaultMergeStrategy
from maistro.result import BranchRequest, BranchSpec, StepResult
from maistro.runner import Runner
from maistro.signals import Signal
from maistro.state import RunState


class MockStep:
    """Mock step for testing branch execution."""

    def __init__(
        self,
        name: str,
        return_signal: Signal = Signal.COMPLETE,
        context_update: dict[str, Any] | None = None,
        next_step: str | None = None,
        await_token: str | None = None,
    ) -> None:
        """Initialize mock step."""
        self.name = name
        self._return_signal = return_signal
        self._context_update = context_update or {}
        self._next_step = next_step
        self._await_token = await_token
        self.execute_calls: list[tuple[Any, Any]] = []

    async def execute(
        self, context: Any, input_data: Any | None = None
    ) -> StepResult[Any, None]:
        """Execute the mock step."""
        self.execute_calls.append((copy.deepcopy(context), input_data))
        updated_context = context.copy() if isinstance(context, dict) else context
        if isinstance(updated_context, dict):
            updated_context.update(self._context_update)
        return StepResult(
            context=updated_context,
            signal=self._return_signal,
            next_step=self._next_step,
            context_update=self._context_update,
            await_token=self._await_token,
        )

    def can_execute(self, context: Any, input_data: Any | None = None) -> bool:
        """Check if step can execute."""
        return True


class TestContextForking:
    """Tests for fn-16.1: context forking via deep copy."""

    async def test_branch_context_is_deep_copied(self) -> None:
        """Verify branch context is deep copied, not shared reference."""
        # Setup
        initial_context = {"key": "value", "nested": {"inner": "data"}}
        engine = Engine[dict[str, Any]](
            step_order=["step1"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {}, InMemoryEventLog())

        # Initialize run state
        state, _, _ = engine.init("run-1", initial_context, "step1")

        # Create branch spec
        branch_spec = BranchSpec(name="branch_a", data={"hypothesis": "test"})

        # Execute branch
        result = await runner._run_branch(state, "branch_a", branch_spec, None)

        # Verify original context is unchanged (deep copy was made)
        assert state.context["key"] == "value"
        assert state.context["nested"]["inner"] == "data"

    async def test_mutations_in_one_branch_dont_leak_to_another(self) -> None:
        """Verify branches are isolated from each other."""
        # Setup
        initial_context = {"count": 0, "items": []}
        engine = Engine[dict[str, Any]](
            step_order=["step1"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", initial_context, "step1")

        # Create two branch specs
        branch_a = BranchSpec(name="branch_a", data={"value": "a"})
        branch_b = BranchSpec(name="branch_b", data={"value": "b"})

        # Execute branches sequentially
        await runner._run_branch(state, "branch_a", branch_a, None)
        await runner._run_branch(state, "branch_b", branch_b, None)

        # Verify parent context remains unchanged
        assert state.context["count"] == 0
        assert state.context["items"] == []


class TestSequentialExecution:
    """Tests for sequential branch execution order."""

    async def test_branches_execute_in_alphabetical_order(self) -> None:
        """Verify branches run sequentially in sorted order by name."""
        # Track execution order
        execution_order: list[str] = []

        # Create mock runner that records execution order
        initial_context = {"result": []}
        engine = Engine[dict[str, Any]](
            step_order=["step1"],
            merge_strategy=DefaultMergeStrategy(),
        )
        step1 = MockStep("step1", Signal.COMPLETE)
        runner = Runner(engine, {"step1": step1}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", initial_context, "step1")

        # Patch _run_branch to record execution order
        original_run_branch = runner._run_branch

        async def tracking_run_branch(
            state: RunState[Any],
            branch_name: str,
            branch_spec: BranchSpec,
            child_start_step: str | None,
        ) -> dict[str, Any]:
            execution_order.append(branch_name)
            return await original_run_branch(state, branch_name, branch_spec, child_start_step)

        runner._run_branch = tracking_run_branch  # type: ignore

        # Create branches in non-alphabetical order
        branch_request = BranchRequest(
            branches=[
                BranchSpec(name="charlie", data={}),
                BranchSpec(name="alpha", data={}),
                BranchSpec(name="bravo", data={}),
            ],
            merge_step="merge",
        )

        # Execute branches
        events = [event async for event in runner._execute_branches(state, branch_request)]

        # Verify execution order is alphabetical
        assert execution_order == ["alpha", "bravo", "charlie"]


class TestEventOrdering:
    """Tests for event emission ordering."""

    async def test_event_order_is_started_then_completed_per_branch(self) -> None:
        """Verify events are: BranchStarted(A) -> BranchCompleted(A) -> BranchStarted(B) -> ..."""
        initial_context = {}
        engine = Engine[dict[str, Any]](
            step_order=["step1"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", initial_context, "step1")

        branch_request = BranchRequest(
            branches=[
                BranchSpec(name="branch_b", data={}),
                BranchSpec(name="branch_a", data={}),
            ],
            merge_step="merge",
        )

        events = [event async for event in runner._execute_branches(state, branch_request)]

        # Verify event order: Started(A), Completed(A), Started(B), Completed(B)
        assert len(events) == 4
        assert isinstance(events[0], BranchStarted)
        assert events[0].branch_name == "branch_a"
        assert isinstance(events[1], BranchCompleted)
        assert events[1].branch_name == "branch_a"
        assert isinstance(events[2], BranchStarted)
        assert events[2].branch_name == "branch_b"
        assert isinstance(events[3], BranchCompleted)
        assert events[3].branch_name == "branch_b"

    async def test_branch_started_includes_start_step(self) -> None:
        """Verify BranchStarted event includes the child_start_step."""
        initial_context = {}
        engine = Engine[dict[str, Any]](
            step_order=["step1"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", initial_context, "step1")

        branch_request = BranchRequest(
            branches=[BranchSpec(name="branch_a", data={})],
            merge_step="merge",
            child_start_step="generate_query",
        )

        events = [event async for event in runner._execute_branches(state, branch_request)]

        # Verify BranchStarted has correct start_step
        assert isinstance(events[0], BranchStarted)
        assert events[0].start_step == "generate_query"


class TestBranchStepExecution:
    """Tests for fn-16.2: _run_branch step execution."""

    async def test_branch_executes_steps(self) -> None:
        """Verify _run_branch calls step.execute() with correct context."""
        initial_context = {"parent_key": "parent_value"}
        step1 = MockStep("step1", Signal.COMPLETE, {"result": "done"})

        engine = Engine[dict[str, Any]](
            step_order=["step1"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {"step1": step1}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", initial_context, "step1")

        branch_spec = BranchSpec(name="branch_a", data={"hypothesis": "test"})
        result = await runner._run_branch(state, "branch_a", branch_spec, "step1")

        # Verify step was called
        assert len(step1.execute_calls) == 1
        # Verify context passed to step contains parent data
        ctx, input_data = step1.execute_calls[0]
        assert ctx["parent_key"] == "parent_value"
        # Verify input_data is the branch_spec.data (deep copied)
        assert input_data == {"hypothesis": "test"}

    async def test_branch_receives_input_data_first_step_only(self) -> None:
        """Verify BranchSpec.data is passed as input_data to first step only."""
        step1 = MockStep("step1", Signal.CONTINUE, {"step1_result": "a"}, "step2")
        step2 = MockStep("step2", Signal.COMPLETE, {"step2_result": "b"})

        engine = Engine[dict[str, Any]](
            step_order=["step1", "step2"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {"step1": step1, "step2": step2}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", {}, "step1")

        branch_spec = BranchSpec(name="branch_a", data={"hypothesis": "test"})
        await runner._run_branch(state, "branch_a", branch_spec, "step1")

        # First step gets input_data
        assert step1.execute_calls[0][1] == {"hypothesis": "test"}
        # Second step gets None
        assert step2.execute_calls[0][1] is None

    async def test_branch_terminates_on_complete(self) -> None:
        """Verify COMPLETE signal stops branch and returns context delta."""
        step1 = MockStep("step1", Signal.COMPLETE, {"new_key": "new_value"})

        engine = Engine[dict[str, Any]](
            step_order=["step1"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {"step1": step1}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", {"existing": "data"}, "step1")

        branch_spec = BranchSpec(name="branch_a", data={})
        result = await runner._run_branch(state, "branch_a", branch_spec, "step1")

        # Should return delta (only new/changed keys)
        assert "new_key" in result
        assert result["new_key"] == "new_value"
        # Delta should not include unchanged keys
        assert "maistro" not in result

    async def test_branch_terminates_on_fail(self) -> None:
        """Verify FAIL signal returns structured error."""
        step1 = MockStep("step1", Signal.FAIL)

        engine = Engine[dict[str, Any]](
            step_order=["step1"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {"step1": step1}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", {}, "step1")

        branch_spec = BranchSpec(name="branch_a", data={})
        result = await runner._run_branch(state, "branch_a", branch_spec, "step1")

        # Should return structured error
        assert "maistro" in result
        assert "branch_error" in result["maistro"]
        assert result["maistro"]["branch_error"]["reason"] == "SIGNAL_FAIL"
        assert result["maistro"]["branch_error"]["branch_name"] == "branch_a"

    async def test_branch_await_user_error(self) -> None:
        """Verify AWAIT_USER returns structured error."""
        step1 = MockStep("step1", Signal.AWAIT_USER, await_token="test_token")

        engine = Engine[dict[str, Any]](
            step_order=["step1"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {"step1": step1}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", {}, "step1")

        branch_spec = BranchSpec(name="branch_a", data={})
        result = await runner._run_branch(state, "branch_a", branch_spec, "step1")

        assert "maistro" in result
        assert result["maistro"]["branch_error"]["reason"] == "AWAIT_USER"

    async def test_branch_nested_branch_error(self) -> None:
        """Verify BRANCH signal returns structured error (nested not allowed)."""
        # Create a step that returns BRANCH signal
        branch_step = MockStep("branch_step", Signal.BRANCH)
        # Need to set branch_request for validation to pass
        original_execute = branch_step.execute

        async def execute_with_branch(
            context: Any, input_data: Any | None = None
        ) -> StepResult[Any, None]:
            branch_step.execute_calls.append((copy.deepcopy(context), input_data))
            return StepResult(
                context=context,
                signal=Signal.BRANCH,
                branch_request=BranchRequest(
                    branches=[BranchSpec(name="nested", data={})],
                    merge_step="merge",
                ),
            )

        branch_step.execute = execute_with_branch  # type: ignore

        engine = Engine[dict[str, Any]](
            step_order=["branch_step"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {"branch_step": branch_step}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", {}, "branch_step")

        branch_spec = BranchSpec(name="branch_a", data={})
        result = await runner._run_branch(state, "branch_a", branch_spec, "branch_step")

        assert "maistro" in result
        assert result["maistro"]["branch_error"]["reason"] == "NESTED_BRANCH"

    async def test_branch_step_not_found(self) -> None:
        """Verify missing step returns structured error."""
        engine = Engine[dict[str, Any]](
            step_order=["step1"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {}, InMemoryEventLog())  # No steps registered
        state, _, _ = engine.init("run-1", {}, "step1")

        branch_spec = BranchSpec(name="branch_a", data={})
        result = await runner._run_branch(state, "branch_a", branch_spec, "nonexistent")

        assert "maistro" in result
        assert result["maistro"]["branch_error"]["reason"] == "STEP_NOT_FOUND"

    async def test_branch_max_iterations(self) -> None:
        """Verify exceeding max_iterations returns structured error."""
        # Create a step that always continues to itself (infinite loop)
        infinite_step = MockStep("infinite", Signal.CONTINUE, {}, "infinite")

        engine = Engine[dict[str, Any]](
            step_order=["infinite"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {"infinite": infinite_step}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", {}, "infinite")

        branch_spec = BranchSpec(name="branch_a", data={})
        result = await runner._run_branch(
            state, "branch_a", branch_spec, "infinite", max_iterations=5
        )

        assert "maistro" in result
        assert result["maistro"]["branch_error"]["reason"] == "MAX_ITERATIONS"

    async def test_branch_returns_delta_for_dict(self) -> None:
        """Verify dict context returns delta (changed keys only)."""
        step1 = MockStep("step1", Signal.COMPLETE, {"new": "value", "existing": "unchanged"})

        engine = Engine[dict[str, Any]](
            step_order=["step1"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {"step1": step1}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", {"existing": "unchanged", "old": "data"}, "step1")

        branch_spec = BranchSpec(name="branch_a", data={})
        result = await runner._run_branch(state, "branch_a", branch_spec, "step1")

        # Should only include new/changed keys
        assert "new" in result
        # "existing" is unchanged so shouldn't be in delta
        assert "existing" not in result
        # "old" is not in final context so not in delta
        assert "old" not in result

    async def test_branch_exception_handling(self) -> None:
        """Verify exceptions during step execution return structured error."""

        class FailingStep:
            name = "failing"

            async def execute(self, context: Any, input_data: Any = None) -> StepResult:
                raise ValueError("Something went wrong")

            def can_execute(self, context: Any, input_data: Any = None) -> bool:
                return True

        engine = Engine[dict[str, Any]](
            step_order=["failing"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {"failing": FailingStep()}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", {}, "failing")

        branch_spec = BranchSpec(name="branch_a", data={})
        result = await runner._run_branch(state, "branch_a", branch_spec, "failing")

        assert "maistro" in result
        assert result["maistro"]["branch_error"]["reason"] == "EXCEPTION"
        assert result["maistro"]["branch_error"]["exception_class"] == "ValueError"
        assert "Something went wrong" in result["maistro"]["branch_error"]["message"]

    async def test_branch_returns_full_context_wrapper(self) -> None:
        """Verify non-dict context returns {"_full_context": ctx}."""
        from dataclasses import dataclass

        @dataclass
        class CustomContext:
            value: str = "initial"

        class CustomContextStep:
            name = "custom_step"

            async def execute(
                self, context: CustomContext, input_data: Any = None
            ) -> StepResult[CustomContext, None]:
                updated = CustomContext(value="updated")
                return StepResult(context=updated, signal=Signal.COMPLETE)

            def can_execute(self, context: Any, input_data: Any = None) -> bool:
                return True

        engine = Engine[CustomContext](
            step_order=["custom_step"],
            merge_strategy=DefaultMergeStrategy(),
        )
        runner = Runner(engine, {"custom_step": CustomContextStep()}, InMemoryEventLog())
        state, _, _ = engine.init("run-1", CustomContext(), "custom_step")

        branch_spec = BranchSpec(name="branch_a", data={})
        result = await runner._run_branch(state, "branch_a", branch_spec, "custom_step")

        # Non-dict should be wrapped in _full_context
        assert "_full_context" in result
        assert isinstance(result["_full_context"], CustomContext)
        assert result["_full_context"].value == "updated"
