"""Check patterns activity for investigation workflow.

Extracts business logic from CheckPatternsStep into a Temporal activity factory.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

from temporalio import activity

logger = logging.getLogger(__name__)


class PatternRepositoryProtocol(Protocol):
    """Protocol for pattern repository used by check_patterns activity."""

    async def find_matching_patterns(
        self,
        dataset_id: str,
        anomaly_type: str | None,
        min_confidence: float,
    ) -> list[dict[str, Any]]:
        """Find patterns matching the given criteria."""
        ...


@dataclass
class CheckPatternsInput:
    """Input for check_patterns activity."""

    investigation_id: str
    alert_summary: str


@dataclass
class CheckPatternsResult:
    """Result from check_patterns activity."""

    matched_patterns: list[dict[str, Any]]
    error: str | None = None


def _extract_dataset(alert_summary: str) -> str:
    """Extract dataset identifier from alert summary."""
    # Try to extract dataset from common patterns like "... in analytics.events"
    in_pattern = re.search(r"\bin\s+([\w.]+)", alert_summary)
    if in_pattern:
        return in_pattern.group(1)

    # Try to extract from "dataset_name:" pattern
    colon_pattern = re.search(r"([\w.]+):", alert_summary)
    if colon_pattern:
        return colon_pattern.group(1)

    return "unknown"


def _extract_anomaly_type(alert_summary: str) -> str | None:
    """Extract anomaly type from alert summary."""
    alert = alert_summary.lower()

    # Common anomaly type patterns
    anomaly_types = [
        "null_rate",
        "null_spike",
        "volume_drop",
        "schema_drift",
        "duplicates",
        "late_arriving",
        "orphaned_records",
        "data_freshness",
        "cardinality",
    ]

    for anomaly_type in anomaly_types:
        if anomaly_type.replace("_", " ") in alert or anomaly_type in alert:
            return anomaly_type

    return None


def make_check_patterns_activity(
    pattern_repository: PatternRepositoryProtocol,
) -> Any:
    """Factory that creates check_patterns activity with injected dependencies.

    Args:
        pattern_repository: Repository for querying historical patterns.

    Returns:
        The check_patterns activity function.
    """

    @activity.defn
    async def check_patterns(input: CheckPatternsInput) -> CheckPatternsResult:
        """Check for previously seen root cause patterns.

        This activity queries the pattern repository for matches based on:
        - Dataset/metric affected
        - Anomaly type and characteristics

        High-confidence matches (>0.8) get returned for hypothesis generation hints.
        """
        dataset_id = _extract_dataset(input.alert_summary)
        anomaly_type = _extract_anomaly_type(input.alert_summary)

        try:
            patterns = await pattern_repository.find_matching_patterns(
                dataset_id=dataset_id,
                anomaly_type=anomaly_type,
                min_confidence=0.8,
            )
        except Exception as e:
            # Pattern matching is optional - don't fail the investigation
            logger.warning(f"Pattern repository error: {e}")
            patterns = []

        return CheckPatternsResult(matched_patterns=patterns)

    return check_patterns
