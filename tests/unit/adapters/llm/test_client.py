"""Unit tests for AnthropicClient."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataing.adapters.llm.client import AnthropicClient
from dataing.core.domain_types import (
    AnomalyAlert,
    Hypothesis,
    HypothesisCategory,
    InvestigationContext,
    QueryResult,
    SchemaContext,
    TableSchema,
)
from dataing.core.exceptions import LLMError


class TestAnthropicClient:
    """Tests for AnthropicClient."""

    @pytest.fixture
    def client(self) -> AnthropicClient:
        """Return an AnthropicClient instance."""
        with patch("anthropic.AsyncAnthropic"):
            return AnthropicClient(api_key="test_api_key", model="claude-3-sonnet")

    @pytest.fixture
    def sample_alert(self) -> AnomalyAlert:
        """Return a sample anomaly alert."""
        return AnomalyAlert(
            dataset_id="public.orders",
            metric_name="row_count",
            expected_value=1000.0,
            actual_value=500.0,
            deviation_pct=50.0,
            anomaly_date="2024-01-15",
            severity="high",
        )

    @pytest.fixture
    def sample_context(self) -> InvestigationContext:
        """Return a sample investigation context."""
        schema = SchemaContext(
            tables=(
                TableSchema(
                    table_name="public.orders",
                    columns=("id", "total"),
                    column_types={"id": "integer", "total": "numeric"},
                ),
            )
        )
        return InvestigationContext(schema=schema)

    @pytest.fixture
    def sample_hypothesis(self) -> Hypothesis:
        """Return a sample hypothesis."""
        return Hypothesis(
            id="h001",
            title="Test Hypothesis",
            category=HypothesisCategory.DATA_QUALITY,
            reasoning="Test reasoning",
            suggested_query="SELECT 1",
        )

    def test_init(self, client: AnthropicClient) -> None:
        """Test client initialization."""
        assert client.model == "claude-3-sonnet"
        assert client.prompt_manager is not None

    def test_parse_hypotheses_from_json(self, client: AnthropicClient) -> None:
        """Test parsing hypotheses from JSON response."""
        response = """
        Here are the hypotheses:
        ```json
        [
            {
                "id": "h1",
                "title": "Test Hypothesis",
                "category": "data_quality",
                "reasoning": "Some reasoning",
                "suggested_query": "SELECT 1"
            }
        ]
        ```
        """

        result = client._parse_hypotheses(response)

        assert len(result) == 1
        assert result[0].id == "h1"
        assert result[0].title == "Test Hypothesis"
        assert result[0].category == HypothesisCategory.DATA_QUALITY

    def test_parse_hypotheses_from_raw_json(self, client: AnthropicClient) -> None:
        """Test parsing hypotheses from raw JSON response."""
        response = """
        [
            {
                "id": "h1",
                "title": "Test",
                "category": "upstream_dependency",
                "reasoning": "Reason",
                "suggested_query": "SELECT 1"
            }
        ]
        """

        result = client._parse_hypotheses(response)

        assert len(result) == 1
        assert result[0].category == HypothesisCategory.UPSTREAM_DEPENDENCY

    def test_parse_hypotheses_handles_invalid_category(
        self,
        client: AnthropicClient,
    ) -> None:
        """Test that invalid categories default to DATA_QUALITY."""
        response = """
        [{"id": "h1", "title": "Test", "category": "invalid_cat", "reasoning": "R", "suggested_query": "S"}]
        """

        result = client._parse_hypotheses(response)

        assert result[0].category == HypothesisCategory.DATA_QUALITY

    def test_parse_hypotheses_raises_on_no_json(
        self,
        client: AnthropicClient,
    ) -> None:
        """Test that missing JSON raises LLMError."""
        response = "No JSON here, just text."

        with pytest.raises(LLMError) as exc_info:
            client._parse_hypotheses(response)

        assert "No JSON found" in str(exc_info.value)

    def test_parse_hypotheses_raises_on_invalid_json(
        self,
        client: AnthropicClient,
    ) -> None:
        """Test that invalid JSON raises LLMError."""
        response = "no json here at all"

        with pytest.raises(LLMError) as exc_info:
            client._parse_hypotheses(response)

        assert "No JSON found" in str(exc_info.value)

    def test_extract_sql_from_code_block(self, client: AnthropicClient) -> None:
        """Test extracting SQL from code block."""
        response = """
        Here is the query:
        ```sql
        SELECT * FROM users LIMIT 10
        ```
        """

        result = client._extract_sql(response)

        assert result == "SELECT * FROM users LIMIT 10"

    def test_extract_sql_from_generic_code_block(
        self,
        client: AnthropicClient,
    ) -> None:
        """Test extracting SQL from generic code block."""
        response = """
        ```
        SELECT COUNT(*) FROM orders
        ```
        """

        result = client._extract_sql(response)

        assert result == "SELECT COUNT(*) FROM orders"

    def test_extract_sql_from_plain_text(self, client: AnthropicClient) -> None:
        """Test extracting SQL from plain text response."""
        response = "SELECT id FROM users LIMIT 5"

        result = client._extract_sql(response)

        assert result == "SELECT id FROM users LIMIT 5"

    def test_parse_interpretation_from_json(self, client: AnthropicClient) -> None:
        """Test parsing interpretation from JSON response."""
        response = """
        ```json
        {
            "supports_hypothesis": true,
            "confidence": 0.85,
            "interpretation": "Evidence supports the hypothesis"
        }
        ```
        """

        result = client._parse_interpretation(response)

        assert result["supports_hypothesis"] is True
        assert result["confidence"] == 0.85
        assert "Evidence supports" in result["interpretation"]

    def test_parse_interpretation_handles_raw_json(
        self,
        client: AnthropicClient,
    ) -> None:
        """Test parsing interpretation from raw JSON."""
        response = (
            '{"supports_hypothesis": false, "confidence": 0.2, "interpretation": "Not supported"}'
        )

        result = client._parse_interpretation(response)

        assert result["supports_hypothesis"] is False
        assert result["confidence"] == 0.2

    def test_parse_interpretation_defaults_on_invalid(
        self,
        client: AnthropicClient,
    ) -> None:
        """Test that invalid JSON returns defaults."""
        response = "Just some plain text interpretation."

        result = client._parse_interpretation(response)

        assert result["supports_hypothesis"] is None
        assert result["confidence"] == 0.5
        assert result["interpretation"] == response

    def test_parse_synthesis_from_json(self, client: AnthropicClient) -> None:
        """Test parsing synthesis from JSON response."""
        response = """
        ```json
        {
            "root_cause": "ETL job failed",
            "confidence": 0.9,
            "recommendations": ["Restart job", "Add monitoring"]
        }
        ```
        """

        result = client._parse_synthesis(response)

        assert result["root_cause"] == "ETL job failed"
        assert result["confidence"] == 0.9
        assert len(result["recommendations"]) == 2

    def test_parse_synthesis_defaults_on_invalid(
        self,
        client: AnthropicClient,
    ) -> None:
        """Test that invalid JSON returns defaults."""
        response = "Cannot determine root cause."

        result = client._parse_synthesis(response)

        assert result["root_cause"] is None
        assert result["confidence"] == 0.0
        assert "Unable to determine" in result["recommendations"][0]
