"""SSO domain types."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class SSOProviderType(str, Enum):
    """SSO provider types."""

    OIDC = "oidc"
    SAML = "saml"


@dataclass
class SSOConfig:
    """SSO configuration for an organization."""

    id: UUID
    org_id: UUID
    provider_type: SSOProviderType
    display_name: str | None
    is_enabled: bool

    # OIDC settings
    oidc_issuer_url: str | None
    oidc_client_id: str | None

    # SAML settings
    saml_idp_metadata_url: str | None
    saml_idp_entity_id: str | None
    saml_certificate: str | None

    created_at: datetime
    updated_at: datetime


@dataclass
class DomainClaim:
    """A domain claimed by an organization for SSO routing."""

    id: UUID
    org_id: UUID
    domain: str
    is_verified: bool
    verification_token: str | None
    verified_at: datetime | None
    expires_at: datetime | None
    created_at: datetime


@dataclass
class SSOIdentity:
    """Links an IdP identity to a local user account."""

    id: UUID
    user_id: UUID
    sso_config_id: UUID
    idp_user_id: str
    created_at: datetime


@dataclass
class SSODiscoveryResult:
    """Result of SSO discovery for an email domain."""

    method: str  # "password", "oidc", or "saml"
    auth_url: str | None = None
    state: str | None = None
    display_name: str | None = None
