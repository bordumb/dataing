"""Tests for LLM response models."""

import pytest
from dataing.adapters.llm.response_models import InterpretationResponse
from pydantic import ValidationError


class TestInterpretationResponse:
    """Tests for InterpretationResponse model."""

    def test_valid_interpretation_with_causal_chain(self) -> None:
        """Test that valid interpretation with causal_chain passes validation."""
        response = InterpretationResponse(
            supports_hypothesis=True,
            confidence=0.85,
            interpretation=(
                "The 485 orphaned orders appeared after 03:14 UTC "
                "when the users table stopped updating."
            ),
            causal_chain="users ETL stopped at 03:14 -> stale table -> JOIN produces NULLs",
            key_findings=["485 orders with NULL user_id", "All created after 03:14 UTC"],
            next_investigation_step=None,
        )
        assert response.confidence == 0.85
        assert response.causal_chain is not None

    def test_causal_chain_required(self) -> None:
        """Test that causal_chain is required."""
        with pytest.raises(ValidationError) as exc_info:
            InterpretationResponse(
                supports_hypothesis=True,
                confidence=0.85,
                interpretation="The results confirm there are NULL user_ids in the orders table.",
                key_findings=["NULLs exist"],
                causal_chain=None,
            )
        assert "causal_chain" in str(exc_info.value)

    def test_causal_chain_min_length(self) -> None:
        """Test causal_chain minimum length validation."""
        with pytest.raises(ValidationError) as exc_info:
            InterpretationResponse(
                supports_hypothesis=True,
                confidence=0.85,
                interpretation=(
                    "The 485 orphaned orders appeared after 03:14 UTC "
                    "when the users table stopped."
                ),
                causal_chain="too short",
                key_findings=["485 orders affected"],
            )
        assert "causal_chain" in str(exc_info.value).lower()

    def test_key_findings_min_length(self) -> None:
        """Test key_findings requires at least 1 item."""
        with pytest.raises(ValidationError) as exc_info:
            InterpretationResponse(
                supports_hypothesis=True,
                confidence=0.85,
                interpretation=(
                    "The 485 orphaned orders appeared after 03:14 UTC "
                    "when the users table stopped."
                ),
                causal_chain="users ETL stopped at 03:14 -> stale table -> JOIN produces NULLs",
                key_findings=[],
            )
        assert "key_findings" in str(exc_info.value).lower()

    def test_inconclusive_requires_next_step(self) -> None:
        """Test that inconclusive interpretation requires next_investigation_step."""
        # When supports_hypothesis is None (inconclusive), next_investigation_step
        # should be provided. This is a soft requirement enforced by the LLM-as-judge,
        # not Pydantic validation.
        response = InterpretationResponse(
            supports_hypothesis=None,
            confidence=0.4,
            interpretation=(
                "The results are inconclusive - need more data to determine root cause."
            ),
            causal_chain="Insufficient data to establish causal relationship",
            key_findings=["Query returned 0 rows"],
            next_investigation_step="Query the upstream users table directly",
        )
        assert response.next_investigation_step is not None
