"""Investigation service for coordinating API operations.

This module provides the InvestigationService that coordinates between
the API layer, repository, orchestrator, and collaboration service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from dataing.core.domain_types import AnomalyAlert
    from dataing.core.investigation.collaboration import CollaborationService
    from dataing.core.investigation.orchestrator import InvestigationOrchestrator
    from dataing.core.investigation.repository import InvestigationRepository

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import BranchStatus, BranchType, StepType, VersionId


class BranchState(BaseModel):
    """State of a branch for API responses."""

    model_config = ConfigDict(frozen=True)

    branch_id: UUID
    status: str
    current_step: str
    synthesis: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = []


class InvestigationState(BaseModel):
    """Full investigation state for API responses."""

    model_config = ConfigDict(frozen=True)

    investigation_id: UUID
    status: str
    main_branch: BranchState
    user_branch: BranchState | None = None


class InvestigationService:
    """Service for coordinating investigation operations.

    This service provides the business logic layer between the API
    and the underlying domain services (repository, orchestrator,
    collaboration).
    """

    def __init__(
        self,
        repository: InvestigationRepository,
        orchestrator: InvestigationOrchestrator,
        collaboration: CollaborationService,
    ) -> None:
        """Initialize the investigation service.

        Args:
            repository: Repository for persistence operations.
            orchestrator: Orchestrator for executing investigation steps.
            collaboration: Service for user branch management.
        """
        self.repository = repository
        self.orchestrator = orchestrator
        self.collaboration = collaboration

    async def start_investigation(
        self,
        tenant_id: UUID,
        alert: AnomalyAlert,
        user_id: UUID | None = None,
    ) -> tuple[UUID, UUID]:
        """Start a new investigation for an alert.

        Creates the investigation, main branch, and initial snapshot
        positioned at GATHER_CONTEXT step.

        Args:
            tenant_id: ID of the tenant starting the investigation.
            alert: The anomaly alert triggering this investigation.
            user_id: Optional ID of the user starting the investigation.

        Returns:
            Tuple of (investigation_id, main_branch_id).
        """
        # Create investigation
        investigation = await self.repository.create_investigation(
            tenant_id=tenant_id,
            alert=alert.model_dump(),
            created_by=user_id,
        )

        # Create main branch
        main_branch = await self.repository.create_branch(
            investigation_id=investigation.id,
            branch_type=BranchType.MAIN,
            name="main",
        )

        # Set main branch
        await self.repository.set_main_branch(investigation.id, main_branch.id)

        # Create initial snapshot at GATHER_CONTEXT
        initial_context = InvestigationContext(
            alert_summary=f"{alert.anomaly_type} in {alert.dataset_id}",
        )
        snapshot = await self.repository.create_snapshot(
            investigation_id=investigation.id,
            branch_id=main_branch.id,
            version=VersionId(),
            step=StepType.GATHER_CONTEXT,
            context=initial_context,
            created_by=user_id,
            trigger="user",
        )

        # Update branch head
        await self.repository.update_branch_head(main_branch.id, snapshot.id)

        return investigation.id, main_branch.id

    async def get_state(
        self,
        investigation_id: UUID,
        user_id: UUID,
    ) -> InvestigationState:
        """Get current investigation state.

        Returns the investigation state including main branch and
        optionally the user's branch if one exists.

        Args:
            investigation_id: ID of the investigation.
            user_id: ID of the user requesting state.

        Returns:
            InvestigationState with main and optional user branch.

        Raises:
            ValueError: If investigation not found.
        """
        # Get investigation
        investigation = await self.repository.get_investigation(investigation_id)
        if investigation is None:
            raise ValueError(f"Investigation not found: {investigation_id}")

        if investigation.main_branch_id is None:
            raise ValueError(f"Investigation has no main branch: {investigation_id}")

        # Get main branch state
        main_branch = await self.repository.get_branch(investigation.main_branch_id)
        main_snapshot = None
        if main_branch and main_branch.head_snapshot_id:
            main_snapshot = await self.repository.get_snapshot(
                main_branch.head_snapshot_id
            )

        main_branch_state = self._create_branch_state(main_branch, main_snapshot)

        # Get user branch if exists
        user_branch_state = None
        user_branch = await self.repository.get_user_branch(investigation_id, user_id)
        if user_branch:
            user_snapshot = None
            if user_branch.head_snapshot_id:
                user_snapshot = await self.repository.get_snapshot(
                    user_branch.head_snapshot_id
                )
            user_branch_state = self._create_branch_state(user_branch, user_snapshot)

        # Determine overall status
        status = "active"
        if investigation.outcome:
            status = "completed"
        elif main_branch and main_branch.status == BranchStatus.ABANDONED:
            status = "failed"

        return InvestigationState(
            investigation_id=investigation.id,
            status=status,
            main_branch=main_branch_state,
            user_branch=user_branch_state,
        )

    async def send_message(
        self,
        investigation_id: UUID,
        user_id: UUID,
        message: str,
    ) -> UUID:
        """Send a message to the user's branch.

        Gets or creates a user branch if one doesn't exist, then adds
        the message. Resumes the branch if it was suspended.

        Args:
            investigation_id: ID of the investigation.
            user_id: ID of the user sending the message.
            message: The message content.

        Returns:
            The branch ID that received the message.
        """
        # Get or create user branch
        branch = await self.collaboration.get_or_create_user_branch(
            investigation_id, user_id
        )

        # Add message
        await self.collaboration.send_message(branch.id, user_id, message)

        # Resume branch if suspended
        if branch.status == BranchStatus.SUSPENDED:
            await self.collaboration.resume_branch(branch.id)

        return branch.id

    def _create_branch_state(
        self,
        branch: Any,
        snapshot: Any,
    ) -> BranchState:
        """Create BranchState from branch and snapshot.

        Args:
            branch: The branch entity.
            snapshot: The current snapshot (may be None).

        Returns:
            BranchState for API response.
        """
        if branch is None:
            return BranchState(
                branch_id=UUID("00000000-0000-0000-0000-000000000000"),
                status="unknown",
                current_step="unknown",
            )

        current_step = "unknown"
        synthesis = None
        evidence: list[dict[str, Any]] = []

        if snapshot:
            current_step = snapshot.step.value
            if snapshot.context.current_synthesis:
                synthesis = snapshot.context.current_synthesis
            evidence = snapshot.context.evidence

        return BranchState(
            branch_id=branch.id,
            status=branch.status.value,
            current_step=current_step,
            synthesis=synthesis,
            evidence=evidence,
        )
