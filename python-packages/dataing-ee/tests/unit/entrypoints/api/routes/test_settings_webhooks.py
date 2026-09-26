"""Tests for webhook settings routes."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from dataing_ee.entrypoints.api.routes.settings import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

SLACK_URL = "https://hooks.slack.com/services/T000/B000/SECRETTOKEN"
CREATED_AT = datetime(2026, 9, 26, tzinfo=UTC)


def webhook_row(webhook_id: UUID, url: str) -> dict[str, Any]:
    """Build a webhooks row as AppDatabase.list_webhooks returns it."""
    return {
        "id": webhook_id,
        "url": url,
        "secret": "whsec_signingsecret",
        "events": ["investigation.completed"],
        "is_active": True,
        "last_triggered_at": None,
        "last_status": None,
        "created_at": CREATED_AT,
    }


@pytest.fixture
def app_db() -> MagicMock:
    """Create a mock application database."""
    return MagicMock(spec=AppDatabase)


@pytest.fixture
def client(app_db: MagicMock) -> TestClient:
    """Create a test client authenticated as a read-only API key."""
    read_only_auth = ApiKeyContext(
        key_id=uuid4(),
        tenant_id=uuid4(),
        tenant_slug="test-tenant",
        tenant_name="Test Tenant",
        user_id=None,
        scopes=["read"],
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_app_db] = lambda: app_db
    app.dependency_overrides[verify_api_key] = lambda: read_only_auth

    return TestClient(app)


class TestListWebhooks:
    """Tests for GET /settings/webhooks endpoint."""

    def test_does_not_return_webhook_secrets(self, client: TestClient, app_db: MagicMock) -> None:
        """Slack, Teams, and Discord URLs carry a bearer secret in the path."""
        app_db.list_webhooks = AsyncMock(return_value=[webhook_row(uuid4(), SLACK_URL)])

        response = client.get("/settings/webhooks")

        assert response.status_code == 200
        assert "SECRETTOKEN" not in response.text
        assert "whsec_signingsecret" not in response.text

    def test_returns_url_reduced_to_scheme_and_host(
        self, client: TestClient, app_db: MagicMock
    ) -> None:
        """Returns a display URL that identifies the destination without its secret."""
        webhook_id = uuid4()
        app_db.list_webhooks = AsyncMock(return_value=[webhook_row(webhook_id, SLACK_URL)])

        response = client.get("/settings/webhooks")

        assert response.status_code == 200
        assert response.json() == [
            {
                "id": str(webhook_id),
                "display_url": "https://hooks.slack.com",
                "events": ["investigation.completed"],
                "is_active": True,
                "last_triggered_at": None,
                "last_status": None,
                "created_at": CREATED_AT.isoformat(),
            }
        ]
