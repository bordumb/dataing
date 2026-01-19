"""Tests for SSO state repository."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing_ee.adapters.sso.state_repository import (
    SSOStateRepository,
    StateConsumedError,
    StateExpiredError,
    StateNotFoundError,
    StateValidationError,
)
from dataing_ee.core.sso import SSOState


@pytest.fixture
def mock_conn() -> MagicMock:
    """Create mock database connection."""
    return MagicMock()


@pytest.fixture
def repository(mock_conn: MagicMock) -> SSOStateRepository:
    """Create repository with mock connection."""
    return SSOStateRepository(mock_conn)


class TestCreateState:
    """Tests for create_state method."""

    async def test_creates_state_with_defaults(
        self,
        repository: SSOStateRepository,
        mock_conn: MagicMock,
    ) -> None:
        """Creates state with default TTL."""
        org_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "state_id": "test-state-id",
                "nonce": "test-nonce",
                "org_id": org_id,
                "redirect_uri": None,
                "created_at": now,
                "expires_at": now + timedelta(seconds=600),
                "consumed_at": None,
            }
        )

        state = await repository.create_state(org_id=org_id)

        assert isinstance(state, SSOState)
        assert state.org_id == org_id
        assert state.consumed_at is None
        mock_conn.fetchrow.assert_called_once()

    async def test_creates_state_with_redirect_uri(
        self,
        repository: SSOStateRepository,
        mock_conn: MagicMock,
    ) -> None:
        """Creates state with redirect URI."""
        org_id = uuid4()
        redirect_uri = "https://app.example.com/dashboard"
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "state_id": "test-state-id",
                "nonce": "test-nonce",
                "org_id": org_id,
                "redirect_uri": redirect_uri,
                "created_at": now,
                "expires_at": now + timedelta(seconds=600),
                "consumed_at": None,
            }
        )

        state = await repository.create_state(org_id=org_id, redirect_uri=redirect_uri)

        assert state.redirect_uri == redirect_uri

    async def test_creates_state_with_custom_ttl(
        self,
        repository: SSOStateRepository,
        mock_conn: MagicMock,
    ) -> None:
        """Creates state with custom TTL."""
        org_id = uuid4()
        now = datetime.now(UTC)
        custom_ttl = 300  # 5 minutes

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "state_id": "test-state-id",
                "nonce": "test-nonce",
                "org_id": org_id,
                "redirect_uri": None,
                "created_at": now,
                "expires_at": now + timedelta(seconds=custom_ttl),
                "consumed_at": None,
            }
        )

        state = await repository.create_state(org_id=org_id, ttl_seconds=custom_ttl)

        # Verify the expiry is roughly correct (within a few seconds)
        expected_expiry = now + timedelta(seconds=custom_ttl)
        assert abs((state.expires_at - expected_expiry).total_seconds()) < 5


class TestValidateAndConsume:
    """Tests for validate_and_consume method."""

    async def test_validates_and_consumes_state(
        self,
        repository: SSOStateRepository,
        mock_conn: MagicMock,
    ) -> None:
        """Successfully validates and consumes state."""
        org_id = uuid4()
        now = datetime.now(UTC)
        state_id = "valid-state-id"

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "state_id": state_id,
                "nonce": "test-nonce",
                "org_id": org_id,
                "redirect_uri": None,
                "created_at": now - timedelta(minutes=1),
                "expires_at": now + timedelta(minutes=9),
                "consumed_at": None,
            }
        )
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        state = await repository.validate_and_consume(state_id)

        assert state.state_id == state_id
        assert state.consumed_at is not None
        mock_conn.execute.assert_called_once()

    async def test_raises_on_not_found(
        self,
        repository: SSOStateRepository,
        mock_conn: MagicMock,
    ) -> None:
        """Raises StateNotFoundError for unknown state."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        with pytest.raises(StateNotFoundError, match="SSO state not found"):
            await repository.validate_and_consume("unknown-state")

    async def test_raises_on_expired(
        self,
        repository: SSOStateRepository,
        mock_conn: MagicMock,
    ) -> None:
        """Raises StateExpiredError for expired state."""
        org_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "state_id": "expired-state",
                "nonce": "test-nonce",
                "org_id": org_id,
                "redirect_uri": None,
                "created_at": now - timedelta(hours=1),
                "expires_at": now - timedelta(minutes=10),  # Expired
                "consumed_at": None,
            }
        )

        with pytest.raises(StateExpiredError, match="SSO state has expired"):
            await repository.validate_and_consume("expired-state")

    async def test_raises_on_already_consumed(
        self,
        repository: SSOStateRepository,
        mock_conn: MagicMock,
    ) -> None:
        """Raises StateConsumedError for already-used state."""
        org_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "state_id": "consumed-state",
                "nonce": "test-nonce",
                "org_id": org_id,
                "redirect_uri": None,
                "created_at": now - timedelta(minutes=5),
                "expires_at": now + timedelta(minutes=5),
                "consumed_at": now - timedelta(minutes=1),  # Already consumed
            }
        )

        with pytest.raises(StateConsumedError, match="already been used"):
            await repository.validate_and_consume("consumed-state")

    async def test_raises_on_nonce_mismatch(
        self,
        repository: SSOStateRepository,
        mock_conn: MagicMock,
    ) -> None:
        """Raises StateValidationError for nonce mismatch."""
        org_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "state_id": "valid-state",
                "nonce": "stored-nonce",
                "org_id": org_id,
                "redirect_uri": None,
                "created_at": now - timedelta(minutes=1),
                "expires_at": now + timedelta(minutes=9),
                "consumed_at": None,
            }
        )

        with pytest.raises(StateValidationError, match="Nonce mismatch"):
            await repository.validate_and_consume("valid-state", nonce="wrong-nonce")


