"""The investigation brief: what a thread hands to the manager (spec 0001 §7.7)."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from dataing.core.investigation.brief import (
    BriefDraft,
    DraftClaim,
    InvestigationBrief,
    brief_from_draft,
    brief_to_markdown,
    brief_to_prompt,
)


def test_minimal_brief_needs_only_a_symptom() -> None:
    """Everything but the symptom has a default."""
    brief = InvestigationBrief(symptom="Orders dropped")

    assert brief.version == 1
    assert brief.findings == []
    assert brief.scope.tables == []


def test_brief_limits_are_enforced() -> None:
    """Oversized briefs are rejected, not truncated."""
    with pytest.raises(ValidationError):
        InvestigationBrief(symptom="")
    with pytest.raises(ValidationError):
        InvestigationBrief(symptom="x", leads=["l"] * 11)
    with pytest.raises(ValidationError):
        InvestigationBrief(symptom="x", version=2)  # type: ignore[arg-type]


def test_time_window_round_trips_with_from_key() -> None:
    """The wire format uses "from"; it survives a round trip."""
    brief = InvestigationBrief.model_validate(
        {
            "symptom": "x",
            "scope": {
                "time_window": {"from": "2026-09-10T00:00:00Z", "to": "2026-09-16T00:00:00Z"}
            },
        }
    )

    dumped = brief.model_dump(mode="json", by_alias=True)
    assert dumped["scope"]["time_window"]["from"].startswith("2026-09-10")
    assert InvestigationBrief.model_validate(dumped) == brief


def test_draft_citations_resolve_to_messages_and_known_query_results() -> None:
    """#seq citations become message ids; unknown query result ids are dropped."""
    question_id, reply_id = uuid.uuid4(), uuid.uuid4()
    known_result = uuid.uuid4()
    draft = BriefDraft(
        symptom="Completed orders dropped about 30%",
        tables=["analytics.public.orders"],
        findings=[
            DraftClaim(
                statement="Only app_v2 orders dropped",
                source_seq=4,
                query_result_id=str(known_result),
            ),
            DraftClaim(statement="Made up", source_seq=99, query_result_id="not-a-uuid"),
        ],
        ruled_out=[DraftClaim(statement="Not regional", source_seq=2)],
        leads=["app_v2 deploy on the 14th"],
        notes="",
    )

    brief = brief_from_draft(
        draft,
        seq_to_message={2: question_id, 4: reply_id},
        known_query_results={known_result},
        datasource_id=None,
    )

    assert brief.findings[0].message_id == reply_id
    assert brief.findings[0].query_result_id == known_result
    assert brief.findings[1].message_id is None
    assert brief.findings[1].query_result_id is None
    assert brief.ruled_out[0].message_id == question_id
    assert brief.scope.tables == ["analytics.public.orders"]


@pytest.mark.parametrize(
    ("source_seq", "expected"),
    [
        (4, "shared"),
        ("4", "shared"),
        ("#4", "shared"),
        ("s4", "scratch"),
        ("#S4", "scratch"),
        ("s99", None),
        ("x4", None),
        ("s", None),
    ],
)
def test_scratch_citations_resolve_against_the_scratch_thread(
    source_seq: int | str, expected: str | None
) -> None:
    """A draft from a scratch chat cites shared messages as #n and scratch ones as #sn."""
    shared_id, scratch_id = uuid.uuid4(), uuid.uuid4()
    draft = BriefDraft(symptom="x", findings=[DraftClaim(statement="claim", source_seq=source_seq)])

    brief = brief_from_draft(
        draft,
        seq_to_message={4: shared_id},
        scratch_seq_to_message={4: scratch_id},
        known_query_results=set(),
        datasource_id=None,
    )

    ids = {"shared": shared_id, "scratch": scratch_id, None: None}
    assert brief.findings[0].message_id == ids[expected]


def test_scratch_citations_are_dropped_without_a_scratch_thread() -> None:
    """A shared-thread draft has no s-numbers to resolve."""
    draft = BriefDraft(symptom="x", findings=[DraftClaim(statement="claim", source_seq="s4")])

    brief = brief_from_draft(
        draft, seq_to_message={4: uuid.uuid4()}, known_query_results=set(), datasource_id=None
    )

    assert brief.findings[0].message_id is None


def test_prompt_text_separates_findings_exclusions_and_leads() -> None:
    """The manager sees facts, exclusions and leads as labelled sections."""
    brief = InvestigationBrief.model_validate(
        {
            "symptom": "Orders dropped",
            "findings": [{"statement": "Only app_v2"}],
            "ruled_out": [{"statement": "Not regional"}],
            "leads": ["app_v2 deploy"],
            "notes": "Dashboard counts completed only",
        }
    )

    text = brief_to_prompt(brief)

    assert "Symptom: Orders dropped" in text
    assert "Observed (treat as facts):\n- Only app_v2" in text
    assert "Ruled out (do not propose these):\n- Not regional" in text
    assert "Leads (test these first):\n- app_v2 deploy" in text
    assert "Dashboard counts completed only" in text


def test_markdown_rendering_for_the_thread() -> None:
    """The brief message shows a readable summary."""
    brief = InvestigationBrief(symptom="Orders dropped", leads=["app_v2 deploy"])

    markdown = brief_to_markdown(brief)

    assert markdown.startswith("**Investigation brief**")
    assert "app_v2 deploy" in markdown
