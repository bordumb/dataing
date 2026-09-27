"""Unit tests for AgentClient.

One AgentClient serves every investigation in a process, across tenants. Any
conversation history carried from one LLM call into the next would leak one
tenant's schemas, alerts and query rows into another tenant's prompt.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from bond import BondAgent
from pydantic_ai import models
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelResponse,
    TextPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from dataing.adapters.datasource.types import (
    Catalog,
    Column,
    NormalizedType,
    QueryResult,
    Schema,
    SchemaResponse,
    SourceCategory,
    SourceType,
    Table,
)
from dataing.agents import client as client_module
from dataing.agents.client import AgentClient
from dataing.core.domain_types import (
    AnomalyAlert,
    Evidence,
    Hypothesis,
    HypothesisCategory,
    InvestigationContext,
    MetricSpec,
)

LlmCall = Callable[[AgentClient, str], Awaitable[object]]
RecordedRequests = list[list[ModelMessage]]


def _alert(tenant: str) -> AnomalyAlert:
    return AnomalyAlert(
        dataset_ids=[f"{tenant}.orders"],
        metric_spec=MetricSpec.from_column("row_count"),
        anomaly_type="row_count",
        expected_value=1000.0,
        actual_value=500.0,
        deviation_pct=50.0,
        anomaly_date="2026-09-01",
        severity="high",
    )


def _schema(tenant: str) -> SchemaResponse:
    orders = Table(
        name="orders",
        table_type="table",
        native_type="TABLE",
        native_path=f"{tenant}.orders",
        columns=[Column(name="id", data_type=NormalizedType.INTEGER, native_type="integer")],
    )
    return SchemaResponse(
        source_id=f"{tenant}-warehouse",
        source_type=SourceType.POSTGRESQL,
        source_category=SourceCategory.DATABASE,
        fetched_at=datetime(2026, 9, 1, tzinfo=UTC),
        catalogs=[Catalog(name="default", schemas=[Schema(name=tenant, tables=[orders])])],
    )


def _hypothesis(tenant: str) -> Hypothesis:
    return Hypothesis(
        id="h1",
        title=f"Upstream load into {tenant}.orders stalled",
        category=HypothesisCategory.UPSTREAM_DEPENDENCY,
        reasoning="Row count halved right after the nightly load window.",
        suggested_query=f"SELECT count(*) FROM {tenant}.orders LIMIT 10",
    )


async def _generate_hypotheses(client: AgentClient, tenant: str) -> object:
    context = InvestigationContext(schema=_schema(tenant))
    return await client.generate_hypotheses(_alert(tenant), context)


async def _generate_query(client: AgentClient, tenant: str) -> object:
    return await client.generate_query(_hypothesis(tenant), _schema(tenant), alert=_alert(tenant))


async def _interpret_evidence(client: AgentClient, tenant: str) -> object:
    results = QueryResult(
        columns=[{"name": "email", "data_type": "string"}],
        rows=[{"email": f"buyer@{tenant}.example"}],
        row_count=1,
    )
    sql = f"SELECT email FROM {tenant}.orders LIMIT 10"
    return await client.interpret_evidence(_hypothesis(tenant), sql, results)


async def _synthesize_findings(client: AgentClient, tenant: str) -> object:
    evidence = Evidence(
        hypothesis_id="h1",
        query=f"SELECT count(*) FROM {tenant}.orders LIMIT 10",
        result_summary=f"{tenant}.orders has 500 rows",
        row_count=1,
        supports_hypothesis=True,
        confidence=0.9,
        interpretation=f"Load into {tenant}.orders stopped at 03:14 UTC.",
    )
    return await client.synthesize_findings_raw(_alert(tenant), [evidence])


async def _counter_analyze(client: AgentClient, tenant: str) -> object:
    return await client.counter_analyze(
        synthesis={"root_cause": f"Load into {tenant}.orders stopped at 03:14 UTC"},
        evidence=[{"hypothesis_id": "h1", "interpretation": f"{tenant}.orders halved"}],
        hypotheses=[{"id": "h1", "title": f"Upstream load into {tenant}.orders stalled"}],
    )


_HYPOTHESES_REPLY: dict[str, Any] = {
    "hypotheses": [
        {
            "id": "h1",
            "title": "Upstream load stalled overnight",
            "category": "upstream_dependency",
            "reasoning": "Row count halved right after the nightly load window.",
            "suggested_query": "SELECT count(*) FROM orders LIMIT 10",
            "expected_if_true": "Fewer rows after 03:00 UTC",
            "expected_if_false": "Steady row counts all day",
        }
    ]
}
_QUERY_REPLY: dict[str, Any] = {
    "query": "SELECT count(*) FROM orders LIMIT 10",
    "explanation": "Counts rows.",
}
_INTERPRETATION_REPLY: dict[str, Any] = {
    "supports_hypothesis": True,
    "confidence": 0.9,
    "interpretation": "The nightly load stopped writing rows at 03:14 UTC, halving the table.",
    "causal_chain": "Load job timeout at 03:14 UTC -> no inserts -> row count halved",
    "key_findings": ["No rows inserted after 03:14 UTC"],
}
_SYNTHESIS_REPLY: dict[str, Any] = {
    "root_cause": "Nightly load job timed out at 03:14 UTC",
    "confidence": 0.9,
    "causal_chain": ["Load job timed out", "Row count halved"],
    "estimated_onset": "03:14 UTC",
    "affected_scope": "Downstream revenue dashboards",
    "supporting_evidence": ["No rows inserted after 03:14 UTC"],
    "recommendations": ["Re-run the nightly load job"],
}
_COUNTER_ANALYSIS_REPLY: dict[str, Any] = {
    "alternative_explanations": ["A source-side outage"],
    "weaknesses": ["Only one day of data checked"],
    "confidence_adjustment": -0.1,
    "recommendation": "accept",
}


def _install_recording_model(monkeypatch: pytest.MonkeyPatch, reply: str) -> RecordedRequests:
    """Swap AgentClient's Anthropic model for one that records every request."""
    requests: RecordedRequests = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        requests.append(list(messages))
        return ModelResponse(parts=[TextPart(reply)])

    model = FunctionModel(respond)
    monkeypatch.setattr(client_module, "AnthropicModel", lambda *args, **kwargs: model)
    # If the swap above ever stops applying, fail instead of calling Anthropic.
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)
    return requests


