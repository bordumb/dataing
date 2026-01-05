"""Tests for SSO domain types."""

from datetime import UTC, datetime
from uuid import uuid4

from dataing.core.sso import (
    DomainClaim,
    SSOConfig,
    SSODiscoveryResult,
    SSOIdentity,
    SSOProviderType,
)


class TestSSOProviderType:
    """Tests for SSOProviderType enum."""

    def test_oidc_value(self) -> None:
        """OIDC has correct string value."""
        assert SSOProviderType.OIDC.value == "oidc"

    def test_saml_value(self) -> None:
        """SAML has correct string value."""
        assert SSOProviderType.SAML.value == "saml"


class TestSSOConfig:
    """Tests for SSOConfig dataclass."""

    def test_create_oidc_config(self) -> None:
        """Can create OIDC configuration."""
        config = SSOConfig(
            id=uuid4(),
            org_id=uuid4(),
            provider_type=SSOProviderType.OIDC,
            display_name="Sign in with Okta",
            is_enabled=True,
            oidc_issuer_url="https://acme.okta.com",
            oidc_client_id="client123",
            saml_idp_metadata_url=None,
            saml_idp_entity_id=None,
            saml_certificate=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert config.provider_type == SSOProviderType.OIDC
        assert config.oidc_issuer_url == "https://acme.okta.com"

    def test_create_saml_config(self) -> None:
        """Can create SAML configuration."""
        config = SSOConfig(
            id=uuid4(),
            org_id=uuid4(),
            provider_type=SSOProviderType.SAML,
            display_name="Sign in with Azure AD",
            is_enabled=True,
            oidc_issuer_url=None,
            oidc_client_id=None,
            saml_idp_metadata_url="https://login.microsoftonline.com/metadata.xml",
            saml_idp_entity_id="https://sts.windows.net/tenant-id/",
            saml_certificate="-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert config.provider_type == SSOProviderType.SAML
        assert config.saml_idp_entity_id is not None


class TestDomainClaim:
    """Tests for DomainClaim dataclass."""

    def test_create_unverified_claim(self) -> None:
        """Can create unverified domain claim."""
        claim = DomainClaim(
            id=uuid4(),
            org_id=uuid4(),
            domain="acme.com",
            is_verified=False,
            verification_token="dataing-verify=abc123",
            verified_at=None,
            expires_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        assert claim.domain == "acme.com"
        assert claim.is_verified is False
        assert claim.verification_token is not None

    def test_create_verified_claim(self) -> None:
        """Can create verified domain claim."""
        now = datetime.now(UTC)
        claim = DomainClaim(
            id=uuid4(),
            org_id=uuid4(),
            domain="verified.com",
            is_verified=True,
            verification_token=None,
            verified_at=now,
            expires_at=None,
            created_at=now,
        )
        assert claim.is_verified is True
        assert claim.verified_at is not None


class TestSSOIdentity:
    """Tests for SSOIdentity dataclass."""

    def test_create_identity(self) -> None:
        """Can create SSO identity linking IdP user to local user."""
        identity = SSOIdentity(
            id=uuid4(),
            user_id=uuid4(),
            sso_config_id=uuid4(),
            idp_user_id="auth0|12345",
            created_at=datetime.now(UTC),
        )
        assert identity.idp_user_id == "auth0|12345"


class TestSSODiscoveryResult:
    """Tests for SSODiscoveryResult dataclass."""

    def test_password_result(self) -> None:
        """Can create password discovery result."""
        result = SSODiscoveryResult(method="password")
        assert result.method == "password"
        assert result.auth_url is None

    def test_oidc_result(self) -> None:
        """Can create OIDC discovery result with auth URL."""
        result = SSODiscoveryResult(
            method="oidc",
            auth_url="https://acme.okta.com/oauth2/authorize?...",
            state="random-state",
            display_name="Okta",
        )
        assert result.method == "oidc"
        assert result.auth_url is not None
        assert result.state is not None
