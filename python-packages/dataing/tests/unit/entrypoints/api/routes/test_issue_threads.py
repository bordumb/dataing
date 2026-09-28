"""Tests for the issue thread API (docs/specs/0001_issue_chat.md §7.1).

Who may do what is decided in the handlers (thread kind, ownership, authorship,
and the write scope for asking the agent), so these tests pin it down directly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.core.auth.jwt import create_access_token
from dataing.core.auth.types import OrgRole
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.routes.issue_threads import (
    get_issue_thread_repository,
    router,
)

TENANT_ID = uuid.uuid4()
ISSUE_ID = uuid.uuid4()
MAYA = uuid.uuid4()
RAJ = uuid.uuid4()


def _auth(role: OrgRole, user_id: uuid.UUID) -> dict[str, Any]:
    """Return request kwargs with a JWT for a user of TENANT_ID."""
    token = create_access_token(
        user_id=str(user_id), org_id=str(TENANT_ID), role=role.value, teams=[]
    )
    return {"headers": {"Authorization": f"Bearer {token}"}}


class FakeThreads:
    """In-memory stand-in for IssueThreadRepository."""

    def __init__(self) -> None:
        """Initialize with one shared thread on ISSUE_ID."""
        self.threads: dict[uuid.UUID, dict[str, Any]] = {}
        self.messages: dict[uuid.UUID, dict[str, Any]] = {}
        self.running: dict[uuid.UUID, int] = {}
        self.snapshots: dict[uuid.UUID, dict[str, Any]] = {}
        self.shared = self._thread("shared", None)

    def _thread(self, kind: str, owner: uuid.UUID | None) -> dict[str, Any]:
        thread = {
            "id": uuid.uuid4(),
            "tenant_id": TENANT_ID,
            "issue_id": ISSUE_ID,
            "kind": kind,
            "owner_user_id": owner,
            "title": None,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        self.threads[thread["id"]] = thread
        return thread

    async def ensure_shared_thread(self, issue_id: uuid.UUID) -> dict[str, Any]:
        return self.shared

    async def create_scratch_thread(
        self, tenant_id: uuid.UUID, issue_id: uuid.UUID, owner: uuid.UUID, title: str | None
    ) -> dict[str, Any]:
        thread = self._thread("scratch", owner)
        thread["title"] = title
        return thread

    async def get_thread(self, thread_id: uuid.UUID) -> dict[str, Any] | None:
        return self.threads.get(thread_id)

    async def list_threads(self, issue_id: uuid.UUID, user_id: uuid.UUID | None) -> list[Any]:
        return [
            t
            for t in self.threads.values()
            if t["kind"] == "shared" or t["owner_user_id"] == user_id
        ]

    async def delete_thread(self, thread_id: uuid.UUID) -> None:
        self.threads.pop(thread_id)

    async def append_message(self, thread_id: uuid.UUID, **fields: Any) -> dict[str, Any]:
        now = datetime.now(UTC)
        seq = 1 + sum(1 for m in self.messages.values() if m["thread_id"] == thread_id)
        message = {
            "id": uuid.uuid4(),
            "tenant_id": TENANT_ID,
            "thread_id": thread_id,
            "seq": seq,
            "rev": seq,
            "author_kind": fields["author_kind"],
            "author_user_id": fields.get("author_user_id"),
            "requested_by_user_id": fields.get("requested_by_user_id"),
            "request_message_id": fields.get("request_message_id"),
            "kind": fields["kind"],
            "body_md": fields.get("body_md", ""),
            "payload": fields.get("payload") or {},
            "status": fields.get("status", "complete"),
            "asks_agent": fields.get("asks_agent", False),
            "reply_to_id": fields.get("reply_to_id"),
            "created_at": now,
            "updated_at": now,
            "touched_at": now,
            "edited_at": None,
            "deleted_at": None,
        }
        self.messages[message["id"]] = message
        return message

    async def get_message(self, message_id: uuid.UUID) -> dict[str, Any] | None:
        return self.messages.get(message_id)

    async def update_message(self, message_id: uuid.UUID, **fields: Any) -> dict[str, Any]:
        message = self.messages[message_id]
        if fields.get("body_md") is not None:
            message["body_md"] = fields["body_md"]
        if fields.get("edited"):
            message["edited_at"] = datetime.now(UTC)
        if fields.get("status") is not None:
            message["status"] = fields["status"]
        if fields.get("payload") is not None:
            message["payload"] = fields["payload"]
        return message

    async def soft_delete_message(self, message_id: uuid.UUID) -> dict[str, Any]:
        message = self.messages[message_id]
        message["deleted_at"] = datetime.now(UTC)
        message["body_md"] = ""
        return message

    async def list_messages(
        self, thread_id: uuid.UUID, *, after_seq: int = 0, limit: int = 200
    ) -> list[dict[str, Any]]:
        rows = [
            m
            for m in self.messages.values()
            if m["thread_id"] == thread_id and m["seq"] > after_seq
        ]
        return sorted(rows, key=lambda m: m["seq"])[:limit]

    async def count_running_turns(self, user_id: uuid.UUID) -> int:
        return self.running.get(user_id, 0)

    async def append_event(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    async def get_messages(self, message_ids: list[uuid.UUID]) -> list[dict[str, Any]]:
        return [self.messages[i] for i in message_ids if i in self.messages]

    async def publish_messages(
        self,
        shared_thread_id: uuid.UUID,
        *,
        source_thread_id: uuid.UUID,
        author_user_id: uuid.UUID,
        body_md: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.published_from = messages
        return await self.append_message(
            shared_thread_id,
            author_kind="user",
            kind="published",
            author_user_id=author_user_id,
            body_md=body_md,
            payload={
                "source_thread_id": str(source_thread_id),
                "source_message_ids": [str(m["id"]) for m in messages],
            },
        )

    async def get_query_result(self, result_id: uuid.UUID) -> dict[str, Any] | None:
        snapshot = self.snapshots.get(result_id)
        if snapshot is None:
            return None
        message = self.messages[snapshot["message_id"]]
        return {**snapshot, "thread_id": message["thread_id"]}


@pytest.fixture
def threads() -> FakeThreads:
    """Return the fake repository."""
    return FakeThreads()


@pytest.fixture
def client(threads: FakeThreads) -> TestClient:
    """Return a client for the thread routes over the fake repository."""
    db = AsyncMock()
    db.fetch_one.return_value = {"id": ISSUE_ID, "tenant_id": TENANT_ID}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_app_db] = lambda: db
    app.dependency_overrides[get_issue_thread_repository] = lambda: threads
    from dataing.entrypoints.api.routes.issue_threads import get_thread_agent

    app.dependency_overrides[get_thread_agent] = lambda: None
    return TestClient(app)


def _messages_url(thread_id: uuid.UUID) -> str:
    return f"/issues/{ISSUE_ID}/threads/{thread_id}/messages"


class TestSharedThread:
    """Comments in the shared thread are open to viewers; asking the agent is not."""

    def test_viewer_can_comment(self, client: TestClient, threads: FakeThreads) -> None:
        """A viewer's comment is stored as a user comment."""
        response = client.post(
            _messages_url(threads.shared["id"]),
            json={"body_md": "looks like app_v2"},
            **_auth(OrgRole.VIEWER, RAJ),
        )

        assert response.status_code == 201
        body = response.json()
        assert (body["kind"], body["author_kind"], body["asks_agent"]) == (
            "comment",
            "user",
            False,
        )
        assert body["author_user_id"] == str(RAJ)

    def test_viewer_cannot_ask_the_agent(self, client: TestClient, threads: FakeThreads) -> None:
        """Asking the agent runs queries, so it needs the write scope."""
        response = client.post(
            _messages_url(threads.shared["id"]),
            json={"body_md": "@agent is it every region?", "ask_agent": True},
            **_auth(OrgRole.VIEWER, RAJ),
        )

        assert response.status_code == 403
        assert threads.messages == {}

    def test_member_can_ask_the_agent(self, client: TestClient, threads: FakeThreads) -> None:
        """A member's question is stored with asks_agent set."""
        response = client.post(
            _messages_url(threads.shared["id"]),
            json={"body_md": "is it every region?", "ask_agent": True},
            **_auth(OrgRole.MEMBER, MAYA),
        )

        assert response.status_code == 201
        assert response.json()["asks_agent"] is True

    def test_fourth_running_turn_is_rejected(
        self, client: TestClient, threads: FakeThreads
    ) -> None:
        """A person may have at most three agent turns queued or streaming."""
        threads.running[MAYA] = 3

        response = client.post(
            _messages_url(threads.shared["id"]),
            json={"body_md": "one more", "ask_agent": True},
            **_auth(OrgRole.MEMBER, MAYA),
        )

        assert response.status_code == 429

    def test_shared_thread_cannot_be_deleted(
        self, client: TestClient, threads: FakeThreads
    ) -> None:
        """Only scratch threads can be deleted."""
        response = client.delete(
            f"/issues/{ISSUE_ID}/threads/{threads.shared['id']}", **_auth(OrgRole.ADMIN, MAYA)
        )

        assert response.status_code == 400

    def test_messages_list_in_order(self, client: TestClient, threads: FakeThreads) -> None:
        """Messages page by seq."""
        for text in ("a", "b", "c"):
            client.post(
                _messages_url(threads.shared["id"]),
                json={"body_md": text},
                **_auth(OrgRole.MEMBER, MAYA),
            )

        response = client.get(
            _messages_url(threads.shared["id"]),
            params={"after_seq": 1},
            **_auth(OrgRole.VIEWER, RAJ),
        )

        assert response.status_code == 200
        assert [m["body_md"] for m in response.json()["items"]] == ["b", "c"]


