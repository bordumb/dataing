"""Tests for new investigation orchestrator."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

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