class TestGetState:
    """Tests for get_state method."""

    async def test_returns_state_if_found(
        self,
        repository: SSOStateRepository,
        mock_conn: MagicMock,
    ) -> None:
        """Returns state if found."""
        org_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "state_id": "test-state",
                "nonce": "test-nonce",
                "org_id": org_id,
                "redirect_uri": "https://example.com",
                "created_at": now,
                "expires_at": now + timedelta(minutes=10),
                "consumed_at": None,
            }
        )

        state = await repository.get_state("test-state")

        assert state is not None
        assert state.state_id == "test-state"

    async def test_returns_none_if_not_found(
        self,
        repository: SSOStateRepository,
        mock_conn: MagicMock,
    ) -> None:
        """Returns None if state not found."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        state = await repository.get_state("unknown-state")

        assert state is None


class TestCleanupExpired:
    """Tests for cleanup_expired method."""

    async def test_deletes_expired_states(
        self,
        repository: SSOStateRepository,
        mock_conn: MagicMock,
    ) -> None:
        """Deletes expired states and returns count."""
        mock_conn.execute = AsyncMock(return_value="DELETE 5")

        count = await repository.cleanup_expired()

        assert count == 5
        mock_conn.execute.assert_called_once()

    async def test_returns_zero_when_none_expired(
        self,
        repository: SSOStateRepository,
        mock_conn: MagicMock,
    ) -> None:
        """Returns 0 when no expired states."""
        mock_conn.execute = AsyncMock(return_value="DELETE 0")

        count = await repository.cleanup_expired()

        assert count == 0


class TestCleanupConsumed:
    """Tests for cleanup_consumed method."""

    async def test_deletes_old_consumed_states(
        self,
        repository: SSOStateRepository,
        mock_conn: MagicMock,
    ) -> None:
        """Deletes consumed states older than threshold."""
        mock_conn.execute = AsyncMock(return_value="DELETE 10")

        count = await repository.cleanup_consumed(older_than_hours=24)

        assert count == 10


class TestSSOStateProperties:
    """Tests for SSOState properties."""

    def test_is_expired_true(self) -> None:
        """Returns True when expired."""
        now = datetime.now(UTC)
        state = SSOState(
            state_id="test",
            nonce="test",
            org_id=uuid4(),
            redirect_uri=None,
            created_at=now - timedelta(hours=1),
            expires_at=now - timedelta(minutes=10),
            consumed_at=None,
        )

        assert state.is_expired is True

    def test_is_expired_false(self) -> None:
        """Returns False when not expired."""
        now = datetime.now(UTC)
        state = SSOState(
            state_id="test",
            nonce="test",
            org_id=uuid4(),
            redirect_uri=None,
            created_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=9),
            consumed_at=None,
        )

        assert state.is_expired is False

    def test_is_consumed_true(self) -> None:
        """Returns True when consumed."""
        now = datetime.now(UTC)
        state = SSOState(
            state_id="test",
            nonce="test",
            org_id=uuid4(),
            redirect_uri=None,
            created_at=now - timedelta(minutes=5),
            expires_at=now + timedelta(minutes=5),
            consumed_at=now - timedelta(minutes=1),
        )

        assert state.is_consumed is True

    def test_is_consumed_false(self) -> None:
        """Returns False when not consumed."""
        now = datetime.now(UTC)
        state = SSOState(
            state_id="test",
            nonce="test",
            org_id=uuid4(),
            redirect_uri=None,
            created_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(minutes=9),
            consumed_at=None,
        )

        assert state.is_consumed is False
