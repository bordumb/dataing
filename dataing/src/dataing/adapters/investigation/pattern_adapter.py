"""Pattern repository adapter for unified investigation steps.

This module provides a pattern repository implementation for CheckPatternsStep.
Initially returns empty results; can be extended to use database persistence.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID


class InMemoryPatternRepository:
    """In-memory pattern repository for CheckPatternsStep.

    Implements PatternRepositoryProtocol expected by CheckPatternsStep.
    Stores patterns in memory; suitable for single-instance deployments
    or as a fallback when database persistence is not available.
    """

    def __init__(self) -> None:
        """Initialize the repository."""
        self._patterns: dict[UUID, dict[str, Any]] = {}

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
            created_from_investigation_id: Optional investigation that created this.

        Returns:
            UUID of the created pattern.
        """
        import uuid

        pattern_id = uuid.uuid4()
        self._patterns[pattern_id] = {
            "id": pattern_id,
            "tenant_id": tenant_id,
            "name": name,
            "description": description,
            "trigger_signals": trigger_signals,
            "typical_root_cause": typical_root_cause,
            "resolution_steps": resolution_steps,
            "affected_datasets": affected_datasets,
            "affected_metrics": affected_metrics,
            "created_from_investigation_id": created_from_investigation_id,
            "match_count": 0,
            "success_count": 0,
        }
        return pattern_id

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
        matches = []

        for pattern in self._patterns.values():
            # Check dataset match
            if dataset_id not in pattern.get("affected_datasets", []):
                # Also check trigger signals for dataset reference
                trigger_signals = pattern.get("trigger_signals", {})
                if dataset_id not in str(trigger_signals):
                    continue

            # Check anomaly type match if specified
            if anomaly_type:
                trigger_signals = pattern.get("trigger_signals", {})
                if anomaly_type not in str(trigger_signals):
                    continue

            # Calculate confidence based on match/success ratio
            match_count = pattern.get("match_count", 0)
            success_count = pattern.get("success_count", 0)
            confidence = success_count / match_count if match_count > 0 else 0.5

            if confidence >= min_confidence:
                matches.append({
                    **pattern,
                    "confidence": confidence,
                })

        return matches

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
        if pattern_id not in self._patterns:
            return

        pattern = self._patterns[pattern_id]
        pattern["match_count"] = pattern.get("match_count", 0) + 1
        if matched:
            pattern["success_count"] = pattern.get("success_count", 0) + 1
