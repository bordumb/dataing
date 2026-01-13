"""Tests for maestro core protocols."""

from dataclasses import dataclass

import pytest

from maestro import BranchRequest, BranchSpec, Signal, Step, StepResult


class TestSignal:
    """Tests for Signal enum."""

    def test_signal_values(self) -> None:
        """Signal has exactly 5 core values."""
        assert len(Signal) == 5
        assert Signal.CONTINUE == "continue"
        assert Signal.COMPLETE == "complete"
        assert Signal.FAIL == "fail"
        assert Signal.BRANCH == "branch"
        assert Signal.MERGE == "merge"

    def test_signal_is_str_enum(self) -> None:
        """Signal values are strings."""
        assert isinstance(Signal.CONTINUE.value, str)
        assert Signal.CONTINUE.value == "continue"


class TestBranchSpec:
    """Tests for BranchSpec dataclass."""

    def test_branch_spec_creation(self) -> None:
        """BranchSpec can be created with name and data."""
        spec = BranchSpec(name="test", data={"key": "value"})
        assert spec.name == "test"
        assert spec.data == {"key": "value"}

    def test_branch_spec_default_data(self) -> None:
        """BranchSpec defaults to empty dict for data."""
        spec = BranchSpec(name="test")
        assert spec.data == {}

    def test_branch_spec_is_frozen(self) -> None:
        """BranchSpec is immutable."""
        spec = BranchSpec(name="test")
        with pytest.raises(AttributeError):
            spec.name = "changed"  # type: ignore[misc]


class TestBranchRequest:
    """Tests for BranchRequest dataclass."""

    def test_branch_request_creation(self) -> None:
        """BranchRequest can be created with branches and merge_step."""
        branches = [BranchSpec(name="a"), BranchSpec(name="b")]
        request = BranchRequest(branches=branches, merge_step="merge")
        assert len(request.branches) == 2
        assert request.merge_step == "merge"
        assert request.child_start_step is None

    def test_branch_request_with_child_start(self) -> None:
        """BranchRequest accepts optional child_start_step."""
        branches = [BranchSpec(name="a")]
        request = BranchRequest(
            branches=branches, merge_step="merge", child_start_step="init"
        )
        assert request.child_start_step == "init"

    def test_branch_request_is_frozen(self) -> None:
        """BranchRequest is immutable."""
        request = BranchRequest(branches=[], merge_step="merge")
        with pytest.raises(AttributeError):
            request.merge_step = "changed"  # type: ignore[misc]


class TestStepResult:
    """Tests for StepResult dataclass."""

    @dataclass(frozen=True)
    class DummyContext:
        """Simple context for testing."""

        value: int

    def test_step_result_creation(self) -> None:
        """StepResult can be created with context and signal."""
        ctx = self.DummyContext(value=42)
        result: StepResult[TestStepResult.DummyContext, None] = StepResult(
            context=ctx, signal=Signal.CONTINUE
        )
        assert result.context.value == 42
        assert result.signal == Signal.CONTINUE
        assert result.output is None
        assert result.next_step is None
        assert result.branch_request is None

    def test_step_result_with_output(self) -> None:
        """StepResult can include step output."""
        ctx = self.DummyContext(value=1)
        result: StepResult[TestStepResult.DummyContext, str] = StepResult(
            context=ctx, signal=Signal.COMPLETE, output="done"
        )
        assert result.output == "done"

    def test_step_result_with_next_step(self) -> None:
        """StepResult can specify next step for routing."""
        ctx = self.DummyContext(value=1)
        result: StepResult[TestStepResult.DummyContext, None] = StepResult(
            context=ctx, signal=Signal.CONTINUE, next_step="process"
        )
        assert result.next_step == "process"

    def test_step_result_with_branch_request(self) -> None:
        """StepResult can include branch request for BRANCH signal."""
        ctx = self.DummyContext(value=1)
        branches = [BranchSpec(name="a"), BranchSpec(name="b")]
        branch_req = BranchRequest(branches=branches, merge_step="merge")
        result: StepResult[TestStepResult.DummyContext, None] = StepResult(
            context=ctx, signal=Signal.BRANCH, branch_request=branch_req
        )
        assert result.branch_request is not None
        assert len(result.branch_request.branches) == 2

    def test_step_result_branch_without_request_raises(self) -> None:
        """StepResult with BRANCH signal requires branch_request."""
        ctx = self.DummyContext(value=1)
        with pytest.raises(ValueError, match="BRANCH signal requires branch_request"):
            StepResult(context=ctx, signal=Signal.BRANCH)

    def test_step_result_is_frozen(self) -> None:
        """StepResult is immutable."""
        ctx = self.DummyContext(value=1)
        result: StepResult[TestStepResult.DummyContext, None] = StepResult(
            context=ctx, signal=Signal.CONTINUE
        )
        with pytest.raises(AttributeError):
            result.signal = Signal.COMPLETE  # type: ignore[misc]


class TestStepProtocol:
    """Tests for Step protocol."""

    @dataclass(frozen=True)
    class CounterContext:
        """Context for counter tests."""

        count: int

    class IncrementStep:
        """Simple step that increments counter."""

        @property
        def name(self) -> str:
            """Return step name."""
            return "increment"

        async def execute(
            self,
            context: "TestStepProtocol.CounterContext",
            input_data: int | None = None,
        ) -> StepResult["TestStepProtocol.CounterContext", int]:
            """Increment the counter."""
            increment = input_data if input_data is not None else 1
            new_ctx = TestStepProtocol.CounterContext(count=context.count + increment)
            return StepResult(
                context=new_ctx, signal=Signal.CONTINUE, output=new_ctx.count
            )

        def can_execute(self, context: "TestStepProtocol.CounterContext") -> bool:
            """Check if we can increment."""
            return context.count < 100

    def test_step_is_runtime_checkable(self) -> None:
        """Step protocol can be checked at runtime."""
        step = self.IncrementStep()
        assert isinstance(step, Step)

    def test_step_has_name(self) -> None:
        """Step has a name property."""
        step = self.IncrementStep()
        assert step.name == "increment"

    @pytest.mark.asyncio
    async def test_step_execute(self) -> None:
        """Step can execute and return result."""
        step = self.IncrementStep()
        ctx = self.CounterContext(count=5)
        result = await step.execute(ctx)
        assert result.context.count == 6
        assert result.signal == Signal.CONTINUE
        assert result.output == 6

    @pytest.mark.asyncio
    async def test_step_execute_with_input(self) -> None:
        """Step can use input_data."""
        step = self.IncrementStep()
        ctx = self.CounterContext(count=5)
        result = await step.execute(ctx, input_data=10)
        assert result.context.count == 15
        assert result.output == 15

    def test_step_can_execute(self) -> None:
        """Step can check execution preconditions."""
        step = self.IncrementStep()
        assert step.can_execute(self.CounterContext(count=50))
        assert not step.can_execute(self.CounterContext(count=100))

    def test_non_step_class_fails_isinstance(self) -> None:
        """Non-step classes fail isinstance check."""

        class NotAStep:
            pass

        assert not isinstance(NotAStep(), Step)

    def test_partial_step_fails_isinstance(self) -> None:
        """Partially-implemented step fails isinstance check."""

        class PartialStep:
            @property
            def name(self) -> str:
                return "partial"

            # Missing execute and can_execute

        assert not isinstance(PartialStep(), Step)
