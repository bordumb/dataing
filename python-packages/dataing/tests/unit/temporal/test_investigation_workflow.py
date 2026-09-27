"""Unit tests for how InvestigationWorkflow hands failed evaluations to synthesis.

Runs the real parent workflow, child workflows, and query/synthesis activities
in-process via fixtures.temporal. Context, pattern, hypothesis-generation and
evidence-chain activities are stubbed.
"""

from __future__ import annotations

from collections.abc import Collection

import pytest
from fixtures.temporal import FakeAgent, FakeDatasource, InProcessTemporal, sql_for

from dataing.adapters.datasource.errors import ConnectionFailedError, QuerySyntaxError
from dataing.adapters.datasource.types import QueryResult
from dataing.core.domain_types import UntestedHypothesis
from dataing.entrypoints.temporal_worker import AdapterDatabase
from dataing.temporal.activities import (
    CheckPatternsInput,
    CheckPatternsResult,
    FinalizeEvidenceChainInput,
    FinalizeEvidenceChainResult,
    GatherContextInput,
    GatherContextResult,
    GenerateHypothesesInput,
    GenerateHypothesesResult,
    make_execute_query_activity,
    make_generate_query_activity,
    make_interpret_evidence_activity,
    make_synthesize_activity,
)
from dataing.temporal.workflows.investigation import InvestigationInput, InvestigationWorkflow

HYPOTHESES = [
    {"id": "h-1", "title": "Upstream ETL wrote NULL amounts"},
    {"id": "h-2", "title": "Schema change renamed amount"},
]

NULL_AMOUNTS = QueryResult(
    columns=[{"name": "order_id", "data_type": "integer"}],
    rows=[{"order_id": 7, "amount": None}],
    row_count=1,
)


async def gather_context(input: GatherContextInput) -> GatherContextResult:
    return GatherContextResult(schema_info={}, lineage_info=None)


async def check_patterns(input: CheckPatternsInput) -> CheckPatternsResult:
    return CheckPatternsResult(matched_patterns=[])


async def generate_hypotheses(input: GenerateHypothesesInput) -> GenerateHypothesesResult:
    return GenerateHypothesesResult(hypotheses=HYPOTHESES)


async def finalize_evidence_chain(
    input: FinalizeEvidenceChainInput,
) -> FinalizeEvidenceChainResult:
    return FinalizeEvidenceChainResult(root_hash="root", evidence_count=len(input.evidence))


async def _investigate(
    monkeypatch: pytest.MonkeyPatch,
    datasource: FakeDatasource,
    agent: FakeAgent,
    *,
    terminated: Collection[str] = (),
) -> None:
    async def get_adapter(datasource_id: str) -> FakeDatasource:
        return datasource

    temporal = InProcessTemporal(
        gather_context,
        check_patterns,
        generate_hypotheses,
        finalize_evidence_chain,
        make_generate_query_activity(adapter=agent),
        make_execute_query_activity(database=AdapterDatabase(get_adapter)),
        make_interpret_evidence_activity(adapter=agent),
        make_synthesize_activity(adapter=agent),
        terminated=terminated,
    )
    temporal.install(monkeypatch)

    await InvestigationWorkflow().run(
        InvestigationInput(
            investigation_id="inv-1",
            tenant_id="tenant-1",
            datasource_id="ds-1",
            alert_data={},
            alert_summary="orders.amount null rate spiked to 40%",
            enable_snapshots=False,
        )
    )

    assert temporal.escaped == []
    # The adapter turns these dicts into UntestedHypothesis: keep the keys in sync
    for synthesis in agent.synthesized:
        for untested in synthesis["untested_hypotheses"]:
            UntestedHypothesis.model_validate(untested)


async def test_failed_evaluation_reaches_synthesis_as_untested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hypothesis whose query failed is passed to synthesis as untested, with the error."""
    datasource = FakeDatasource(
        {
            sql_for("h-1"): NULL_AMOUNTS,
            sql_for("h-2"): QuerySyntaxError('column "amount" does not exist'),
        }
    )
    agent = FakeAgent()

    await _investigate(monkeypatch, datasource, agent)

    [synthesis] = agent.synthesized
    assert [e["hypothesis_id"] for e in synthesis["evidence"]] == ["h-1"]
    assert synthesis["untested_hypotheses"] == [
        {
            "hypothesis_id": "h-2",
            "title": "Schema change renamed amount",
            "error": 'Query execution failed: column "amount" does not exist',
        }
    ]


async def test_failed_interpretation_reaches_synthesis_as_untested_not_refuted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A hypothesis whose interpretation failed is untested, never refuted evidence."""
    datasource = FakeDatasource({sql_for("h-1"): NULL_AMOUNTS, sql_for("h-2"): NULL_AMOUNTS})
    agent = FakeAgent(interpretation_errors={"h-2": RuntimeError("LLM request timed out")})

    await _investigate(monkeypatch, datasource, agent)

    [synthesis] = agent.synthesized
    assert [e["hypothesis_id"] for e in synthesis["evidence"]] == ["h-1"]
    assert synthesis["untested_hypotheses"] == [
        {
            "hypothesis_id": "h-2",
            "title": "Schema change renamed amount",
            "error": "Evidence interpretation failed: LLM request timed out",
        }
    ]


async def test_datasource_down_reaches_synthesis_as_all_untested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When every query fails, synthesis gets no evidence and every hypothesis as untested."""
    down = ConnectionFailedError("connection refused")
    datasource = FakeDatasource({sql_for("h-1"): down, sql_for("h-2"): down})
    agent = FakeAgent()

    await _investigate(monkeypatch, datasource, agent)

    [synthesis] = agent.synthesized
    assert synthesis["evidence"] == []
    assert synthesis["untested_hypotheses"] == [
        {
            "hypothesis_id": hypothesis["id"],
            "title": hypothesis["title"],
            "error": "Query execution failed: connection refused",
        }
        for hypothesis in HYPOTHESES
    ]


async def test_terminated_evaluation_reaches_synthesis_as_untested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A child workflow terminated mid-evaluation leaves its hypothesis untested."""
    datasource = FakeDatasource({sql_for("h-1"): NULL_AMOUNTS, sql_for("h-2"): NULL_AMOUNTS})
    agent = FakeAgent()

    await _investigate(monkeypatch, datasource, agent, terminated={"wf-1-hypothesis-1"})

    [synthesis] = agent.synthesized
    assert [e["hypothesis_id"] for e in synthesis["evidence"]] == ["h-1"]
    assert synthesis["untested_hypotheses"] == [
        {
            "hypothesis_id": "h-2",
            "title": "Schema change renamed amount",
            "error": "Evaluation failed: Terminated",
        }
    ]