class TestScratchThreads:
    """Scratch threads are invisible to everyone but their owner."""

    def test_member_creates_a_scratch_thread(self, client: TestClient) -> None:
        """Creating one returns it, owned by the caller."""
        response = client.post(
            f"/issues/{ISSUE_ID}/threads",
            json={"title": "enum check"},
            **_auth(OrgRole.MEMBER, MAYA),
        )

        assert response.status_code == 201
        assert response.json()["kind"] == "scratch"
        assert response.json()["owner_user_id"] == str(MAYA)

    def test_listing_shows_only_own_scratch_threads(
        self, client: TestClient, threads: FakeThreads
    ) -> None:
        """Another person's scratch thread is not listed."""
        threads._thread("scratch", RAJ)
        mine = threads._thread("scratch", MAYA)

        response = client.get(f"/issues/{ISSUE_ID}/threads", **_auth(OrgRole.MEMBER, MAYA))

        ids = [t["id"] for t in response.json()["items"]]
        assert ids == [str(threads.shared["id"]), str(mine["id"])]

    @pytest.mark.parametrize(
        ("method", "suffix"),
        [("get", "/messages"), ("post", "/messages"), ("delete", "")],
    )
    def test_other_peoples_scratch_threads_are_not_found(
        self, client: TestClient, threads: FakeThreads, method: str, suffix: str
    ) -> None:
        """Every route answers 404 for someone else's scratch thread, admins included."""
        theirs = threads._thread("scratch", RAJ)
        url = f"/issues/{ISSUE_ID}/threads/{theirs['id']}{suffix}"
        kwargs: dict[str, Any] = {"json": {"body_md": "hi"}} if method == "post" else {}

        response = getattr(client, method)(url, **kwargs, **_auth(OrgRole.ADMIN, MAYA))

        assert response.status_code == 404

    def test_owner_deletes_own_scratch_thread(
        self, client: TestClient, threads: FakeThreads
    ) -> None:
        """The owner can delete their scratch thread."""
        mine = threads._thread("scratch", MAYA)

        response = client.delete(
            f"/issues/{ISSUE_ID}/threads/{mine['id']}", **_auth(OrgRole.MEMBER, MAYA)
        )

        assert response.status_code == 204
        assert mine["id"] not in threads.threads

    def test_thread_from_another_issue_is_not_found(
        self, client: TestClient, threads: FakeThreads
    ) -> None:
        """A thread id only works under its own issue."""
        response = client.get(
            f"/issues/{uuid.uuid4()}/threads/{threads.shared['id']}/messages",
            **_auth(OrgRole.MEMBER, MAYA),
        )

        assert response.status_code == 404


