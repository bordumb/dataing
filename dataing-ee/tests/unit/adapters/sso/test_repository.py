"""Tests for SSO repository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing_ee.adapters.sso import SSORepository
from dataing_ee.core.sso import SSOProviderType


@pytest.fixture
def mock_conn() -> MagicMock:
    """Create mock database connection."""
    return MagicMock()


@pytest.fixture
def repository(mock_conn: MagicMock) -> SSORepository:
    """Create repository with mock connection."""
    return SSORepository(mock_conn)


class TestSSORepository:
    """Tests for SSORepository initialization."""

    def test_can_instantiate(self, mock_conn: MagicMock) -> None:
        """Can create repository with connection."""
        repo = SSORepository(mock_conn)
        assert repo._conn is mock_conn


class TestGetSSOConfig:
    """Tests for get_sso_config method."""

    async def test_returns_none_when_not_found(
        self, repository: SSORepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when config not found."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        result = await repository.get_sso_config(uuid4())

        assert result is None

    async def test_returns_config_when_found(
        self, repository: SSORepository, mock_conn: MagicMock
    ) -> None:
        """Returns config when found."""
        org_id = uuid4()
        config_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": config_id,
                "org_id": org_id,
                "provider_type": "oidc",
                "display_name": "Sign in with Okta",
                "is_enabled": True,
                "oidc_issuer_url": "https://acme.okta.com",
                "oidc_client_id": "client123",
                "saml_idp_metadata_url": None,
                "saml_idp_entity_id": None,
                "saml_certificate": None,
                "created_at": now,
                "updated_at": now,
            }
        )

        result = await repository.get_sso_config(org_id)

        assert result is not None
        assert result.id == config_id
        assert result.org_id == org_id
        assert result.provider_type == SSOProviderType.OIDC
        assert result.oidc_issuer_url == "https://acme.okta.com"


class TestGetDomainClaim:
    """Tests for get_domain_claim method."""

    async def test_returns_none_when_not_found(
        self, repository: SSORepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when domain not claimed."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        result = await repository.get_domain_claim("unknown.com")

        assert result is None

    async def test_returns_claim_when_found(
        self, repository: SSORepository, mock_conn: MagicMock
    ) -> None:
        """Returns claim when domain is claimed."""
        claim_id = uuid4()
        org_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": claim_id,
                "org_id": org_id,
                "domain": "acme.com",
                "is_verified": True,
                "verification_token": None,
                "verified_at": now,
                "expires_at": None,
                "created_at": now,
            }
        )

        result = await repository.get_domain_claim("acme.com")

        assert result is not None
        assert result.domain == "acme.com"
        assert result.is_verified is True


class TestCreateSSOConfig:
    """Tests for create_sso_config method."""

    async def test_creates_oidc_config(
        self, repository: SSORepository, mock_conn: MagicMock
    ) -> None:
        """Can create OIDC configuration."""
        org_id = uuid4()
        config_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": config_id,
                "org_id": org_id,
                "provider_type": "oidc",
                "display_name": "Okta",
                "is_enabled": True,
                "oidc_issuer_url": "https://acme.okta.com",
                "oidc_client_id": "client123",
                "saml_idp_metadata_url": None,
                "saml_idp_entity_id": None,
                "saml_certificate": None,
                "created_at": now,
                "updated_at": now,
            }
        )

        result = await repository.create_sso_config(
            org_id=org_id,
            provider_type=SSOProviderType.OIDC,
            display_name="Okta",
            oidc_issuer_url="https://acme.okta.com",
            oidc_client_id="client123",
            oidc_client_secret="secret",  # pragma: allowlist secret
        )

        assert result.provider_type == SSOProviderType.OIDC
        assert result.oidc_issuer_url == "https://acme.okta.com"


class TestSSOIdentity:
    """Tests for SSO identity methods."""

    async def test_get_identity_not_found(
        self, repository: SSORepository, mock_conn: MagicMock
    ) -> None:
        """Returns None when identity not found."""
        mock_conn.fetchrow = AsyncMock(return_value=None)

        result = await repository.get_sso_identity(uuid4(), "idp-user-123")

        assert result is None

    async def test_create_identity(self, repository: SSORepository, mock_conn: MagicMock) -> None:
        """Can create SSO identity."""
        user_id = uuid4()
        config_id = uuid4()
        identity_id = uuid4()
        now = datetime.now(UTC)

        mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": identity_id,
                "user_id": user_id,
                "sso_config_id": config_id,
                "idp_user_id": "auth0|12345",
                "created_at": now,
            }
        )

        result = await repository.create_sso_identity(user_id, config_id, "auth0|12345")

        assert result.user_id == user_id
        assert result.idp_user_id == "auth0|12345"
