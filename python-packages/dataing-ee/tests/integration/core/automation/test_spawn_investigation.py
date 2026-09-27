"""Integration tests for the spawn_investigation automation action on the migrated schema."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from dataing_ee.core.automation.executor import ActionExecutor, ActionResult, ExecutionContext

from dataing.adapters.db.app_db import AppDatabase
from dataing.core.domain_types import AnomalyAlert
from dataing.services.investigation import InvestigationStarterService

pytestmark = pytest.mark.integration

RULE_ID = uuid4()


class RecordingTemporalClient:
    """Stands in for the Temporal server: records the workflows it is asked to start."""

    def __init__(self) -> None:
        self.started: list[dict[str, Any]] = []

    async def start_investigation(self, **kwargs: Any) -> None:
        self.started.append(kwargs)


async def _create_tenant(db: AppDatabase) -> UUID:
    tenant_id = uuid4()
    await db.execute(
        "INSERT INTO tenants (id, name, slug) VALUES ($1, $2, $3)",
        tenant_id,
        "Test Tenant",
        f"test-{tenant_id.hex[:12]}",
    )
    return tenant_id


async def _create_datasource(db: AppDatabase, tenant_id: UUID) -> UUID:
    datasource_id = uuid4()
    await db.execute(
        """INSERT INTO data_sources (id, tenant_id, name, type, connection_config_encrypted)
           VALUES ($1, $2, $3, 'postgresql', 'unused')""",
        datasource_id,
        tenant_id,
        f"warehouse-{datasource_id.hex[:8]}",
    )
    return datasource_id


async def _create_issue(
    db: AppDatabase, tenant_id: UUID, *, dataset_id: str | None = "public.orders"
) -> dict[str, Any]:
    """Store an issue and return its row, the issue data a rule acts on."""
    issue = await db.execute_returning(
        """INSERT INTO issues (tenant_id, number, title, description, severity, dataset_id)
           VALUES ($1, next_issue_number($1), $2, $3, 'high', $4)
           RETURNING *""",
        tenant_id,
        "Null spike in orders.customer_id",
        "customer_id is null on a quarter of today's orders",
        dataset_id,
    )
    assert issue is not None
    return issue


async def _spawn(
    db: AppDatabase,
    issue: dict[str, Any],
    temporal: RecordingTemporalClient,
    params: dict[str, Any] | None = None,
) -> ActionResult:
    ctx = ExecutionContext(
        db=db,
        tenant_id=issue["tenant_id"],
        issue_id=issue["id"],
        rule_id=RULE_ID,
        investigation_starter=InvestigationStarterService(db=db, temporal_client=temporal),
    )
    [result] = await ActionExecutor().execute_actions(
        [{"type": "spawn_investigation", "params": params or {}}], ctx, issue
    )
    return result


async def _investigation_count(db: AppDatabase, tenant_id: UUID) -> int:
    row = await db.fetch_one(
        "SELECT COUNT(*)::int AS count FROM investigations WHERE tenant_id = $1", tenant_id
    )
    assert row is not None
    count: int = row["count"]
    return count


async def test_spawn_starts_an_investigation_on_a_valid_anomaly_alert(
    migrated_db: AppDatabase,
) -> None:
    """The stored alert is an AnomalyAlert built from the issue, plus its datasource."""
    tenant_id = await _create_tenant(migrated_db)
    datasource_id = await _create_datasource(migrated_db, tenant_id)
    issue = await _create_issue(migrated_db, tenant_id)
    temporal = RecordingTemporalClient()

    result = await _spawn(migrated_db, issue, temporal)

    assert result.success, result.error
    investigation_id = UUID(result.result["investigation_id"])
    row = await migrated_db.fetch_one(
        "SELECT tenant_id, alert, status FROM investigations WHERE id = $1", investigation_id
    )
    assert row is not None
    assert (row["tenant_id"], row["status"]) == (tenant_id, "active")
    alert_data = json.loads(row["alert"])
    assert alert_data.pop("datasource_id") == str(datasource_id)
    alert = AnomalyAlert.model_validate(alert_data)
    assert alert.model_dump(mode="json") == alert_data
    assert alert.dataset_ids == ["public.orders"]
    assert alert.metric_spec.display_name == "Null spike in orders.customer_id"
    assert alert.severity == "high"
    assert alert.anomaly_date == issue["created_at"].date().isoformat()
    assert [(w["investigation_id"], w["datasource_id"]) for w in temporal.started] == [
        (str(investigation_id), str(datasource_id))
    ]


async def test_spawn_links_the_issue_and_reuses_its_investigation(
    migrated_db: AppDatabase,
) -> None:
    """A rule firing again on the same issue does not start a second investigation."""
    tenant_id = await _create_tenant(migrated_db)
    await _create_datasource(migrated_db, tenant_id)
    issue = await _create_issue(migrated_db, tenant_id)
    temporal = RecordingTemporalClient()

    first = await _spawn(migrated_db, issue, temporal, {"profile": "deep"})
    second = await _spawn(migrated_db, issue, temporal, {"profile": "deep"})

    assert first.success, first.error
    investigation_id = first.result["investigation_id"]
    assert second.success, second.error
    assert second.result == {"investigation_id": investigation_id, "already_exists": True}
    runs = await migrated_db.fetch_all(
        """SELECT investigation_id, trigger_type, trigger_ref, execution_profile
           FROM issue_investigation_runs WHERE issue_id = $1""",
        issue["id"],
    )
    assert [
        (
            str(run["investigation_id"]),
            run["trigger_type"],
            json.loads(run["trigger_ref"]),
            run["execution_profile"],
        )
        for run in runs
    ] == [(investigation_id, "rule", {"rule_id": str(RULE_ID)}, "deep")]
    assert len(temporal.started) == 1


async def test_spawn_runs_against_the_datasource_the_rule_names(
    migrated_db: AppDatabase,
) -> None:
    """With several datasources, the action's datasource_id param picks one."""
    tenant_id = await _create_tenant(migrated_db)
    await _create_datasource(migrated_db, tenant_id)
    chosen = await _create_datasource(migrated_db, tenant_id)
    issue = await _create_issue(migrated_db, tenant_id)
    temporal = RecordingTemporalClient()

    result = await _spawn(migrated_db, issue, temporal, {"datasource_id": str(chosen)})

    assert result.success, result.error
    assert [w["datasource_id"] for w in temporal.started] == [str(chosen)]


