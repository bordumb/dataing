"""Unit tests for Runbooks API routes (EE)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from dataing_ee.entrypoints.api.routes.runbooks import (
    GenerateRunbookRequest,
    LinkFeedbackRequest,
    RunbookCreate,
    RunbookUpdate,
    router,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key


@pytest.fixture
def tenant_id() -> UUID:
    """Return the caller's tenant ID."""
    return uuid4()


@pytest.fixture
def mock_db() -> MagicMock:
    """Create mock app database."""
    return MagicMock(spec=AppDatabase)


@pytest.fixture
def mock_auth_context(tenant_id: UUID) -> ApiKeyContext:
    """Create mock auth context for the caller's tenant."""
    return ApiKeyContext(
        key_id=uuid4(),
        tenant_id=tenant_id,
        tenant_slug="test",
        tenant_name="Test Tenant",
        user_id=uuid4(),
        scopes=["read", "write"],
    )


@pytest.fixture
def app(mock_db: MagicMock, mock_auth_context: ApiKeyContext) -> FastAPI:
    """Create test app with runbook routes."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_app_db] = lambda: mock_db
    app.dependency_overrides[verify_api_key] = lambda: mock_auth_context
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestRunbookCreateSchema:
    """Test RunbookCreate Pydantic schema."""

    def test_valid_create(self) -> None:
        """Test valid creation payload."""
        payload = RunbookCreate(
            title="Database Connection Troubleshooting",
            body="# Overview\n\nThis runbook covers database connection issues.",
            summary="How to troubleshoot database connections",
            dataset_id="warehouse.orders",
            labels=["database", "production"],
            symptoms=[{"description": "Connection timeout", "severity": "high"}],
            root_cause="Network configuration issue",
            verification_steps=[{"step": 1, "description": "Check connectivity"}],
            fix_steps=[{"step": 1, "description": "Restart connection pool"}],
            prevention_notes="Set up connection monitoring",
            is_published=True,
        )
        assert payload.title == "Database Connection Troubleshooting"
        assert payload.is_published is True
        assert len(payload.labels) == 2
        assert len(payload.symptoms) == 1

    def test_minimal_create(self) -> None:
        """Test minimal creation payload."""
        payload = RunbookCreate(
            title="Test Runbook",
            body="Test body content",
        )
        assert payload.title == "Test Runbook"
        assert payload.body == "Test body content"
        assert payload.summary is None
        assert payload.labels == []
        assert payload.symptoms == []
        assert payload.is_published is False

    def test_empty_title_invalid(self) -> None:
        """Test empty title is rejected."""
        with pytest.raises(ValueError):
            RunbookCreate(title="", body="content")

    def test_empty_body_invalid(self) -> None:
        """Test empty body is rejected."""
        with pytest.raises(ValueError):
            RunbookCreate(title="Test", body="")


class TestRunbookUpdateSchema:
    """Test RunbookUpdate Pydantic schema."""

    def test_all_none(self) -> None:
        """Test all fields can be None."""
        update = RunbookUpdate()
        assert update.title is None
        assert update.body is None
        assert update.summary is None
        assert update.labels is None
        assert update.is_published is None

    def test_partial_update(self) -> None:
        """Test partial update."""
        update = RunbookUpdate(title="New Title", is_published=True)
        assert update.title == "New Title"
        assert update.is_published is True
        assert update.body is None

    def test_update_symptoms(self) -> None:
        """Test updating symptoms."""
        update = RunbookUpdate(symptoms=[{"description": "New symptom", "severity": "medium"}])
        assert update.symptoms is not None
        assert len(update.symptoms) == 1
        assert update.symptoms[0]["description"] == "New symptom"


class TestGenerateRunbookRequestSchema:
    """Test GenerateRunbookRequest Pydantic schema."""

    def test_default_not_published(self) -> None:
        """Test default is not published."""
        request = GenerateRunbookRequest()
        assert request.publish is False

    def test_publish_flag(self) -> None:
        """Test publish flag."""
        request = GenerateRunbookRequest(publish=True)
        assert request.publish is True


class TestLinkFeedbackRequestSchema:
    """Test LinkFeedbackRequest Pydantic schema."""

    def test_helpful_feedback(self) -> None:
        """Test helpful feedback."""
        feedback = LinkFeedbackRequest(
            was_helpful=True,
            feedback_notes="This runbook solved the issue",
        )
        assert feedback.was_helpful is True
        assert feedback.feedback_notes == "This runbook solved the issue"

    def test_not_helpful_feedback(self) -> None:
        """Test not helpful feedback."""
        feedback = LinkFeedbackRequest(
            was_helpful=False,
            feedback_notes="Didn't apply to my case",
        )
        assert feedback.was_helpful is False

    def test_minimal_feedback(self) -> None:
        """Test minimal feedback (no notes)."""
        feedback = LinkFeedbackRequest(was_helpful=True)
        assert feedback.was_helpful is True
        assert feedback.feedback_notes is None


class FakeRunbookStore:
    """In-memory runbooks and runbook_links rows behind mock_db.

    Answers the SQL that provide_link_feedback issues, whether it arrives through
    pool-level AppDatabase calls (each its own autocommit statement) or through the
    connection that AppDatabase.acquire() yields. ``log`` records each row lock and
    write with the number of the transaction it ran in, or None if autocommitted.
    """

    def __init__(self) -> None:
        """Initialize empty tables."""
        self.runbook_tenants: dict[UUID, UUID] = {}
        self.scores: dict[UUID, float] = {}
        self.verdicts: dict[tuple[UUID, UUID], bool | None] = {}
        self.log: list[tuple[str, int | None]] = []
        self._transactions = 0
        self._open_transaction: int | None = None

    def add_link(self, runbook_id: UUID, tenant_id: UUID, was_helpful: bool | None = None) -> UUID:
        """Link a new issue to the runbook, creating the runbook if needed."""
        self.runbook_tenants[runbook_id] = tenant_id
        self.scores.setdefault(runbook_id, 0.0)
        issue_id = uuid4()
        self.verdicts[runbook_id, issue_id] = was_helpful
        return issue_id

    async def autocommit(self, query: str, *args: Any) -> Any:
        """Run a pool-level AppDatabase statement outside any transaction."""
        return self._run(query, args, transaction=None)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        """Open a transaction on the acquired connection."""
        self._transactions += 1
        self._open_transaction = self._transactions
        try:
            yield
        finally:
            self._open_transaction = None

    async def fetchrow(self, query: str, *args: Any) -> Any:
        """Run a query on the acquired connection."""
        return self._run(query, args, self._open_transaction)

    async def execute(self, query: str, *args: Any) -> Any:
        """Run a statement on the acquired connection."""
        return self._run(query, args, self._open_transaction)

    def _run(self, query: str, args: tuple[Any, ...], transaction: int | None) -> Any:
        """Apply one statement to the rows and return its result."""
        sql = " ".join(query.split())
        if "FROM runbooks WHERE id = $1 AND tenant_id = $2" in sql:
            runbook_id, tenant_id = args
            if self.runbook_tenants.get(runbook_id) != tenant_id:
                return None
            if sql.endswith("FOR UPDATE"):
                self.log.append(("lock runbooks", transaction))
            return {"id": runbook_id}
        if sql.startswith("UPDATE runbook_links SET was_helpful = $1, feedback_notes = $2"):
            was_helpful, _notes, runbook_id, issue_id = args
            if (runbook_id, issue_id) not in self.verdicts:
                return "UPDATE 0"
            self.verdicts[runbook_id, issue_id] = was_helpful
            self.log.append(("update runbook_links", transaction))
            return "UPDATE 1"
        if "FROM runbook_links" in sql:
            (runbook_id,) = args
            verdicts = [v for (rb_id, _), v in self.verdicts.items() if rb_id == runbook_id]
            return {"helpful": verdicts.count(True), "not_helpful": verdicts.count(False)}
        if sql.startswith("UPDATE runbooks SET usefulness_score = $1 WHERE id = $2"):
            score, runbook_id = args
            self.scores[runbook_id] = score
            self.log.append(("update runbooks", transaction))
            return "UPDATE 1"
        raise AssertionError(f"unexpected query: {sql}")


@pytest.fixture
def store(mock_db: MagicMock) -> FakeRunbookStore:
    """Back mock_db, and the connection its acquire() yields, with in-memory rows."""
    store = FakeRunbookStore()
    mock_db.fetch_one.side_effect = store.autocommit
    mock_db.execute.side_effect = store.autocommit
    mock_db.acquire.return_value.__aenter__.return_value = store
    return store


def feedback_url(runbook_id: UUID, issue_id: UUID) -> str:
    """Return the feedback endpoint for a runbook link."""
    return f"/api/v1/runbooks/{runbook_id}/link/{issue_id}/feedback"


class TestProvideLinkFeedback:
    """Tests for POST /runbooks/{runbook_id}/link/{issue_id}/feedback."""

    def test_own_runbook_records_feedback(
        self, client: TestClient, store: FakeRunbookStore, tenant_id: UUID
    ) -> None:
        """Test feedback on a link to the caller's own runbook is recorded."""
        runbook_id = uuid4()
        issue_id = store.add_link(runbook_id, tenant_id)

        response = client.post(feedback_url(runbook_id, issue_id), json={"was_helpful": True})

        assert response.status_code == 200
        assert response.json() == {"status": "feedback_recorded"}
        assert store.verdicts[runbook_id, issue_id] is True

    def test_other_tenants_runbook_returns_404_without_update(
        self, client: TestClient, store: FakeRunbookStore
    ) -> None:
        """Test feedback on another tenant's runbook link is rejected before any write."""
        runbook_id = uuid4()
        # The link row exists, so an UPDATE not scoped to the caller's tenant would match it.
        issue_id = store.add_link(runbook_id, tenant_id=uuid4())

        response = client.post(
            feedback_url(runbook_id, issue_id),
            json={"was_helpful": False, "feedback_notes": "overwritten"},
        )

        assert response.status_code == 404
        assert store.verdicts[runbook_id, issue_id] is None
        assert store.log == []

    def test_unknown_link_returns_404_without_score_update(
        self, client: TestClient, store: FakeRunbookStore, tenant_id: UUID
    ) -> None:
        """Test feedback on an issue the runbook is not linked to changes no score."""
        runbook_id = uuid4()
        store.add_link(runbook_id, tenant_id, was_helpful=True)

        response = client.post(feedback_url(runbook_id, uuid4()), json={"was_helpful": True})

        assert response.status_code == 404
        assert response.json() == {"detail": "Link not found"}
        assert not any(entry == "update runbooks" for entry, _ in store.log)

    @pytest.mark.parametrize(("was_helpful", "expected_score"), [(True, 0.2), (False, 0.05)])
    def test_repeating_a_verdict_does_not_change_score_again(
        self,
        client: TestClient,
        store: FakeRunbookStore,
        tenant_id: UUID,
        was_helpful: bool,
        expected_score: float,
    ) -> None:
        """Test re-posting the same verdict on a link leaves the score where it was."""
        runbook_id = uuid4()
        store.add_link(runbook_id, tenant_id, was_helpful=True)  # another issue's verdict
        issue_id = store.add_link(runbook_id, tenant_id)

        scores: list[float] = []
        for _ in range(3):
            response = client.post(
                feedback_url(runbook_id, issue_id), json={"was_helpful": was_helpful}
            )
            assert response.status_code == 200
            scores.append(store.scores[runbook_id])

        assert scores == pytest.approx([expected_score] * 3)

    def test_flipping_a_verdict_changes_score_once(
        self, client: TestClient, store: FakeRunbookStore, tenant_id: UUID
    ) -> None:
        """Test changing a link's verdict moves the score by the difference, exactly once."""
        runbook_id = uuid4()
        store.add_link(runbook_id, tenant_id, was_helpful=True)  # another issue's verdict
        issue_id = store.add_link(runbook_id, tenant_id)

        scores: list[float] = []
        for was_helpful in (True, False, False, True):
            client.post(feedback_url(runbook_id, issue_id), json={"was_helpful": was_helpful})
            scores.append(store.scores[runbook_id])

        # Two helpful verdicts score 0.2. Flipping one to unhelpful drops it to 0.05
        # (-0.1, then -0.05), where a repeat leaves it; flipping back restores 0.2.
        assert scores == pytest.approx([0.2, 0.05, 0.05, 0.2])

    def test_unhelpful_verdicts_never_push_score_below_zero(
        self, client: TestClient, store: FakeRunbookStore, tenant_id: UUID
    ) -> None:
        """Test a runbook whose only verdict is unhelpful scores zero, not negative."""
        runbook_id = uuid4()
        issue_id = store.add_link(runbook_id, tenant_id)

        client.post(feedback_url(runbook_id, issue_id), json={"was_helpful": True})
        client.post(feedback_url(runbook_id, issue_id), json={"was_helpful": False})

        assert store.scores[runbook_id] == 0.0

    def test_writes_share_one_transaction_under_runbook_lock(
        self, client: TestClient, store: FakeRunbookStore, tenant_id: UUID
    ) -> None:
        """Test the link and score writes run in one transaction that locks the runbook first.

        The lock serializes concurrent feedback on a runbook, so each recomputed
        score counts every verdict committed before it.
        """
        runbook_id = uuid4()
        issue_id = store.add_link(runbook_id, tenant_id)

        client.post(feedback_url(runbook_id, issue_id), json={"was_helpful": True})

        assert store.log == [
            ("lock runbooks", 1),
            ("update runbook_links", 1),
            ("update runbooks", 1),
        ]


