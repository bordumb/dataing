"""Tests for LLM response models."""

import pytest
from dataing.adapters.llm.response_models import (
    HypothesisResponse,
    InterpretationResponse,
    SynthesisResponse,
)
from dataing.core.domain_types import HypothesisCategory
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


class TestSynthesisResponse:
    """Tests for SynthesisResponse model."""

    def test_valid_synthesis_with_all_fields(self) -> None:
        """Test valid synthesis with all required fields."""
        response = SynthesisResponse(
            root_cause="Users ETL job timed out at 03:14 UTC due to API rate limiting",
            confidence=0.85,
            causal_chain=[
                "API rate limit hit at 03:14 UTC",
                "users ETL job timeout",
                "users table stale after 03:14",
                "orders JOIN produces NULLs",
            ],
            estimated_onset="03:14 UTC",
            affected_scope="orders table, order_items table, all downstream reports",
            supporting_evidence=["485 orders with NULL user_id", "Last user update: 03:14 UTC"],
            recommendations=["Re-run stg_users job: airflow trigger_dag stg_users --backfill"],
        )
        assert response.confidence == 0.85
        assert len(response.causal_chain) == 4

    def test_causal_chain_required(self) -> None:
        """Test that causal_chain is required."""
        with pytest.raises(ValidationError) as exc_info:
            SynthesisResponse(
                root_cause="Some root cause explanation here",
                confidence=0.85,
                estimated_onset="03:14 UTC",
                affected_scope="orders table and downstream",
                supporting_evidence=["evidence"],
                recommendations=["fix it"],
            )
        assert "causal_chain" in str(exc_info.value)

    def test_causal_chain_min_length(self) -> None:
        """Test causal_chain requires at least 2 steps."""
        with pytest.raises(ValidationError) as exc_info:
            SynthesisResponse(
                root_cause="Users ETL job timed out at 03:14 UTC",
                confidence=0.85,
                causal_chain=["only one step"],
                estimated_onset="03:14 UTC",
                affected_scope="orders table and downstream",
                supporting_evidence=["evidence"],
                recommendations=["fix it"],
            )
        assert "causal_chain" in str(exc_info.value).lower()

    def test_estimated_onset_required(self) -> None:
        """Test that estimated_onset is required."""
        with pytest.raises(ValidationError) as exc_info:
            SynthesisResponse(
                root_cause="Users ETL job timed out due to API rate limiting",
                confidence=0.85,
                causal_chain=["cause", "effect"],
                affected_scope="orders table and downstream",
                supporting_evidence=["evidence"],
                recommendations=["fix it"],
            )
        assert "estimated_onset" in str(exc_info.value)

    def test_affected_scope_required(self) -> None:
        """Test that affected_scope is required."""
        with pytest.raises(ValidationError) as exc_info:
            SynthesisResponse(
                root_cause="Users ETL job timed out due to API rate limiting",
                confidence=0.85,
                causal_chain=["cause", "effect"],
                estimated_onset="03:14 UTC",
                supporting_evidence=["evidence"],
                recommendations=["fix it"],
            )
        assert "affected_scope" in str(exc_info.value)

    def test_null_root_cause_allowed(self) -> None:
        """Test that null root_cause is allowed for inconclusive investigations."""
        response = SynthesisResponse(
            root_cause=None,
            confidence=0.3,
            causal_chain=["insufficient data", "cannot determine cause"],
            estimated_onset="unknown",
            affected_scope="unknown scope - need more investigation",
            supporting_evidence=["No clear evidence found"],
            recommendations=["Gather more data from upstream systems"],
        )
        assert response.root_cause is None


class TestHypothesisResponse:
    """Tests for HypothesisResponse model."""

    def test_valid_hypothesis_with_testability_fields(self) -> None:
        """Test valid hypothesis with expected_if_true/false fields."""
        response = HypothesisResponse(
            id="h1",
            title="Upstream users ETL job failed causing NULL user_ids",
            category=HypothesisCategory.UPSTREAM_DEPENDENCY,
            reasoning="The users table may have stopped receiving updates, causing JOINs to fail",
            suggested_query="SELECT COUNT(*) FROM orders WHERE user_id IS NULL LIMIT 100",
            expected_if_true="High count of NULL user_ids after a specific timestamp",
            expected_if_false="Zero or very few NULL user_ids",
        )
        assert response.expected_if_true is not None
        assert response.expected_if_false is not None

    def test_expected_if_true_required(self) -> None:
        """Test that expected_if_true is required."""
        with pytest.raises(ValidationError) as exc_info:
            HypothesisResponse(
                id="h1",
                title="Upstream users ETL job failed",
                category=HypothesisCategory.UPSTREAM_DEPENDENCY,
                reasoning="The users table may have stopped receiving updates",
                suggested_query="SELECT COUNT(*) FROM orders WHERE user_id IS NULL LIMIT 100",
                expected_if_false="Zero NULL user_ids",
            )
        assert "expected_if_true" in str(exc_info.value)

    def test_expected_if_false_required(self) -> None:
        """Test that expected_if_false is required."""
        with pytest.raises(ValidationError) as exc_info:
            HypothesisResponse(
                id="h1",
                title="Upstream users ETL job failed",
                category=HypothesisCategory.UPSTREAM_DEPENDENCY,
                reasoning="The users table may have stopped receiving updates",
                suggested_query="SELECT COUNT(*) FROM orders WHERE user_id IS NULL LIMIT 100",
                expected_if_true="High count of NULL user_ids",
            )
        assert "expected_if_false" in str(exc_info.value)
