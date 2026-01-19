"""Tests for InvestigationService."""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.investigation.collaboration import CollaborationService
from dataing.core.investigation.entities import (
    Branch,
    Investigation,
    InvestigationContext,
    Snapshot,
)
from dataing.core.investigation.service import InvestigationService
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
        dataset_ids=["analytics.events"],
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
        status=BranchStatus.ACTIVE,
    )


@pytest.fixture
def sample_snapshot(
    head_snapshot_id: UUID,
    investigation_id: UUID,
    main_branch_id: UUID,
) -> Snapshot:
    """Create sample snapshot."""
    return Snapshot(
        id=head_snapshot_id,
        investigation_id=investigation_id,
        branch_id=main_branch_id,
        version=VersionId(),
        step=StepType.GATHER_CONTEXT,
        context=InvestigationContext(
            alert_summary="NULL rate spike in analytics.events",
        ),
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
        status=BranchStatus.SUSPENDED,
    )


@pytest.fixture
def mock_repository(
    sample_investigation: Investigation,
    sample_main_branch: Branch,
    sample_snapshot: Snapshot,
) -> AsyncMock:
    """Create mock repository."""
    repo = AsyncMock()
    repo.create_investigation.return_value = sample_investigation
    repo.get_investigation.return_value = sample_investigation
    repo.create_branch.return_value = sample_main_branch
    repo.get_branch.return_value = sample_main_branch
    repo.create_snapshot.return_value = sample_snapshot
    repo.get_snapshot.return_value = sample_snapshot
    repo.get_user_branch.return_value = None
    return repo


@pytest.fixture
def mock_agent_client() -> AsyncMock:
    """Create mock agent client."""
    return AsyncMock()


@pytest.fixture
def mock_context_engine() -> AsyncMock:
    """Create mock context engine."""
    return AsyncMock()


@pytest.fixture
def mock_pattern_repository() -> AsyncMock:
    """Create mock pattern repository."""
    return AsyncMock()


@pytest.fixture
def mock_data_adapter() -> AsyncMock:
    """Create mock data adapter."""
    adapter = AsyncMock()
    adapter.execute_query = AsyncMock(return_value={"columns": [], "rows": [], "row_count": 0})
    return adapter


@pytest.fixture
def mock_collaboration() -> AsyncMock:
    """Create mock collaboration service."""
    return AsyncMock(spec=CollaborationService)


@pytest.fixture
def mock_app_db() -> AsyncMock:
    """Create mock app database for job creation."""
    db = AsyncMock()
    db.create_investigation_job.return_value = {"id": uuid4()}
    return db


