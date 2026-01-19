"""Tests for CollaborationService."""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.investigation.collaboration import CollaborationService
from dataing.core.investigation.entities import Branch, Investigation, Snapshot
from dataing.core.investigation.values import (
    BranchStatus,
    BranchType,
    StepType,
    VersionId,
)


@pytest.fixture
def tenant_id() -> UUID:
    """Return a tenant ID."""
    return uuid4()


@pytest.fixture
def user_id() -> UUID:
    """Return a user ID."""
    return uuid4()


@pytest.fixture
def investigation_id() -> UUID:
    """Return an investigation ID."""
    return uuid4()


@pytest.fixture
def main_branch_id() -> UUID:
    """Return a main branch ID."""
    return uuid4()


@pytest.fixture
def head_snapshot_id() -> UUID:
    """Return a head snapshot ID."""
    return uuid4()


@pytest.fixture
def sample_alert() -> AnomalyAlert:
    """Create a sample anomaly alert."""
    return AnomalyAlert(
        dataset_id="analytics.events",
        metric_spec=MetricSpec.from_column("user_id", "NULL rate"),
        anomaly_type="null_rate",
        expected_value=0.01,
        actual_value=0.15,
        deviation_pct=1400.0,
        anomaly_date="2026-01-10",
        severity="high",
    )


@pytest.fixture
def sample_investigation(
    investigation_id: UUID,
    tenant_id: UUID,
    main_branch_id: UUID,
    sample_alert: AnomalyAlert,
) -> Investigation:
    """Create sample investigation."""
    return Investigation(
        id=investigation_id,
        tenant_id=tenant_id,
        alert=sample_alert,
        main_branch_id=main_branch_id,
    )


@pytest.fixture
def sample_main_branch(
    main_branch_id: UUID,
    investigation_id: UUID,
    head_snapshot_id: UUID,
) -> Branch:
    """Create sample main branch."""
    return Branch(
        id=main_branch_id,
        investigation_id=investigation_id,
        branch_type=BranchType.MAIN,
        name="main",
        head_snapshot_id=head_snapshot_id,
        status=BranchStatus.SUSPENDED,
    )


@pytest.fixture
def sample_user_branch(
    investigation_id: UUID,
    user_id: UUID,
    main_branch_id: UUID,
    head_snapshot_id: UUID,
) -> Branch:
    """Create sample user branch."""
    return Branch(
        id=uuid4(),
        investigation_id=investigation_id,
        branch_type=BranchType.USER,
        name=f"user_{user_id}",
        parent_branch_id=main_branch_id,
        forked_from_snapshot_id=head_snapshot_id,
        owner_user_id=user_id,
        head_snapshot_id=head_snapshot_id,
        status=BranchStatus.ACTIVE,
    )


@pytest.fixture
def mock_repository(
    sample_investigation: Investigation,
    sample_main_branch: Branch,
) -> AsyncMock:
    """Create mock repository."""
    repo = AsyncMock()
    repo.get_investigation.return_value = sample_investigation
    repo.get_branch.return_value = sample_main_branch
    repo.get_user_branch.return_value = None  # No existing user branch by default
    return repo


