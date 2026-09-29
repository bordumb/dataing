"""Tests for the issue sidebar backend (docs/specs/0001_issue_chat.md §7.2).

Covers the transitions the UI may offer, PATCH clearing semantics (explicit
null clears, omitted fields stay), status and assignee validated together, and
the issue ``context`` round trip. The routes speak raw SQL, so a small fake
database interprets the handful of statements they issue.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.adapters.db import issues as issues_adapter
from dataing.core.auth.jwt import create_access_token
from dataing.core.auth.types import OrgRole
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.routes.issues import router, transition_options

TENANT_ID = uuid.uuid4()
MAYA = uuid.uuid4()
RAJ = uuid.uuid4()


def _auth(user_id: uuid.UUID = MAYA) -> dict[str, Any]:
    """Return request kwargs with a member JWT for TENANT_ID."""
    token = create_access_token(
        user_id=str(user_id), org_id=str(TENANT_ID), role=OrgRole.MEMBER.value, teams=[]
    )
    return {"headers": {"Authorization": f"Bearer {token}"}}


def _normalize(query: str) -> str:
    return " ".join(query.split())


class FakeIssueDb:
    """In-memory stand-in for AppDatabase that understands the issue routes' SQL."""

    def __init__(self) -> None:
        """Initialize empty tables."""
        self.issues: dict[uuid.UUID, dict[str, Any]] = {}
        self.labels: dict[uuid.UUID, list[str]] = defaultdict(list)
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.synthesized: set[uuid.UUID] = set()

    def add_issue(self, **fields: Any) -> dict[str, Any]:
        """Insert an issue row directly and return it."""
        now = datetime.now(UTC)
        row: dict[str, Any] = {
            "id": uuid.uuid4(),
            "tenant_id": TENANT_ID,
            "number": len(self.issues) + 1,
            "title": "Null spike in orders.customer_id",
            "description": None,
            "status": "open",
            "priority": None,
            "severity": None,
            "due_at": None,
            "dataset_id": None,
            "assignee_user_id": None,
            "acknowledged_by": None,
            "created_by_user_id": MAYA,
            "author_type": "human",
            "source_provider": None,
            "source_external_id": None,
            "source_external_url": None,
            "resolution_note": None,
            "context": "{}",
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
        }
        row.update(fields)
        self.issues[row["id"]] = row
        return row

    def event_types(self) -> list[str]:
        """Return the recorded event types in order."""
        return [event_type for event_type, _ in self.events]

    async def fetch_one(self, query: str, *args: Any) -> dict[str, Any] | None:
        """Answer single-row reads."""
        q = _normalize(query)
        if "next_issue_number" in q:
            return {"number": len(self.issues) + 1}
        if "FROM issue_investigation_runs" in q:
            return {"exists": 1} if args[0] in self.synthesized else None
        if "COUNT(*)" in q and "FROM issues" in q:
            return {"count": sum(1 for r in self.issues.values() if r["tenant_id"] == args[0])}
        if "FROM issues WHERE id = $1 AND tenant_id = $2" in q:
            row = self.issues.get(args[0])
            return dict(row) if row and row["tenant_id"] == args[1] else None
        raise AssertionError(f"unexpected fetch_one: {q}")

    async def fetch_all(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Answer multi-row reads."""
        q = _normalize(query)
        if "FROM issue_labels" in q:
            return [{"label": label} for label in sorted(self.labels[args[0]])]
        if "FROM issue_investigation_runs" in q:
            return [{"issue_id": i} for i in args[0] if i in self.synthesized]
        if "FROM issues" in q:
            rows = [dict(r) for r in self.issues.values() if r["tenant_id"] == args[0]]
            return sorted(rows, key=lambda r: r["updated_at"], reverse=True)
        raise AssertionError(f"unexpected fetch_all: {q}")

    async def execute(self, query: str, *args: Any) -> str:
        """Apply writes to labels and events."""
        q = _normalize(query)
        if q.startswith("INSERT INTO issue_events"):
            self.events.append((args[1], json.loads(args[3])))
        elif q.startswith("DELETE FROM issue_labels"):
            self.labels[args[0]] = []
        elif q.startswith("INSERT INTO issue_labels"):
            self.labels[args[0]].append(args[1])
        else:
            raise AssertionError(f"unexpected execute: {q}")
        return "OK"

    async def execute_returning(self, query: str, *args: Any) -> dict[str, Any] | None:
        """Apply issue INSERT and UPDATE statements."""
        q = _normalize(query)
        if q.startswith("INSERT INTO issues"):
            match = re.search(r"INSERT INTO issues \((.*?)\) VALUES", q)
            assert match
            columns = [c.strip() for c in match.group(1).split(",")]
            row = self.add_issue(**dict(zip(columns, args, strict=True)))
            return dict(row)
        if q.startswith("UPDATE issues"):
            set_clause = q.split(" SET ", 1)[1].split(" WHERE ", 1)[0]
            where = re.search(r"WHERE id = \$(\d+) AND tenant_id = \$(\d+)", q)
            assert where
            row = self.issues.get(args[int(where.group(1)) - 1])
            if not row or row["tenant_id"] != args[int(where.group(2)) - 1]:
                return None
            for column, value in re.findall(r"(\w+) = (\$\d+|NULL)", set_clause):
                row[column] = None if value == "NULL" else args[int(value[1:]) - 1]
            return dict(row)
        raise AssertionError(f"unexpected execute_returning: {q}")


class FakeThreadRepository:
    """Swallows the thread copy of each issue event."""

    def __init__(self, db: Any) -> None:
        """Initialize the fake."""

    async def append_event(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Do nothing."""
        return {}


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeIssueDb:
    """Return the fake database, with thread event copies disabled."""
    monkeypatch.setattr(issues_adapter, "IssueThreadRepository", FakeThreadRepository)
    return FakeIssueDb()


@pytest.fixture
def client(db: FakeIssueDb) -> TestClient:
    """Return a client for the issue routes over the fake database."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_app_db] = lambda: db
    return TestClient(app)


class TestTransitionOptions:
    """allowed_transitions and transition_requirements for each status."""

    @pytest.mark.parametrize(
        ("status", "allowed"),
        [
            ("open", ["triaged", "closed"]),
            ("triaged", ["in_progress", "blocked", "closed"]),
            ("in_progress", ["blocked", "resolved", "closed"]),
            ("blocked", ["in_progress", "resolved", "closed"]),
            ("resolved", ["open", "closed"]),
            ("closed", ["open"]),
        ],
    )
    def test_allowed_transitions_follow_the_state_machine(
        self, status: str, allowed: list[str]
    ) -> None:
        """Allowed moves are the structural transitions, in lifecycle order."""
        result, _ = transition_options(status, None, None, None, False)

        assert result == allowed

    def test_unowned_triaged_issue_needs_an_assignee_to_start(self) -> None:
        """In progress and blocked need an owner the issue does not have yet."""
        _, requirements = transition_options("triaged", None, None, None, False)

        assert requirements == {
            "in_progress": ["assignee_user_id"],
            "blocked": ["assignee_user_id"],
        }

    def test_acknowledged_issue_needs_nothing_to_start(self) -> None:
        """acknowledged_by satisfies the owner guard."""
        _, requirements = transition_options("triaged", None, uuid.uuid4(), None, False)

        assert requirements == {}

    def test_resolving_needs_a_note(self) -> None:
        """Without a note or a synthesized run, resolving needs a note."""
        _, requirements = transition_options("in_progress", uuid.uuid4(), None, None, False)

        assert requirements == {"resolved": ["resolution_note"]}

    def test_synthesized_run_satisfies_resolve(self) -> None:
        """A linked synthesized investigation stands in for the note."""
        _, requirements = transition_options("blocked", uuid.uuid4(), None, None, True)

        assert requirements == {}

    def test_existing_note_satisfies_resolve(self) -> None:
        """A note already on the issue satisfies the guard."""
        _, requirements = transition_options("in_progress", uuid.uuid4(), None, "fixed", False)

        assert requirements == {}


class TestIssueResponseShape:
    """Every IssueResponse carries transitions, requirements and context."""

    def test_get_includes_transitions_and_context(
        self, client: TestClient, db: FakeIssueDb
    ) -> None:
        """GET exposes the moves and what each needs."""
        issue = db.add_issue(status="triaged", context='{"column": "customer_id"}')

        body = client.get(f"/issues/{issue['id']}", **_auth()).json()

        assert body["allowed_transitions"] == ["in_progress", "blocked", "closed"]
        assert body["transition_requirements"] == {
            "in_progress": ["assignee_user_id"],
            "blocked": ["assignee_user_id"],
        }
        assert body["context"] == {"column": "customer_id"}

    def test_list_uses_linked_synthesis(self, client: TestClient, db: FakeIssueDb) -> None:
        """List items drop the note requirement when a run has a synthesis."""
        with_run = db.add_issue(status="in_progress", assignee_user_id=MAYA)
        without_run = db.add_issue(status="in_progress", assignee_user_id=MAYA)
        db.synthesized.add(with_run["id"])

        items = {i["id"]: i for i in client.get("/issues", **_auth()).json()["items"]}

        assert items[str(with_run["id"])]["transition_requirements"] == {}
        assert items[str(without_run["id"])]["transition_requirements"] == {
            "resolved": ["resolution_note"]
        }
        assert items[str(with_run["id"])]["allowed_transitions"] == [
            "blocked",
            "resolved",
            "closed",
        ]


class TestCreateContext:
    """Create accepts and persists the issue context."""

    def test_create_persists_context(self, client: TestClient, db: FakeIssueDb) -> None:
        """Context is stored as JSON and echoed back."""
        context = {"observed_at": "2026-09-27T14:05:00Z", "column": "customer_id"}

        response = client.post("/issues", json={"title": "Nulls", "context": context}, **_auth())

        assert response.status_code == 201
        body = response.json()
        assert body["context"] == context
        assert body["allowed_transitions"] == ["triaged", "closed"]
        stored = db.issues[uuid.UUID(body["id"])]["context"]
        assert json.loads(stored) == context

    def test_create_defaults_context_to_empty(self, client: TestClient) -> None:
        """No context means an empty object."""
        body = client.post("/issues", json={"title": "Nulls"}, **_auth()).json()

        assert body["context"] == {}

    def test_create_rejects_oversized_context(self, client: TestClient) -> None:
        """Context is a small hint, not a payload store."""
        response = client.post(
            "/issues", json={"title": "Nulls", "context": {"blob": "x" * 5000}}, **_auth()
        )

        assert response.status_code == 422


class TestPatchClearing:
    """Explicit null clears a column; an omitted field stays unchanged."""

    def test_null_clears_assignee(self, client: TestClient, db: FakeIssueDb) -> None:
        """Unassigning records an assigned event with no assignee."""
        issue = db.add_issue(status="triaged", assignee_user_id=RAJ)

        response = client.patch(
            f"/issues/{issue['id']}", json={"assignee_user_id": None}, **_auth()
        )

        assert response.status_code == 200
        assert response.json()["assignee_user_id"] is None
        assert db.issues[issue["id"]]["assignee_user_id"] is None
        assert db.events == [("assigned", {"assignee_user_id": None, "from": str(RAJ), "to": None})]

    def test_omitted_fields_stay(self, client: TestClient, db: FakeIssueDb) -> None:
        """Changing priority leaves the assignee alone."""
        issue = db.add_issue(assignee_user_id=RAJ, priority="P2")

        body = client.patch(f"/issues/{issue['id']}", json={"priority": "P0"}, **_auth()).json()

        assert body["priority"] == "P0"
        assert body["assignee_user_id"] == str(RAJ)
        assert db.events == [("priority_changed", {"from": "P2", "to": "P0"})]

    def test_null_clears_every_nullable_field(self, client: TestClient, db: FakeIssueDb) -> None:
        """All nullable sidebar fields can be cleared in one PATCH."""
        issue = db.add_issue(
            assignee_user_id=RAJ,
            acknowledged_by=RAJ,
            priority="P1",
            severity="high",
            due_at=datetime(2026, 10, 1, tzinfo=UTC),
            resolution_note="old note",
            description="desc",
            dataset_id="public.orders",
        )
        fields = [
            "assignee_user_id",
            "acknowledged_by",
            "priority",
            "severity",
            "due_at",
            "resolution_note",
            "description",
            "dataset_id",
        ]

        response = client.patch(f"/issues/{issue['id']}", json=dict.fromkeys(fields), **_auth())

        assert response.status_code == 200
        body = response.json()
        for field in fields:
            assert body[field] is None, field
            assert db.issues[issue["id"]][field] is None, field
        assert sorted(db.event_types()) == sorted(
            [
                "assigned",
                "acknowledged",
                "priority_changed",
                "severity_changed",
                "field_changed",
                "field_changed",
                "field_changed",
                "field_changed",
            ]
        )
        changed = {p["field"] for t, p in db.events if t == "field_changed"}
        assert changed == {"due_at", "resolution_note", "description", "dataset_id"}

    def test_title_cannot_be_cleared(self, client: TestClient, db: FakeIssueDb) -> None:
        """Title is required, so null is rejected."""
        issue = db.add_issue()

        response = client.patch(f"/issues/{issue['id']}", json={"title": None}, **_auth())

        assert response.status_code == 422

    def test_status_cannot_be_null(self, client: TestClient, db: FakeIssueDb) -> None:
        """Status is required, so null is rejected."""
        issue = db.add_issue()

        response = client.patch(f"/issues/{issue['id']}", json={"status": None}, **_auth())

        assert response.status_code == 422

    def test_unchanged_values_record_nothing(self, client: TestClient, db: FakeIssueDb) -> None:
        """Sending the current values is a no-op."""
        issue = db.add_issue(priority="P1", assignee_user_id=RAJ)

        response = client.patch(
            f"/issues/{issue['id']}",
            json={"priority": "P1", "assignee_user_id": str(RAJ)},
            **_auth(),
        )

        assert response.status_code == 200
        assert db.events == []


class TestPatchNewFields:
    """PATCH accepts dataset_id, due_at and context."""

    def test_sets_dataset_due_and_context(self, client: TestClient, db: FakeIssueDb) -> None:
        """New fields are stored, returned and logged."""
        issue = db.add_issue()

        response = client.patch(
            f"/issues/{issue['id']}",
            json={
                "dataset_id": "public.orders",
                "due_at": "2026-10-01T12:00:00Z",
                "context": {"column": "customer_id"},
            },
            **_auth(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["dataset_id"] == "public.orders"
        assert body["due_at"].startswith("2026-10-01T12:00:00")
        assert body["context"] == {"column": "customer_id"}
        assert json.loads(db.issues[issue["id"]]["context"]) == {"column": "customer_id"}
        changed = {p["field"]: p for t, p in db.events if t == "field_changed"}
        assert set(changed) == {"dataset_id", "due_at", "context"}
        assert changed["dataset_id"] == {"field": "dataset_id", "from": None, "to": "public.orders"}

    def test_null_context_resets_to_empty(self, client: TestClient, db: FakeIssueDb) -> None:
        """Context is NOT NULL, so clearing it stores an empty object."""
        issue = db.add_issue(context='{"column": "customer_id"}')

        body = client.patch(f"/issues/{issue['id']}", json={"context": None}, **_auth()).json()

        assert body["context"] == {}
        assert json.loads(db.issues[issue["id"]]["context"]) == {}

    def test_label_changes_are_logged(self, client: TestClient, db: FakeIssueDb) -> None:
        """Replacing labels logs each added and removed label."""
        issue = db.add_issue()
        db.labels[issue["id"]] = ["nulls", "orders"]

        body = client.patch(
            f"/issues/{issue['id']}", json={"labels": ["orders", "p0"]}, **_auth()
        ).json()

        assert body["labels"] == ["orders", "p0"]
        assert sorted(db.events, key=lambda e: e[0]) == [
            ("label_added", {"label": "p0"}),
            ("label_removed", {"label": "nulls"}),
        ]


class TestStatusWithAssignee:
    """Status and assignee in one PATCH are validated together."""

    def test_start_and_assign_in_one_patch(self, client: TestClient, db: FakeIssueDb) -> None:
        """Assign to me + in progress succeeds on an unowned issue."""
        issue = db.add_issue(status="triaged")

        response = client.patch(
            f"/issues/{issue['id']}",
            json={"status": "in_progress", "assignee_user_id": str(MAYA)},
            **_auth(),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "in_progress"
        assert body["assignee_user_id"] == str(MAYA)
        assert body["allowed_transitions"] == ["blocked", "resolved", "closed"]
        assert set(db.event_types()) == {"status_changed", "assigned"}

    def test_start_without_owner_is_rejected(self, client: TestClient, db: FakeIssueDb) -> None:
        """The guard still applies when no assignee is sent."""
        issue = db.add_issue(status="triaged")

        response = client.patch(f"/issues/{issue['id']}", json={"status": "in_progress"}, **_auth())

        assert response.status_code == 400
        assert db.issues[issue["id"]]["status"] == "triaged"
        assert db.events == []

    def test_guard_sees_cleared_assignee(self, client: TestClient, db: FakeIssueDb) -> None:
        """Clearing the only owner in the same PATCH fails the guard."""
        issue = db.add_issue(status="triaged", assignee_user_id=RAJ)

        response = client.patch(
            f"/issues/{issue['id']}",
            json={"status": "in_progress", "assignee_user_id": None},
            **_auth(),
        )

        assert response.status_code == 400
        assert db.issues[issue["id"]]["assignee_user_id"] == RAJ

    def test_resolve_with_note_in_one_patch(self, client: TestClient, db: FakeIssueDb) -> None:
        """A note sent with the move satisfies the resolve guard."""
        issue = db.add_issue(status="in_progress", assignee_user_id=MAYA)

        response = client.patch(
            f"/issues/{issue['id']}",
            json={"status": "resolved", "resolution_note": "Backfilled"},
            **_auth(),
        )

        assert response.status_code == 200
        assert response.json()["resolution_note"] == "Backfilled"

    def test_close_sets_closed_at_and_reopen_clears_it(
        self, client: TestClient, db: FakeIssueDb
    ) -> None:
        """closed_at follows the closed status."""
        issue = db.add_issue(status="open")

        closed = client.patch(f"/issues/{issue['id']}", json={"status": "closed"}, **_auth())
        reopened = client.patch(f"/issues/{issue['id']}", json={"status": "open"}, **_auth())

        assert closed.json()["closed_at"] is not None
        assert reopened.json()["closed_at"] is None