class TestInvestigationServiceStartInvestigation:
    """Tests for InvestigationService.start_investigation."""

    @pytest.mark.asyncio
    async def test_creates_investigation(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        mock_app_db: AsyncMock,
        tenant_id: UUID,
        user_id: UUID,
        sample_alert: AnomalyAlert,
    ) -> None:
        """Creates a new investigation record."""
        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
            app_db=mock_app_db,
        )

        await service.start_investigation(
            tenant_id=tenant_id,
            alert=sample_alert,
            data_adapter=mock_data_adapter,
            user_id=user_id,
        )

        mock_repository.create_investigation.assert_called_once()
        call_kwargs = mock_repository.create_investigation.call_args.kwargs
        assert call_kwargs["tenant_id"] == tenant_id
        assert call_kwargs["created_by"] == user_id

    @pytest.mark.asyncio
    async def test_creates_main_branch(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        mock_app_db: AsyncMock,
        tenant_id: UUID,
        user_id: UUID,
        sample_alert: AnomalyAlert,
        sample_investigation: Investigation,
    ) -> None:
        """Creates main branch for investigation."""
        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
            app_db=mock_app_db,
        )

        await service.start_investigation(
            tenant_id=tenant_id,
            alert=sample_alert,
            data_adapter=mock_data_adapter,
            user_id=user_id,
        )

        mock_repository.create_branch.assert_called_once()
        call_kwargs = mock_repository.create_branch.call_args.kwargs
        assert call_kwargs["investigation_id"] == sample_investigation.id
        assert call_kwargs["branch_type"] == BranchType.MAIN
        assert call_kwargs["name"] == "main"

    @pytest.mark.asyncio
    async def test_sets_main_branch_on_investigation(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        mock_app_db: AsyncMock,
        tenant_id: UUID,
        user_id: UUID,
        sample_alert: AnomalyAlert,
        sample_investigation: Investigation,
        sample_main_branch: Branch,
    ) -> None:
        """Sets main branch ID on investigation."""
        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
            app_db=mock_app_db,
        )

        await service.start_investigation(
            tenant_id=tenant_id,
            alert=sample_alert,
            data_adapter=mock_data_adapter,
            user_id=user_id,
        )

        mock_repository.set_main_branch.assert_called_once_with(
            sample_investigation.id, sample_main_branch.id
        )

    @pytest.mark.asyncio
    async def test_creates_initial_snapshot(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        mock_app_db: AsyncMock,
        tenant_id: UUID,
        user_id: UUID,
        sample_alert: AnomalyAlert,
        sample_investigation: Investigation,
        sample_main_branch: Branch,
    ) -> None:
        """Creates initial snapshot at GATHER_CONTEXT step."""
        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
            app_db=mock_app_db,
        )

        await service.start_investigation(
            tenant_id=tenant_id,
            alert=sample_alert,
            data_adapter=mock_data_adapter,
            user_id=user_id,
        )

        mock_repository.create_snapshot.assert_called_once()
        call_kwargs = mock_repository.create_snapshot.call_args.kwargs
        assert call_kwargs["investigation_id"] == sample_investigation.id
        assert call_kwargs["branch_id"] == sample_main_branch.id
        assert call_kwargs["step"] == StepType.GATHER_CONTEXT
        assert call_kwargs["created_by"] == user_id
        assert call_kwargs["trigger"] == "user"

    @pytest.mark.asyncio
    async def test_updates_branch_head(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        mock_app_db: AsyncMock,
        tenant_id: UUID,
        user_id: UUID,
        sample_alert: AnomalyAlert,
        sample_main_branch: Branch,
        sample_snapshot: Snapshot,
    ) -> None:
        """Updates branch head to point to initial snapshot."""
        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
            app_db=mock_app_db,
        )

        await service.start_investigation(
            tenant_id=tenant_id,
            alert=sample_alert,
            data_adapter=mock_data_adapter,
            user_id=user_id,
        )

        mock_repository.update_branch_head.assert_called_once_with(
            sample_main_branch.id, sample_snapshot.id
        )

    @pytest.mark.asyncio
    async def test_returns_investigation_and_branch_ids(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        mock_app_db: AsyncMock,
        tenant_id: UUID,
        user_id: UUID,
        sample_alert: AnomalyAlert,
        sample_investigation: Investigation,
        sample_main_branch: Branch,
    ) -> None:
        """Returns investigation ID and main branch ID."""
        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
            app_db=mock_app_db,
        )

        investigation_id, branch_id, status = await service.start_investigation(
            tenant_id=tenant_id,
            alert=sample_alert,
            data_adapter=mock_data_adapter,
            user_id=user_id,
        )

        assert investigation_id == sample_investigation.id
        assert branch_id == sample_main_branch.id
        assert status == "created"

    @pytest.mark.asyncio
    async def test_works_without_user_id(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        mock_app_db: AsyncMock,
        tenant_id: UUID,
        sample_alert: AnomalyAlert,
    ) -> None:
        """Allows starting investigation without user ID (API key auth)."""
        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
            app_db=mock_app_db,
        )

        investigation_id, branch_id, status = await service.start_investigation(
            tenant_id=tenant_id,
            alert=sample_alert,
            data_adapter=mock_data_adapter,
            user_id=None,
        )

        assert investigation_id is not None
        assert branch_id is not None
        assert status == "created"
        call_kwargs = mock_repository.create_investigation.call_args.kwargs
        assert call_kwargs["created_by"] is None