class TestCollaborationServiceGetOrCreateUserBranch:
    """Tests for CollaborationService.get_or_create_user_branch."""

    @pytest.mark.asyncio
    async def test_returns_existing_user_branch(
        self,
        mock_repository: AsyncMock,
        investigation_id: UUID,
        user_id: UUID,
        sample_user_branch: Branch,
    ) -> None:
        """Returns existing user branch if one exists."""
        mock_repository.get_user_branch.return_value = sample_user_branch

        service = CollaborationService(repository=mock_repository)
        result = await service.get_or_create_user_branch(
            investigation_id=investigation_id,
            user_id=user_id,
        )

        assert result == sample_user_branch
        mock_repository.create_branch.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_new_branch_when_none_exists(
        self,
        mock_repository: AsyncMock,
        investigation_id: UUID,
        user_id: UUID,
        sample_main_branch: Branch,
    ) -> None:
        """Creates new user branch forked from main when none exists."""
        mock_repository.get_user_branch.return_value = None
        created_branch = Branch(
            id=uuid4(),
            investigation_id=investigation_id,
            branch_type=BranchType.USER,
            name=f"user_{user_id}",
            parent_branch_id=sample_main_branch.id,
            forked_from_snapshot_id=sample_main_branch.head_snapshot_id,
            owner_user_id=user_id,
            status=BranchStatus.ACTIVE,
        )
        mock_repository.create_branch.return_value = created_branch

        service = CollaborationService(repository=mock_repository)
        result = await service.get_or_create_user_branch(
            investigation_id=investigation_id,
            user_id=user_id,
        )

        assert result == created_branch
        mock_repository.create_branch.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_branch_with_correct_parameters(
        self,
        mock_repository: AsyncMock,
        investigation_id: UUID,
        user_id: UUID,
        sample_main_branch: Branch,
    ) -> None:
        """Creates branch with correct parameters from main branch."""
        mock_repository.get_user_branch.return_value = None
        mock_repository.create_branch.return_value = Branch(
            id=uuid4(),
            investigation_id=investigation_id,
            branch_type=BranchType.USER,
            name=f"user_{user_id}",
            status=BranchStatus.ACTIVE,
        )

        service = CollaborationService(repository=mock_repository)
        await service.get_or_create_user_branch(
            investigation_id=investigation_id,
            user_id=user_id,
        )

        mock_repository.create_branch.assert_called_once_with(
            investigation_id=investigation_id,
            branch_type=BranchType.USER,
            name=f"user_{user_id}",
            parent_branch_id=sample_main_branch.id,
            forked_from_snapshot_id=sample_main_branch.head_snapshot_id,
            owner_user_id=user_id,
        )

    @pytest.mark.asyncio
    async def test_raises_when_investigation_not_found(
        self,
        mock_repository: AsyncMock,
        user_id: UUID,
    ) -> None:
        """Raises error when investigation not found."""
        mock_repository.get_investigation.return_value = None

        service = CollaborationService(repository=mock_repository)

        with pytest.raises(ValueError, match="Investigation not found"):
            await service.get_or_create_user_branch(
                investigation_id=uuid4(),
                user_id=user_id,
            )

    @pytest.mark.asyncio
    async def test_raises_when_main_branch_not_found(
        self,
        mock_repository: AsyncMock,
        investigation_id: UUID,
        user_id: UUID,
        sample_investigation: Investigation,
    ) -> None:
        """Raises error when main branch not found."""
        mock_repository.get_investigation.return_value = sample_investigation
        mock_repository.get_branch.return_value = None

        service = CollaborationService(repository=mock_repository)

        with pytest.raises(ValueError, match="Main branch not found"):
            await service.get_or_create_user_branch(
                investigation_id=investigation_id,
                user_id=user_id,
            )

    @pytest.mark.asyncio
    async def test_raises_when_no_main_branch_id(
        self,
        mock_repository: AsyncMock,
        investigation_id: UUID,
        tenant_id: UUID,
        user_id: UUID,
        sample_alert: AnomalyAlert,
    ) -> None:
        """Raises error when investigation has no main branch set."""
        investigation_no_main = Investigation(
            id=investigation_id,
            tenant_id=tenant_id,
            alert=sample_alert,
            main_branch_id=None,
        )
        mock_repository.get_investigation.return_value = investigation_no_main

        service = CollaborationService(repository=mock_repository)

        with pytest.raises(ValueError, match="Investigation has no main branch"):
            await service.get_or_create_user_branch(
                investigation_id=investigation_id,
                user_id=user_id,
            )


class TestCollaborationServiceSendMessage:
    """Tests for CollaborationService.send_message."""

    @pytest.mark.asyncio
    async def test_adds_message_to_branch(
        self,
        mock_repository: AsyncMock,
        user_id: UUID,
    ) -> None:
        """Adds message to the branch."""
        branch_id = uuid4()
        message = "Can you investigate the upstream ETL?"
        message_id = uuid4()
        mock_repository.add_message.return_value = message_id

        service = CollaborationService(repository=mock_repository)
        result = await service.send_message(
            branch_id=branch_id,
            user_id=user_id,
            message=message,
        )

        assert result == message_id
        mock_repository.add_message.assert_called_once_with(
            branch_id=branch_id,
            role="user",
            content=message,
            user_id=user_id,
        )

    @pytest.mark.asyncio
    async def test_send_message_returns_message_id(
        self,
        mock_repository: AsyncMock,
        user_id: UUID,
    ) -> None:
        """Returns the message ID from the repository."""
        branch_id = uuid4()
        expected_id = uuid4()
        mock_repository.add_message.return_value = expected_id

        service = CollaborationService(repository=mock_repository)
        result = await service.send_message(
            branch_id=branch_id,
            user_id=user_id,
            message="Test message",
        )

        assert result == expected_id