class TestRunbookContentValidation:
    """Test runbook content edge cases."""

    def test_long_title(self) -> None:
        """Test title length limit."""
        # Should accept up to 500 chars
        long_title = "A" * 500
        payload = RunbookCreate(title=long_title, body="content")
        assert len(payload.title) == 500

        # Should reject > 500 chars
        with pytest.raises(ValueError):
            RunbookCreate(title="A" * 501, body="content")

    def test_labels_list(self) -> None:
        """Test labels as list of strings."""
        payload = RunbookCreate(
            title="Test",
            body="content",
            labels=["database", "etl", "production", "urgent"],
        )
        assert len(payload.labels) == 4
        assert "database" in payload.labels

    def test_symptoms_structure(self) -> None:
        """Test symptoms as list of dicts."""
        payload = RunbookCreate(
            title="Test",
            body="content",
            symptoms=[
                {"description": "Symptom 1", "severity": "high"},
                {"description": "Symptom 2", "severity": "low", "extra": "field"},
            ],
        )
        assert len(payload.symptoms) == 2
        assert payload.symptoms[0]["severity"] == "high"
        # Extra fields are allowed
        assert payload.symptoms[1].get("extra") == "field"

    def test_verification_steps_structure(self) -> None:
        """Test verification steps structure."""
        payload = RunbookCreate(
            title="Test",
            body="content",
            verification_steps=[
                {"step": 1, "description": "Check A", "query": "SELECT 1"},
                {"step": 2, "description": "Check B"},
            ],
        )
        assert len(payload.verification_steps) == 2
        assert payload.verification_steps[0]["query"] == "SELECT 1"

    def test_fix_steps_structure(self) -> None:
        """Test fix steps structure."""
        payload = RunbookCreate(
            title="Test",
            body="content",
            fix_steps=[
                {"step": 1, "description": "Do A", "type": "manual"},
                {"step": 2, "description": "Do B", "type": "automated"},
            ],
        )
        assert len(payload.fix_steps) == 2
        assert payload.fix_steps[1]["type"] == "automated"