class TestInvestigationServiceGetState:
    """Tests for InvestigationService.get_state."""

    @pytest.mark.asyncio
    async def test_returns_investigation_state(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        investigation_id: UUID,
        user_id: UUID,
        sample_investigation: Investigation,
        sample_main_branch: Branch,
        sample_snapshot: Snapshot,
    ) -> None:
        """Returns investigation state with main branch."""
        mock_repository.get_investigation.return_value = sample_investigation
        mock_repository.get_branch.return_value = sample_main_branch
        mock_repository.get_snapshot.return_value = sample_snapshot
        mock_repository.get_user_branch.return_value = None

        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
        )

        state = await service.get_state(
            investigation_id=investigation_id,
            user_id=user_id,
        )

        assert state.investigation_id == sample_investigation.id
        assert state.main_branch is not None
        assert state.main_branch.branch_id == sample_main_branch.id

    @pytest.mark.asyncio
    async def test_includes_user_branch_if_exists(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        investigation_id: UUID,
        user_id: UUID,
        sample_investigation: Investigation,
        sample_main_branch: Branch,
        sample_snapshot: Snapshot,
        sample_user_branch: Branch,
    ) -> None:
        """Includes user branch if one exists."""
        mock_repository.get_investigation.return_value = sample_investigation
        mock_repository.get_branch.side_effect = [
            sample_main_branch,
            sample_user_branch,
        ]
        mock_repository.get_snapshot.return_value = sample_snapshot
        mock_repository.get_user_branch.return_value = sample_user_branch

        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
        )

        state = await service.get_state(
            investigation_id=investigation_id,
            user_id=user_id,
        )

        assert state.user_branch is not None
        assert state.user_branch.branch_id == sample_user_branch.id

    @pytest.mark.asyncio
    async def test_raises_when_investigation_not_found(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        user_id: UUID,
    ) -> None:
        """Raises error when investigation not found."""
        mock_repository.get_investigation.return_value = None

        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
        )

        with pytest.raises(ValueError, match="Investigation not found"):
            await service.get_state(
                investigation_id=uuid4(),
                user_id=user_id,
            )


class TestInvestigationServiceSendMessage:
    """Tests for InvestigationService.send_message."""

    @pytest.mark.asyncio
    async def test_gets_or_creates_user_branch(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        investigation_id: UUID,
        user_id: UUID,
        sample_user_branch: Branch,
    ) -> None:
        """Gets or creates user branch for message."""
        mock_collaboration.get_or_create_user_branch.return_value = sample_user_branch

        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
        )

        await service.send_message(
            investigation_id=investigation_id,
            user_id=user_id,
            message="Can you investigate upstream?",
        )

        mock_collaboration.get_or_create_user_branch.assert_called_once_with(
            investigation_id, user_id
        )

    @pytest.mark.asyncio
    async def test_adds_message_to_branch(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        investigation_id: UUID,
        user_id: UUID,
        sample_user_branch: Branch,
    ) -> None:
        """Adds user message to the branch."""
        mock_collaboration.get_or_create_user_branch.return_value = sample_user_branch
        message = "Can you investigate upstream?"

        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
        )

        await service.send_message(
            investigation_id=investigation_id,
            user_id=user_id,
            message=message,
        )

        mock_collaboration.send_message.assert_called_once_with(
            sample_user_branch.id, user_id, message
        )

    @pytest.mark.asyncio
    async def test_resumes_suspended_branch(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        investigation_id: UUID,
        user_id: UUID,
        sample_user_branch: Branch,
    ) -> None:
        """Resumes branch if it was suspended."""
        # sample_user_branch has status=SUSPENDED
        mock_collaboration.get_or_create_user_branch.return_value = sample_user_branch

        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
        )

        await service.send_message(
            investigation_id=investigation_id,
            user_id=user_id,
            message="Continue investigating",
        )

        mock_collaboration.resume_branch.assert_called_once_with(sample_user_branch.id)

    @pytest.mark.asyncio
    async def test_does_not_resume_active_branch(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        investigation_id: UUID,
        user_id: UUID,
        sample_user_branch: Branch,
    ) -> None:
        """Does not resume branch if already active."""
        active_branch = Branch(
            id=sample_user_branch.id,
            investigation_id=investigation_id,
            branch_type=BranchType.USER,
            name=f"user_{user_id}",
            status=BranchStatus.ACTIVE,
        )
        mock_collaboration.get_or_create_user_branch.return_value = active_branch

        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
        )

        await service.send_message(
            investigation_id=investigation_id,
            user_id=user_id,
            message="Message to active branch",
        )

        mock_collaboration.resume_branch.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_branch_id(
        self,
        mock_repository: AsyncMock,
        mock_agent_client: AsyncMock,
        mock_context_engine: AsyncMock,
        mock_pattern_repository: AsyncMock,
        mock_data_adapter: AsyncMock,
        mock_collaboration: AsyncMock,
        investigation_id: UUID,
        user_id: UUID,
        sample_user_branch: Branch,
    ) -> None:
        """Returns the branch ID after sending message."""
        mock_collaboration.get_or_create_user_branch.return_value = sample_user_branch

        service = InvestigationService(
            repository=mock_repository,
            collaboration=mock_collaboration,
            agent_client=mock_agent_client,
            context_engine=mock_context_engine,
            pattern_repository=mock_pattern_repository,
        )

        branch_id = await service.send_message(
            investigation_id=investigation_id,
            user_id=user_id,
            message="Test message",
        )

        assert branch_id == sample_user_branch.id
