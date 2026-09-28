"""The one way to start an investigation (docs/specs/0001_issue_chat.md §7.11).

Every run belongs to an issue. The starter resolves the issue it was given, or opens
one, then writes the run: the investigations row, the issue's run row and the card in
the issue's shared thread. Last, it starts the workflow with the issue linked, so the
outcome is always written back. The issue page, POST /investigations (UI, SDK, CLI,
notebook), both webhooks and the EE rule action all start runs here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog

from dataing.adapters.db.issue_threads import IssueThreadRepository
from dataing.adapters.db.issues import get_run, open_issue, record_issue_event
from dataing.agents.prompts.brief import BRIEF_METADATA_KEY
from dataing.core.domain_types import AnomalyAlert, MetricSpec
from dataing.core.investigation.brief import (
    InvestigationBrief,
    brief_from_alert,
    brief_to_prompt,
)
from dataing.core.json_utils import to_json_string
from dataing.temporal.activities.publish_outcome import publish_outcome

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase
    from dataing.temporal.client import TemporalInvestigationClient

logger = structlog.get_logger()

TRIGGER_TYPES = frozenset({"human", "api", "webhook", "rule"})
MAX_TITLE = 500


class IssueNotFoundError(LookupError):
    """The issue to start on doesn't exist in the tenant."""


class DatasetRequiredError(ValueError):
    """Neither the request, the issue, the brief nor the alert names a table."""


class InvestigationStartFailed(RuntimeError):
    """The run was written but its workflow didn't start; the run shows why."""


@dataclass
class StartedInvestigation:
    """A run that started, and the issue it lives in."""

    investigation_id: UUID
    run_id: UUID
    issue_id: UUID
    issue_number: int
    run: dict[str, Any]
    status: str = "queued"


