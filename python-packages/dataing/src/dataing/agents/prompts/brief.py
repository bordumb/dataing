"""The team's investigation brief as a prompt section (docs/specs/0001_issue_chat.md §7.7).

A run started from an issue thread carries the brief's prompt text in its alert
metadata. Every prompt that renders the alert adds it, so the manager and each
subagent start from what the team already established.
"""

from __future__ import annotations

from dataing.core.domain_types import AnomalyAlert

BRIEF_METADATA_KEY = "brief"


def team_brief_section(alert: AnomalyAlert | None) -> str:
    """Return the "Team brief" prompt section, or "" when the alert has no brief."""
    if alert is None or not alert.metadata:
        return ""
    brief = alert.metadata.get(BRIEF_METADATA_KEY)
    if not isinstance(brief, str) or not brief.strip():
        return ""
    return (
        "\n## Team brief\n"
        "The team investigated this issue before starting you. Treat observed findings as "
        "facts, do not propose causes they ruled out, and test their leads first.\n\n"
        f"{brief.strip()}\n"
    )