class TestEditingMessages:
    """Only authors edit; authors or admins delete."""

    def _comment(self, client: TestClient, threads: FakeThreads) -> str:
        response = client.post(
            _messages_url(threads.shared["id"]),
            json={"body_md": "first draft"},
            **_auth(OrgRole.MEMBER, MAYA),
        )
        message_id: str = response.json()["id"]
        return message_id

    def test_author_edits_own_comment(self, client: TestClient, threads: FakeThreads) -> None:
        """The author's edit replaces the body and stamps edited_at."""
        message_id = self._comment(client, threads)

        response = client.patch(
            f"{_messages_url(threads.shared['id'])}/{message_id}",
            json={"body_md": "second draft"},
            **_auth(OrgRole.MEMBER, MAYA),
        )

        assert response.status_code == 200
        assert response.json()["body_md"] == "second draft"
        assert response.json()["edited_at"] is not None

    def test_others_cannot_edit(self, client: TestClient, threads: FakeThreads) -> None:
        """Even an admin can't edit someone else's words."""
        message_id = self._comment(client, threads)

        response = client.patch(
            f"{_messages_url(threads.shared['id'])}/{message_id}",
            json={"body_md": "rewritten"},
            **_auth(OrgRole.ADMIN, RAJ),
        )

        assert response.status_code == 403

    def test_admin_can_delete(self, client: TestClient, threads: FakeThreads) -> None:
        """An admin may remove any comment."""
        message_id = self._comment(client, threads)

        response = client.delete(
            f"{_messages_url(threads.shared['id'])}/{message_id}", **_auth(OrgRole.ADMIN, RAJ)
        )

        assert response.status_code == 204
        assert threads.messages[uuid.UUID(message_id)]["deleted_at"] is not None

    def test_other_member_cannot_delete(self, client: TestClient, threads: FakeThreads) -> None:
        """A member can't delete someone else's comment."""
        message_id = self._comment(client, threads)

        response = client.delete(
            f"{_messages_url(threads.shared['id'])}/{message_id}", **_auth(OrgRole.MEMBER, RAJ)
        )

        assert response.status_code == 403