class InvestigationStarterService:
    """Starts investigations, each in an issue, for every entry point."""

    def __init__(
        self,
        db: AppDatabase,
        temporal_client: TemporalInvestigationClient | None = None,
    ) -> None:
        """Initialize the starter."""
        self.db = db
        self.temporal_client = temporal_client

    async def start(
        self,
        *,
        tenant_id: UUID,
        datasource_id: UUID,
        trigger_type: str,
        brief: InvestigationBrief | None = None,
        alert: AnomalyAlert | None = None,
        issue_id: UUID | None = None,
        dataset_id: str | None = None,
        actor_user_id: UUID | None = None,
        trigger_ref: dict[str, Any] | None = None,
        execution_profile: str = "standard",
        source_thread_id: UUID | None = None,
        parent_run_id: UUID | None = None,
        source_provider: str | None = None,
    ) -> StartedInvestigation:
        """Start a run in an issue: the given one, or one opened for it.

        Args:
            tenant_id: The tenant.
            datasource_id: The datasource the run queries, already resolved.
            trigger_type: human, api, webhook or rule.
            brief: What the run starts from. Built from the alert when not given.
            alert: The alert that triggered it (SDK, webhooks, rules). Built from the
                brief when not given.
            issue_id: The issue to run in; without one, an issue is opened.
            dataset_id: The table to investigate, if the issue has none.
            actor_user_id: The person who started it; None for API keys and webhooks.
            trigger_ref: What triggered it, recorded on the run row.
            execution_profile: safe, standard or deep.
            source_thread_id: The thread the brief was drafted in.
            parent_run_id: The run this one continues.
            source_provider: For an issue this opens, the integration it came from.

        Raises:
            RuntimeError: Temporal isn't configured.
            IssueNotFoundError: issue_id isn't an issue of the tenant.
            DatasetRequiredError: Nothing names a table to investigate.
            InvestigationStartFailed: The workflow didn't start; the run shows why.
        """
        if self.temporal_client is None:
            raise RuntimeError("Temporal client not configured")
        if trigger_type not in TRIGGER_TYPES:
            raise ValueError(f"Unknown trigger type {trigger_type!r}")
        if brief is None:
            if alert is None:
                raise ValueError("A brief or an alert is required")
            brief = brief_from_alert(alert, datasource_id)
        brief = brief.model_copy(
            update={"scope": brief.scope.model_copy(update={"datasource_id": datasource_id})}
        )

        existing = await self._issue(tenant_id, issue_id) if issue_id else None
        dataset = (
            dataset_id
            or (existing["dataset_id"] if existing else None)
            or next(iter(brief.scope.tables), None)
            or (alert.dataset_ids[0] if alert and alert.dataset_ids else None)
        )
        if not dataset:
            raise DatasetRequiredError(
                "Name a table to investigate: the issue, the brief's scope tables and the "
                "alert have none"
            )
        issue = existing or await open_issue(
            self.db,
            tenant_id=tenant_id,
            title=_title(brief.symptom),
            severity=alert.severity if alert else None,
            dataset_id=dataset,
            created_by=actor_user_id,
            author_type="human" if actor_user_id else "integration",
            source_provider=source_provider,
        )

        brief_json = brief.model_dump(mode="json", by_alias=True)
        if alert is None:
            alert = _alert_from_brief(brief, dataset=dataset, issue=issue)
        alert_data = {
            **alert.model_dump(mode="json"),
            "datasource_id": str(datasource_id),
            "issue_id": str(issue["id"]),
            "brief": brief_json,
        }
        investigation_id = uuid4()
        await self.db.execute(
            "INSERT INTO investigations (id, tenant_id, alert, created_by) VALUES ($1, $2, $3, $4)",
            investigation_id,
            tenant_id,
            to_json_string(alert_data),
            actor_user_id,
        )
        run_row = await self.db.execute_returning(
            """
            INSERT INTO issue_investigation_runs (
                issue_id, investigation_id, trigger_type, trigger_ref, brief,
                source_thread_id, parent_run_id, execution_profile, approval_status
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
            """,
            issue["id"],
            investigation_id,
            trigger_type,
            to_json_string(trigger_ref or {}),
            to_json_string(brief_json),
            source_thread_id,
            parent_run_id,
            execution_profile,
            "approved" if execution_profile == "deep" else None,
        )
        if run_row is None:
            raise RuntimeError("Failed to create the investigation run")
        run_id: UUID = run_row["id"]
        await self._announce(
            issue_id=issue["id"],
            investigation_id=investigation_id,
            run_id=run_id,
            brief=brief,
            brief_json=brief_json,
            actor_user_id=actor_user_id,
            trigger_type=trigger_type,
            execution_profile=execution_profile,
            source_thread_id=source_thread_id,
            parent_run_id=parent_run_id,
        )

        try:
            await self.temporal_client.start_investigation(
                investigation_id=str(investigation_id),
                tenant_id=str(tenant_id),
                datasource_id=str(datasource_id),
                alert_data=alert_data,
                alert_summary=(
                    f"Investigation spawned from issue: {issue['title']}. "
                    f"Dataset: {dataset}. Symptom: {brief.symptom}"
                ),
            )
        except Exception as e:
            message = f"Couldn't start the investigation: {e}"
            logger.error("investigation_start_failed", error=str(e))
            await publish_outcome(
                self.db,
                {
                    "investigation_id": str(investigation_id),
                    "tenant_id": str(tenant_id),
                    "issue_id": str(issue["id"]),
                    "failure": {"code": "start_failed", "message": message, "step": "start"},
                },
            )
            raise InvestigationStartFailed(message) from e

        logger.info(
            "investigation_started",
            investigation_id=str(investigation_id),
            issue_id=str(issue["id"]),
            trigger_type=trigger_type,
        )
        run = await get_run(self.db, run_id)
        assert run is not None
        return StartedInvestigation(
            investigation_id=investigation_id,
            run_id=run_id,
            issue_id=issue["id"],
            issue_number=issue["number"],
            run=run,
        )

    async def _issue(self, tenant_id: UUID, issue_id: UUID) -> dict[str, Any]:
        issue = await self.db.fetch_one(
            """
            SELECT id, number, title, severity, dataset_id, created_at
            FROM issues WHERE id = $1 AND tenant_id = $2
            """,
            issue_id,
            tenant_id,
        )
        if issue is None:
            raise IssueNotFoundError(f"Issue {issue_id} not found")
        return issue

    async def _announce(
        self,
        *,
        issue_id: UUID,
        investigation_id: UUID,
        run_id: UUID,
        brief: InvestigationBrief,
        brief_json: dict[str, Any],
        actor_user_id: UUID | None,
        trigger_type: str,
        execution_profile: str,
        source_thread_id: UUID | None,
        parent_run_id: UUID | None,
    ) -> None:
        """Log the run on the issue and put its card in the shared thread."""
        await record_issue_event(
            self.db,
            issue_id,
            "investigation_spawned",
            actor_user_id,
            {
                "investigation_id": str(investigation_id),
                "run_id": str(run_id),
                "symptom": brief.symptom,
                "execution_profile": execution_profile,
                "trigger_type": trigger_type,
            },
        )
        threads = IssueThreadRepository(self.db)
        shared = await threads.ensure_shared_thread(issue_id)
        started_from = (
            " from a scratch chat" if source_thread_id and source_thread_id != shared["id"] else ""
        )
        await threads.append_message(
            shared["id"],
            # A run no person started (API key, webhook, rule) is dataing's
            author_kind="user" if actor_user_id else "system",
            kind="investigation",
            author_user_id=actor_user_id,
            body_md=f"Started an investigation{started_from}: {brief.symptom}",
            payload={
                "investigation_id": str(investigation_id),
                "run_id": str(run_id),
                "execution_profile": execution_profile,
                "trigger_type": trigger_type,
                "brief": brief_json,
                "source_thread_id": str(source_thread_id) if source_thread_id else None,
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
            },
        )
        await self.db.execute("UPDATE issues SET updated_at = NOW() WHERE id = $1", issue_id)


def _title(symptom: str) -> str:
    """Return the first line of a symptom as an issue title."""
    first = symptom.strip().splitlines()[0] if symptom.strip() else "Investigation"
    return first if len(first) <= MAX_TITLE else first[: MAX_TITLE - 1] + "…"


def _alert_from_brief(
    brief: InvestigationBrief, *, dataset: str, issue: dict[str, Any]
) -> AnomalyAlert:
    """Describe a brief as the alert its run starts from.

    The symptom is the metric the agents investigate. The issue's dataset comes first
    and the brief's other tables become reference tables; every prompt that renders
    the alert adds the brief as its "Team brief" section.
    """
    return AnomalyAlert(
        dataset_ids=[dataset] + [t for t in brief.scope.tables if t != dataset],
        metric_spec=MetricSpec(
            metric_type="description", expression=brief.symptom, display_name=issue["title"]
        ),
        anomaly_type="custom",
        expected_value=0.0,
        actual_value=0.0,
        deviation_pct=0.0,
        anomaly_date=issue["created_at"].date().isoformat(),
        severity=issue["severity"] or "medium",
        metadata={BRIEF_METADATA_KEY: brief_to_prompt(brief)},
    )
