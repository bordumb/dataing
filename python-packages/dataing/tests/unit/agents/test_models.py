"""Tests for agent response models."""

import pytest
from pydantic import ValidationError

from dataing.agents.models import (
    HypothesisResponse,
    InterpretationResponse,
    QueryResponse,
    SynthesisResponse,
)
from dataing.core.domain_types import HypothesisCategory


class TestQueryValidation:
    """Tests for query validators on HypothesisResponse and QueryResponse."""

    # Happy path tests
    def test_valid_select_with_limit_hypothesis(self) -> None:
        """Test valid SELECT with LIMIT passes for HypothesisResponse."""
        response = HypothesisResponse(
            id="h1",
            title="Test hypothesis with valid query",
            category=HypothesisCategory.UPSTREAM_DEPENDENCY,
            reasoning="Testing query validation works correctly",
            suggested_query="SELECT * FROM users WHERE id = 1 LIMIT 100",
            expected_if_true="Results showing the issue",
            expected_if_false="No results indicating other cause",
        )
        assert "SELECT" in response.suggested_query.upper()

    def test_valid_select_with_limit_query_response(self) -> None:
        """Test valid SELECT with LIMIT passes for QueryResponse."""
        response = QueryResponse(
            query="SELECT id, name FROM users WHERE active = true LIMIT 50",
            explanation="Get active users",
        )
        assert "SELECT" in response.query.upper()

    def test_valid_select_with_subquery(self) -> None:
        """Test valid SELECT with subquery and LIMIT passes."""
        response = QueryResponse(
            query="SELECT * FROM orders WHERE user_id IN (SELECT id FROM users) LIMIT 100",
        )
        assert response.query is not None

    # Markdown stripping tests
    def test_markdown_sql_stripped(self) -> None:
        """Test query wrapped in ```sql ... ``` is stripped."""
        response = QueryResponse(
            query="```sql\nSELECT * FROM users LIMIT 10\n```",
        )
        assert not response.query.startswith("```")
        assert "SELECT" in response.query

    def test_markdown_uppercase_sql_stripped(self) -> None:
        """Test query wrapped in ```SQL ... ``` is stripped."""
        response = QueryResponse(
            query="```SQL\nSELECT * FROM users LIMIT 10\n```",
        )
        assert not response.query.startswith("```")

    def test_markdown_postgresql_stripped(self) -> None:
        """Test query wrapped in ```postgresql ... ``` is stripped."""
        response = QueryResponse(
            query="```postgresql\nSELECT * FROM users LIMIT 10\n```",
        )
        assert not response.query.startswith("```")

    def test_markdown_unclosed_block_handled(self) -> None:
        """Test unclosed markdown block is handled gracefully."""
        response = QueryResponse(
            query="```sql\nSELECT * FROM users LIMIT 10",
        )
        assert not response.query.startswith("```")
        assert "SELECT" in response.query

    # Validation error tests
    def test_missing_limit_raises_hypothesis(self) -> None:
        """Test missing LIMIT raises ValueError for HypothesisResponse."""
        with pytest.raises(ValidationError) as exc_info:
            HypothesisResponse(
                id="h1",
                title="Test hypothesis without LIMIT",
                category=HypothesisCategory.UPSTREAM_DEPENDENCY,
                reasoning="Testing that LIMIT is required",
                suggested_query="SELECT * FROM users",
                expected_if_true="Should not pass",
                expected_if_false="Should fail",
            )
        assert "LIMIT" in str(exc_info.value)

    def test_missing_limit_raises_query_response(self) -> None:
        """Test missing LIMIT raises ValueError for QueryResponse."""
        with pytest.raises(ValidationError) as exc_info:
            QueryResponse(query="SELECT * FROM users")
        assert "LIMIT" in str(exc_info.value)

    def test_query_response_requires_select(self) -> None:
        """Test QueryResponse without SELECT raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            QueryResponse(query="SHOW TABLES LIMIT 10")
        assert "SELECT" in str(exc_info.value)

    # Mutation blocking tests (parametrized)
    @pytest.mark.parametrize(
        "mutation_query",
        [
            "INSERT INTO users (name) VALUES ('test')",
            "UPDATE users SET name = 'test' WHERE id = 1",
            "DELETE FROM users WHERE id = 1",
            "DROP TABLE users",
            "TRUNCATE TABLE users",
            "ALTER TABLE users ADD COLUMN foo INT",
            "CREATE TABLE test (id INT)",
            "GRANT SELECT ON users TO public",
            "REVOKE SELECT ON users FROM public",
        ],
        ids=[
            "insert",
            "update",
            "delete",
            "drop",
            "truncate",
            "alter",
            "create",
            "grant",
            "revoke",
        ],
    )
    def test_mutation_statements_blocked_hypothesis(self, mutation_query: str) -> None:
        """Test mutation statements are blocked for HypothesisResponse."""
        with pytest.raises(ValidationError):
            HypothesisResponse(
                id="h1",
                title="Test mutation blocking",
                category=HypothesisCategory.UPSTREAM_DEPENDENCY,
                reasoning="Attempting dangerous query",
                suggested_query=mutation_query,
                expected_if_true="Should not pass",
                expected_if_false="Should fail",
            )
        # Test passes if ValidationError is raised (query is rejected)

    # False positive prevention tests
    def test_column_named_deleted_at_allowed(self) -> None:
        """Test column named 'deleted_at' is allowed (no false positive)."""
        response = QueryResponse(
            query="SELECT id, deleted_at FROM users WHERE deleted_at IS NULL LIMIT 100",
        )
        assert "deleted_at" in response.query

    def test_table_named_update_log_allowed(self) -> None:
        """Test table named 'update_log' is allowed (no false positive)."""
        response = QueryResponse(
            query="SELECT * FROM update_log WHERE id = 1 LIMIT 100",
        )
        assert "update_log" in response.query

    def test_column_named_created_by_allowed(self) -> None:
        """Test column named 'created_by' is allowed (no false positive)."""
        response = QueryResponse(
            query="SELECT id, created_by FROM records LIMIT 100",
        )
        assert "created_by" in response.query

    def test_column_named_inserted_at_allowed(self) -> None:
        """Test column named 'inserted_at' is allowed (no false positive)."""
        response = QueryResponse(
            query="SELECT inserted_at FROM events LIMIT 100",
        )
        assert "inserted_at" in response.query

    # Edge case tests
    def test_multi_statement_query_rejected(self) -> None:
        """Test multi-statement query is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            QueryResponse(query="SELECT 1 LIMIT 1; DROP TABLE users")
        assert "multi-statement" in str(exc_info.value).lower()

    def test_empty_query_after_markdown_strip_raises(self) -> None:
        """Test empty query after markdown strip raises ValueError."""
        with pytest.raises(ValidationError) as exc_info:
            QueryResponse(query="```sql\n```")
        error_str = str(exc_info.value).lower()
        assert "empty" in error_str or "parse" in error_str


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
                    "The 485 orphaned orders appeared after 03:14 UTC when the users table stopped."
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
                    "The 485 orphaned orders appeared after 03:14 UTC when the users table stopped."
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

    def test_code_change_category_accepted(self) -> None:
        """Test that code_change category is accepted as valid."""
        response = HypothesisResponse(
            id="h1",
            title="Recent code deploy broke the order calculation logic",
            category=HypothesisCategory.CODE_CHANGE,
            reasoning=(
                "The anomaly appeared shortly after a code deployment "
                "that modified the order processing pipeline"
            ),
            suggested_query="SELECT * FROM orders WHERE created_at > '2026-01-15' LIMIT 100",
            expected_if_true="Anomalous values appearing after deploy timestamp",
            expected_if_false="Values consistent before and after deploy",
        )
        assert response.category == HypothesisCategory.CODE_CHANGE
        assert response.category.value == "code_change"

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