class TestCollaborationServiceResumeBranch:
    """Tests for CollaborationService.resume_branch."""

    @pytest.mark.asyncio
    async def test_updates_branch_status_to_active(
        self,
        mock_repository: AsyncMock,
    ) -> None:
        """Resume sets branch status to ACTIVE."""
        branch_id = uuid4()
        suspended_branch = Branch(
            id=branch_id,
            investigation_id=uuid4(),
            branch_type=BranchType.USER,
            name="user_test",
            status=BranchStatus.SUSPENDED,
        )
        mock_repository.get_branch.return_value = suspended_branch

        service = CollaborationService(repository=mock_repository)
        await service.resume_branch(branch_id=branch_id)

        mock_repository.update_branch_status.assert_called_once_with(branch_id, BranchStatus.ACTIVE)

    @pytest.mark.asyncio
    async def test_raises_when_branch_not_found(
        self,
        mock_repository: AsyncMock,
    ) -> None:
        """Raises error when branch not found."""
        mock_repository.get_branch.return_value = None

        service = CollaborationService(repository=mock_repository)

        with pytest.raises(ValueError, match="Branch not found"):
            await service.resume_branch(branch_id=uuid4())

    @pytest.mark.asyncio
    async def test_raises_when_branch_not_suspended(
        self,
        mock_repository: AsyncMock,
    ) -> None:
        """Raises error when branch is not in SUSPENDED or COMPLETED state."""
        branch_id = uuid4()
        active_branch = Branch(
            id=branch_id,
            investigation_id=uuid4(),
            branch_type=BranchType.USER,
            name="user_test",
            status=BranchStatus.ACTIVE,
        )
        mock_repository.get_branch.return_value = active_branch

        service = CollaborationService(repository=mock_repository)

        with pytest.raises(ValueError, match="Branch cannot accept input"):
            await service.resume_branch(branch_id=branch_id)

    @pytest.mark.asyncio
    async def test_allows_resume_from_completed(
        self,
        mock_repository: AsyncMock,
    ) -> None:
        """Allows resuming from COMPLETED state."""
        branch_id = uuid4()
        completed_branch = Branch(
            id=branch_id,
            investigation_id=uuid4(),
            branch_type=BranchType.USER,
            name="user_test",
            status=BranchStatus.COMPLETED,
        )
        mock_repository.get_branch.return_value = completed_branch

        service = CollaborationService(repository=mock_repository)
        await service.resume_branch(branch_id=branch_id)

        mock_repository.update_branch_status.assert_called_once_with(branch_id, BranchStatus.ACTIVE)


