"""Investigation service for coordinating API operations.

This module provides the InvestigationService that coordinates between
the API layer, repository, and collaboration service.

Uses maestro.Workflow for investigation execution.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from dataing.adapters.context.engine import ContextEngine
    from dataing.adapters.datasource.base import BaseAdapter
    from dataing.adapters.db.app_db import AppDatabase
    from dataing.adapters.investigation.pattern_adapter import InMemoryPatternRepository
    from dataing.agents.client import AgentClient
    from dataing.core.domain_types import AnomalyAlert
    from dataing.core.investigation.collaboration import CollaborationService
    from dataing.core.investigation.repository import InvestigationRepository
    from dataing.services.usage import UsageTracker

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.values import (
    BranchStatus,
    BranchType,
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
    and the underlying domain services (repository, collaboration).
    """

    def __init__(
        self,
        repository: InvestigationRepository,
        collaboration: CollaborationService,
        agent_client: AgentClient,
        context_engine: ContextEngine,
        pattern_repository: InMemoryPatternRepository | None = None,
        usage_tracker: UsageTracker | None = None,
        app_db: AppDatabase | None = None,
    ) -> None:
        """Initialize the investigation service.

        Args:
            repository: Repository for persistence operations.
            collaboration: Service for user branch management.
            agent_client: LLM client for AI operations.
            context_engine: Engine for gathering context from data sources.
            pattern_repository: Optional pattern repository for historical patterns.
            usage_tracker: Optional usage tracker for recording usage metrics.
            app_db: Optional app database for creating notifications.
        """
        self.repository = repository
        self.collaboration = collaboration
        self._agent_client = agent_client
        self._context_engine = context_engine
        self._pattern_repository = pattern_repository
        self._usage_tracker = usage_tracker
        self._app_db = app_db

    async def start_investigation(
        self,
        tenant_id: UUID,
        alert: AnomalyAlert,
        data_adapter: BaseAdapter,
        user_id: UUID | None = None,
        datasource_id: UUID | None = None,
        correlation_id: str | None = None,
    ) -> tuple[UUID, UUID, str]:
        """Start a new investigation for an alert.

        Creates the investigation, main branch, and initial snapshot,
        then queues the job for durable execution via Redis/Arq.

        Args:
            tenant_id: ID of the tenant starting the investigation.
            alert: The anomaly alert triggering this investigation.
            data_adapter: Connected data source adapter (unused, for interface compat).
            user_id: Optional ID of the user starting the investigation.
            datasource_id: Datasource ID for worker adapter reconstruction.
            correlation_id: Optional correlation ID for distributed tracing.

        Returns:
            Tuple of (investigation_id, main_branch_id, status).
            Status is always "queued".

        Raises:
            RuntimeError: If app_db is not configured (required for job creation).
        """
        # Create investigation
        investigation = await self.repository.create_investigation(
            tenant_id=tenant_id,
            alert=alert.model_dump(),
            created_by=user_id,
        )

        # Record investigation start for usage tracking
        if self._usage_tracker:
            await self._usage_tracker.record_investigation(
                tenant_id=tenant_id,
                investigation_id=investigation.id,
                status="started",
            )

        # Create main branch
        main_branch = await self.repository.create_branch(
            investigation_id=investigation.id,
            branch_type=BranchType.MAIN,
            name="main",
        )

        # Set main branch
        await self.repository.set_main_branch(investigation.id, main_branch.id)

        # Build rich alert summary with all critical information
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
            alert=alert.model_dump(mode="json"),
        )

        # Create initial snapshot at GATHER_CONTEXT
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

        # Require app_db for job creation
        if not self._app_db:
            raise RuntimeError("app_db is required for investigation job creation")

        # Create job record for durable execution
        job = await self._app_db.create_investigation_job(
            investigation_id=investigation.id,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
            priority=0,
        )
        logger.info(
            f"Created investigation job: job_id={job['id']}, investigation_id={investigation.id}"
        )

        # Queue for durable execution
        from dataing.core.queue import enqueue_investigation

        await enqueue_investigation(
            investigation_id=str(investigation.id),
            tenant_id=str(tenant_id),
            datasource_id=str(datasource_id) if datasource_id else None,
            correlation_id=correlation_id,
        )
        logger.info(f"Enqueued investigation {investigation.id} for durable execution")

        return investigation.id, main_branch.id, "queued"

    async def _create_completion_notification(
        self,
        branch_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """Create notification when investigation completes or fails.

        Only creates notifications for main branch completion (not child branches).

        Args:
            branch_id: ID of the branch that completed/failed.
            status: "completed" or "failed".
            error_message: Optional error message for failures.
        """
        if not self._app_db:
            return  # No app_db configured, skip notifications

        try:
            # Get branch to check if it's the main branch
            branch = await self.repository.get_branch(branch_id)
            if branch is None or branch.branch_type != BranchType.MAIN:
                return  # Only notify for main branch completion

            # Get investigation for tenant_id and alert info
            investigation = await self.repository.get_investigation(branch.investigation_id)
            if investigation is None:
                return

            # Extract alert summary for notification title
            alert_info = investigation.alert or {}
            dataset_id = alert_info.get("dataset_id", "Unknown dataset")
            metric_name = alert_info.get("metric_name", "")
            alert_summary = f"{dataset_id}"
            if metric_name:
                alert_summary += f" - {metric_name}"

            if status == "completed":
                await self._app_db.create_notification(
                    tenant_id=investigation.tenant_id,
                    type="investigation_completed",
                    title=f"Investigation completed: {alert_summary[:50]}",
                    body="The investigation has finished analyzing the data anomaly.",
                    resource_kind="investigation",
                    resource_id=investigation.id,
                    severity="success",
                )
            else:  # failed
                error_body = (
                    f"Investigation failed: {error_message[:200]}"
                    if error_message
                    else "Investigation failed without error details."
                )
                await self._app_db.create_notification(
                    tenant_id=investigation.tenant_id,
                    type="investigation_failed",
                    title=f"Investigation failed: {alert_summary[:50]}",
                    body=error_body,
                    resource_kind="investigation",
                    resource_id=investigation.id,
                    severity="error",
                )

            logger.info(f"Created {status} notification for investigation {investigation.id}")

        except Exception as e:
            # Don't fail the investigation if notification creation fails
            logger.error(f"Failed to create notification for branch {branch_id}: {e}")

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
            main_snapshot = await self.repository.get_snapshot(main_branch.head_snapshot_id)

        main_branch_state = self._create_branch_state(main_branch, main_snapshot)

        # Get user branch if exists
        user_branch_state = None
        user_branch = await self.repository.get_user_branch(investigation_id, user_id)
        if user_branch:
            user_snapshot = None
            if user_branch.head_snapshot_id:
                user_snapshot = await self.repository.get_snapshot(user_branch.head_snapshot_id)
            user_branch_state = self._create_branch_state(user_branch, user_snapshot)

        # Determine overall status
        status = "active"
        if investigation.outcome:
            outcome_status = None
            if isinstance(investigation.outcome, dict):
                outcome_status = investigation.outcome.get("status")
            status = outcome_status or "completed"
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
        branch = await self.collaboration.get_or_create_user_branch(investigation_id, user_id)

        # Add message
        await self.collaboration.send_message(branch.id, user_id, message)

        # Resume branch if suspended
        if branch.status == BranchStatus.SUSPENDED:
            await self.collaboration.resume_branch(branch.id)

        branch_id: UUID = branch.id
        return branch_id

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
                StepType.CHECK_PATTERNS,
                StepType.GENERATE_HYPOTHESES,
                StepType.GENERATE_QUERY,
                StepType.EXECUTE_QUERY,
                StepType.INTERPRET_EVIDENCE,
                StepType.SYNTHESIZE,
            ]

            # Add terminal step
            if current_step == StepType.FAIL.value:
                workflow_steps.append(StepType.FAIL)
            elif current_step == "cancelled":
                # Special case for cancelled
                pass # Handled below
            else:
                workflow_steps.append(StepType.COMPLETE)

            current_idx = -1
            for i, step in enumerate(workflow_steps):
                if step.value == current_step:
                    current_idx = i
                    break

            for i, step in enumerate(workflow_steps):
                # A step is completed if it's before current, or if it IS current and terminal
                is_completed = i < current_idx
                if i == current_idx and step in (StepType.COMPLETE, StepType.FAIL):
                    is_completed = True

                step_history.append(
                    StepHistoryItem(
                        step=step.value,
                        completed=is_completed,
                    )
                )

            # Handle cancelled as a special terminal step if needed
            if current_step == "cancelled":
                step_history.append(
                    StepHistoryItem(
                        step="cancelled",
                        completed=True,
                    )
                )

            # Extract matched patterns from context
            for pattern in snapshot.context.matched_patterns:
                matched_patterns.append(
                    MatchedPattern(
                        pattern_id=pattern.get("id", "unknown"),
                        pattern_name=pattern.get("name", "Unknown Pattern"),
                        confidence=pattern.get("confidence", 0.0),
                        description=pattern.get("description"),
                    )
                )

        # Check if branch can merge (user branches that are completed)
        can_merge = (
            branch.branch_type == BranchType.USER and branch.status == BranchStatus.COMPLETED
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
