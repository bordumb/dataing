"""Unit tests for synthesis prompts with code changes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dataing.agents.prompts import synthesis
from dataing.core.domain_types import (
    AnomalyAlert,
    Evidence,
    MetricSpec,
    RelevantCodeChange,
)


class TestBuildCodeChangesSection:
    """Tests for _build_code_changes_section helper."""

    def test_empty_list_returns_empty_string(self) -> None:
        """Test that empty list returns empty string."""
        result = synthesis._build_code_changes_section([])
        assert result == ""

    def test_single_change_formatted_correctly(self) -> None:
        """Test that a single code change is formatted correctly."""
        changes = [
            RelevantCodeChange(
                commit_hash="abc12345def67890",
                author_name="Jane Developer",
                message="fix: update order calculations",
                committed_at=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
                affected_assets=["prod.analytics.orders"],
                relevance_score=1.0,
                relevance_reason="directly_affects_asset",
            )
        ]

        result = synthesis._build_code_changes_section(changes)

        assert "## Related Code Changes" in result
        assert "abc12345" in result
        assert "2026-01-15 10:30" in result
        assert "Jane Developer" in result
        assert "fix: update order calculations" in result

    def test_multiple_changes_all_shown(self) -> None:
        """Test that multiple code changes are all shown."""
        changes = [
            RelevantCodeChange(
                commit_hash="abc123",
                author_name="Dev 1",
                message="First commit",
                committed_at=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
                affected_assets=[],
                relevance_score=1.0,
                relevance_reason="directly_affects_asset",
            ),
            RelevantCodeChange(
                commit_hash="def456",
                author_name="Dev 2",
                message="Second commit",
                committed_at=datetime(2026, 1, 14, 9, 0, tzinfo=UTC),
                affected_assets=[],
                relevance_score=0.7,
                relevance_reason="affects_upstream_dependency",
            ),
        ]

        result = synthesis._build_code_changes_section(changes)

        assert "abc123" in result
        assert "def456" in result
        assert "Dev 1" in result
        assert "Dev 2" in result

    def test_null_fields_handled(self) -> None:
        """Test that null optional fields are handled gracefully."""
        changes = [
            RelevantCodeChange(
                commit_hash="xyz789",
                author_name=None,
                message=None,
                committed_at=None,
                affected_assets=[],
                relevance_score=0.4,
                relevance_reason="matches_file_path_pattern",
            )
        ]

        result = synthesis._build_code_changes_section(changes)

        assert "xyz789" in result
        assert "unknown" in result
        assert "No message" in result

    def test_long_message_truncated(self) -> None:
        """Test that long commit messages are truncated to 80 chars."""
        long_message = "x" * 150
        changes = [
            RelevantCodeChange(
                commit_hash="abc123",
                author_name="Dev",
                message=long_message,
                committed_at=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
                affected_assets=[],
                relevance_score=1.0,
                relevance_reason="directly_affects_asset",
            )
        ]

        result = synthesis._build_code_changes_section(changes)

        # Message should be truncated to 80 chars
        assert "x" * 80 in result
        assert "x" * 81 not in result


class TestBuildUser:
    """Tests for build_user function with code changes."""

    @pytest.fixture
    def sample_alert(self) -> AnomalyAlert:
        """Return a sample anomaly alert."""
        return AnomalyAlert(
            dataset_ids=["prod.analytics.orders"],
            metric_spec=MetricSpec(
                metric_type="column",
                expression="total_amount",
                display_name="Total Amount",
                columns_referenced=["total_amount"],
            ),
            anomaly_type="null_rate",
            expected_value=0.01,
            actual_value=0.15,
            deviation_pct=1400.0,
            anomaly_date="2026-01-15",
            severity="high",
        )

    @pytest.fixture
    def sample_evidence(self) -> list[Evidence]:
        """Return sample evidence."""
        return [
            Evidence(
                hypothesis_id="h1",
                query="SELECT COUNT(*) FROM orders WHERE total_amount IS NULL",
                result_summary="count=485",
                row_count=1,
                supports_hypothesis=True,
                confidence=0.85,
                interpretation="485 orders have NULL total_amount after 03:14 UTC",
            )
        ]

    def test_prompt_without_code_changes(
        self, sample_alert: AnomalyAlert, sample_evidence: list[Evidence]
    ) -> None:
        """Test that prompt is generated correctly without code changes."""
        result = synthesis.build_user(sample_alert, sample_evidence)

        assert "## Original Anomaly" in result
        assert "prod.analytics.orders" in result
        assert "## Investigation Findings" in result
        assert "## Related Code Changes" not in result

    def test_prompt_with_code_changes(
        self, sample_alert: AnomalyAlert, sample_evidence: list[Evidence]
    ) -> None:
        """Test that prompt includes code changes section when provided."""
        code_changes = [
            RelevantCodeChange(
                commit_hash="abc12345",
                author_name="Jane Dev",
                message="fix: update order total calculation",
                committed_at=datetime(2026, 1, 14, 15, 30, tzinfo=UTC),
                affected_assets=["prod.analytics.orders"],
                relevance_score=1.0,
                relevance_reason="directly_affects_asset",
            )
        ]

        result = synthesis.build_user(sample_alert, sample_evidence, code_changes)

        assert "## Original Anomaly" in result
        assert "## Related Code Changes" in result
        assert "abc12345" in result
        assert "Jane Dev" in result
        assert "fix: update order total calculation" in result

    def test_prompt_with_empty_code_changes(
        self, sample_alert: AnomalyAlert, sample_evidence: list[Evidence]
    ) -> None:
        """Test that empty code changes list doesn't add section."""
        result = synthesis.build_user(sample_alert, sample_evidence, code_changes=[])

        assert "## Related Code Changes" not in result

    def test_prompt_with_none_code_changes(
        self, sample_alert: AnomalyAlert, sample_evidence: list[Evidence]
    ) -> None:
        """Test that None code changes doesn't add section."""
        result = synthesis.build_user(sample_alert, sample_evidence, code_changes=None)

        assert "## Related Code Changes" not in result

    def test_code_changes_section_after_evidence(
        self, sample_alert: AnomalyAlert, sample_evidence: list[Evidence]
    ) -> None:
        """Test that code changes section appears after investigation findings."""
        code_changes = [
            RelevantCodeChange(
                commit_hash="abc123",
                author_name="Dev",
                message="test",
                committed_at=datetime(2026, 1, 14, 10, 0, tzinfo=UTC),
                affected_assets=[],
                relevance_score=1.0,
                relevance_reason="directly_affects_asset",
            )
        ]

        result = synthesis.build_user(sample_alert, sample_evidence, code_changes)

        findings_pos = result.find("## Investigation Findings")
        changes_pos = result.find("## Related Code Changes")
        synthesize_pos = result.find("Synthesize these findings")

        assert findings_pos < changes_pos < synthesize_pos


class TestBuildSystem:
    """Tests for build_system function."""

    def test_includes_code_change_guidance(self) -> None:
        """Test that system prompt includes guidance for code change root causes."""
        result = synthesis.build_system()

        assert "CODE CHANGES" in result
        assert "commit hash" in result.lower()
        assert "revert commit" in result.lower()

    def test_includes_fix_proposal_guidance(self) -> None:
        """Test that system prompt includes guidance for fix proposals."""
        result = synthesis.build_system()

        # Check fix proposal section exists
        assert "FIX PROPOSAL" in result
        assert "confidence > 0.7" in result.lower()

        # Check fix types are documented
        assert "sql_ddl" in result
        assert "sql_dml" in result
        assert "dbt_patch" in result
        assert "python_patch" in result
        assert "manual_instruction" in result

        # Check safety rules are included
        assert "DROP TABLE" in result
        assert "WHERE clause" in result

    def test_fix_proposal_maps_root_cause_to_fix_type(self) -> None:
        """Test that prompt includes mapping from root cause category to fix type."""
        result = synthesis.build_system()

        # Check fix type selection guidance
        assert "Schema issues" in result
        assert "Data quality" in result
        assert "Transformation logic" in result