class TestCollaborationServiceCreateInitialSnapshot:
    """Tests for CollaborationService.create_initial_snapshot_for_user_branch."""

    @pytest.fixture
    def parent_snapshot(self, head_snapshot_id: UUID, investigation_id: UUID) -> Snapshot:
        """Create parent snapshot."""
        from dataing.core.investigation.entities import InvestigationContext

        return Snapshot(
            id=head_snapshot_id,
            investigation_id=investigation_id,
            branch_id=uuid4(),
            version=VersionId(major=1, minor=0, patch=0),
            step=StepType.AWAIT_USER,
            context=InvestigationContext(
                alert_summary="Test anomaly",
                current_synthesis={"root_cause": "Test cause", "confidence": 0.9},
            ),
        )

    @pytest.mark.asyncio
    async def test_creates_snapshot_from_parent(
        self,
        mock_repository: AsyncMock,
        sample_user_branch: Branch,
        parent_snapshot: Snapshot,
    ) -> None:
        """Creates initial snapshot for user branch from forked snapshot."""
        mock_repository.get_branch.return_value = sample_user_branch
        mock_repository.get_snapshot.return_value = parent_snapshot
        expected_snapshot = Snapshot(
            id=uuid4(),
            investigation_id=parent_snapshot.investigation_id,
            branch_id=sample_user_branch.id,
            version=VersionId(major=1, minor=0, patch=1),
            step=StepType.CLASSIFY_INTENT,
            context=parent_snapshot.context,
        )
        mock_repository.create_snapshot.return_value = expected_snapshot

        service = CollaborationService(repository=mock_repository)
        result = await service.create_initial_snapshot_for_user_branch(
            branch_id=sample_user_branch.id,
            user_message="Can you look at upstream ETL?",
        )

        assert result == expected_snapshot

    @pytest.mark.asyncio
    async def test_creates_snapshot_at_classify_intent_step(
        self,
        mock_repository: AsyncMock,
        sample_user_branch: Branch,
        parent_snapshot: Snapshot,
    ) -> None:
        """Creates snapshot at CLASSIFY_INTENT step."""
        mock_repository.get_branch.return_value = sample_user_branch
        mock_repository.get_snapshot.return_value = parent_snapshot
        mock_repository.create_snapshot.return_value = Snapshot(
            id=uuid4(),
            investigation_id=parent_snapshot.investigation_id,
            branch_id=sample_user_branch.id,
            version=VersionId(major=1, minor=0, patch=1),
            step=StepType.CLASSIFY_INTENT,
            context=parent_snapshot.context,
        )

        service = CollaborationService(repository=mock_repository)
        await service.create_initial_snapshot_for_user_branch(
            branch_id=sample_user_branch.id,
            user_message="Test",
        )

        call_kwargs = mock_repository.create_snapshot.call_args.kwargs
        assert call_kwargs["step"] == StepType.CLASSIFY_INTENT

    @pytest.mark.asyncio
    async def test_stores_user_message_in_step_cursor(
        self,
        mock_repository: AsyncMock,
        sample_user_branch: Branch,
        parent_snapshot: Snapshot,
    ) -> None:
        """Stores user message in step_cursor for ClassifyIntentStep."""
        mock_repository.get_branch.return_value = sample_user_branch
        mock_repository.get_snapshot.return_value = parent_snapshot
        mock_repository.create_snapshot.return_value = Snapshot(
            id=uuid4(),
            investigation_id=parent_snapshot.investigation_id,
            branch_id=sample_user_branch.id,
            version=VersionId(major=1, minor=0, patch=1),
            step=StepType.CLASSIFY_INTENT,
            context=parent_snapshot.context,
        )

        user_message = "Can you look at the ETL job?"

        service = CollaborationService(repository=mock_repository)
        await service.create_initial_snapshot_for_user_branch(
            branch_id=sample_user_branch.id,
            user_message=user_message,
        )

        call_kwargs = mock_repository.create_snapshot.call_args.kwargs
        assert call_kwargs["step_cursor"]["user_message"] == user_message

    @pytest.mark.asyncio
    async def test_updates_branch_head(
        self,
        mock_repository: AsyncMock,
        sample_user_branch: Branch,
        parent_snapshot: Snapshot,
    ) -> None:
        """Updates branch head to point to new snapshot."""
        mock_repository.get_branch.return_value = sample_user_branch
        mock_repository.get_snapshot.return_value = parent_snapshot
        new_snapshot = Snapshot(
            id=uuid4(),
            investigation_id=parent_snapshot.investigation_id,
            branch_id=sample_user_branch.id,
            version=VersionId(major=1, minor=0, patch=1),
            step=StepType.CLASSIFY_INTENT,
            context=parent_snapshot.context,
        )
        mock_repository.create_snapshot.return_value = new_snapshot

        service = CollaborationService(repository=mock_repository)
        await service.create_initial_snapshot_for_user_branch(
            branch_id=sample_user_branch.id,
            user_message="Test",
        )

        mock_repository.update_branch_head.assert_called_once_with(
            sample_user_branch.id, new_snapshot.id
        )

    @pytest.mark.asyncio
    async def test_raises_when_branch_not_found(
        self,
        mock_repository: AsyncMock,
    ) -> None:
        """Raises error when branch not found."""
        mock_repository.get_branch.return_value = None

        service = CollaborationService(repository=mock_repository)

        with pytest.raises(ValueError, match="Branch not found"):
            await service.create_initial_snapshot_for_user_branch(
                branch_id=uuid4(),
                user_message="Test",
            )

    @pytest.mark.asyncio
    async def test_raises_when_no_forked_snapshot(
        self,
        mock_repository: AsyncMock,
    ) -> None:
        """Raises error when branch has no forked_from_snapshot_id."""
        branch_no_fork = Branch(
            id=uuid4(),
            investigation_id=uuid4(),
            branch_type=BranchType.USER,
            name="user_test",
            forked_from_snapshot_id=None,
            status=BranchStatus.ACTIVE,
        )
        mock_repository.get_branch.return_value = branch_no_fork

        service = CollaborationService(repository=mock_repository)

        with pytest.raises(ValueError, match="Branch has no forked snapshot"):
            await service.create_initial_snapshot_for_user_branch(
                branch_id=branch_no_fork.id,
                user_message="Test",
            )
