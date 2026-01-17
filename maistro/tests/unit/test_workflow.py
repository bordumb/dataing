"""Tests for Workflow engine."""

from dataclasses import dataclass

import pytest

from maistro import (
    BranchRequest,
    BranchSpec,
    Signal,
    StepResult,
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
        return StepResult(context=new_ctx, signal=Signal.CONTINUE, output=new_ctx.count)

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
        return StepResult(context=context, signal=Signal.COMPLETE, output="done")

    def can_execute(self, context: CounterContext) -> bool:
        """Return True if the step can be executed."""
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
        """Return True if the step can be executed."""
        return True


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
        """Return True if the step can be executed."""
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
        """Return True if the step can be executed."""
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
    async def test_run_branch_signal_without_merge_step_raises(self) -> None:
        """Run raises WorkflowError on BRANCH signal when merge step doesn't exist.

        The BranchingStep specifies merge_step="merge" but no such step exists
        in the workflow, so after branch completion it fails to find the merge step.
        """
        workflow: Workflow[CounterContext] = Workflow()
        workflow.add_step(BranchingStep())

        with pytest.raises(WorkflowError) as exc_info:
            await workflow.run(CounterContext(count=0), "branch")

        # Fails because merge step doesn't exist in the workflow
        assert "Step not found" in exc_info.value.message

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
