"""The team's brief reaches the manager and subagent prompts (spec 0001 §7.7).

The spawn route stores the brief's prompt text in the alert's metadata, so every
step that renders the alert also renders the brief.
"""

from __future__ import annotations

from datetime import UTC, datetime

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
from dataing.agents.prompts import hypothesis, query, synthesis
from dataing.agents.prompts.brief import team_brief_section
from dataing.core.domain_types import (
    AnomalyAlert,
    Evidence,
    Hypothesis,
    HypothesisCategory,
    InvestigationContext,
    MetricSpec,
)

BRIEF_TEXT = (
    "Symptom: Completed orders dropped\n\n"
    "Observed (treat as facts):\n- Only app_v2 orders dropped\n\n"
    "Ruled out (do not propose these):\n- Not region-specific"
)


def _alert(with_brief: bool = True) -> AnomalyAlert:
    return AnomalyAlert(
        dataset_ids=["analytics.orders"],
        metric_spec=MetricSpec(
            metric_type="description",
            expression="Completed orders dropped",
            display_name="Orders dropped",
        ),
        anomaly_type="custom",
        expected_value=0.0,
        actual_value=0.0,
        deviation_pct=0.0,
        anomaly_date="2026-09-14",
        severity="high",
        metadata={"brief": BRIEF_TEXT} if with_brief else None,
    )


def _context() -> InvestigationContext:
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
                                        name="status",
                                        data_type=NormalizedType.STRING,
                                        native_type="TEXT",
                                        nullable=True,
                                    )
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
    )
    return InvestigationContext(schema=schema, lineage=None)


def test_section_is_empty_without_a_brief() -> None:
    """Alerts from checks or webhooks have no brief and no section."""
    assert team_brief_section(_alert(with_brief=False)) == ""


def test_hypothesis_prompt_includes_the_brief() -> None:
    """The manager generates hypotheses knowing what's observed and ruled out."""
    prompt = hypothesis.build_user(_alert(), _context())

    assert "## Team brief" in prompt
    assert "Ruled out (do not propose these):\n- Not region-specific" in prompt


def test_query_prompt_includes_the_brief() -> None:
    """Each subagent writes its query knowing the team's findings."""
    test = Hypothesis(
        id="h1",
        title="app_v2 writes a different status",
        category=HypothesisCategory.DATA_QUALITY,
        reasoning="Only app_v2 dropped",
        suggested_query="SELECT 1",
    )

    prompt = query.build_user(test, _alert())

    assert "Only app_v2 orders dropped" in prompt


def test_synthesis_prompt_includes_the_brief() -> None:
    """Synthesis weighs evidence against what the team already established."""
    evidence = [
        Evidence(
            hypothesis_id="h1",
            query="SELECT 1",
            result_summary="1 row",
            row_count=1,
            supports_hypothesis=True,
            confidence=0.9,
            interpretation="Status values differ",
        )
    ]

    prompt = synthesis.build_user(_alert(), evidence)

    assert "## Team brief" in prompt
    assert "Only app_v2 orders dropped" in prompt


def test_prompts_without_a_brief_are_unchanged() -> None:
    """No brief, no section."""
    assert "Team brief" not in hypothesis.build_user(_alert(with_brief=False), _context())
