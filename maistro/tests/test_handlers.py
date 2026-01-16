"""Tests for signal handlers."""

from dataclasses import dataclass, field

import pytest

from maistro import (
    BranchContext,
    BranchingSignalHandler,
    BranchRequest,
    BranchSpec,
    DefaultSignalHandler,
    MergeStrategy,
    Signal,
    SignalHandlerError,
    SignalResult,
    StepResult,
    Workflow,
)


@dataclass(frozen=True)
class SampleContext:
    """Simple context for testing."""

    value: int
    items: tuple[str, ...] = field(default_factory=tuple)


class AddMergeStrategy:
    """Merge strategy that sums values from all branches."""

    def merge(
        self,
        parent_context: SampleContext,
        child_contexts: list[BranchContext[SampleContext]],
    ) -> SampleContext:
        """Sum values from all children."""
        total = sum(bc.context.value for bc in child_contexts)
        all_items = []
        for bc in child_contexts:
            all_items.extend(bc.context.items)
        return SampleContext(value=total, items=tuple(all_items))


class TestDefaultSignalHandler:
    """Tests for DefaultSignalHandler."""

    @pytest.fixture
    def handler(self) -> DefaultSignalHandler[SampleContext]:
        """Create handler instance."""
        return DefaultSignalHandler[SampleContext]()

    @pytest.fixture
    def workflow(self) -> Workflow[SampleContext]:
        """Create workflow instance."""
        return Workflow[SampleContext]()

    @pytest.mark.asyncio
    async def test_handle_continue(
        self, handler: DefaultSignalHandler[SampleContext], workflow: Workflow[SampleContext]
    ) -> None:
        """CONTINUE signal returns context with should_continue=True."""
        ctx = SampleContext(value=1)
        result = StepResult(context=ctx, signal=Signal.CONTINUE, next_step="next")

        signal_result = await handler.handle_continue(ctx, result, workflow)

        assert signal_result.should_continue
        assert signal_result.context.value == 1
        assert signal_result.next_step == "next"

    @pytest.mark.asyncio
    async def test_handle_complete(
        self, handler: DefaultSignalHandler[SampleContext], workflow: Workflow[SampleContext]
    ) -> None:
        """COMPLETE signal returns should_continue=False."""
        ctx = SampleContext(value=42)
        result = StepResult(context=ctx, signal=Signal.COMPLETE)

        signal_result = await handler.handle_complete(ctx, result, workflow)

        assert not signal_result.should_continue
        assert signal_result.context.value == 42

    @pytest.mark.asyncio
    async def test_handle_fail(
        self, handler: DefaultSignalHandler[SampleContext], workflow: Workflow[SampleContext]
    ) -> None:
        """FAIL signal returns should_continue=False with error."""
        ctx = SampleContext(value=0)
        result = StepResult(context=ctx, signal=Signal.FAIL)

        signal_result = await handler.handle_fail(ctx, result, workflow)

        assert not signal_result.should_continue
        assert signal_result.error is not None

    @pytest.mark.asyncio
    async def test_handle_branch_raises(
        self, handler: DefaultSignalHandler[SampleContext], workflow: Workflow[SampleContext]
    ) -> None:
        """BRANCH signal raises NotImplementedError."""
        ctx = SampleContext(value=0)
        branches = [BranchSpec(name="a")]
        branch_req = BranchRequest(branches=branches, merge_step="merge")
        result = StepResult(
            context=ctx, signal=Signal.BRANCH, branch_request=branch_req
        )

        with pytest.raises(NotImplementedError):
            await handler.handle_branch(ctx, result, workflow)

    @pytest.mark.asyncio
    async def test_handle_merge_raises(
        self, handler: DefaultSignalHandler[SampleContext], workflow: Workflow[SampleContext]
    ) -> None:
        """MERGE signal raises NotImplementedError."""
        ctx = SampleContext(value=0)
        result = StepResult(context=ctx, signal=Signal.MERGE)

        with pytest.raises(NotImplementedError):
            await handler.handle_merge(ctx, result, workflow)

    @pytest.mark.asyncio
    async def test_handle_routes_to_continue(
        self, handler: DefaultSignalHandler[SampleContext], workflow: Workflow[SampleContext]
    ) -> None:
        """handle() routes CONTINUE to handle_continue."""
        ctx = SampleContext(value=1)
        result = StepResult(context=ctx, signal=Signal.CONTINUE, next_step="next")

        signal_result = await handler.handle(Signal.CONTINUE, ctx, result, workflow)

        assert signal_result.should_continue
        assert signal_result.next_step == "next"

    @pytest.mark.asyncio
    async def test_handle_routes_to_complete(
        self, handler: DefaultSignalHandler[SampleContext], workflow: Workflow[SampleContext]
    ) -> None:
        """handle() routes COMPLETE to handle_complete."""
        ctx = SampleContext(value=1)
        result = StepResult(context=ctx, signal=Signal.COMPLETE)

        signal_result = await handler.handle(Signal.COMPLETE, ctx, result, workflow)

        assert not signal_result.should_continue


