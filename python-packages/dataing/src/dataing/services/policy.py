"""Policy evaluation service for triage and investigation automation.

This service resolves the effective action for an issue using team rules
and dataset/tag overrides. It follows precedence: dataset overrides > team default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

import structlog

from dataing.adapters.db.team_policy_repository import (
    PolicyAction,
    TeamPolicy,
    TeamPolicyOverride,
    TeamPolicyRepository,
    TeamQueueLimits,
)

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase

logger = structlog.get_logger()


@dataclass
class QueueConfig:
    """Queue configuration for rate limiting and concurrency."""

    rate_limit_per_minute: int = 60
    burst_size: int = 10
    max_concurrent: int = 5
    batch_size: int = 5

    @classmethod
    def from_limits(cls, limits: TeamQueueLimits | None) -> QueueConfig:
        """Create QueueConfig from TeamQueueLimits or defaults."""
        if limits is None:
            return cls()
        return cls(
            rate_limit_per_minute=limits.rate_limit_per_minute,
            burst_size=limits.burst_size,
            max_concurrent=limits.max_concurrent,
            batch_size=limits.batch_size,
        )


@dataclass
class PolicyResult:
    """Result of policy evaluation for an issue."""

    action: PolicyAction
    queue_config: QueueConfig
    source: str  # "team_default", "dataset_override", "tag_override"
    team_id: UUID
    policy_id: UUID | None = None
    override_id: UUID | None = None
    auto_investigate_min_severity: str | None = None
    review_required_max_severity: str | None = None
    matched_tags: list[UUID] = field(default_factory=list)


@dataclass
class IssueContext:
    """Context for evaluating policy against an issue."""

    team_id: UUID
    dataset_id: str | None = None
    tag_ids: list[UUID] = field(default_factory=list)
    severity: str | None = None
    source: str | None = None  # e.g., "dbt", "airflow"


class PolicyService:
    """Service for evaluating team policies and resolving effective actions."""

    def __init__(self, db: AppDatabase) -> None:
        """Initialize the policy service."""
        self.db = db
        self.repo = TeamPolicyRepository(db)

    async def evaluate(self, context: IssueContext) -> PolicyResult:
        """Evaluate policy for an issue and return the effective action.

        Precedence order (highest to lowest):
        1. Dataset-specific override (if dataset_id matches)
        2. Tag-specific override (if any tag_id matches)
        3. Team default policy
        4. System defaults

        Args:
            context: Issue context including team_id, dataset_id, and tag_ids.

        Returns:
            PolicyResult with the resolved action and queue configuration.
        """
        team_id = context.team_id

        # Get team policy
        policy = await self.repo.get_policy_by_team(team_id)

        # Get queue limits
        queue_limits = await self.repo.get_queue_limits(team_id)
        queue_config = QueueConfig.from_limits(queue_limits)

        # Check source filter (if policy has sources set, issue source must match)
        if policy and policy.sources and context.source:
            if context.source not in policy.sources:
                logger.debug(
                    "policy_source_mismatch",
                    team_id=str(team_id),
                    issue_source=context.source,
                    policy_sources=policy.sources,
                )
                # Source doesn't match - use defaults
                return self._default_result(team_id, queue_config)

        # Try dataset-specific override first
        if context.dataset_id:
            override = await self.repo.get_override_for_dataset(team_id, context.dataset_id)
            if override and override.is_active:
                logger.debug(
                    "policy_dataset_override_matched",
                    team_id=str(team_id),
                    dataset_id=context.dataset_id,
                    override_id=str(override.id),
                )
                return self._result_from_override(
                    override=override,
                    base_policy=policy,
                    queue_config=queue_config,
                    source="dataset_override",
                )

        # Try tag-specific overrides
        if context.tag_ids:
            overrides = await self.repo.get_overrides_for_team(team_id)
            tag_overrides = [o for o in overrides if o.tag_id in context.tag_ids]
            if tag_overrides:
                # Use the first matching tag override (could prioritize by severity later)
                override = tag_overrides[0]
                matched_tags = [o.tag_id for o in tag_overrides if o.tag_id]
                logger.debug(
                    "policy_tag_override_matched",
                    team_id=str(team_id),
                    tag_ids=[str(t) for t in matched_tags],
                    override_id=str(override.id),
                )
                return self._result_from_override(
                    override=override,
                    base_policy=policy,
                    queue_config=queue_config,
                    source="tag_override",
                    matched_tags=[t for t in matched_tags if t is not None],
                )

        # Fall back to team default policy
        if policy and policy.is_active:
            action = self._resolve_action_for_severity(
                default_action=policy.default_action,
                severity=context.severity,
                auto_investigate_min_severity=policy.auto_investigate_min_severity,
                review_required_max_severity=policy.review_required_max_severity,
            )
            logger.debug(
                "policy_team_default_applied",
                team_id=str(team_id),
                policy_id=str(policy.id),
                action=action.value,
            )
            return PolicyResult(
                action=action,
                queue_config=queue_config,
                source="team_default",
                team_id=team_id,
                policy_id=policy.id,
                auto_investigate_min_severity=policy.auto_investigate_min_severity,
                review_required_max_severity=policy.review_required_max_severity,
            )

        # System defaults
        return self._default_result(team_id, queue_config)

    async def get_policy_for_team(self, team_id: UUID) -> TeamPolicy | None:
        """Get the policy for a team."""
        return await self.repo.get_policy_by_team(team_id)

    async def get_overrides_for_team(self, team_id: UUID) -> list[TeamPolicyOverride]:
        """Get all policy overrides for a team."""
        return await self.repo.get_overrides_for_team(team_id)

    async def get_queue_config(self, team_id: UUID) -> QueueConfig:
        """Get the queue configuration for a team."""
        limits = await self.repo.get_queue_limits(team_id)
        return QueueConfig.from_limits(limits)

    def _result_from_override(
        self,
        override: TeamPolicyOverride,
        base_policy: TeamPolicy | None,
        queue_config: QueueConfig,
        source: str,
        matched_tags: list[UUID] | None = None,
    ) -> PolicyResult:
        """Create a PolicyResult from an override, inheriting from base policy if needed."""
        # Get action from override, or inherit from base policy
        action = override.default_action
        if action is None and base_policy:
            action = base_policy.default_action
        if action is None:
            action = PolicyAction.ISSUE_ONLY

        # Get severity settings - prefer override, fall back to policy
        auto_min = override.auto_investigate_min_severity
        if auto_min is None and base_policy:
            auto_min = base_policy.auto_investigate_min_severity

        review_max = override.review_required_max_severity
        if review_max is None and base_policy:
            review_max = base_policy.review_required_max_severity

        return PolicyResult(
            action=action,
            queue_config=queue_config,
            source=source,
            team_id=override.team_id,
            policy_id=base_policy.id if base_policy else None,
            override_id=override.id,
            auto_investigate_min_severity=auto_min,
            review_required_max_severity=review_max,
            matched_tags=matched_tags or [],
        )

    def _resolve_action_for_severity(
        self,
        default_action: PolicyAction,
        severity: str | None,
        auto_investigate_min_severity: str | None,
        review_required_max_severity: str | None,
    ) -> PolicyAction:
        """Resolve the effective action based on severity settings.

        Severity levels (low to high): info, low, medium, high, critical

        Args:
            default_action: The default action from policy.
            severity: The issue's severity level.
            auto_investigate_min_severity: Minimum severity for auto investigation.
            review_required_max_severity: Maximum severity that requires review.

        Returns:
            The resolved PolicyAction.
        """
        if severity is None:
            return default_action

        severity_order = ["info", "low", "medium", "high", "critical"]

        def severity_rank(s: str) -> int:
            try:
                return severity_order.index(s.lower())
            except ValueError:
                return -1

        issue_rank = severity_rank(severity)
        if issue_rank < 0:
            return default_action

        # Check if severity triggers auto-investigation
        if auto_investigate_min_severity:
            auto_rank = severity_rank(auto_investigate_min_severity)
            if auto_rank >= 0 and issue_rank >= auto_rank:
                return PolicyAction.AUTO

        # Check if severity requires review
        if review_required_max_severity:
            review_rank = severity_rank(review_required_max_severity)
            if review_rank >= 0 and issue_rank <= review_rank:
                return PolicyAction.REVIEW

        return default_action

    def _default_result(self, team_id: UUID, queue_config: QueueConfig) -> PolicyResult:
        """Create a default PolicyResult when no policy is configured."""
        return PolicyResult(
            action=PolicyAction.ISSUE_ONLY,
            queue_config=queue_config,
            source="system_default",
            team_id=team_id,
        )


# Convenience functions for API layer


async def evaluate_policy_for_issue(
    db: AppDatabase,
    team_id: UUID,
    dataset_id: str | None = None,
    tag_ids: list[UUID] | None = None,
    severity: str | None = None,
    source: str | None = None,
) -> PolicyResult:
    """Evaluate policy for an issue.

    This is a convenience function for use in API routes.

    Args:
        db: Application database.
        team_id: Team ID.
        dataset_id: Optional dataset identifier.
        tag_ids: Optional list of tag IDs.
        severity: Optional severity level.
        source: Optional issue source (e.g., "dbt", "airflow").

    Returns:
        PolicyResult with the resolved action.
    """
    service = PolicyService(db)
    context = IssueContext(
        team_id=team_id,
        dataset_id=dataset_id,
        tag_ids=tag_ids or [],
        severity=severity,
        source=source,
    )
    return await service.evaluate(context)
