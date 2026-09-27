"""Only a comment's author may edit it; its author or an admin may delete it.

Covers knowledge and schema comments, which any tenant user may post, so
ownership (not the write scope) decides who may change an existing one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fixtures.route_authorization import jwt_request_kwargs

from dataing.core.auth.types import OrgRole
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.routes.knowledge_comments import router as knowledge_router
from dataing.entrypoints.api.routes.schema_comments import router as schema_router

DATASET_ID = uuid.uuid4()
AUTHOR_ID = uuid.uuid4()


class CommentKind:
    """A comment route family and the app database methods behind it."""

    def __init__(self, router: APIRouter, segment: str, record: str) -> None:
        """Initialize the comment kind."""
        self.router = router
        self.segment = segment
        self.get = f"get_{record}"
        self.update = f"update_{record}"
        self.delete = f"delete_{record}"

    def path(self, comment_id: uuid.UUID) -> str:
        """Return the URL of one comment."""
        return f"/datasets/{DATASET_ID}/{self.segment}/{comment_id}"


KINDS = [
    pytest.param(
        CommentKind(knowledge_router, "knowledge-comments", "knowledge_comment"), id="knowledge"
    ),
    pytest.param(CommentKind(schema_router, "schema-comments", "schema_comment"), id="schema"),
]


def _comment(author_id: uuid.UUID | None, content: str = "original") -> dict[str, Any]:
    """Return a stored comment row."""
    now = datetime.now(UTC)
    return {
        "id": uuid.uuid4(),
        "dataset_id": DATASET_ID,
        "field_name": "email",
        "parent_id": None,
        "content": content,
        "author_id": author_id,
        "author_name": None,
        "upvotes": 0,
        "downvotes": 0,
        "created_at": now,
        "updated_at": now,
    }


@pytest.fixture(params=KINDS)
def kind(request: pytest.FixtureRequest) -> CommentKind:
    """Return each comment kind in turn."""
    return request.param


@pytest.fixture
def db(kind: CommentKind) -> AsyncMock:
    """Return an app database holding one comment written by AUTHOR_ID."""
    db = AsyncMock()
    getattr(db, kind.get).return_value = _comment(AUTHOR_ID)
    getattr(db, kind.update).return_value = _comment(AUTHOR_ID, content="edited")
    getattr(db, kind.delete).return_value = True
    return db


@pytest.fixture
def client(kind: CommentKind, db: AsyncMock) -> TestClient:
    """Return a client for the comment routes with real JWT and API key auth."""
    app = FastAPI()
    app.include_router(kind.router)
    app.dependency_overrides[get_app_db] = lambda: db
    app.state.app_db = db
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("role", [OrgRole.VIEWER, OrgRole.MEMBER])
def test_author_can_edit_their_comment(
    client: TestClient, kind: CommentKind, db: AsyncMock, role: OrgRole
) -> None:
    """The author edits their comment, whatever their role."""
    response = client.patch(
        kind.path(uuid.uuid4()),
        json={"content": "edited"},
        **jwt_request_kwargs(role, user_id=AUTHOR_ID),
    )

    assert response.status_code == 200
    assert response.json()["content"] == "edited"
    getattr(db, kind.update).assert_awaited_once()


@pytest.mark.parametrize("role", [OrgRole.MEMBER, OrgRole.ADMIN])
def test_other_users_cannot_edit_a_comment(
    client: TestClient, kind: CommentKind, db: AsyncMock, role: OrgRole
) -> None:
    """Nobody but the author edits a comment, admins included."""
    response = client.patch(
        kind.path(uuid.uuid4()), json={"content": "edited"}, **jwt_request_kwargs(role)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the author can edit this comment"
    getattr(db, kind.update).assert_not_called()


def test_author_can_delete_their_comment(
    client: TestClient, kind: CommentKind, db: AsyncMock
) -> None:
    """A viewer deletes their own comment."""
    response = client.delete(
        kind.path(uuid.uuid4()), **jwt_request_kwargs(OrgRole.VIEWER, user_id=AUTHOR_ID)
    )

    assert response.status_code == 204
    getattr(db, kind.delete).assert_awaited_once()


def test_admin_can_delete_any_comment(client: TestClient, kind: CommentKind, db: AsyncMock) -> None:
    """An admin removes someone else's comment."""
    response = client.delete(kind.path(uuid.uuid4()), **jwt_request_kwargs(OrgRole.ADMIN))

    assert response.status_code == 204
    getattr(db, kind.delete).assert_awaited_once()


def test_other_member_cannot_delete_a_comment(
    client: TestClient, kind: CommentKind, db: AsyncMock
) -> None:
    """A member who is not the author gets 403 and nothing is deleted."""
    response = client.delete(kind.path(uuid.uuid4()), **jwt_request_kwargs(OrgRole.MEMBER))

    assert response.status_code == 403
    assert response.json()["detail"] == "Only the author or an admin can delete this comment"
    getattr(db, kind.delete).assert_not_called()


def test_caller_without_a_user_is_never_the_author(
    client: TestClient, kind: CommentKind, db: AsyncMock
) -> None:
    """An API key with no user cannot edit a comment that has no author either."""
    getattr(db, kind.get).return_value = _comment(author_id=None)
    db.get_api_key_by_hash.return_value = {
        "id": uuid.uuid4(),
        "tenant_id": uuid.uuid4(),
        "user_id": None,
        "scopes": ["read", "write"],
    }

    response = client.patch(
        kind.path(uuid.uuid4()),
        json={"content": "edited"},
        headers={"X-API-Key": "dd_service_key"},
    )

    assert response.status_code == 403
    getattr(db, kind.update).assert_not_called()