class TestBranchingSignalHandler:
    """Tests for BranchingSignalHandler."""

    @pytest.fixture
    def merge_strategy(self) -> AddMergeStrategy:
        """Create merge strategy."""
        return AddMergeStrategy()

    @pytest.fixture
    def handler(
        self, merge_strategy: AddMergeStrategy
    ) -> BranchingSignalHandler[SampleContext]:
        """Create handler instance."""
        return BranchingSignalHandler[SampleContext](merge_strategy)

    @pytest.fixture
    def workflow(self) -> Workflow[SampleContext]:
        """Create workflow instance."""
        return Workflow[SampleContext]()

    @pytest.mark.asyncio
    async def test_handle_branch_creates_contexts(
        self,
        handler: BranchingSignalHandler[SampleContext],
        workflow: Workflow[SampleContext],
    ) -> None:
        """BRANCH signal creates child branch contexts."""
        ctx = SampleContext(value=10)
        branches = [
            BranchSpec(name="branch_a", data={"key": "a"}),
            BranchSpec(name="branch_b", data={"key": "b"}),
        ]
        branch_req = BranchRequest(
            branches=branches, merge_step="merge", child_start_step="process"
        )
        result = StepResult(
            context=ctx, signal=Signal.BRANCH, branch_request=branch_req
        )

        signal_result = await handler.handle_branch(ctx, result, workflow)

        assert signal_result.should_continue
        assert signal_result.next_step == "process"
        assert signal_result.branch_contexts is not None
        assert len(signal_result.branch_contexts) == 2

        branch_a = signal_result.branch_contexts[0]
        assert branch_a.name == "branch_a"
        assert branch_a.context.value == 10
        assert branch_a.data == {"key": "a"}

    @pytest.mark.asyncio
    async def test_handle_branch_without_request_raises(
        self,
        handler: BranchingSignalHandler[SampleContext],
        workflow: Workflow[SampleContext],
    ) -> None:
        """BRANCH signal without branch_request is prevented by StepResult validation."""
        ctx = SampleContext(value=0)
        # StepResult validation prevents BRANCH without branch_request
        with pytest.raises(ValueError, match="BRANCH signal requires branch_request"):
            StepResult(context=ctx, signal=Signal.BRANCH)

    def test_register_branch_completion(
        self,
        handler: BranchingSignalHandler[SampleContext],
    ) -> None:
        """Branch completion can be registered."""
        merge_step = "merge"
        handler._expected_counts[merge_step] = 2

        branch_a = BranchContext(name="a", context=SampleContext(value=5))
        is_complete = handler.register_branch_completion(merge_step, branch_a)
        assert not is_complete

        branch_b = BranchContext(name="b", context=SampleContext(value=10))
        is_complete = handler.register_branch_completion(merge_step, branch_b)
        assert is_complete

    @pytest.mark.asyncio
    async def test_handle_merge_combines_contexts(
        self,
        handler: BranchingSignalHandler[SampleContext],
        workflow: Workflow[SampleContext],
    ) -> None:
        """MERGE signal uses strategy to combine contexts."""
        merge_step = "merge"
        parent_ctx = SampleContext(value=0)
        handler._parent_contexts[merge_step] = parent_ctx
        handler._expected_counts[merge_step] = 2

        # Register completed branches
        handler._pending_branches[merge_step] = [
            BranchContext(name="a", context=SampleContext(value=5, items=("a",))),
            BranchContext(name="b", context=SampleContext(value=10, items=("b",))),
        ]

        result = StepResult(
            context=parent_ctx, signal=Signal.MERGE, next_step=merge_step
        )

        signal_result = await handler.handle_merge(parent_ctx, result, workflow)

        assert signal_result.should_continue
        assert signal_result.context.value == 15  # 5 + 10
        assert set(signal_result.context.items) == {"a", "b"}

    @pytest.mark.asyncio
    async def test_handle_merge_no_pending_raises(
        self,
        handler: BranchingSignalHandler[SampleContext],
        workflow: Workflow[SampleContext],
    ) -> None:
        """MERGE signal with no pending branches raises error."""
        ctx = SampleContext(value=0)
        result = StepResult(context=ctx, signal=Signal.MERGE, next_step="unknown")

        with pytest.raises(SignalHandlerError) as exc_info:
            await handler.handle_merge(ctx, result, workflow)

        assert "No pending branches" in str(exc_info.value)


