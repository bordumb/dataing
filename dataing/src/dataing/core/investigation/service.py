"""Investigation service for coordinating API operations.

This module provides the InvestigationService that coordinates between
the API layer, repository, orchestrator, and collaboration service.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from dataing.adapters.context.engine import ContextEngine
    from dataing.adapters.datasource.base import BaseAdapter
    from dataing.adapters.investigation.pattern_adapter import InMemoryPatternRepository
    from dataing.agents.client import AgentClient
    from dataing.core.domain_types import AnomalyAlert
    from dataing.core.investigation.collaboration import CollaborationService
    from dataing.core.investigation.orchestrator import InvestigationOrchestrator
    from dataing.core.investigation.repository import InvestigationRepository

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import (
    BranchStatus,
    BranchType,
    ExecutionSignal,
    StepType,
    VersionId,
)

logger = logging.getLogger(__name__)


class StepHistoryItem(BaseModel):
    """A step in the branch history."""

    model_config = ConfigDict(frozen=True)

    step: str
    completed: bool
    timestamp: str | None = None


class MatchedPattern(BaseModel):
    """A pattern that was matched during investigation."""

    model_config = ConfigDict(frozen=True)

    pattern_id: str
    pattern_name: str
    confidence: float
    description: str | None = None


class BranchState(BaseModel):
    """State of a branch for API responses."""

    model_config = ConfigDict(frozen=True)

    branch_id: UUID
    status: str
    current_step: str
    synthesis: dict[str, Any] | None = None
    evidence: list[dict[str, Any]] = []
    # Phase 3: Additional data for visualization
    step_history: list[StepHistoryItem] = []
    matched_patterns: list[MatchedPattern] = []
    can_merge: bool = False
    parent_branch_id: UUID | None = None


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
        collaboration: CollaborationService,
        agent_client: AgentClient,
        context_engine: ContextEngine,
        pattern_repository: InMemoryPatternRepository | None = None,
    ) -> None:
        """Initialize the investigation service.

        Args:
            repository: Repository for persistence operations.
            collaboration: Service for user branch management.
            agent_client: LLM client for AI operations.
            context_engine: Engine for gathering context from data sources.
            pattern_repository: Optional pattern repository for historical patterns.
        """
        self.repository = repository
        self.collaboration = collaboration
        self._agent_client = agent_client
        self._context_engine = context_engine
        self._pattern_repository = pattern_repository

    async def start_investigation(
        self,
        tenant_id: UUID,
        alert: AnomalyAlert,
        data_adapter: BaseAdapter,
        user_id: UUID | None = None,
    ) -> tuple[UUID, UUID]:
        """Start a new investigation for an alert.

        Creates the investigation, main branch, and initial snapshot
        positioned at GATHER_CONTEXT step. Also creates an orchestrator
        with real dependencies for this specific investigation.

        Args:
            tenant_id: ID of the tenant starting the investigation.
            alert: The anomaly alert triggering this investigation.
            data_adapter: Connected data source adapter for this investigation.
            user_id: Optional ID of the user starting the investigation.

        Returns:
            Tuple of (investigation_id, main_branch_id).
        """
        from dataing.adapters.investigation.step_factory import create_step_registry
        from dataing.core.investigation.orchestrator import InvestigationOrchestrator

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
        # Build rich alert summary with all critical information for hypothesis generation
        metric_name = alert.metric_spec.display_name
        columns = ", ".join(alert.metric_spec.columns_referenced) or "unknown column"
        alert_summary = (
            f"{alert.anomaly_type} anomaly on {columns} in {alert.dataset_id}: "
            f"expected {alert.expected_value}, actual {alert.actual_value} "
            f"({alert.deviation_pct:.1f}% deviation). "
            f"Metric: {metric_name}. Date: {alert.anomaly_date}."
        )
        initial_context = InvestigationContext(
            alert_summary=alert_summary,
            alert=alert.model_dump(mode="json"),  # Full alert for LLM prompts
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

        # Create step registry with real dependencies for this investigation
        step_registry = create_step_registry(
            agent_client=self._agent_client,
            context_engine=self._context_engine,
            alert=alert,
            data_adapter=data_adapter,
            pattern_repository=self._pattern_repository,
        )

        # Create orchestrator for this investigation
        orchestrator = InvestigationOrchestrator(
            repository=self.repository,
            registry=step_registry,
        )

        # Start the orchestrator in the background
        asyncio.create_task(
            self._run_investigation(main_branch.id, orchestrator),
            name=f"investigation-{investigation.id}",
        )

        return investigation.id, main_branch.id

    async def _run_investigation(
        self,
        branch_id: UUID,
        orchestrator: InvestigationOrchestrator,
        max_iterations: int = 50,
    ) -> None:
        """Run the orchestrator tick loop for a branch.

        This runs in the background after starting an investigation.

        Args:
            branch_id: ID of the branch to run.
            orchestrator: The orchestrator with steps wired for this investigation.
            max_iterations: Maximum number of iterations to prevent infinite loops.
        """
        logger.info(f"Starting investigation loop for branch {branch_id}")

        for i in range(max_iterations):
            try:
                result = await orchestrator.tick(branch_id)
                logger.info(
                    f"Tick {i + 1}: signal={result.signal.value}, "
                    f"snapshot={result.new_snapshot_id}"
                )

                if result.signal == ExecutionSignal.COMPLETE:
                    logger.info(f"Investigation branch {branch_id} completed")
                    break
                elif result.signal == ExecutionSignal.FAIL:
                    logger.warning(
                        f"Investigation branch {branch_id} failed: {result.error}"
                    )
                    break
                elif result.signal == ExecutionSignal.AWAIT_USER:
                    logger.info(f"Investigation branch {branch_id} awaiting user input")
                    break
                elif result.signal == ExecutionSignal.BRANCH:
                    # Handle child branches
                    if result.child_branch_ids:
                        logger.info(
                            f"Created {len(result.child_branch_ids)} child branches"
                        )
                        # Run child branches in parallel with the same orchestrator
                        tasks = [
                            self._run_investigation(child_id, orchestrator)
                            for child_id in result.child_branch_ids
                        ]
                        await asyncio.gather(*tasks)
                        # After children complete, the parent branch is resumed
                        # Continue the loop to tick the parent at the merge step
                        logger.info(f"Child branches completed, resuming parent {branch_id}")
                        continue
                    break

                # Small delay between ticks
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error in investigation loop: {e}", exc_info=True)
                break

        else:
            logger.warning(
                f"Investigation branch {branch_id} reached max iterations ({max_iterations})"
            )

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
        step_history: list[StepHistoryItem] = []
        matched_patterns: list[MatchedPattern] = []

        if snapshot:
            current_step = snapshot.step.value
            if snapshot.context.current_synthesis:
                synthesis = snapshot.context.current_synthesis
            evidence = snapshot.context.evidence

            # Build step history from workflow steps
            workflow_steps = [
                StepType.GATHER_CONTEXT,
                StepType.GENERATE_HYPOTHESES,
                StepType.GENERATE_QUERY,
                StepType.EXECUTE_QUERY,
                StepType.INTERPRET_EVIDENCE,
                StepType.SYNTHESIZE,
                StepType.COMPLETE,
            ]
            current_idx = -1
            for i, step in enumerate(workflow_steps):
                if step.value == current_step:
                    current_idx = i
                    break

            for i, step in enumerate(workflow_steps):
                step_history.append(StepHistoryItem(
                    step=step.value,
                    completed=i < current_idx,
                ))

            # Extract matched patterns from context
            for pattern in snapshot.context.matched_patterns:
                matched_patterns.append(MatchedPattern(
                    pattern_id=pattern.get("id", "unknown"),
                    pattern_name=pattern.get("name", "Unknown Pattern"),
                    confidence=pattern.get("confidence", 0.0),
                    description=pattern.get("description"),
                ))

        # Check if branch can merge (user branches that are completed)
        can_merge = (
            branch.branch_type == BranchType.USER
            and branch.status == BranchStatus.COMPLETED
        )

        return BranchState(
            branch_id=branch.id,
            status=branch.status.value,
            current_step=current_step,
            synthesis=synthesis,
            evidence=evidence,
            step_history=step_history,
            matched_patterns=matched_patterns,
            can_merge=can_merge,
            parent_branch_id=branch.parent_branch_id,
        )
