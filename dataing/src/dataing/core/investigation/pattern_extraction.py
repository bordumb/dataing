"""Pattern extraction service for learning from completed investigations.

This module provides functionality to extract reusable patterns from
completed investigations. Patterns help speed up future investigations
by providing hints based on previously observed root causes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from dataing.core.domain_types import AnomalyAlert

    from .repository import InvestigationRepository


class LLMProtocol(Protocol):
    """Protocol for LLM client used by PatternExtractionService."""

    async def extract_pattern(
        self,
        *,
        alert: AnomalyAlert,
        outcome: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Extract a reusable pattern from investigation results.

        Args:
            alert: The anomaly alert that triggered the investigation.
            outcome: The investigation outcome (root cause, confidence, etc.).
            evidence: Evidence collected during the investigation.

        Returns:
            Pattern dict with fields:
            - name: str - Human-readable pattern name
            - description: str - Detailed description of the pattern
            - trigger_signals: dict - Signals that indicate this pattern
            - typical_root_cause: str - The typical root cause for this pattern
            - resolution_steps: list[str] - Steps to resolve the issue
            - affected_datasets: list[str] - Datasets commonly affected
            - affected_metrics: list[str] - Metrics commonly affected
        """
        ...


class PatternRepositoryProtocol(Protocol):
    """Protocol for pattern persistence operations.

    This defines the interface for storing and querying learned patterns.
    All patterns are tenant-isolated.
    """

    async def create_pattern(
        self,
        *,
        tenant_id: UUID,
        name: str,
        description: str,
        trigger_signals: dict[str, Any],
        typical_root_cause: str,
        resolution_steps: list[str],
        affected_datasets: list[str],
        affected_metrics: list[str],
        created_from_investigation_id: UUID | None = None,
    ) -> UUID:
        """Create a new pattern.

        Args:
            tenant_id: Tenant this pattern belongs to.
            name: Human-readable pattern name.
            description: Detailed description of the pattern.
            trigger_signals: Signals that indicate this pattern.
            typical_root_cause: The typical root cause for this pattern.
            resolution_steps: Steps to resolve the issue.
            affected_datasets: Datasets commonly affected by this pattern.
            affected_metrics: Metrics commonly affected by this pattern.
            created_from_investigation_id: Optional investigation that created this pattern.

        Returns:
            UUID of the created pattern.
        """
        ...

    async def find_matching_patterns(
        self,
        *,
        dataset_id: str,
        anomaly_type: str | None = None,
        metric_name: str | None = None,
        min_confidence: float = 0.8,
    ) -> list[dict[str, Any]]:
        """Find patterns matching criteria.

        Args:
            dataset_id: The dataset identifier to search patterns for.
            anomaly_type: Optional anomaly type to filter by.
            metric_name: Optional metric name to filter by.
            min_confidence: Minimum confidence threshold (default 0.8).

        Returns:
            List of matching pattern dicts.
        """
        ...

    async def update_pattern_stats(
        self,
        pattern_id: UUID,
        matched: bool,
        resolution_time_minutes: int | None = None,
    ) -> None:
        """Update pattern statistics after use.

        Args:
            pattern_id: ID of the pattern to update.
            matched: Whether the pattern led to successful resolution.
            resolution_time_minutes: Optional time to resolution in minutes.
        """
        ...


class PatternExtractionService:
    """Service for extracting patterns from completed investigations.

    This service analyzes completed investigations and extracts reusable
    patterns that can speed up future investigations. Patterns are only
    extracted from investigations that meet quality criteria:
    - Investigation must be completed (has outcome)
    - Confidence must be above threshold (default 0.85)

    Patterns are tenant-isolated and stored for per-organization learning.
    """

    def __init__(
        self,
        repository: InvestigationRepository,
        pattern_repository: PatternRepositoryProtocol,
        llm: LLMProtocol,
        confidence_threshold: float = 0.85,
    ) -> None:
        """Initialize the pattern extraction service.

        Args:
            repository: Repository for accessing investigation data.
            pattern_repository: Repository for storing extracted patterns.
            llm: LLM client for pattern extraction.
            confidence_threshold: Minimum confidence for pattern extraction.
        """
        self.repository = repository
        self.pattern_repository = pattern_repository
        self.llm = llm
        self.confidence_threshold = confidence_threshold

    async def should_extract_pattern(
        self,
        investigation_id: UUID,
    ) -> bool:
        """Check if investigation is suitable for pattern extraction.

        An investigation is suitable for pattern extraction if:
        1. It has completed (has an outcome)
        2. The confidence is above the threshold

        Args:
            investigation_id: ID of the investigation to check.

        Returns:
            True if the investigation is suitable for pattern extraction.
        """
        investigation = await self.repository.get_investigation(investigation_id)

        if investigation is None:
            return False

        # Only extract from completed investigations
        if investigation.outcome is None:
            return False

        # Check confidence threshold
        confidence = investigation.outcome.get("confidence", 0)
        if confidence < self.confidence_threshold:
            return False

        return True

    async def extract_pattern(
        self,
        investigation_id: UUID,
        tenant_id: UUID,
    ) -> dict[str, Any] | None:
        """Extract a reusable pattern from a completed investigation.

        Uses LLM to analyze the investigation and extract a pattern that
        can be used to accelerate future investigations with similar
        characteristics.

        Args:
            investigation_id: ID of the investigation to extract from.
            tenant_id: Tenant ID for pattern isolation.

        Returns:
            Pattern dict with pattern_id if successful, None if investigation
            is not suitable for extraction.
        """
        investigation = await self.repository.get_investigation(investigation_id)

        if investigation is None or investigation.outcome is None:
            return None

        # Check if main_branch_id is set
        if investigation.main_branch_id is None:
            return None

        # Get the main branch and its final snapshot
        main_branch = await self.repository.get_branch(investigation.main_branch_id)

        if main_branch is None or main_branch.head_snapshot_id is None:
            return None

        final_snapshot = await self.repository.get_snapshot(main_branch.head_snapshot_id)

        if final_snapshot is None:
            return None

        # Use LLM to extract pattern
        pattern: dict[str, Any] = await self.llm.extract_pattern(
            alert=investigation.alert,
            outcome=investigation.outcome,
            evidence=final_snapshot.context.evidence,
        )

        # Save pattern to repository
        pattern_id = await self.pattern_repository.create_pattern(
            tenant_id=tenant_id,
            name=pattern["name"],
            description=pattern["description"],
            trigger_signals=pattern["trigger_signals"],
            typical_root_cause=pattern["typical_root_cause"],
            resolution_steps=pattern["resolution_steps"],
            affected_datasets=pattern.get("affected_datasets", []),
            affected_metrics=pattern.get("affected_metrics", []),
            created_from_investigation_id=investigation_id,
        )

        return {"pattern_id": pattern_id, **pattern}