class ScriptedChanges:
    """changes_since that returns a scripted list of rows per poll."""

    def __init__(self, polls: list[list[dict[str, Any]]]) -> None:
        """Initialize with the rows each poll returns."""
        self.polls = polls
        self.cursors: list[int] = []

    async def changes_since(
        self, thread_id: uuid.UUID, *, after_rev: int, overlap_seconds: float = 5.0
    ) -> list[dict[str, Any]]:
        self.cursors.append(after_rev)
        return self.polls.pop(0) if self.polls else []


def _row(message_id: uuid.UUID, rev: int, body: str = "") -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "id": message_id,
        "thread_id": uuid.uuid4(),
        "seq": 1,
        "rev": rev,
        "author_kind": "agent",
        "author_user_id": None,
        "requested_by_user_id": None,
        "request_message_id": None,
        "kind": "agent_reply",
        "body_md": body,
        "payload": {},
        "status": "streaming",
        "asks_agent": False,
        "reply_to_id": None,
        "created_at": now,
        "updated_at": now,
        "edited_at": None,
        "deleted_at": None,
    }


async def _collect(changes: ScriptedChanges, after_rev: int = 0, polls: int = 4) -> list[Any]:
    from dataing.entrypoints.api.routes.issue_threads import thread_message_stream

    async def connected() -> bool:
        return False

    return [
        event
        async for event in thread_message_stream(
            changes,
            uuid.uuid4(),
            after_rev=after_rev,
            is_disconnected=connected,
            poll_interval=0,
            heartbeat_every=3,
            max_polls=polls,
        )
    ]


class TestThreadStream:
    """The stream sends each (id, rev) once and resumes from the highest rev."""

    async def test_updates_are_sent_and_repeats_skipped(self) -> None:
        """A row re-read in the overlap window is not sent twice; its update is."""
        a, b = uuid.uuid4(), uuid.uuid4()
        changes = ScriptedChanges(
            [
                [_row(a, 5, "par"), _row(b, 6)],
                [_row(a, 5, "par"), _row(b, 6)],  # overlap re-read
                [_row(a, 7, "partial")],  # update
            ]
        )

        events = await _collect(changes)

        messages = [e for e in events if e["event"] == "message"]
        assert [e["id"] for e in messages] == ["5", "6", "7"]
        assert changes.cursors == [0, 6, 6, 7]

    async def test_late_commit_below_the_cursor_is_still_sent(self) -> None:
        """A row whose rev is below the cursor but new to this stream is sent."""
        a, late = uuid.uuid4(), uuid.uuid4()
        changes = ScriptedChanges([[_row(a, 9)], [_row(late, 8), _row(a, 9)]])

        events = await _collect(changes)

        assert [e["id"] for e in events if e["event"] == "message"] == ["9", "8"]

    async def test_heartbeat_and_timeout(self) -> None:
        """Idle streams send heartbeats and end with a timeout event."""
        events = await _collect(ScriptedChanges([]), polls=6)

        assert [e["event"] for e in events] == ["heartbeat", "heartbeat", "timeout"]

    async def test_stops_when_the_client_disconnects(self) -> None:
        """Nothing is polled once the client is gone."""
        from dataing.entrypoints.api.routes.issue_threads import thread_message_stream

        changes = ScriptedChanges([[_row(uuid.uuid4(), 1)]])

        async def gone() -> bool:
            return True

        events = [
            e
            async for e in thread_message_stream(
                changes, uuid.uuid4(), after_rev=0, is_disconnected=gone, poll_interval=0
            )
        ]

        assert events == []
        assert changes.cursors == []