async def test_spawn_fails_when_no_single_datasource_applies(migrated_db: AppDatabase) -> None:
    """A tenant with several datasources needs the rule to name one."""
    tenant_id = await _create_tenant(migrated_db)
    await _create_datasource(migrated_db, tenant_id)
    await _create_datasource(migrated_db, tenant_id)
    issue = await _create_issue(migrated_db, tenant_id)
    temporal = RecordingTemporalClient()

    result = await _spawn(migrated_db, issue, temporal)

    assert not result.success
    assert "datasource" in (result.error or "")
    assert temporal.started == []
    assert await _investigation_count(migrated_db, tenant_id) == 0


async def test_spawn_rejects_another_tenants_datasource(migrated_db: AppDatabase) -> None:
    """A rule cannot point an investigation at a datasource outside its tenant."""
    tenant_id = await _create_tenant(migrated_db)
    await _create_datasource(migrated_db, tenant_id)
    foreign = await _create_datasource(migrated_db, await _create_tenant(migrated_db))
    issue = await _create_issue(migrated_db, tenant_id)
    temporal = RecordingTemporalClient()

    result = await _spawn(migrated_db, issue, temporal, {"datasource_id": str(foreign)})

    assert not result.success
    assert "datasource" in (result.error or "")
    assert temporal.started == []
    assert await _investigation_count(migrated_db, tenant_id) == 0


async def test_spawn_fails_when_the_issue_has_no_dataset(migrated_db: AppDatabase) -> None:
    """Investigations target a dataset; an issue without one cannot spawn."""
    tenant_id = await _create_tenant(migrated_db)
    await _create_datasource(migrated_db, tenant_id)
    issue = await _create_issue(migrated_db, tenant_id, dataset_id=None)
    temporal = RecordingTemporalClient()

    result = await _spawn(migrated_db, issue, temporal)

    assert not result.success
    assert "dataset" in (result.error or "")
    assert temporal.started == []
    assert await _investigation_count(migrated_db, tenant_id) == 0
