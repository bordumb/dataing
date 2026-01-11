"""Tests for new investigation orchestrator."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from dataing.core.investigation.entities import (
    Branch,
    InvestigationContext,
    Snapshot,
)
from dataing.core.investigation.orchestrator import InvestigationOrchestrator
from dataing.core.investigation.registry import StepRegistry
from dataing.core.investigation.steps.protocol import Step, StepResult
from dataing.core.investigation.values import (
    BranchStatus,
    BranchType,
    ExecutionSignal,
    StepType,
    VersionId,
)


@pytest.fixture
def sample_context() -> InvestigationContext:
    """Create sample context."""
    return InvestigationContext(alert_summary="Test anomaly")


@pytest.fixture
def sample_snapshot(sample_context: InvestigationContext) -> Snapshot:
    """Create sample snapshot."""
    return Snapshot(
        investigation_id=uuid4(),
        branch_id=uuid4(),
        version=VersionId(major=1, minor=0, patch=0),
        step=StepType.GATHER_CONTEXT,
        context=sample_context,
    )


@pytest.fixture
def sample_branch(sample_snapshot: Snapshot) -> Branch:
    """Create sample branch."""
    return Branch(
        id=sample_snapshot.branch_id,
        investigation_id=sample_snapshot.investigation_id,
        branch_type=BranchType.MAIN,
        name="main",
        head_snapshot_id=sample_snapshot.id,
        status=BranchStatus.ACTIVE,
    )


@pytest.fixture
def mock_repository(sample_snapshot: Snapshot, sample_branch: Branch) -> AsyncMock:
    """Create mock repository."""
    repo = AsyncMock()
    repo.get_snapshot.return_value = sample_snapshot
    repo.get_branch.return_value = sample_branch
    repo.create_snapshot.return_value = sample_snapshot
    return repo


@pytest.fixture
def mock_step(sample_context: InvestigationContext) -> MagicMock:
    """Create mock step that returns CONTINUE."""
    step = MagicMock(spec=Step)
    step.step_type = StepType.GATHER_CONTEXT
    step.can_execute.return_value = True
    step.execute = AsyncMock(
        return_value=StepResult(
            context=sample_context,
            signal=ExecutionSignal.CONTINUE,
            next_step=StepType.GENERATE_HYPOTHESES,
        )
    )
    return step


@pytest.fixture
def registry(mock_step: MagicMock) -> StepRegistry:
    """Create registry with mock step."""
    reg = StepRegistry()
    reg.register(mock_step)
    return reg


class TestInvestigationOrchestrator:
    """Tests for InvestigationOrchestrator."""

    @pytest.mark.asyncio
    async def test_tick_executes_current_step(
        self,
        mock_repository: AsyncMock,
        registry: StepRegistry,
        sample_branch: Branch,
        mock_step: MagicMock,
    ) -> None:
        """tick() executes the step for current snapshot."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
        )

        await orchestrator.tick(sample_branch.id)

        mock_step.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_continue_creates_new_snapshot(
        self,
        mock_repository: AsyncMock,
        registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() with CONTINUE signal creates new snapshot."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
        )

        await orchestrator.tick(sample_branch.id)

        mock_repository.create_snapshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_continue_updates_branch_head(
        self,
        mock_repository: AsyncMock,
        registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() with CONTINUE signal updates branch head."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
        )

        await orchestrator.tick(sample_branch.id)

        mock_repository.update_branch_head.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_complete_updates_investigation_outcome(
        self,
        mock_repository: AsyncMock,
        sample_branch: Branch,
        sample_snapshot: Snapshot,
        sample_context: InvestigationContext,
    ) -> None:
        """tick() with COMPLETE signal updates investigation outcome."""
        # Create step that returns COMPLETE
        complete_step = MagicMock(spec=Step)
        complete_step.step_type = StepType.SYNTHESIZE
        complete_step.can_execute.return_value = True
        complete_step.execute = AsyncMock(
            return_value=StepResult(
                context=sample_context,
                signal=ExecutionSignal.COMPLETE,
                output={"root_cause": "Test", "confidence": 0.9},
            )
        )

        registry = StepRegistry()
        registry.register(complete_step)

        # Update snapshot to be at SYNTHESIZE step
        complete_snapshot = Snapshot(
            id=sample_snapshot.id,
            investigation_id=sample_snapshot.investigation_id,
            branch_id=sample_snapshot.branch_id,
            version=sample_snapshot.version,
            step=StepType.SYNTHESIZE,
            context=sample_context,
        )
        mock_repository.get_snapshot.return_value = complete_snapshot

        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
        )

        await orchestrator.tick(sample_branch.id)

        mock_repository.update_investigation_outcome.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_complete_marks_branch_completed(
        self,
        mock_repository: AsyncMock,
        sample_branch: Branch,
        sample_snapshot: Snapshot,
        sample_context: InvestigationContext,
    ) -> None:
        """tick() with COMPLETE signal marks branch as completed."""
        complete_step = MagicMock(spec=Step)
        complete_step.step_type = StepType.SYNTHESIZE
        complete_step.can_execute.return_value = True
        complete_step.execute = AsyncMock(
            return_value=StepResult(
                context=sample_context,
                signal=ExecutionSignal.COMPLETE,
                output={"root_cause": "Test", "confidence": 0.9},
            )
        )

        registry = StepRegistry()
        registry.register(complete_step)

        complete_snapshot = Snapshot(
            id=sample_snapshot.id,
            investigation_id=sample_snapshot.investigation_id,
            branch_id=sample_snapshot.branch_id,
            version=sample_snapshot.version,
            step=StepType.SYNTHESIZE,
            context=sample_context,
        )
        mock_repository.get_snapshot.return_value = complete_snapshot

        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
        )

        await orchestrator.tick(sample_branch.id)

        mock_repository.update_branch_status.assert_called_with(
            sample_branch.id,
            BranchStatus.COMPLETED,
        )

    @pytest.mark.asyncio
    async def test_tick_returns_result(
        self,
        mock_repository: AsyncMock,
        registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() returns the tick result."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
        )

        result = await orchestrator.tick(sample_branch.id)

        assert result is not None
        assert result.signal == ExecutionSignal.CONTINUE

    @pytest.mark.asyncio
    async def test_tick_branch_not_found(
        self,
        mock_repository: AsyncMock,
        registry: StepRegistry,
    ) -> None:
        """tick() returns FAIL when branch not found."""
        mock_repository.get_branch.return_value = None

        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
        )

        result = await orchestrator.tick(uuid4())

        assert result.signal == ExecutionSignal.FAIL
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_tick_no_head_snapshot(
        self,
        mock_repository: AsyncMock,
        registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() returns FAIL when branch has no head snapshot."""
        no_head_branch = Branch(
            id=sample_branch.id,
            investigation_id=sample_branch.investigation_id,
            branch_type=BranchType.MAIN,
            name="main",
            head_snapshot_id=None,
            status=BranchStatus.ACTIVE,
        )
        mock_repository.get_branch.return_value = no_head_branch

        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
        )

        result = await orchestrator.tick(sample_branch.id)

        assert result.signal == ExecutionSignal.FAIL
        assert "no head snapshot" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_tick_step_not_registered(
        self,
        mock_repository: AsyncMock,
        sample_branch: Branch,
    ) -> None:
        """tick() returns FAIL when step not registered."""
        empty_registry = StepRegistry()

        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=empty_registry,
        )

        result = await orchestrator.tick(sample_branch.id)

        assert result.signal == ExecutionSignal.FAIL
        assert "no step registered" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_tick_preconditions_not_met(
        self,
        mock_repository: AsyncMock,
        sample_branch: Branch,
        sample_context: InvestigationContext,
    ) -> None:
        """tick() returns FAIL when step preconditions not met."""
        failing_step = MagicMock(spec=Step)
        failing_step.step_type = StepType.GATHER_CONTEXT
        failing_step.can_execute.return_value = False

        registry = StepRegistry()
        registry.register(failing_step)

        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
        )

        result = await orchestrator.tick(sample_branch.id)

        assert result.signal == ExecutionSignal.FAIL
        assert "preconditions not met" in (result.error or "").lower()


class TestOrchestratorLocking:
    """Tests for orchestrator lock acquisition and release."""

    @pytest.mark.asyncio
    async def test_tick_acquires_lock_before_execution(
        self,
        mock_repository: AsyncMock,
        registry: StepRegistry,
        sample_branch: Branch,
        mock_step: MagicMock,
    ) -> None:
        """tick() acquires lock before executing step."""
        from dataing.core.investigation.repository import ExecutionLock

        lock = ExecutionLock(
            branch_id=sample_branch.id,
            locked_by="test-worker",
            expires_at="2024-01-01T00:00:00Z",
        )
        mock_repository.acquire_lock.return_value = lock

        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
            worker_id="test-worker",
        )

        await orchestrator.tick(sample_branch.id)

        # Lock should be acquired before step execution
        mock_repository.acquire_lock.assert_called_once_with(
            sample_branch.id,
            "test-worker",
            300,  # default TTL
        )

    @pytest.mark.asyncio
    async def test_tick_releases_lock_after_success(
        self,
        mock_repository: AsyncMock,
        registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() releases lock after successful execution."""
        from dataing.core.investigation.repository import ExecutionLock

        lock = ExecutionLock(
            branch_id=sample_branch.id,
            locked_by="test-worker",
            expires_at="2024-01-01T00:00:00Z",
        )
        mock_repository.acquire_lock.return_value = lock
        mock_repository.release_lock.return_value = True

        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
            worker_id="test-worker",
        )

        await orchestrator.tick(sample_branch.id)

        mock_repository.release_lock.assert_called_once_with(
            sample_branch.id,
            "test-worker",
        )

    @pytest.mark.asyncio
    async def test_tick_releases_lock_on_error(
        self,
        mock_repository: AsyncMock,
        registry: StepRegistry,
        sample_branch: Branch,
        mock_step: MagicMock,
    ) -> None:
        """tick() releases lock even when step execution fails."""
        from dataing.core.investigation.repository import ExecutionLock

        lock = ExecutionLock(
            branch_id=sample_branch.id,
            locked_by="test-worker",
            expires_at="2024-01-01T00:00:00Z",
        )
        mock_repository.acquire_lock.return_value = lock
        mock_repository.release_lock.return_value = True

        # Make step raise an exception
        mock_step.execute.side_effect = RuntimeError("Step failed")

        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
            worker_id="test-worker",
        )

        # Should not raise, just return FAIL
        result = await orchestrator.tick(sample_branch.id)

        # Lock should still be released
        mock_repository.release_lock.assert_called_once_with(
            sample_branch.id,
            "test-worker",
        )
        assert result.signal == ExecutionSignal.FAIL

    @pytest.mark.asyncio
    async def test_tick_fails_when_lock_not_acquired(
        self,
        mock_repository: AsyncMock,
        registry: StepRegistry,
        sample_branch: Branch,
        mock_step: MagicMock,
    ) -> None:
        """tick() returns FAIL when lock cannot be acquired."""
        mock_repository.acquire_lock.return_value = None  # Lock not acquired

        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
            worker_id="test-worker",
        )

        result = await orchestrator.tick(sample_branch.id)

        assert result.signal == ExecutionSignal.FAIL
        assert "lock" in (result.error or "").lower()
        # Step should not have been executed
        mock_step.execute.assert_not_called()
        # Release should not be called since lock wasn't acquired
        mock_repository.release_lock.assert_not_called()

    @pytest.mark.asyncio
    async def test_tick_uses_worker_id_from_init(
        self,
        mock_repository: AsyncMock,
        registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() uses the worker_id provided at initialization."""
        from dataing.core.investigation.repository import ExecutionLock

        custom_worker_id = "custom-worker-12345"
        lock = ExecutionLock(
            branch_id=sample_branch.id,
            locked_by=custom_worker_id,
            expires_at="2024-01-01T00:00:00Z",
        )
        mock_repository.acquire_lock.return_value = lock
        mock_repository.release_lock.return_value = True

        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
            worker_id=custom_worker_id,
        )

        await orchestrator.tick(sample_branch.id)

        mock_repository.acquire_lock.assert_called_once_with(
            sample_branch.id,
            custom_worker_id,
            300,
        )
        mock_repository.release_lock.assert_called_once_with(
            sample_branch.id,
            custom_worker_id,
        )

    @pytest.mark.asyncio
    async def test_tick_uses_custom_ttl(
        self,
        mock_repository: AsyncMock,
        registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() uses the lock_ttl_seconds provided at initialization."""
        from dataing.core.investigation.repository import ExecutionLock

        custom_ttl = 600  # 10 minutes
        lock = ExecutionLock(
            branch_id=sample_branch.id,
            locked_by="test-worker",
            expires_at="2024-01-01T00:00:00Z",
        )
        mock_repository.acquire_lock.return_value = lock
        mock_repository.release_lock.return_value = True

        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
            worker_id="test-worker",
            lock_ttl_seconds=custom_ttl,
        )

        await orchestrator.tick(sample_branch.id)

        mock_repository.acquire_lock.assert_called_once_with(
            sample_branch.id,
            "test-worker",
            custom_ttl,
        )

    @pytest.mark.asyncio
    async def test_default_worker_id_is_generated(
        self,
        mock_repository: AsyncMock,
        registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """Worker ID is auto-generated if not provided."""
        from dataing.core.investigation.repository import ExecutionLock

        lock = ExecutionLock(
            branch_id=sample_branch.id,
            locked_by="auto-generated",
            expires_at="2024-01-01T00:00:00Z",
        )
        mock_repository.acquire_lock.return_value = lock
        mock_repository.release_lock.return_value = True

        orchestrator = InvestigationOrchestrator(
            repository=mock_repository,
            registry=registry,
            # No worker_id provided - should auto-generate
        )

        # Should have a worker_id attribute
        assert orchestrator.worker_id is not None
        assert len(orchestrator.worker_id) > 0

        await orchestrator.tick(sample_branch.id)

        # acquire_lock should be called with the generated worker_id
        call_args = mock_repository.acquire_lock.call_args
        assert call_args[0][1] == orchestrator.worker_id


class TestOrchestratorBranching:
    """Tests for orchestrator BRANCH signal handling."""

    @pytest.fixture
    def branch_step(self, sample_context: InvestigationContext) -> MagicMock:
        """Create mock step that returns BRANCH signal."""
        from dataing.core.investigation.steps.protocol import BranchRequest, BranchSpec

        step = MagicMock(spec=Step)
        step.step_type = StepType.GENERATE_HYPOTHESES
        step.can_execute.return_value = True
        step.execute = AsyncMock(
            return_value=StepResult(
                context=sample_context,
                signal=ExecutionSignal.BRANCH,
                branch_request=BranchRequest(
                    branch_type=BranchType.HYPOTHESIS,
                    branches=[
                        BranchSpec(name="hypothesis-1", data={"hypothesis_id": "h1"}),
                        BranchSpec(name="hypothesis-2", data={"hypothesis_id": "h2"}),
                    ],
                    merge_step=StepType.SYNTHESIZE,
                    child_start_step=StepType.GENERATE_QUERY,
                ),
            )
        )
        return step

    @pytest.fixture
    def hypothesis_snapshot(
        self,
        sample_snapshot: Snapshot,
        sample_context: InvestigationContext,
    ) -> Snapshot:
        """Create snapshot at GENERATE_HYPOTHESES step."""
        return Snapshot(
            id=sample_snapshot.id,
            investigation_id=sample_snapshot.investigation_id,
            branch_id=sample_snapshot.branch_id,
            version=sample_snapshot.version,
            step=StepType.GENERATE_HYPOTHESES,
            context=sample_context,
        )

    @pytest.fixture
    def branch_registry(self, branch_step: MagicMock) -> StepRegistry:
        """Create registry with branch step."""
        reg = StepRegistry()
        reg.register(branch_step)
        return reg

    @pytest.fixture
    def mock_branch_repository(
        self,
        hypothesis_snapshot: Snapshot,
        sample_branch: Branch,
    ) -> AsyncMock:
        """Create mock repository for branching tests."""
        repo = AsyncMock()
        repo.get_snapshot.return_value = hypothesis_snapshot
        repo.get_branch.return_value = sample_branch

        # Mock create_branch to return new branches with unique IDs
        child_branch_counter = [0]

        async def create_branch_side_effect(
            investigation_id: UUID,
            branch_type: BranchType,
            name: str,
            parent_branch_id: UUID | None = None,
            forked_from_snapshot_id: UUID | None = None,
            owner_user_id: UUID | None = None,
        ) -> Branch:
            child_branch_counter[0] += 1
            return Branch(
                id=uuid4(),
                investigation_id=investigation_id,
                branch_type=branch_type,
                name=name,
                parent_branch_id=parent_branch_id,
                forked_from_snapshot_id=forked_from_snapshot_id,
                status=BranchStatus.ACTIVE,
            )

        repo.create_branch.side_effect = create_branch_side_effect

        # Mock create_snapshot to return new snapshots
        async def create_snapshot_side_effect(
            investigation_id: UUID,
            branch_id: UUID,
            version: VersionId,
            step: StepType,
            context: InvestigationContext,
            parent_snapshot_id: UUID | None = None,
            created_by: UUID | None = None,
            trigger: str = "system",
            step_cursor: dict[str, Any] | None = None,
        ) -> Snapshot:
            return Snapshot(
                id=uuid4(),
                investigation_id=investigation_id,
                branch_id=branch_id,
                version=version,
                step=step,
                context=context,
                parent_snapshot_id=parent_snapshot_id,
                step_cursor=step_cursor or {},
            )

        repo.create_snapshot.side_effect = create_snapshot_side_effect

        return repo

    @pytest.mark.asyncio
    async def test_tick_branch_creates_child_branches(
        self,
        mock_branch_repository: AsyncMock,
        branch_registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() with BRANCH signal creates child branches for each BranchSpec."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_branch_repository,
            registry=branch_registry,
        )

        await orchestrator.tick(sample_branch.id)

        # Should create 2 child branches (one per BranchSpec)
        assert mock_branch_repository.create_branch.call_count == 2

        # Verify branch parameters
        calls = mock_branch_repository.create_branch.call_args_list
        assert calls[0].kwargs["name"] == "hypothesis-1"
        assert calls[0].kwargs["branch_type"] == BranchType.HYPOTHESIS
        assert calls[0].kwargs["parent_branch_id"] == sample_branch.id
        assert calls[1].kwargs["name"] == "hypothesis-2"
        assert calls[1].kwargs["branch_type"] == BranchType.HYPOTHESIS

    @pytest.mark.asyncio
    async def test_tick_branch_creates_child_snapshots(
        self,
        mock_branch_repository: AsyncMock,
        branch_registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() with BRANCH signal creates initial snapshot for each child branch."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_branch_repository,
            registry=branch_registry,
        )

        await orchestrator.tick(sample_branch.id)

        # Should create snapshots for child branches (at child_start_step)
        # Find calls with GENERATE_QUERY step (child snapshots)
        snapshot_calls = [
            call
            for call in mock_branch_repository.create_snapshot.call_args_list
            if call.kwargs.get("step") == StepType.GENERATE_QUERY
        ]
        assert len(snapshot_calls) == 2

    @pytest.mark.asyncio
    async def test_tick_branch_sets_merge_point(
        self,
        mock_branch_repository: AsyncMock,
        branch_registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() with BRANCH signal sets merge point on parent branch."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_branch_repository,
            registry=branch_registry,
        )

        await orchestrator.tick(sample_branch.id)

        mock_branch_repository.set_merge_point.assert_called_once()
        call_kwargs = mock_branch_repository.set_merge_point.call_args.kwargs
        assert call_kwargs["parent_branch_id"] == sample_branch.id
        assert len(call_kwargs["child_branch_ids"]) == 2
        assert call_kwargs["merge_step"] == StepType.SYNTHESIZE

    @pytest.mark.asyncio
    async def test_tick_branch_suspends_parent(
        self,
        mock_branch_repository: AsyncMock,
        branch_registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() with BRANCH signal suspends parent branch."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_branch_repository,
            registry=branch_registry,
        )

        await orchestrator.tick(sample_branch.id)

        mock_branch_repository.update_branch_status.assert_called_once_with(
            sample_branch.id,
            BranchStatus.SUSPENDED,
        )

    @pytest.mark.asyncio
    async def test_tick_branch_returns_child_ids(
        self,
        mock_branch_repository: AsyncMock,
        branch_registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() with BRANCH signal returns child branch IDs in result."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_branch_repository,
            registry=branch_registry,
        )

        result = await orchestrator.tick(sample_branch.id)

        assert result.signal == ExecutionSignal.BRANCH
        assert result.child_branch_ids is not None
        assert len(result.child_branch_ids) == 2

    @pytest.mark.asyncio
    async def test_tick_branch_fails_without_branch_request(
        self,
        mock_branch_repository: AsyncMock,
        sample_branch: Branch,
        sample_context: InvestigationContext,
    ) -> None:
        """tick() with BRANCH signal fails if no branch_request provided."""
        # Create step that returns BRANCH but no branch_request
        bad_branch_step = MagicMock(spec=Step)
        bad_branch_step.step_type = StepType.GENERATE_HYPOTHESES
        bad_branch_step.can_execute.return_value = True
        bad_branch_step.execute = AsyncMock(
            return_value=StepResult(
                context=sample_context,
                signal=ExecutionSignal.BRANCH,
                branch_request=None,  # Missing!
            )
        )

        registry = StepRegistry()
        registry.register(bad_branch_step)

        # Update snapshot step type to match
        hypothesis_snapshot = Snapshot(
            id=uuid4(),
            investigation_id=sample_branch.investigation_id,
            branch_id=sample_branch.id,
            version=VersionId(major=1, minor=0, patch=0),
            step=StepType.GENERATE_HYPOTHESES,
            context=sample_context,
        )
        mock_branch_repository.get_snapshot.return_value = hypothesis_snapshot

        orchestrator = InvestigationOrchestrator(
            repository=mock_branch_repository,
            registry=registry,
        )

        result = await orchestrator.tick(sample_branch.id)

        assert result.signal == ExecutionSignal.FAIL
        assert "branch_request" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_tick_branch_updates_child_branch_heads(
        self,
        mock_branch_repository: AsyncMock,
        branch_registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() with BRANCH signal updates head for each child branch."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_branch_repository,
            registry=branch_registry,
        )

        await orchestrator.tick(sample_branch.id)

        # Should update branch head: once for parent (with updated context) + once per child
        # Parent head is updated to preserve context (e.g., hypotheses) before creating children
        assert mock_branch_repository.update_branch_head.call_count == 3

    @pytest.mark.asyncio
    async def test_tick_branch_uses_default_child_start_step(
        self,
        mock_branch_repository: AsyncMock,
        sample_branch: Branch,
        sample_context: InvestigationContext,
    ) -> None:
        """tick() with BRANCH signal uses GENERATE_QUERY as default child start step."""
        from dataing.core.investigation.steps.protocol import BranchRequest, BranchSpec

        # Create step with no child_start_step specified
        step = MagicMock(spec=Step)
        step.step_type = StepType.GENERATE_HYPOTHESES
        step.can_execute.return_value = True
        step.execute = AsyncMock(
            return_value=StepResult(
                context=sample_context,
                signal=ExecutionSignal.BRANCH,
                branch_request=BranchRequest(
                    branch_type=BranchType.HYPOTHESIS,
                    branches=[BranchSpec(name="hypothesis-1", data={})],
                    merge_step=StepType.SYNTHESIZE,
                    # child_start_step is None
                ),
            )
        )

        registry = StepRegistry()
        registry.register(step)

        hypothesis_snapshot = Snapshot(
            id=uuid4(),
            investigation_id=sample_branch.investigation_id,
            branch_id=sample_branch.id,
            version=VersionId(major=1, minor=0, patch=0),
            step=StepType.GENERATE_HYPOTHESES,
            context=sample_context,
        )
        mock_branch_repository.get_snapshot.return_value = hypothesis_snapshot

        orchestrator = InvestigationOrchestrator(
            repository=mock_branch_repository,
            registry=registry,
        )

        await orchestrator.tick(sample_branch.id)

        # Child snapshot should be at GENERATE_QUERY (default)
        snapshot_calls = mock_branch_repository.create_snapshot.call_args_list
        assert any(
            call.kwargs.get("step") == StepType.GENERATE_QUERY for call in snapshot_calls
        )

    @pytest.mark.asyncio
    async def test_tick_branch_stores_branch_data_in_step_cursor(
        self,
        mock_branch_repository: AsyncMock,
        branch_registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() with BRANCH signal stores BranchSpec data in snapshot step_cursor."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_branch_repository,
            registry=branch_registry,
        )

        await orchestrator.tick(sample_branch.id)

        # Find child snapshot creation calls
        snapshot_calls = [
            call
            for call in mock_branch_repository.create_snapshot.call_args_list
            if call.kwargs.get("step") == StepType.GENERATE_QUERY
        ]

        # Verify step_cursor contains branch data
        step_cursors = [call.kwargs.get("step_cursor", {}) for call in snapshot_calls]
        hypothesis_ids = [cursor.get("hypothesis_id") for cursor in step_cursors]
        assert "h1" in hypothesis_ids or "h2" in hypothesis_ids


class TestOrchestratorAwaitUser:
    """Tests for orchestrator AWAIT_USER signal handling."""

    @pytest.fixture
    def await_user_step(self, sample_context: InvestigationContext) -> MagicMock:
        """Create mock step that returns AWAIT_USER signal."""
        step = MagicMock(spec=Step)
        step.step_type = StepType.CLASSIFY_INTENT
        step.can_execute.return_value = True
        step.execute = AsyncMock(
            return_value=StepResult(
                context=sample_context,
                signal=ExecutionSignal.AWAIT_USER,
                output={"clarification": "The root cause is..."},
                next_step=StepType.AWAIT_USER,
            )
        )
        return step

    @pytest.fixture
    def await_user_snapshot(
        self,
        sample_snapshot: Snapshot,
        sample_context: InvestigationContext,
    ) -> Snapshot:
        """Create snapshot at CLASSIFY_INTENT step."""
        return Snapshot(
            id=sample_snapshot.id,
            investigation_id=sample_snapshot.investigation_id,
            branch_id=sample_snapshot.branch_id,
            version=sample_snapshot.version,
            step=StepType.CLASSIFY_INTENT,
            context=sample_context,
        )

    @pytest.fixture
    def await_user_registry(self, await_user_step: MagicMock) -> StepRegistry:
        """Create registry with await_user step."""
        reg = StepRegistry()
        reg.register(await_user_step)
        return reg

    @pytest.fixture
    def mock_await_user_repository(
        self,
        await_user_snapshot: Snapshot,
        sample_branch: Branch,
    ) -> AsyncMock:
        """Create mock repository for await_user tests."""
        repo = AsyncMock()
        repo.get_snapshot.return_value = await_user_snapshot
        repo.get_branch.return_value = sample_branch
        repo.create_snapshot.return_value = await_user_snapshot
        return repo

    @pytest.mark.asyncio
    async def test_tick_await_user_suspends_branch(
        self,
        mock_await_user_repository: AsyncMock,
        await_user_registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() with AWAIT_USER signal suspends the branch."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_await_user_repository,
            registry=await_user_registry,
        )

        await orchestrator.tick(sample_branch.id)

        mock_await_user_repository.update_branch_status.assert_called_once_with(
            sample_branch.id,
            BranchStatus.SUSPENDED,
        )

    @pytest.mark.asyncio
    async def test_tick_await_user_creates_snapshot(
        self,
        mock_await_user_repository: AsyncMock,
        await_user_registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() with AWAIT_USER signal creates a snapshot at AWAIT_USER step."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_await_user_repository,
            registry=await_user_registry,
        )

        await orchestrator.tick(sample_branch.id)

        # Should create snapshot at AWAIT_USER step
        mock_await_user_repository.create_snapshot.assert_called_once()
        call_kwargs = mock_await_user_repository.create_snapshot.call_args.kwargs
        assert call_kwargs["step"] == StepType.AWAIT_USER

    @pytest.mark.asyncio
    async def test_tick_await_user_returns_signal(
        self,
        mock_await_user_repository: AsyncMock,
        await_user_registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() with AWAIT_USER signal returns the signal in result."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_await_user_repository,
            registry=await_user_registry,
        )

        result = await orchestrator.tick(sample_branch.id)

        assert result.signal == ExecutionSignal.AWAIT_USER
        assert result.output == {"clarification": "The root cause is..."}

    @pytest.mark.asyncio
    async def test_tick_await_user_updates_branch_head(
        self,
        mock_await_user_repository: AsyncMock,
        await_user_registry: StepRegistry,
        sample_branch: Branch,
    ) -> None:
        """tick() with AWAIT_USER signal updates the branch head."""
        orchestrator = InvestigationOrchestrator(
            repository=mock_await_user_repository,
            registry=await_user_registry,
        )

        await orchestrator.tick(sample_branch.id)

        mock_await_user_repository.update_branch_head.assert_called_once()