class TestEventDescriptions:
    """Issue events read as short sentences in the thread."""

    @pytest.mark.parametrize(
        ("event_type", "payload", "text"),
        [
            (
                "status_changed",
                {"from": "open", "to": "triaged"},
                "Status changed from open to triaged",
            ),
            ("priority_changed", {"from": "P2", "to": "P1"}, "Priority changed from P2 to P1"),
            ("severity_changed", {"from": None, "to": "high"}, "Severity set to high"),
            (
                "field_changed",
                {"field": "due_at", "from": "2026-10-01", "to": None},
                "Due at cleared",
            ),
            ("label_added", {"label": "app_v2"}, "Label app_v2 added"),
            ("acknowledged", {"to": "u1"}, "Acknowledged"),
        ],
    )
    def test_describe_event(self, event_type: str, payload: dict[str, Any], text: str) -> None:
        """Each event type has a readable description."""
        from dataing.adapters.db.issue_threads import describe_event

        assert describe_event(event_type, payload) == text


class FakeAgent:
    """Records the requests sent to the thread workflow."""

    def __init__(self, fail: bool = False) -> None:
        """Initialize; with fail=True every enqueue raises."""
        self.fail = fail
        self.requests: list[dict[str, Any]] = []
        self.cancelled: list[tuple[str, str]] = []

    async def enqueue_thread_request(self, request: dict[str, Any]) -> None:
        if self.fail:
            raise RuntimeError("temporal down")
        self.requests.append(request)

    async def cancel_thread_request(self, thread_id: str, message_id: str) -> None:
        self.cancelled.append((thread_id, message_id))


def _client_with_agent(threads: FakeThreads, agent: FakeAgent | None) -> TestClient:
    from dataing.entrypoints.api.routes.issue_threads import get_thread_agent

    db = AsyncMock()
    db.fetch_one.return_value = {"id": ISSUE_ID, "tenant_id": TENANT_ID}
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_app_db] = lambda: db
    app.dependency_overrides[get_issue_thread_repository] = lambda: threads
    app.dependency_overrides[get_thread_agent] = lambda: agent
    return TestClient(app)


class TestAskingTheAgent:
    """Asking creates a queued reply and hands the request to the thread workflow."""

    def test_question_queues_a_reply_and_enqueues_it(self, threads: FakeThreads) -> None:
        """The reply exists at once, queued, so the UI and the turn limit see it."""
        agent = FakeAgent()
        client = _client_with_agent(threads, agent)

        response = client.post(
            _messages_url(threads.shared["id"]),
            json={"body_md": "is it every region?", "ask_agent": True},
            **_auth(OrgRole.MEMBER, MAYA),
        )

        assert response.status_code == 201
        question_id = response.json()["id"]
        (reply,) = (m for m in threads.messages.values() if m["kind"] == "agent_reply")
        assert reply["status"] == "queued"
        assert str(reply["request_message_id"]) == question_id
        assert reply["requested_by_user_id"] == MAYA
        (request,) = agent.requests
        assert request["message_id"] == question_id
        assert request["thread_id"] == str(threads.shared["id"])
        assert request["requested_by"] == str(MAYA)
        assert request["kind"] == "answer"

    def test_unavailable_agent_marks_the_reply_failed(self, threads: FakeThreads) -> None:
        """If the workflow can't be reached, the reply says so instead of waiting forever."""
        client = _client_with_agent(threads, FakeAgent(fail=True))

        response = client.post(
            _messages_url(threads.shared["id"]),
            json={"body_md": "q", "ask_agent": True},
            **_auth(OrgRole.MEMBER, MAYA),
        )

        assert response.status_code == 201
        (reply,) = (m for m in threads.messages.values() if m["kind"] == "agent_reply")
        assert reply["status"] == "error"

    def test_plain_comment_does_not_reach_the_agent(self, threads: FakeThreads) -> None:
        """Only messages that ask the agent are enqueued."""
        agent = FakeAgent()
        client = _client_with_agent(threads, agent)

        client.post(
            _messages_url(threads.shared["id"]),
            json={"body_md": "fyi"},
            **_auth(OrgRole.MEMBER, MAYA),
        )

        assert agent.requests == []


