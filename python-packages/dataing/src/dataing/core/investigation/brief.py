"""The investigation brief: what a thread hands to the manager (spec 0001 §7.7).

The agent drafts a BriefDraft from the thread, citing messages by their ``#seq``
number. A draft made from a scratch chat also sees the shared thread: shared
messages keep their ``#seq`` and scratch messages are numbered ``#s<seq>``, so a
citation is never ambiguous. brief_from_draft turns the draft into an
InvestigationBrief, keeping only citations that point at real messages and query
results of the threads it read. People edit the brief before it starts a run; the
manager reads it as prompt text.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BriefClaim(BaseModel):
    """A finding or exclusion, optionally backed by a thread message and a query."""

    statement: str = Field(..., min_length=1, max_length=500)
    message_id: UUID | None = None
    query_result_id: UUID | None = None


class TimeWindow(BaseModel):
    """The period the investigation should look at."""

    model_config = ConfigDict(populate_by_name=True)

    from_: datetime = Field(..., alias="from")
    to: datetime


class BriefScope(BaseModel):
    """Where the investigation should look."""

    datasource_id: UUID | None = None
    tables: list[str] = Field(default_factory=list, max_length=20)
    time_window: TimeWindow | None = None


class InvestigationBrief(BaseModel):
    """Everything the thread learned that the manager should start from."""

    version: Literal[1] = 1
    symptom: str = Field(..., min_length=1, max_length=1000)
    scope: BriefScope = Field(default_factory=BriefScope)
    findings: list[BriefClaim] = Field(default_factory=list, max_length=20)
    ruled_out: list[BriefClaim] = Field(default_factory=list, max_length=20)
    leads: list[str] = Field(default_factory=list, max_length=10)
    notes: str = Field(default="", max_length=2000)


class DraftClaim(BaseModel):
    """A claim as the drafting model writes it: cited by message number."""

    statement: str = Field(..., description="One sentence.")
    source_seq: int | str | None = Field(
        default=None,
        description=(
            "The #number of the thread message this came from; for a scratch-chat "
            'message, its s-number such as "s3".'
        ),
    )
    query_result_id: str | None = Field(
        default=None, description="The result id of the query that shows it, if any."
    )


class BriefDraft(BaseModel):
    """Structured output of the drafting model."""

    symptom: str = Field(..., description="What is wrong, in one or two sentences.")
    tables: list[str] = Field(default_factory=list, description="Tables to look at.")
    findings: list[DraftClaim] = Field(
        default_factory=list, description="What the thread established, with sources."
    )
    ruled_out: list[DraftClaim] = Field(
        default_factory=list, description="Causes the thread already ruled out."
    )
    leads: list[str] = Field(default_factory=list, description="Suspected causes to test first.")
    notes: str = Field(default="", description="Anything else the investigation needs.")


def _parse_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _cited_message(
    source_seq: int | str | None,
    shared: dict[int, UUID],
    scratch: dict[int, UUID],
) -> UUID | None:
    """Resolve a citation: 4, "4" or "#4" is shared; "s4" or "#s4" is scratch."""
    if source_seq is None or isinstance(source_seq, bool):
        return None
    if isinstance(source_seq, int):
        return shared.get(source_seq)
    text = source_seq.strip().lstrip("#").strip().lower()
    messages = shared
    if text.startswith("s"):
        messages, text = scratch, text[1:]
    if not text.isdigit():
        return None
    return messages.get(int(text))


def brief_from_draft(
    draft: BriefDraft,
    *,
    seq_to_message: dict[int, UUID],
    known_query_results: set[UUID],
    datasource_id: UUID | None,
    scratch_seq_to_message: dict[int, UUID] | None = None,
) -> InvestigationBrief:
    """Turn a model draft into a brief, dropping citations that don't resolve.

    Args:
        draft: The model's draft.
        seq_to_message: Message ids of the shared thread (or the only thread) by seq.
        known_query_results: Query result ids that belong to the threads read.
        datasource_id: The datasource the thread queried, if any.
        scratch_seq_to_message: Message ids of the scratch chat by seq, when the
            draft was made from one; its messages are cited as ``s<seq>``.
    """
    scratch = scratch_seq_to_message or {}

    def claim(item: DraftClaim) -> BriefClaim:
        result_id = _parse_uuid(item.query_result_id)
        return BriefClaim(
            statement=item.statement[:500],
            message_id=_cited_message(item.source_seq, seq_to_message, scratch),
            query_result_id=result_id if result_id in known_query_results else None,
        )

    return InvestigationBrief(
        symptom=draft.symptom[:1000] or "Investigate this issue",
        scope=BriefScope(datasource_id=datasource_id, tables=draft.tables[:20]),
        findings=[claim(c) for c in draft.findings[:20]],
        ruled_out=[claim(c) for c in draft.ruled_out[:20]],
        leads=[lead[:300] for lead in draft.leads[:10]],
        notes=draft.notes[:2000],
    )


def _section(title: str, items: list[str]) -> str:
    return f"{title}:\n" + "\n".join(f"- {item}" for item in items)


def brief_to_prompt(brief: InvestigationBrief) -> str:
    """Render a brief as prompt text for the manager and its subagents."""
    parts = [f"Symptom: {brief.symptom}"]
    if brief.scope.tables:
        parts.append(_section("Tables in scope", brief.scope.tables))
    if brief.scope.time_window:
        window = brief.scope.time_window
        parts.append(f"Time window: {window.from_.isoformat()} to {window.to.isoformat()}")
    if brief.findings:
        parts.append(_section("Observed (treat as facts)", [c.statement for c in brief.findings]))
    if brief.ruled_out:
        parts.append(
            _section("Ruled out (do not propose these)", [c.statement for c in brief.ruled_out])
        )
    if brief.leads:
        parts.append(_section("Leads (test these first)", brief.leads))
    if brief.notes:
        parts.append(f"Notes from the team: {brief.notes}")
    return "\n\n".join(parts)


def brief_to_markdown(brief: InvestigationBrief) -> str:
    """Render a brief for the thread."""
    lines = ["**Investigation brief**", "", f"**Symptom:** {brief.symptom}"]
    for title, items in (
        ("Findings", [c.statement for c in brief.findings]),
        ("Ruled out", [c.statement for c in brief.ruled_out]),
        ("Leads", brief.leads),
        ("Tables", brief.scope.tables),
    ):
        if items:
            lines += ["", f"**{title}**", *[f"- {item}" for item in items]]
    if brief.notes:
        lines += ["", f"**Notes:** {brief.notes}"]
    return "\n".join(lines)
