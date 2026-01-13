"""CheckPatterns step implementation.

This step checks for previously seen root cause patterns.
It runs after GatherContext and before GenerateHypotheses.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from dataing.core.investigation.entities import InvestigationContext
from dataing.core.investigation.pattern_extraction import PatternRepositoryProtocol
from dataing.core.investigation.values import StepType

from .protocol import Signal, Step, StepResult

logger = logging.getLogger(__name__)


class CheckPatternsStep(Step[None, list[dict[str, Any]]]):
    """Check for previously seen root cause patterns.

    This step queries the pattern repository for matches based on:
    - Dataset/metric affected
    - Anomaly type and characteristics
    - Time patterns

    High-confidence matches (>0.8) get injected as hints to hypothesis generation.
    """

    step_type = StepType.CHECK_PATTERNS

    def __init__(self, pattern_repository: PatternRepositoryProtocol) -> None:
        """Initialize the step.

        Args:
            pattern_repository: Repository for querying historical patterns.
        """
        self.pattern_repository = pattern_repository

    def can_execute(self, context: InvestigationContext) -> bool:
        """Check if step can execute.

        Pattern checking can always run (even without schema info).
        Patterns are optional enrichment, not a hard requirement.

        Args:
            context: Current investigation context.

        Returns:
            True (pattern checking is always possible).
        """
        return True

    async def execute(
        self,
        context: InvestigationContext,
        input_data: None = None,
    ) -> StepResult[InvestigationContext, list[dict[str, Any]]]:
        """Execute pattern matching against historical root causes.

        Args:
            context: Current investigation context.
            input_data: Not used for this step.

        Returns:
            StepResult with matched patterns in context.
        """
        dataset_id = self._extract_dataset(context)
        anomaly_type = self._extract_anomaly_type(context)

        try:
            patterns = await self.pattern_repository.find_matching_patterns(
                dataset_id=dataset_id,
                anomaly_type=anomaly_type,
                min_confidence=0.8,
            )
        except Exception as e:
            # Pattern matching is optional - don't fail the investigation
            logger.warning(f"Pattern repository error: {e}")
            patterns = []

        # Create new context with matched patterns using model_copy
        new_context = context.model_copy(update={"matched_patterns": patterns})

        return StepResult(
            context=new_context,
            signal=Signal.CONTINUE,
            output=patterns,
            next_step=StepType.GENERATE_HYPOTHESES.value,
        )

    def _extract_dataset(self, context: InvestigationContext) -> str:
        """Extract dataset identifier from context.

        Attempts to extract the dataset name from the alert summary.
        Falls back to "unknown" if extraction fails.

        Args:
            context: Investigation context containing alert summary.

        Returns:
            Dataset identifier string.
        """
        alert = context.alert_summary

        # Try to extract dataset from common patterns like "... in analytics.events"
        in_pattern = re.search(r"\bin\s+([\w.]+)", alert)
        if in_pattern:
            return in_pattern.group(1)

        # Try to extract from "dataset_name:" pattern
        colon_pattern = re.search(r"([\w.]+):", alert)
        if colon_pattern:
            return colon_pattern.group(1)

        return "unknown"

    def _extract_anomaly_type(self, context: InvestigationContext) -> str | None:
        """Extract anomaly type from context.

        Attempts to extract the anomaly type from the alert summary.

        Args:
            context: Investigation context containing alert summary.

        Returns:
            Anomaly type string or None if not found.
        """
        alert = context.alert_summary.lower()

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