def _dump(messages: list[ModelMessage]) -> str:
    return ModelMessagesTypeAdapter.dump_json(messages).decode()


class TestAgentClientHistoryIsolation:
    """Every AgentClient LLM call starts from an empty conversation history."""

    @pytest.mark.parametrize(
        ("call", "reply"),
        [
            pytest.param(_generate_hypotheses, _HYPOTHESES_REPLY, id="generate_hypotheses"),
            pytest.param(_generate_query, _QUERY_REPLY, id="generate_query"),
            pytest.param(_interpret_evidence, _INTERPRETATION_REPLY, id="interpret_evidence"),
            pytest.param(_synthesize_findings, _SYNTHESIS_REPLY, id="synthesize_findings"),
            pytest.param(_counter_analyze, _COUNTER_ANALYSIS_REPLY, id="counter_analyze"),
        ],
    )
    async def test_second_call_does_not_see_first_call_messages(
        self,
        monkeypatch: pytest.MonkeyPatch,
        call: LlmCall,
        reply: dict[str, Any],
    ) -> None:
        """Test that a second call on one client sends none of the first call's messages."""
        requests = _install_recording_model(monkeypatch, json.dumps(reply))
        client = AgentClient(api_key="test-key")

        await call(client, "tenant_a")
        await call(client, "tenant_b")

        assert len(requests) == 2, "expected exactly one model request per call"
        first, second = requests
        assert "tenant_a" in _dump(first)
        assert "tenant_b" in _dump(second)
        assert "tenant_a" not in _dump(second), "tenant_a data leaked into tenant_b's call"
        assert [message.kind for message in second] == ["request"]

    def test_client_holds_no_bond_agents(self) -> None:
        """Test that the client keeps no BondAgent, since each one accumulates history."""
        client = AgentClient(api_key="test-key")

        held = [name for name, value in vars(client).items() if isinstance(value, BondAgent)]

        assert held == []
