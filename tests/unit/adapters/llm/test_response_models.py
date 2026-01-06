"""Tests for LLM response models validation."""

import pytest
from pydantic import ValidationError

from dataing.adapters.llm.response_models import (
    HypothesisResponse,
    HypothesesResponse,
    InterpretationResponse,
    QueryResponse,
    SynthesisResponse,
)
from dataing.core.domain_types import HypothesisCategory


class TestHypothesisResponse:
    """Tests for HypothesisResponse validation."""

    def test_valid_hypothesis(self) -> None:
        """Accept valid hypothesis."""
        h = HypothesisResponse(
            id="h1",
            title="Upstream table stg_orders has missing data",
            category=HypothesisCategory.UPSTREAM_DEPENDENCY,
            reasoning="The orders table depends on stg_orders which may have failed to load",
            suggested_query="SELECT COUNT(*) FROM analytics.stg_orders LIMIT 1000",
        )
        assert h.id == "h1"
        assert h.category == HypothesisCategory.UPSTREAM_DEPENDENCY

    def test_rejects_short_title(self) -> None:
        """Reject title that's too short."""
        with pytest.raises(ValidationError) as exc_info:
            HypothesisResponse(
                id="h1",
                title="Bad",
                category=HypothesisCategory.DATA_QUALITY,
                reasoning="Some reasoning here that is long enough",
                suggested_query="SELECT 1 LIMIT 1",
            )
        assert "title" in str(exc_info.value).lower()

    def test_rejects_query_without_limit(self) -> None:
        """Reject query missing LIMIT clause."""
        with pytest.raises(ValidationError) as exc_info:
            HypothesisResponse(
                id="h1",
                title="Valid title that is long enough for validation",
                category=HypothesisCategory.DATA_QUALITY,
                reasoning="Some reasoning here that is long enough",
                suggested_query="SELECT * FROM users",
            )
        assert "LIMIT" in str(exc_info.value)

    def test_rejects_mutation_query(self) -> None:
        """Reject query with mutation keywords."""
        with pytest.raises(ValidationError) as exc_info:
            HypothesisResponse(
                id="h1",
                title="Valid title that is long enough for validation",
                category=HypothesisCategory.DATA_QUALITY,
                reasoning="Some reasoning here that is long enough",
                suggested_query="DELETE FROM users LIMIT 100",
            )
        assert "forbidden" in str(exc_info.value).lower()

    def test_allows_deleted_column_name(self) -> None:
        """Allow 'deleted' in column names (word boundary regex)."""
        h = HypothesisResponse(
            id="h1",
            title="Check for soft-deleted records in the database",
            category=HypothesisCategory.DATA_QUALITY,
            reasoning="Looking for records where deleted flag is incorrectly set",
            suggested_query="SELECT * FROM users WHERE deleted = false LIMIT 100",
        )
        assert "deleted" in h.suggested_query.lower()

    def test_strips_markdown_from_query(self) -> None:
        """Strip markdown code blocks from suggested_query."""
        h = HypothesisResponse(
            id="h1",
            title="Check for records with specific conditions",
            category=HypothesisCategory.DATA_QUALITY,
            reasoning="Looking for records that match certain criteria",
            suggested_query="```sql\nSELECT * FROM users LIMIT 10\n```",
        )
        assert not h.suggested_query.startswith("```")
        assert h.suggested_query == "SELECT * FROM users LIMIT 10"


class TestQueryResponse:
    """Tests for QueryResponse validation."""

    def test_strips_markdown(self) -> None:
        """Strip markdown code blocks from query."""
        q = QueryResponse(
            query="```sql\nSELECT * FROM users LIMIT 10\n```",
            explanation="Get users",
        )
        assert q.query == "SELECT * FROM users LIMIT 10"

    def test_rejects_non_select(self) -> None:
        """Reject non-SELECT queries."""
        with pytest.raises(ValidationError):
            QueryResponse(query="INSERT INTO users VALUES (1) LIMIT 1")

    def test_rejects_missing_limit(self) -> None:
        """Reject query without LIMIT."""
        with pytest.raises(ValidationError):
            QueryResponse(query="SELECT * FROM users")


class TestInterpretationResponse:
    """Tests for InterpretationResponse validation."""

    def test_confidence_upper_bound(self) -> None:
        """Reject confidence > 1.0."""
        with pytest.raises(ValidationError):
            InterpretationResponse(
                supports_hypothesis=True,
                confidence=1.5,
                interpretation="This is a valid interpretation text",
            )

    def test_confidence_lower_bound(self) -> None:
        """Reject confidence < 0.0."""
        with pytest.raises(ValidationError):
            InterpretationResponse(
                supports_hypothesis=True,
                confidence=-0.1,
                interpretation="This is a valid interpretation text",
            )

    def test_null_support_allowed(self) -> None:
        """Allow null for inconclusive evidence."""
        i = InterpretationResponse(
            supports_hypothesis=None,
            confidence=0.4,
            interpretation="Evidence is inconclusive for this hypothesis",
        )
        assert i.supports_hypothesis is None


class TestSynthesisResponse:
    """Tests for SynthesisResponse validation."""

    def test_rejects_vague_root_cause(self) -> None:
        """Reject root cause that's too short."""
        with pytest.raises(ValidationError):
            SynthesisResponse(
                root_cause="Bad data",
                confidence=0.8,
                supporting_evidence=["Evidence 1"],
                recommendations=["Fix it"],
            )

    def test_allows_null_root_cause(self) -> None:
        """Allow null root cause for inconclusive investigations."""
        s = SynthesisResponse(
            root_cause=None,
            confidence=0.3,
            supporting_evidence=[],
            recommendations=["Collect more data"],
        )
        assert s.root_cause is None

    def test_requires_recommendations(self) -> None:
        """Require at least one recommendation."""
        with pytest.raises(ValidationError):
            SynthesisResponse(
                root_cause=None,
                confidence=0.3,
                supporting_evidence=[],
                recommendations=[],
            )
