"""Collaboration service for user branch management.

This module provides the CollaborationService that manages user branches
for investigations, enabling users to explore different directions
independently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from .entities import Branch, Snapshot
    from .repository import InvestigationRepository

from .values import BranchStatus, BranchType, StepType


class CollaborationService:
    """Service for managing user collaboration on investigations.

    Enables:
    - Creating user-specific branches forked from main
    - Sending messages to branches
    - Resuming suspended branches for continued investigation
    """

    def __init__(self, repository: InvestigationRepository) -> None:
        """Initialize the collaboration service.

        Args:
            repository: Repository for persistence operations.
        """
        self.repository = repository

    async def get_or_create_user_branch(
        self,
        investigation_id: UUID,
        user_id: UUID,
    ) -> Branch:
        """Get user's branch or create one forked from main.

        If the user already has a branch for this investigation, returns it.
        Otherwise, creates a new branch forked from the main branch's current
        snapshot.

        Args:
            investigation_id: ID of the investigation.
            user_id: ID of the user requesting a branch.

        Returns:
            The user's branch (existing or newly created).

        Raises:
            ValueError: If investigation or main branch not found.
        """
        # Check if user has existing branch
        existing = await self.repository.get_user_branch(investigation_id, user_id)
        if existing:
            return existing

        # Get investigation
        investigation = await self.repository.get_investigation(investigation_id)
        if investigation is None:
            raise ValueError(f"Investigation not found: {investigation_id}")

        if investigation.main_branch_id is None:
            raise ValueError(f"Investigation has no main branch: {investigation_id}")

        # Get main branch and its current snapshot
        main_branch = await self.repository.get_branch(investigation.main_branch_id)
        if main_branch is None:
            raise ValueError(f"Main branch not found: {investigation.main_branch_id}")

        # Fork from main's current snapshot
        return await self.repository.create_branch(
            investigation_id=investigation_id,
            branch_type=BranchType.USER,
            name=f"user_{user_id}",
            parent_branch_id=main_branch.id,
            forked_from_snapshot_id=main_branch.head_snapshot_id,
            owner_user_id=user_id,
        )

    async def send_message(
        self,
        branch_id: UUID,
        user_id: UUID,
        message: str,
    ) -> UUID:
        """Send a message to a branch.

        Adds the user's message to the branch's message history.

        Args:
            branch_id: ID of the branch to send message to.
            user_id: ID of the user sending the message.
            message: The message content.

        Returns:
            The ID of the created message.
        """
        return await self.repository.add_message(
            branch_id=branch_id,
            role="user",
            content=message,
            user_id=user_id,
        )

    async def resume_branch(
        self,
        branch_id: UUID,
    ) -> None:
        """Resume a suspended or completed branch.

        Sets the branch status to ACTIVE so it can be processed.

        Args:
            branch_id: ID of the branch to resume.

        Raises:
            ValueError: If branch not found or cannot accept input.
        """
        branch = await self.repository.get_branch(branch_id)
        if branch is None:
            raise ValueError(f"Branch not found: {branch_id}")

        if not branch.can_accept_input:
            raise ValueError(f"Branch cannot accept input: {branch_id} (status: {branch.status})")

        await self.repository.update_branch_status(branch_id, BranchStatus.ACTIVE)

    async def create_initial_snapshot_for_user_branch(
        self,
        branch_id: UUID,
        user_message: str,
    ) -> Snapshot:
        """Create initial snapshot for a user branch.

        Creates a snapshot at CLASSIFY_INTENT step with the user's message
        stored in step_cursor, ready for intent classification.

        Args:
            branch_id: ID of the user branch.
            user_message: The user's message to process.

        Returns:
            The created snapshot.

        Raises:
            ValueError: If branch not found or has no forked snapshot.
        """
        branch = await self.repository.get_branch(branch_id)
        if branch is None:
            raise ValueError(f"Branch not found: {branch_id}")

        if branch.forked_from_snapshot_id is None:
            raise ValueError(f"Branch has no forked snapshot: {branch_id}")

        # Get the parent snapshot to copy context from
        parent_snapshot = await self.repository.get_snapshot(branch.forked_from_snapshot_id)
        if parent_snapshot is None:
            raise ValueError(f"Forked snapshot not found: {branch.forked_from_snapshot_id}")

        # Create new snapshot at CLASSIFY_INTENT step
        new_snapshot = await self.repository.create_snapshot(
            investigation_id=branch.investigation_id,
            branch_id=branch_id,
            version=parent_snapshot.version.next_patch(),
            step=StepType.CLASSIFY_INTENT,
            context=parent_snapshot.context,
            parent_snapshot_id=parent_snapshot.id,
            step_cursor={"user_message": user_message},
        )

        # Update branch head
        await self.repository.update_branch_head(branch_id, new_snapshot.id)

        return new_snapshot
