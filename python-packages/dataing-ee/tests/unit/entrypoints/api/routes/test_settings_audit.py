"""Audit logging through the EE settings routes.

Settings handlers name their JSON body `request`; the audit decorator must still
find the real HTTP request and record an entry.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from dataing_ee.entrypoints.api.routes.settings import router
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key
from dataing.services.auth import AuthService


@pytest.fixture
def auth_context() -> ApiKeyContext:
    """Create the caller's API key context."""
    return ApiKeyContext(
        key_id=uuid4(),
        tenant_id=uuid4(),
        tenant_slug="acme",
        tenant_name="Acme",
        user_id=uuid4(),
        scopes=["read", "write", "admin"],
    )


@pytest.fixture
def audit_repo() -> AsyncMock:
    """Create mock audit repository."""
    return AsyncMock()


@pytest.fixture
def app_db() -> AsyncMock:
    """Create mock application database."""
    return AsyncMock()


@pytest.fixture
def client(auth_context: ApiKeyContext, audit_repo: AsyncMock, app_db: AsyncMock) -> TestClient:
    """Create test client for the settings router."""
    app = FastAPI()
    app.include_router(router)
    app.state.audit_repo = audit_repo

    async def authenticate(request: Request) -> ApiKeyContext:
        # Like verify_api_key, expose the caller on request.state for audit logging
        request.state.auth_context = auth_context
        return auth_context

    app.dependency_overrides[verify_api_key] = authenticate
    app.dependency_overrides[get_app_db] = lambda: app_db
    return TestClient(app)


def test_create_webhook_records_audit_entry(
    client: TestClient,
    audit_repo: AsyncMock,
    app_db: AsyncMock,
    auth_context: ApiKeyContext,
) -> None:
    """POST /settings/webhooks records webhook.create for the caller."""
    webhook_id = uuid4()
    app_db.create_webhook.return_value = {"id": webhook_id}

    response = client.post(
        "/settings/webhooks",
        json={"url": "https://hooks.example.com/dataing", "events": ["investigation.completed"]},
    )

    assert response.status_code == 201
    audit_repo.record.assert_awaited_once()
    entry = audit_repo.record.await_args.args[0]
    assert entry.action == "webhook.create"
    assert entry.resource_type == "webhook"
    assert entry.resource_id == webhook_id
    assert entry.tenant_id == auth_context.tenant_id
    assert entry.actor_id == auth_context.user_id
    assert entry.request_method == "POST"
    assert entry.request_path == "/settings/webhooks"


def test_delete_webhook_records_the_webhook(
    client: TestClient, audit_repo: AsyncMock, app_db: AsyncMock
) -> None:
    """DELETE /settings/webhooks/{id} records webhook.delete against that webhook, as a 204."""
    webhook_id = uuid4()
    app_db.execute.return_value = "DELETE 1"

    response = client.delete(f"/settings/webhooks/{webhook_id}")

    assert response.status_code == 204
    entry = audit_repo.record.await_args.args[0]
    assert entry.action == "webhook.delete"
    assert entry.resource_id == webhook_id
    assert entry.status_code == 204


def test_revoke_api_key_records_the_key(
    client: TestClient, audit_repo: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DELETE /settings/api-keys/{key_id} records api_key.revoke against that key, as a 204."""
    key_id = uuid4()
    monkeypatch.setattr(AuthService, "revoke_api_key", AsyncMock(return_value=True))

    response = client.delete(f"/settings/api-keys/{key_id}")

    assert response.status_code == 204
    entry = audit_repo.record.await_args.args[0]
    assert entry.action == "api_key.revoke"
    assert entry.resource_id == key_id
    assert entry.status_code == 204