class TestCancellingATurn:
    """The requester or an admin can cancel a queued or streaming answer."""

    def _ask(self, client: TestClient, threads: FakeThreads) -> dict[str, Any]:
        client.post(
            _messages_url(threads.shared["id"]),
            json={"body_md": "q", "ask_agent": True},
            **_auth(OrgRole.MEMBER, MAYA),
        )
        (reply,) = (m for m in threads.messages.values() if m["kind"] == "agent_reply")
        return reply

    def test_requester_cancels_a_queued_answer(self, threads: FakeThreads) -> None:
        """The reply is marked cancelled and the workflow is told."""
        agent = FakeAgent()
        client = _client_with_agent(threads, agent)
        reply = self._ask(client, threads)

        response = client.post(
            f"{_messages_url(threads.shared['id'])}/{reply['id']}/cancel",
            **_auth(OrgRole.MEMBER, MAYA),
        )

        assert response.status_code == 200
        assert reply["status"] == "cancelled"
        assert agent.cancelled == [(str(threads.shared["id"]), str(reply["request_message_id"]))]

    def test_someone_else_cannot_cancel(self, threads: FakeThreads) -> None:
        """Another member can't cancel Maya's question."""
        client = _client_with_agent(threads, FakeAgent())
        reply = self._ask(client, threads)

        response = client.post(
            f"{_messages_url(threads.shared['id'])}/{reply['id']}/cancel",
            **_auth(OrgRole.MEMBER, RAJ),
        )

        assert response.status_code == 403

    def test_finished_answers_cannot_be_cancelled(self, threads: FakeThreads) -> None:
        """A complete reply answers 409."""
        client = _client_with_agent(threads, FakeAgent())
        reply = self._ask(client, threads)
        reply["status"] = "complete"

        response = client.post(
            f"{_messages_url(threads.shared['id'])}/{reply['id']}/cancel",
            **_auth(OrgRole.ADMIN, RAJ),
        )

        assert response.status_code == 409


class TestQueryResults:
    """A query snapshot is readable by whoever can read its thread."""

    def _snapshot(self, threads: FakeThreads, thread_id: uuid.UUID) -> dict[str, Any]:
        reply = {
            "id": uuid.uuid4(),
            "thread_id": thread_id,
            "kind": "agent_reply",
        }
        threads.messages[reply["id"]] = {**reply, "deleted_at": None}
        snapshot = {
            "id": uuid.uuid4(),
            "message_id": reply["id"],
            "tool_call_id": "call-1",
            "sql": "SELECT 1",
            "dialect": "postgres",
            "columns": [{"name": "n"}],
            "rows": [{"n": 1}],
            "row_count": 1,
            "truncated": False,
            "duration_ms": 3,
            "error": None,
            "created_at": datetime.now(UTC),
        }
        threads.snapshots[snapshot["id"]] = snapshot
        return snapshot

    def test_viewer_reads_a_shared_snapshot(self, client: TestClient, threads: FakeThreads) -> None:
        """The SQL and rows come back."""
        snapshot = self._snapshot(threads, threads.shared["id"])

        response = client.get(
            f"/issues/{ISSUE_ID}/threads/{threads.shared['id']}/query-results/{snapshot['id']}",
            **_auth(OrgRole.VIEWER, RAJ),
        )

        assert response.status_code == 200
        assert response.json()["rows"] == [{"n": 1}]
        assert response.json()["sql"] == "SELECT 1"

    def test_snapshot_from_someone_elses_scratch_thread_is_not_found(
        self, client: TestClient, threads: FakeThreads
    ) -> None:
        """Scratch snapshots stay private."""
        theirs = threads._thread("scratch", RAJ)
        snapshot = self._snapshot(threads, theirs["id"])

        response = client.get(
            f"/issues/{ISSUE_ID}/threads/{theirs['id']}/query-results/{snapshot['id']}",
            **_auth(OrgRole.ADMIN, MAYA),
        )

        assert response.status_code == 404

    def test_snapshot_must_belong_to_the_thread(
        self, client: TestClient, threads: FakeThreads
    ) -> None:
        """A snapshot id from another thread is not found here."""
        mine = threads._thread("scratch", MAYA)
        snapshot = self._snapshot(threads, mine["id"])

        response = client.get(
            f"/issues/{ISSUE_ID}/threads/{threads.shared['id']}/query-results/{snapshot['id']}",
            **_auth(OrgRole.MEMBER, MAYA),
        )

        assert response.status_code == 404


