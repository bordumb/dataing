"""Tests for SCIM repository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing.adapters.sso import SCIMRepository, SCIMToken, generate_scim_token, hash_token


@pytest.fixture
def mock_conn() -> MagicMock:
    """Create mock database connection."""
    return MagicMock()


@pytest.fixture
def repository(mock_conn: MagicMock) -> SCIMRepository:
    """Create repository with mock connection."""
    return SCIMRepository(mock_conn)


class TestGenerateScimToken:
    """Tests for generate_scim_token function."""

    def test_generates_prefixed_token(self) -> None:
        """Generated token has scim_ prefix."""
        plain_token, _ = generate_scim_token()
        assert plain_token.startswith("scim_")

    def test_generates_unique_tokens(self) -> None:
        """Each call generates unique token."""
        token1, _ = generate_scim_token()
        token2, _ = generate_scim_token()
        assert token1 != token2

    def test_generates_hash(self) -> None:
        """Returns SHA256 hash of token."""
        plain_token, token_hash = generate_scim_token()
        assert len(token_hash) == 64  # SHA256 hex = 64 chars
        assert hash_token(plain_token) == token_hash


class TestHashToken:
    """Tests for hash_token function."""

    def test_consistent_hash(self) -> None:
        """Same input produces same hash."""
        token = "scim_test123"
        hash1 = hash_token(token)
        hash2 = hash_token(token)
        assert hash1 == hash2

    def test_sha256_length(self) -> None:
        """Hash is SHA256 (64 hex chars)."""
        token = "scim_test123"
        assert len(hash_token(token)) == 64


class TestSCIMRepository:
    """Tests for SCIMRepository."""

    def test_can_instantiate(self, mock_conn: MagicMock) -> None:
        """Can create repository with connection."""
        repo = SCIMRepository(mock_conn)
        assert repo._conn is mock_conn


class TestCreateToken:
    """Tests for create_token method."""

    async def test_creates_token(self, repository: SCIMRepository, mock_conn: MagicMock) -> None:
        """Creates new SCIM token."""
        org_id = uuid4()
        token_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": token_id,
                "org_id": org_id,
                "token_hash": "abc123",
                "description": "Okta SCIM",
                "last_used_at": None,
                "created_at": now,
            }
        )

        plain_token, scim_token = await repository.create_token(org_id, description="Okta SCIM")

        assert plain_token.startswith("scim_")
        assert isinstance(scim_token, SCIMToken)
        assert scim_token.org_id == org_id
        assert scim_token.description == "Okta SCIM"


class TestValidateToken:
    """Tests for validate_token method."""

    async def test_returns_org_id_for_valid_token(
        self, repository: SCIMRepository, mock_conn: MagicMock
    ) -> None:
        """Returns org_id for valid token."""
        org_id = uuid4()
        mock_conn.fetchrow = AsyncMock(return_value={"org_id": org_id})

        result = await repository.validate_token("scim_valid_token")

        assert result == org_id

    async def test_returns_none_for_invalid_token(
        self, repository: SCIMRepository, mock_conn: MagicMock
    ) -> None:
        """Returns None for invalid token."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        result = await repository.validate_token("scim_invalid_token")

        assert result is None


class TestListTokens:
    """Tests for list_tokens method."""

    async def test_returns_empty_list(
        self, repository: SCIMRepository, mock_conn: MagicMock
    ) -> None:
        """Returns empty list when no tokens."""
        mock_conn.fetch = AsyncMock(return_value=[])

        result = await repository.list_tokens(uuid4())

        assert result == []

    async def test_returns_tokens(self, repository: SCIMRepository, mock_conn: MagicMock) -> None:
        """Returns list of tokens."""
        org_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetch = AsyncMock(
            return_value=[
                {
                    "id": uuid4(),
                    "org_id": org_id,
                    "token_hash": "hash1",
                    "description": "Token 1",
                    "last_used_at": now,
                    "created_at": now,
                },
                {
                    "id": uuid4(),
                    "org_id": org_id,
                    "token_hash": "hash2",
                    "description": "Token 2",
                    "last_used_at": None,
                    "created_at": now,
                },
            ]
        )

        result = await repository.list_tokens(org_id)

        assert len(result) == 2
        assert result[0].description == "Token 1"
        assert result[1].description == "Token 2"


class TestRevokeToken:
    """Tests for revoke_token method."""

    async def test_returns_true_when_revoked(
        self, repository: SCIMRepository, mock_conn: MagicMock
    ) -> None:
        """Returns True when token is revoked."""
        mock_conn.execute = AsyncMock(return_value="DELETE 1")

        result = await repository.revoke_token(uuid4(), uuid4())

        assert result is True

    async def test_returns_false_when_not_found(
        self, repository: SCIMRepository, mock_conn: MagicMock
    ) -> None:
        """Returns False when token not found."""
        mock_conn.execute = AsyncMock(return_value="DELETE 0")

        result = await repository.revoke_token(uuid4(), uuid4())

        assert result is False
