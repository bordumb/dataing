"""Tests for Workflow engine."""

from dataclasses import dataclass

import pytest

from maestro import (
    BranchRequest,
    BranchSpec,
    Signal,
    StepResult,
    TickResult,
    Workflow,
    WorkflowError,
)


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
        return StepResult(context=new_ctx, signal=Signal.CONTINUE, output=new_ctx.count)

    def can_execute(self, context: CounterContext) -> bool:
        """Always can execute."""
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
        return StepResult(context=new_ctx, signal=Signal.CONTINUE, output=new_ctx.count)

    def can_execute(self, context: CounterContext) -> bool:
        """Always can execute."""
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
        return StepResult(context=context, signal=Signal.COMPLETE, output="done")

    def can_execute(self, context: CounterContext) -> bool:
        """Always can execute."""
        return True


class FailStep:
    """Step that signals failure."""

    @property
    def name(self) -> str:
        """Return step name."""
        return "fail"

    async def execute(
        self, context: CounterContext, input_data: None = None
    ) -> StepResult[CounterContext, None]:
        """Fail the workflow."""
        return StepResult(context=context, signal=Signal.FAIL)

    def can_execute(self, context: CounterContext) -> bool:
        """Always can execute."""
        return True


class ConditionalStep:
    """Step that only executes when count < 10."""

    @property
    def name(self) -> str:
        """Return step name."""
        return "conditional"

    async def execute(
        self, context: CounterContext, input_data: None = None
    ) -> StepResult[CounterContext, None]:
        """Execute conditionally."""
        new_ctx = CounterContext(count=context.count + 1)
        return StepResult(context=new_ctx, signal=Signal.CONTINUE)

    def can_execute(self, context: CounterContext) -> bool:
        """Only execute when count < 10."""
        return context.count < 10


class BranchingStep:
    """Step that requests branching."""

    @property
    def name(self) -> str:
        """Return step name."""
        return "branch"

    async def execute(
        self, context: CounterContext, input_data: None = None
    ) -> StepResult[CounterContext, None]:
        """Request branch creation."""
        branches = [BranchSpec(name="a"), BranchSpec(name="b")]
        branch_req = BranchRequest(branches=branches, merge_step="merge")
        return StepResult(
            context=context, signal=Signal.BRANCH, branch_request=branch_req
        )

    def can_execute(self, context: CounterContext) -> bool:
        """Always can execute."""
        return True


class RoutingStep:
    """Step that routes to a specific next step."""

    def __init__(self, route_to: str) -> None:
        """Initialize with target step."""
        self._route_to = route_to

    @property
    def name(self) -> str:
        """Return step name."""
        return "router"

    async def execute(
        self, context: CounterContext, input_data: None = None
    ) -> StepResult[CounterContext, None]:
        """Route to specific step."""
        return StepResult(
            context=context, signal=Signal.CONTINUE, next_step=self._route_to
        )

    def can_execute(self, context: CounterContext) -> bool:
        """Always can execute."""
        return True


class TestWorkflow:
    """Tests for Workflow class."""

    def test_add_step(self) -> None:
        """Steps can be added to workflow."""
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(IncrementStep())
        assert workflow.get_step("increment") is not None

    def test_add_duplicate_step_raises(self) -> None:
        """Adding duplicate step raises error."""
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(IncrementStep())
        with pytest.raises(ValueError, match="Step already registered"):
            workflow.add_step(IncrementStep())

    def test_get_step_not_found(self) -> None:
        """Getting unknown step returns None."""
        workflow: Workflow[CounterContext] = Workflow()
        assert workflow.get_step("unknown") is None

    @pytest.mark.asyncio
    async def test_tick_step_not_found(self) -> None:
        """Tick with unknown step returns FAIL."""
        workflow: Workflow[CounterContext] = Workflow()
        ctx = CounterContext(count=0)
        result = await workflow.tick(ctx, "unknown")
        assert result.signal == Signal.FAIL
        assert "not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_tick_executes_step(self) -> None:
        """Tick executes step and returns result."""
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(IncrementStep())
        ctx = CounterContext(count=5)
        result = await workflow.tick(ctx, "increment")
        assert result.signal == Signal.CONTINUE
        assert result.context.count == 6
        assert result.output == 6

    @pytest.mark.asyncio
    async def test_tick_with_input_data(self) -> None:
        """Tick passes input data to step."""
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(IncrementStep())
        ctx = CounterContext(count=5)
        result = await workflow.tick(ctx, "increment", input_data=10)
        assert result.context.count == 15

    @pytest.mark.asyncio
    async def test_tick_can_execute_false_fails(self) -> None:
        """Tick returns FAIL when can_execute is False."""
        workflow: Workflow[CounterContext] = Workflow(fail_on_cannot_execute=True)
        workflow.add_step(ConditionalStep())
        ctx = CounterContext(count=100)
        result = await workflow.tick(ctx, "conditional")
        assert result.signal == Signal.FAIL
        assert "preconditions not met" in (result.error or "")

    @pytest.mark.asyncio
    async def test_tick_can_execute_false_skips(self) -> None:
        """Tick skips step when can_execute is False and configured to skip."""
        workflow: Workflow[CounterContext] = Workflow(fail_on_cannot_execute=False)
        workflow.add_step(ConditionalStep())
        workflow.add_step(CompleteStep())
        ctx = CounterContext(count=100)
        result = await workflow.tick(ctx, "conditional")
        assert result.signal == Signal.CONTINUE
        assert result.next_step == "complete"

    @pytest.mark.asyncio
    async def test_tick_determines_next_step(self) -> None:
        """Tick determines next step from order."""
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(IncrementStep())
        workflow.add_step(DoubleStep())
        ctx = CounterContext(count=1)
        result = await workflow.tick(ctx, "increment")
        assert result.next_step == "double"

    @pytest.mark.asyncio
    async def test_tick_respects_explicit_routing(self) -> None:
        """Tick uses explicit next_step from result."""
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(RoutingStep("complete"))
        workflow.add_step(IncrementStep())
        workflow.add_step(CompleteStep())
        ctx = CounterContext(count=1)
        result = await workflow.tick(ctx, "router")
        assert result.next_step == "complete"