class TestBriefDrafts:
    """Asking for a brief creates a brief message and queues a draft_brief request."""

    def test_member_requests_a_draft(self, threads: FakeThreads) -> None:
        """The brief message starts queued and the workflow gets a draft_brief request."""
        agent = FakeAgent()
        client = _client_with_agent(threads, agent)

        response = client.post(
            f"/issues/{ISSUE_ID}/threads/{threads.shared['id']}/brief-drafts",
            **_auth(OrgRole.MEMBER, MAYA),
        )

        assert response.status_code == 201
        body = response.json()
        assert (body["kind"], body["status"], body["author_kind"]) == ("brief", "queued", "agent")
        (request,) = agent.requests
        assert request["kind"] == "draft_brief"
        assert request["message_id"] == body["id"]

    def test_viewer_cannot_request_a_draft(self, threads: FakeThreads) -> None:
        """Drafting leads to starting an investigation, which needs write."""
        client = _client_with_agent(threads, FakeAgent())

        response = client.post(
            f"/issues/{ISSUE_ID}/threads/{threads.shared['id']}/brief-drafts",
            **_auth(OrgRole.VIEWER, RAJ),
        )

        assert response.status_code == 403


class TestPublishing:
    """The owner of a scratch chat copies selected messages into the shared thread."""

    def _client(self, threads: FakeThreads) -> tuple[TestClient, AsyncMock]:
        db = AsyncMock()
        db.fetch_one.return_value = {"id": ISSUE_ID, "tenant_id": TENANT_ID}
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_app_db] = lambda: db
        app.dependency_overrides[get_issue_thread_repository] = lambda: threads
        return TestClient(app), db

    async def _scratch_chat(self, threads: FakeThreads) -> tuple[dict[str, Any], list[Any]]:
        scratch = threads._thread("scratch", MAYA)
        question = await threads.append_message(
            scratch["id"],
            author_kind="user",
            kind="comment",
            author_user_id=MAYA,
            body_md="are the enum values new?",
        )
        answer = await threads.append_message(
            scratch["id"],
            author_kind="agent",
            kind="agent_reply",
            requested_by_user_id=MAYA,
            body_md="Yes: `app_v2` appeared on the 14th.",
        )
        aside = await threads.append_message(
            scratch["id"], author_kind="user", kind="comment", author_user_id=MAYA, body_md="hmm"
        )
        return scratch, [question, answer, aside]

    def _publish(
        self, client: TestClient, thread_id: uuid.UUID, body: dict[str, Any], role: OrgRole
    ) -> Any:
        return client.post(
            f"/issues/{ISSUE_ID}/threads/{thread_id}/publish",
            json=body,
            **_auth(role, MAYA),
        )

    async def test_owner_publishes_selected_messages(self, threads: FakeThreads) -> None:
        """One published message lands in the shared thread: note, then texts in seq order."""
        client, db = self._client(threads)
        scratch, (question, answer, _) = await self._scratch_chat(threads)

        response = self._publish(
            client,
            scratch["id"],
            {"message_ids": [str(answer["id"]), str(question["id"])], "note": "Found it"},
            OrgRole.MEMBER,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["thread_id"] == str(threads.shared["id"])
        assert (body["kind"], body["author_kind"], body["author_user_id"]) == (
            "published",
            "user",
            str(MAYA),
        )
        agent_text = "**Agent:** Yes: `app_v2` appeared on the 14th."
        assert body["body_md"] == f"Found it\n\nare the enum values new?\n\n{agent_text}"
        assert [m["id"] for m in threads.published_from] == [question["id"], answer["id"]]
        statements = [str(c.args[0]) for c in db.execute.call_args_list]
        assert any("UPDATE issues SET updated_at" in sql for sql in statements)

    async def test_deleted_messages_are_skipped(self, threads: FakeThreads) -> None:
        """A deleted comment isn't copied; publishing only deleted ones is refused."""
        client, _ = self._client(threads)
        scratch, (question, answer, _) = await self._scratch_chat(threads)
        await threads.soft_delete_message(question["id"])

        response = self._publish(
            client,
            scratch["id"],
            {"message_ids": [str(question["id"]), str(answer["id"])]},
            OrgRole.MEMBER,
        )
        assert response.status_code == 201
        assert [m["id"] for m in threads.published_from] == [answer["id"]]

        only_deleted = self._publish(
            client, scratch["id"], {"message_ids": [str(question["id"])]}, OrgRole.MEMBER
        )
        assert only_deleted.status_code == 400

    async def test_someone_elses_scratch_chat_is_not_found(self, threads: FakeThreads) -> None:
        """Even an admin can't publish from Raj's scratch chat."""
        client, _ = self._client(threads)
        theirs = threads._thread("scratch", RAJ)
        message = await threads.append_message(
            theirs["id"], author_kind="user", kind="comment", author_user_id=RAJ, body_md="x"
        )

        response = self._publish(
            client, theirs["id"], {"message_ids": [str(message["id"])]}, OrgRole.ADMIN
        )

        assert response.status_code == 404

    async def test_shared_thread_cannot_be_published(self, threads: FakeThreads) -> None:
        """Publishing is only from a scratch chat into the shared thread."""
        client, _ = self._client(threads)
        message = await threads.append_message(
            threads.shared["id"], author_kind="user", kind="comment", author_user_id=MAYA
        )

        response = self._publish(
            client, threads.shared["id"], {"message_ids": [str(message["id"])]}, OrgRole.MEMBER
        )

        assert response.status_code == 400

    async def test_messages_must_belong_to_the_scratch_chat(self, threads: FakeThreads) -> None:
        """A message id from another thread (or an unknown one) is refused."""
        client, _ = self._client(threads)
        scratch, (question, _, _) = await self._scratch_chat(threads)
        elsewhere = await threads.append_message(
            threads.shared["id"], author_kind="user", kind="comment", author_user_id=RAJ
        )

        for foreign in (elsewhere["id"], uuid.uuid4()):
            response = self._publish(
                client,
                scratch["id"],
                {"message_ids": [str(question["id"]), str(foreign)]},
                OrgRole.MEMBER,
            )
            assert response.status_code == 400

    async def test_unfinished_answers_cannot_be_published(self, threads: FakeThreads) -> None:
        """An answer still streaming has no final text to copy."""
        client, _ = self._client(threads)
        scratch, (_, answer, _) = await self._scratch_chat(threads)
        answer["status"] = "streaming"

        response = self._publish(
            client, scratch["id"], {"message_ids": [str(answer["id"])]}, OrgRole.MEMBER
        )

        assert response.status_code == 400

    async def test_viewer_cannot_publish(self, threads: FakeThreads) -> None:
        """Publishing writes to the shared thread, so it needs the write scope."""
        client, _ = self._client(threads)
        scratch, (question, _, _) = await self._scratch_chat(threads)

        response = self._publish(
            client, scratch["id"], {"message_ids": [str(question["id"])]}, OrgRole.VIEWER
        )

        assert response.status_code == 403

    @pytest.mark.parametrize(
        "body",
        [
            {"message_ids": []},
            {"message_ids": [str(uuid.uuid4()) for _ in range(51)]},
            {"message_ids": [str(uuid.uuid4())], "note": "x" * 2001},
        ],
    )
    async def test_request_limits(self, threads: FakeThreads, body: dict[str, Any]) -> None:
        """One to fifty messages and a note of at most 2000 characters."""
        client, _ = self._client(threads)
        scratch, _ = await self._scratch_chat(threads)

        assert self._publish(client, scratch["id"], body, OrgRole.MEMBER).status_code == 422