class TestSignalResult:
    """Tests for SignalResult dataclass."""

    def test_signal_result_creation(self) -> None:
        """SignalResult can be created."""
        ctx = SampleContext(value=1)
        result = SignalResult(context=ctx, should_continue=True)
        assert result.context.value == 1
        assert result.should_continue

    def test_signal_result_with_branches(self) -> None:
        """SignalResult can contain branch contexts."""
        ctx = SampleContext(value=1)
        branches = [BranchContext(name="a", context=ctx)]
        result = SignalResult(
            context=ctx, should_continue=True, branch_contexts=branches
        )
        assert result.branch_contexts is not None
        assert len(result.branch_contexts) == 1

    def test_signal_result_is_frozen(self) -> None:
        """SignalResult is immutable."""
        ctx = SampleContext(value=1)
        result = SignalResult(context=ctx, should_continue=True)
        with pytest.raises(AttributeError):
            result.should_continue = False  # type: ignore[misc]


class TestBranchContext:
    """Tests for BranchContext dataclass."""

    def test_branch_context_creation(self) -> None:
        """BranchContext can be created."""
        ctx = SampleContext(value=5)
        bc = BranchContext(name="test", context=ctx, data={"key": "value"})
        assert bc.name == "test"
        assert bc.context.value == 5
        assert bc.data == {"key": "value"}

    def test_branch_context_default_data(self) -> None:
        """BranchContext defaults to empty dict for data."""
        ctx = SampleContext(value=5)
        bc = BranchContext(name="test", context=ctx)
        assert bc.data == {}

    def test_branch_context_is_frozen(self) -> None:
        """BranchContext is immutable."""
        ctx = SampleContext(value=5)
        bc = BranchContext(name="test", context=ctx)
        with pytest.raises(AttributeError):
            bc.name = "changed"  # type: ignore[misc]


class TestMergeStrategy:
    """Tests for MergeStrategy protocol."""

    def test_merge_strategy_is_runtime_checkable(self) -> None:
        """MergeStrategy can be checked at runtime."""
        strategy = AddMergeStrategy()
        assert isinstance(strategy, MergeStrategy)

    def test_merge_strategy_works(self) -> None:
        """MergeStrategy merges contexts."""
        strategy = AddMergeStrategy()
        parent = SampleContext(value=0)
        children = [
            BranchContext(name="a", context=SampleContext(value=5, items=("x",))),
            BranchContext(name="b", context=SampleContext(value=3, items=("y",))),
        ]

        merged = strategy.merge(parent, children)

        assert merged.value == 8
        assert set(merged.items) == {"x", "y"}


class TestWorkflowSignalHandler:
    """Tests for Workflow signal handler integration."""

    def test_set_signal_handler(self) -> None:
        """Workflow can have signal handler set."""
        workflow: Workflow[SampleContext] = Workflow()
        handler = DefaultSignalHandler[SampleContext]()

        workflow.set_signal_handler(handler)

        assert workflow.get_signal_handler() is handler

    def test_get_signal_handler_default_none(self) -> None:
        """Workflow has no signal handler by default."""
        workflow: Workflow[SampleContext] = Workflow()

        assert workflow.get_signal_handler() is None
