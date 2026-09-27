"""Tests for auth API routes."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.adapters.audit import AuditLogCreate
from dataing.core.auth.service import AuthError, AuthService
from dataing.core.auth.types import User
from dataing.entrypoints.api.deps import get_frontend_url, get_recovery_adapter
from dataing.entrypoints.api.routes.auth import get_auth_service, router


@pytest.fixture
def mock_auth_service() -> MagicMock:
    """Create mock auth service."""
    return MagicMock(spec=AuthService)


@pytest.fixture
def audit_repo() -> AsyncMock:
    """Create mock audit repository."""
    return AsyncMock()


@pytest.fixture
def app(mock_auth_service: MagicMock, audit_repo: AsyncMock) -> FastAPI:
    """Create test app with auth router and mocked service."""
    app = FastAPI()
    app.include_router(router, prefix="/auth")
    app.state.audit_repo = audit_repo
    app.dependency_overrides[get_auth_service] = lambda: mock_auth_service
    app.dependency_overrides[get_recovery_adapter] = lambda: MagicMock()
    app.dependency_overrides[get_frontend_url] = lambda: "https://app.example.com"
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestLoginEndpoint:
    """Test POST /auth/login."""

    def test_login_success(self, client: TestClient, mock_auth_service: MagicMock) -> None:
        """Should return tokens on successful login."""
        mock_auth_service.login = AsyncMock(
            return_value={
                "access_token": "access.token.here",
                "refresh_token": "refresh.token.here",
                "token_type": "bearer",
                "user": {"id": "user-id", "email": "test@example.com", "name": "Test"},
                "org": {"id": "org-id", "name": "Org", "slug": "org", "plan": "free"},
                "role": "admin",
            }
        )

        response = client.post(
            "/auth/login",
            json={
                "email": "test@example.com",
                "password": "password123",  # pragma: allowlist secret
                "org_id": "00000000-0000-0000-0000-000000000001",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_login_invalid_credentials(
        self, client: TestClient, mock_auth_service: MagicMock
    ) -> None:
        """Should return 401 for invalid credentials."""
        mock_auth_service.login = AsyncMock(side_effect=AuthError("Invalid credentials"))

        response = client.post(
            "/auth/login",
            json={
                "email": "test@example.com",
                "password": "wrong",  # pragma: allowlist secret
                "org_id": "00000000-0000-0000-0000-000000000001",
            },
        )

        assert response.status_code == 401


class TestRegisterEndpoint:
    """Test POST /auth/register."""

    def test_register_success(self, client: TestClient, mock_auth_service: MagicMock) -> None:
        """Should create user and return tokens."""
        mock_auth_service.register = AsyncMock(
            return_value={
                "access_token": "access.token.here",
                "refresh_token": "refresh.token.here",
                "token_type": "bearer",
                "user": {"id": "user-id", "email": "new@example.com", "name": "New User"},
                "org": {"id": "org-id", "name": "New Org", "slug": "new-org", "plan": "free"},
                "role": "owner",
            }
        )

        response = client.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "password": "password123",  # pragma: allowlist secret
                "name": "New User",
                "org_name": "New Org",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["user"]["email"] == "new@example.com"


def _token_result(user_id: UUID, org_id: UUID, email: str) -> dict[str, Any]:
    """Build what AuthService.login and register return."""
    return {
        "access_token": "access.token.here",
        "refresh_token": "refresh.token.here",
        "token_type": "bearer",
        "user": {"id": str(user_id), "email": email, "name": "Test"},
        "org": {"id": str(org_id), "name": "Org", "slug": "org", "plan": "free"},
        "role": "owner",
    }


def _user() -> User:
    """Create a password user."""
    return User(
        id=uuid4(),
        email="test@example.com",
        name="Test",
        password_hash="hash",  # pragma: allowlist secret
        created_at=datetime.now(UTC),
    )


def _entries(audit_repo: AsyncMock) -> list[AuditLogCreate]:
    """Return every audit entry recorded, in order."""
    return [call.args[0] for call in audit_repo.record.await_args_list]


def _login(client: TestClient, org_id: UUID) -> Any:
    """Post a login for test@example.com into org_id."""
    return client.post(
        "/auth/login",
        json={
            "email": "test@example.com",
            "password": "password123",  # pragma: allowlist secret
            "org_id": str(org_id),
        },
    )


class TestLoginAudit:
    """Test audit entries for POST /auth/login."""

    def test_records_login(
        self, client: TestClient, mock_auth_service: MagicMock, audit_repo: AsyncMock
    ) -> None:
        """Should record auth.login under the org, attributed to the user."""
        user_id, org_id = uuid4(), uuid4()
        mock_auth_service.login = AsyncMock(
            return_value=_token_result(user_id, org_id, "test@example.com")
        )

        response = _login(client, org_id)

        assert response.status_code == 200
        [entry] = _entries(audit_repo)
        assert entry.action == "auth.login"
        assert entry.tenant_id == org_id
        assert entry.actor_id == user_id
        assert entry.actor_email == "test@example.com"
        assert entry.resource_type == "user"
        assert entry.resource_id == user_id
        assert entry.resource_name == "test@example.com"
        assert entry.status_code == 200

    def test_records_failed_login(
        self, client: TestClient, mock_auth_service: MagicMock, audit_repo: AsyncMock
    ) -> None:
        """Should record auth.login_failed under the org the caller tried."""
        org_id = uuid4()
        mock_auth_service.login = AsyncMock(side_effect=AuthError("Invalid email or password"))
        mock_auth_service.org_exists = AsyncMock(return_value=True)

        response = _login(client, org_id)

        assert response.status_code == 401
        [entry] = _entries(audit_repo)
        assert entry.action == "auth.login_failed"
        assert entry.tenant_id == org_id
        assert entry.actor_id is None
        assert entry.actor_email == "test@example.com"
        assert entry.resource_type == "user"
        assert entry.resource_id is None
        assert entry.resource_name == "test@example.com"
        assert entry.status_code == 401
        assert entry.metadata == {"reason": "Invalid email or password"}

    def test_failed_login_into_unknown_org_records_nothing(
        self, client: TestClient, mock_auth_service: MagicMock, audit_repo: AsyncMock
    ) -> None:
        """Callers pick org_id, so they must not create rows under made-up tenants."""
        mock_auth_service.login = AsyncMock(side_effect=AuthError("Invalid email or password"))
        mock_auth_service.org_exists = AsyncMock(return_value=False)

        response = _login(client, uuid4())

        assert response.status_code == 401
        audit_repo.record.assert_not_awaited()

    def test_audit_failure_does_not_fail_login(
        self, client: TestClient, mock_auth_service: MagicMock, audit_repo: AsyncMock
    ) -> None:
        """Should still log the user in if recording fails."""
        user_id, org_id = uuid4(), uuid4()
        mock_auth_service.login = AsyncMock(
            return_value=_token_result(user_id, org_id, "test@example.com")
        )
        audit_repo.record.side_effect = RuntimeError("database down")

        response = _login(client, org_id)

        assert response.status_code == 200

    def test_org_lookup_failure_keeps_failed_login_a_401(
        self, client: TestClient, mock_auth_service: MagicMock
    ) -> None:
        """An error while auditing must not turn a 401 into a 500."""
        mock_auth_service.login = AsyncMock(side_effect=AuthError("Invalid email or password"))
        mock_auth_service.org_exists = AsyncMock(side_effect=RuntimeError("database down"))

        response = _login(client, uuid4())

        assert response.status_code == 401


class TestRegisterAudit:
    """Test audit entries for POST /auth/register."""

    def test_records_register(
        self, client: TestClient, mock_auth_service: MagicMock, audit_repo: AsyncMock
    ) -> None:
        """Should record auth.register under the new org, attributed to the new user."""
        user_id, org_id = uuid4(), uuid4()
        mock_auth_service.register = AsyncMock(
            return_value=_token_result(user_id, org_id, "new@example.com")
        )

        response = client.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "password": "password123",  # pragma: allowlist secret
                "name": "New User",
                "org_name": "New Org",
            },
        )

        assert response.status_code == 201
        [entry] = _entries(audit_repo)
        assert entry.action == "auth.register"
        assert entry.tenant_id == org_id
        assert entry.actor_id == user_id
        assert entry.actor_email == "new@example.com"
        assert entry.resource_id == user_id
        assert entry.status_code == 201


class TestPasswordResetAudit:
    """Test audit entries for the password reset endpoints."""

    def test_request_records_entry_in_every_org_of_the_user(
        self, client: TestClient, mock_auth_service: MagicMock, audit_repo: AsyncMock
    ) -> None:
        """Should record auth.password_reset_request once per org, not attributed to anyone."""
        user = _user()
        org_a, org_b = uuid4(), uuid4()
        mock_auth_service.request_password_reset = AsyncMock(return_value=user)
        mock_auth_service.get_user_org_ids = AsyncMock(return_value=[org_a, org_b])

        response = client.post("/auth/password-reset/request", json={"email": user.email})

        assert response.status_code == 200
        entries = _entries(audit_repo)
        assert [entry.tenant_id for entry in entries] == [org_a, org_b]
        for entry in entries:
            assert entry.action == "auth.password_reset_request"
            assert entry.actor_id is None
            assert entry.actor_email == user.email
            assert entry.resource_type == "user"
            assert entry.resource_id == user.id

    def test_request_response_does_not_reveal_whether_account_exists(
        self, client: TestClient, mock_auth_service: MagicMock, audit_repo: AsyncMock
    ) -> None:
        """Known and unknown emails get the same response; only known ones are audited."""
        mock_auth_service.request_password_reset = AsyncMock(return_value=_user())
        mock_auth_service.get_user_org_ids = AsyncMock(return_value=[uuid4()])
        known = client.post("/auth/password-reset/request", json={"email": "test@example.com"})

        mock_auth_service.request_password_reset = AsyncMock(return_value=None)
        unknown = client.post("/auth/password-reset/request", json={"email": "no@example.com"})

        assert (unknown.status_code, unknown.json()) == (known.status_code, known.json())
        assert len(_entries(audit_repo)) == 1

    def test_org_lookup_failure_keeps_request_response_unchanged(
        self, client: TestClient, mock_auth_service: MagicMock
    ) -> None:
        """An error while auditing must not reveal that the account exists."""
        mock_auth_service.request_password_reset = AsyncMock(return_value=_user())
        mock_auth_service.get_user_org_ids = AsyncMock(side_effect=RuntimeError("database down"))

        response = client.post("/auth/password-reset/request", json={"email": "test@example.com"})

        assert response.status_code == 200

    def test_confirm_records_entry_in_every_org_of_the_user(
        self, client: TestClient, mock_auth_service: MagicMock, audit_repo: AsyncMock
    ) -> None:
        """Should record auth.password_reset_complete once per org, attributed to the user."""
        user = _user()
        org_a, org_b = uuid4(), uuid4()
        mock_auth_service.reset_password = AsyncMock(return_value=user)
        mock_auth_service.get_user_org_ids = AsyncMock(return_value=[org_a, org_b])

        response = client.post(
            "/auth/password-reset/confirm",
            json={
                "token": "reset-token",
                "new_password": "new-password-123",  # pragma: allowlist secret
            },
        )

        assert response.status_code == 200
        entries = _entries(audit_repo)
        assert [entry.tenant_id for entry in entries] == [org_a, org_b]
        for entry in entries:
            assert entry.action == "auth.password_reset_complete"
            assert entry.actor_id == user.id
            assert entry.actor_email == user.email
            assert entry.resource_id == user.id
