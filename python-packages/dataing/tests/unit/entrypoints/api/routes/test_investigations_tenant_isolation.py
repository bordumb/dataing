"""Tenant isolation tests for /investigations/{investigation_id} routes.

Every route keyed by an investigation ID must answer 404 when the investigation
belongs to another tenant (or does not exist), before it touches Temporal,
snapshot storage, or writes to the app database. The two cases return the same
body so a caller cannot probe for other tenants' investigation IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.entrypoints.api.routes.investigations import router
from dataing.temporal.client import InvestigationStatus, TemporalInvestigationClient
from dataing.temporal.workflows.investigation import InvestigationResult

CALLER_TENANT = UUID("aaaaaaaa-0000-0000-0000-000000000001")
OTHER_TENANT = UUID("bbbbbbbb-0000-0000-0000-000000000002")

# Minimal valid bodies, keyed by endpoint name, for routes that require one.
REQUEST_BODIES: dict[str, dict[str, Any]] = {
    "codify_investigation": {"format": "sql"},
}

INVESTIGATION_ROUTES = sorted(
    (method, route.path, route.name)
    for route in router.routes
    if isinstance(route, APIRoute) and "{investigation_id}" in route.path
    for method in route.methods
)


def _route_id(route: tuple[str, str, str]) -> str:
    method, _, name = route
    return f"{method} {name}"


class FakeAppDb:
    """AppDatabase stand-in holding which tenant owns each investigation.

    Honors a ``tenant_id = $2`` filter, so routes that scope their own
    investigations query are exercised faithfully.
    """

    def __init__(self, owners: dict[UUID, UUID]) -> None:
        """Initialize with investigation ID -> owning tenant ID."""
        self.owners = owners
        self.reads: list[str] = []
        self.writes: list[str] = []

    async def fetch_one(self, query: str, *args: Any) -> dict[str, Any] | None:
        """Return the investigation row visible to this query, if any."""
        self.reads.append(query)
        investigation_id = args[0]
        owner = self.owners.get(investigation_id)
        if owner is None:
            return None
        if "tenant_id = $2" in query and args[1] != owner:
            return None
        return {
            "id": investigation_id,
            "tenant_id": owner,
            "root_hash": None,
            "outcome": None,
            "alert": "{}",
            "status": "completed",
        }

    async def fetch_all(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Return no rows (no evidence recorded)."""
        return []

    async def execute(self, query: str, *args: Any) -> str:
        """Record the write so tests can assert none happened."""
        self.writes.append(query)
        return "INSERT 0 1"


@dataclass
class Harness:
    """Test client plus the collaborators each route may touch."""

    client: TestClient
    db: FakeAppDb
    temporal: AsyncMock
    snapshot_store: AsyncMock


def _completed_status(investigation_id: str) -> InvestigationStatus:
    """Return a finished investigation whose synthesis can be codified."""
    return InvestigationStatus(
        workflow_id=investigation_id,
        run_id="run-1",
        workflow_status="completed",
        result=InvestigationResult(
            investigation_id=investigation_id,
            status="completed",
            synthesis={
                "root_cause": "Row count dropped 40% after the upstream ETL job failed",
                "confidence": 0.9,
                "supporting_evidence": ["orders row count fell from 10k to 6k on 2026-01-10"],
                "recommendations": ["Re-run the upstream ETL job for 2026-01-10"],
                "metadata": {"dataset": "analytics.orders"},
            },
        ),
        current_step="completed",
        progress=1.0,
        is_complete=True,
        is_cancelled=False,
        is_awaiting_user=False,
    )


def _build_harness(
    owners: dict[UUID, UUID], scopes: tuple[str, ...] = ("read", "write")
) -> Harness:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[verify_api_key] = lambda: ApiKeyContext(
        key_id=uuid4(),
        tenant_id=CALLER_TENANT,
        tenant_slug="caller",
        tenant_name="Caller",
        user_id=uuid4(),
        scopes=list(scopes),
    )

    db = FakeAppDb(owners)
    temporal = AsyncMock(spec=TemporalInvestigationClient)
    temporal.get_status.side_effect = _completed_status
    snapshot_store = AsyncMock()
    snapshot_store.exists.return_value = True
    snapshot_store.retrieve.return_value = MagicMock(
        version="1", model_dump=MagicMock(return_value={})
    )

    app.state.app_db = db
    app.state.temporal_client = temporal
    app.state.snapshot_store = snapshot_store
    return Harness(TestClient(app), db, temporal, snapshot_store)


def _call(harness: Harness, route: tuple[str, str, str], investigation_id: UUID) -> Any:
    method, path, name = route
    url = "/api/v1" + path.replace("{investigation_id}", str(investigation_id)).replace(
        "{checkpoint}", "complete"
    )
    return harness.client.request(method, url, json=REQUEST_BODIES.get(name))


def test_sweep_covers_every_investigation_route() -> None:
    """The parametrized sweep must include every known investigation route."""
    swept = {name for _, _, name in INVESTIGATION_ROUTES}

    assert {
        "cancel_investigation",
        "get_investigation",
        "verify_investigation",
        "codify_investigation",
        "get_investigation_status",
        "stream_updates",
        "stream_events",
        "list_snapshots",
        "download_snapshot",
        "export_snapshot_archive",
    } <= swept


@pytest.mark.parametrize("route", INVESTIGATION_ROUTES, ids=_route_id)
@pytest.mark.parametrize("owner", [OTHER_TENANT, None], ids=["other-tenant", "missing"])
def test_investigation_not_owned_by_caller_returns_404(
    route: tuple[str, str, str], owner: UUID | None
) -> None:
    """Another tenant's (or a missing) investigation is a 404 with no side effects."""
    investigation_id = uuid4()
    harness = _build_harness({investigation_id: owner} if owner else {})

    response = _call(harness, route, investigation_id)

    assert response.status_code == 404
    assert response.json() == {"detail": f"Investigation not found: {investigation_id}"}
    assert harness.temporal.mock_calls == []
    assert harness.snapshot_store.mock_calls == []
    assert harness.db.writes == []


@pytest.mark.parametrize("route", INVESTIGATION_ROUTES, ids=_route_id)
def test_investigation_owned_by_caller_is_served(route: tuple[str, str, str]) -> None:
    """The owning tenant still gets through (guards against a vacuous 404)."""
    investigation_id = uuid4()
    harness = _build_harness({investigation_id: CALLER_TENANT})

    response = _call(harness, route, investigation_id)

    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    "route",
    [route for route in INVESTIGATION_ROUTES if route[0] in {"POST", "PUT", "PATCH", "DELETE"}],
    ids=_route_id,
)
def test_read_only_caller_is_refused_before_the_investigation_lookup(
    route: tuple[str, str, str],
) -> None:
    """Write routes check scope first: 403 whether or not the ID exists, and no lookup."""
    investigation_id = uuid4()
    harness = _build_harness({investigation_id: OTHER_TENANT}, scopes=("read",))

    response = _call(harness, route, investigation_id)

    assert response.status_code == 403
    assert harness.db.reads == []
