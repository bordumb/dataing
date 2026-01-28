"""Unit tests for hypothesis generation prompts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dataing.adapters.datasource.types import (
    Catalog,
    Column,
    NormalizedType,
    Schema,
    SchemaResponse,
    SourceCategory,
    SourceType,
    Table,
)
from dataing.agents.prompts import hypothesis
from dataing.core.domain_types import (
    AnomalyAlert,
    InvestigationContext,
    MetricSpec,
    RelevantCodeChange,
)


class TestBuildCodeChangesSection:
    """Tests for _build_code_changes_section helper."""

    def test_empty_list_returns_empty_string(self) -> None:
        """Test that empty list returns empty string."""
        result = hypothesis._build_code_changes_section([])
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

        result = hypothesis._build_code_changes_section(changes)

        assert "## Recent Code Changes (last 14 days)" in result
        assert "[abc12345]" in result
        assert "2026-01-15 10:30" in result
        assert "Jane Developer" in result
        assert "fix: update order calculations" in result
        assert "prod.analytics.orders" in result
        assert "directly_affects_asset" in result
        assert "score: 1.0" in result

    def test_multiple_changes_all_shown(self) -> None:
        """Test that multiple code changes are all shown."""
        changes = [
            RelevantCodeChange(
                commit_hash="abc123",
                author_name="Dev 1",
                message="First commit",
                committed_at=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
                affected_assets=["table1"],
                relevance_score=1.0,
                relevance_reason="directly_affects_asset",
            ),
            RelevantCodeChange(
                commit_hash="def456",
                author_name="Dev 2",
                message="Second commit",
                committed_at=datetime(2026, 1, 14, 9, 0, tzinfo=UTC),
                affected_assets=["table2"],
                relevance_score=0.7,
                relevance_reason="affects_upstream_dependency",
            ),
        ]

        result = hypothesis._build_code_changes_section(changes)

        assert "[abc123]" in result
        assert "[def456]" in result
        assert "Dev 1" in result
        assert "Dev 2" in result
        assert "First commit" in result
        assert "Second commit" in result

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

        result = hypothesis._build_code_changes_section(changes)

        assert "[xyz789]" in result
        assert "unknown" in result  # For date and author
        assert "No message" in result

    def test_long_message_truncated(self) -> None:
        """Test that long commit messages are truncated."""
        long_message = "x" * 200
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

        result = hypothesis._build_code_changes_section(changes)

        # Message should be truncated to 100 chars
        assert "x" * 100 in result
        assert "x" * 101 not in result

    def test_many_affected_assets_truncated(self) -> None:
        """Test that more than 5 affected assets shows count."""
        changes = [
            RelevantCodeChange(
                commit_hash="abc123",
                author_name="Dev",
                message="Many changes",
                committed_at=datetime(2026, 1, 15, 10, 0, tzinfo=UTC),
                affected_assets=[f"table{i}" for i in range(10)],
                relevance_score=1.0,
                relevance_reason="directly_affects_asset",
            )
        ]

        result = hypothesis._build_code_changes_section(changes)

        assert "table0" in result
        assert "table4" in result
        assert "(+5 more)" in result


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
    def sample_context(self) -> InvestigationContext:
        """Return a sample investigation context."""
        schema = SchemaResponse(
            source_id="warehouse",
            source_type=SourceType.POSTGRESQL,
            source_category=SourceCategory.DATABASE,
            fetched_at=datetime.now(UTC),
            catalogs=[
                Catalog(
                    name="default",
                    schemas=[
                        Schema(
                            name="analytics",
                            tables=[
                                Table(
                                    name="orders",
                                    table_type="table",
                                    native_type="TABLE",
                                    native_path="analytics.orders",
                                    columns=[
                                        Column(
                                            name="id",
                                            data_type=NormalizedType.INTEGER,
                                            native_type="INTEGER",
                                            nullable=False,
                                        ),
                                        Column(
                                            name="total_amount",
                                            data_type=NormalizedType.DECIMAL,
                                            native_type="DECIMAL(10,2)",
                                            nullable=True,
                                        ),
                                    ],
                                )
                            ],
                        )
                    ],
                )
            ],
        )
        return InvestigationContext(schema=schema, lineage=None)

    def test_prompt_without_code_changes(
        self, sample_alert: AnomalyAlert, sample_context: InvestigationContext
    ) -> None:
        """Test that prompt is generated correctly without code changes."""
        result = hypothesis.build_user(sample_alert, sample_context)

        assert "## Anomaly Alert" in result
        assert "prod.analytics.orders" in result
        assert "Total Amount" in result
        assert "## Available Schema" in result
        # No code changes section
        assert "## Recent Code Changes" not in result

    def test_prompt_with_code_changes(
        self, sample_alert: AnomalyAlert, sample_context: InvestigationContext
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

        result = hypothesis.build_user(sample_alert, sample_context, code_changes)

        assert "## Anomaly Alert" in result
        assert "## Recent Code Changes" in result
        assert "abc12345" in result
        assert "Jane Dev" in result
        assert "fix: update order total calculation" in result

    def test_prompt_with_empty_code_changes(
        self, sample_alert: AnomalyAlert, sample_context: InvestigationContext
    ) -> None:
        """Test that empty code changes list doesn't add section."""
        result = hypothesis.build_user(sample_alert, sample_context, code_changes=[])

        assert "## Recent Code Changes" not in result

    def test_prompt_with_none_code_changes(
        self, sample_alert: AnomalyAlert, sample_context: InvestigationContext
    ) -> None:
        """Test that None code changes doesn't add section."""
        result = hypothesis.build_user(sample_alert, sample_context, code_changes=None)

        assert "## Recent Code Changes" not in result

    def test_code_changes_section_after_schema(
        self, sample_alert: AnomalyAlert, sample_context: InvestigationContext
    ) -> None:
        """Test that code changes section appears after schema section."""
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

        result = hypothesis.build_user(sample_alert, sample_context, code_changes)

        schema_pos = result.find("## Available Schema")
        changes_pos = result.find("## Recent Code Changes")
        generate_pos = result.find("Generate hypotheses")

        assert schema_pos < changes_pos < generate_pos


class TestBuildSystem:
    """Tests for build_system function."""

    def test_includes_code_change_category(self) -> None:
        """Test that system prompt includes code_change category."""
        result = hypothesis.build_system()

        assert "code_change" in result
        assert "code deploy" in result