class TestWorkflowRun:
    """Tests for Workflow.run() method."""

    @pytest.mark.asyncio
    async def test_run_two_step_workflow(self) -> None:
        """Two-step workflow runs to completion."""
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(IncrementStep())
        workflow.add_step(CompleteStep())

        result = await workflow.run(CounterContext(count=0), "increment")
        assert result.count == 1

    @pytest.mark.asyncio
    async def test_run_multi_step_workflow(self) -> None:
        """Multi-step workflow runs all steps."""
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(IncrementStep())
        workflow.add_step(DoubleStep())
        workflow.add_step(CompleteStep())

        result = await workflow.run(CounterContext(count=5), "increment")
        # 5 + 1 = 6, 6 * 2 = 12
        assert result.count == 12

    @pytest.mark.asyncio
    async def test_run_with_input_data(self) -> None:
        """Run passes input data to first step."""
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(IncrementStep())
        workflow.add_step(CompleteStep())

        result = await workflow.run(CounterContext(count=0), "increment", input_data=10)
        assert result.count == 10

    @pytest.mark.asyncio
    async def test_run_fail_signal_raises(self) -> None:
        """Run raises WorkflowError on FAIL signal."""
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(FailStep())

        with pytest.raises(WorkflowError) as exc_info:
            await workflow.run(CounterContext(count=0), "fail")

        assert exc_info.value.context.count == 0

    @pytest.mark.asyncio
    async def test_run_step_not_found_raises(self) -> None:
        """Run raises WorkflowError when step not found."""
        workflow: Workflow[CounterContext] = Workflow()

        with pytest.raises(WorkflowError) as exc_info:
            await workflow.run(CounterContext(count=0), "unknown")

        assert "not found" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_run_max_iterations_raises(self) -> None:
        """Run raises WorkflowError on max iterations."""

        class LoopStep:
            @property
            def name(self) -> str:
                return "loop"

            async def execute(
                self, context: CounterContext, input_data: None = None
            ) -> StepResult[CounterContext, None]:
                return StepResult(
                    context=context, signal=Signal.CONTINUE, next_step="loop"
                )

            def can_execute(self, context: CounterContext) -> bool:
                return True

        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(LoopStep())

        with pytest.raises(WorkflowError) as exc_info:
            await workflow.run(CounterContext(count=0), "loop", max_iterations=5)

        assert "max iterations" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_run_branch_signal_without_handler_raises(self) -> None:
        """Run raises WorkflowError on BRANCH signal without signal handler."""
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(BranchingStep())

        with pytest.raises(WorkflowError) as exc_info:
            await workflow.run(CounterContext(count=0), "branch")

        assert "signal handler" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_run_explicit_routing(self) -> None:
        """Run follows explicit routing."""
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(RoutingStep("complete"))
        workflow.add_step(IncrementStep())
        workflow.add_step(CompleteStep())

        # Should route from router -> complete, skipping increment
        result = await workflow.run(CounterContext(count=5), "router")
        assert result.count == 5  # Unchanged, skipped increment

    @pytest.mark.asyncio
    async def test_run_completes_at_end_of_steps(self) -> None:
        """Run completes when no more steps."""
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(IncrementStep())
        # No CompleteStep - should complete when increment returns CONTINUE with no next

        result = await workflow.run(CounterContext(count=0), "increment")
        assert result.count == 1


class TestTickResult:
    """Tests for TickResult dataclass."""

    def test_tick_result_creation(self) -> None:
        """TickResult can be created."""
        ctx = CounterContext(count=1)
        result: TickResult[CounterContext] = TickResult(
            context=ctx, signal=Signal.CONTINUE
        )
        assert result.context.count == 1
        assert result.signal == Signal.CONTINUE
        assert result.next_step is None

    def test_tick_result_with_error(self) -> None:
        """TickResult can include error."""
        ctx = CounterContext(count=1)
        result: TickResult[CounterContext] = TickResult(
            context=ctx, signal=Signal.FAIL, error="Something went wrong"
        )
        assert result.error == "Something went wrong"

    def test_tick_result_is_frozen(self) -> None:
        """TickResult is immutable."""
        ctx = CounterContext(count=1)
        result: TickResult[CounterContext] = TickResult(
            context=ctx, signal=Signal.CONTINUE
        )
        with pytest.raises(AttributeError):
            result.signal = Signal.FAIL  # type: ignore[misc]


class TestWorkflowError:
    """Tests for WorkflowError exception."""

    def test_workflow_error_creation(self) -> None:
        """WorkflowError can be created."""
        ctx = CounterContext(count=5)
        error = WorkflowError("Test error", context=ctx)
        assert str(error) == "Test error"
        assert error.context.count == 5
        assert error.message == "Test error"

    def test_workflow_error_without_context(self) -> None:
        """WorkflowError works without context."""
        error = WorkflowError("Test error")
        assert error.context is None
