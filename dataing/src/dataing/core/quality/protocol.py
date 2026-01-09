"""Protocol definition for quality validators."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dataing.agents.models import (
        InterpretationResponse,
        SynthesisResponse,
    )

    from .assessment import ValidationResult


@runtime_checkable
class QualityValidator(Protocol):
    """Interface for LLM output quality validation.

    Implementations may use:
    - LLM-as-judge (semantic validation)
    - Regex patterns (rule-based validation)
    - RL-based scoring (learned validation)

    All implementations return dimensional quality scores
    for training signal capture.
    """

    async def validate_interpretation(
        self,
        response: InterpretationResponse,
        hypothesis_title: str,
        query: str,
    ) -> ValidationResult:
        """Validate an interpretation response.

        Args:
            response: The interpretation to validate.
            hypothesis_title: Title of the hypothesis being tested.
            query: The SQL query that was executed.

        Returns:
            ValidationResult with pass/fail and dimensional scores.
        """
        ...

    async def validate_synthesis(
        self,
        response: SynthesisResponse,
        alert_summary: str,
    ) -> ValidationResult:
        """Validate a synthesis response.

        Args:
            response: The synthesis to validate.
            alert_summary: Summary of the original anomaly alert.

        Returns:
            ValidationResult with pass/fail and dimensional scores.
        """
        ...
