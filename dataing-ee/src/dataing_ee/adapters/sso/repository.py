"""SSO configuration repository."""

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing_ee.core.sso import DomainClaim, SSOConfig, SSOIdentity, SSOProviderType

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


class SSORepository:
    """Repository for SSO configuration and domain claims."""

    def __init__(self, conn: "Connection") -> None:
        """Initialize the repository.

        Args:
            conn: AsyncPG database connection.
        """
        self._conn = conn

    # SSO Config methods

    async def get_sso_config(self, org_id: UUID) -> SSOConfig | None:
        """Get SSO configuration for an organization.

        Args:
            org_id: Organization ID.

        Returns:
            SSO configuration if found, None otherwise.
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, org_id, provider_type, display_name, is_enabled,
                   oidc_issuer_url, oidc_client_id,
                   saml_idp_metadata_url, saml_idp_entity_id, saml_certificate,
                   created_at, updated_at
            FROM sso_configs
            WHERE org_id = $1
            """,
            org_id,
        )
        if not row:
            return None
        return self._row_to_sso_config(row)

    async def create_sso_config(
        self,
        org_id: UUID,
        provider_type: SSOProviderType,
        display_name: str | None = None,
        oidc_issuer_url: str | None = None,
        oidc_client_id: str | None = None,
        oidc_client_secret: str | None = None,
        saml_idp_metadata_url: str | None = None,
        saml_idp_entity_id: str | None = None,
        saml_certificate: str | None = None,
    ) -> SSOConfig:
        """Create SSO configuration for an organization.

        Args:
            org_id: Organization ID.
            provider_type: SSO provider type (oidc or saml).
            display_name: Display name for the SSO button.
            oidc_issuer_url: OIDC issuer URL.
            oidc_client_id: OIDC client ID.
            oidc_client_secret: OIDC client secret (will be encrypted).
            saml_idp_metadata_url: SAML IdP metadata URL.
            saml_idp_entity_id: SAML IdP entity ID.
            saml_certificate: SAML IdP certificate.

        Returns:
            Created SSO configuration.
        """
        # Note: In production, encrypt oidc_client_secret before storing
        encrypted_secret = oidc_client_secret.encode() if oidc_client_secret else None

        row = await self._conn.fetchrow(
            """
            INSERT INTO sso_configs (
                org_id, provider_type, display_name, is_enabled,
                oidc_issuer_url, oidc_client_id, oidc_client_secret_encrypted,
                saml_idp_metadata_url, saml_idp_entity_id, saml_certificate
            ) VALUES ($1, $2, $3, true, $4, $5, $6, $7, $8, $9)
            RETURNING id, org_id, provider_type, display_name, is_enabled,
                      oidc_issuer_url, oidc_client_id,
                      saml_idp_metadata_url, saml_idp_entity_id, saml_certificate,
                      created_at, updated_at
            """,
            org_id,
            provider_type.value,
            display_name,
            oidc_issuer_url,
            oidc_client_id,
            encrypted_secret,
            saml_idp_metadata_url,
            saml_idp_entity_id,
            saml_certificate,
        )
        return self._row_to_sso_config(row)

    async def update_sso_config(
        self,
        config_id: UUID,
        is_enabled: bool | None = None,
        display_name: str | None = None,
    ) -> SSOConfig | None:
        """Update SSO configuration.

        Args:
            config_id: SSO config ID.
            is_enabled: Whether SSO is enabled.
            display_name: Display name.

        Returns:
            Updated SSO configuration if found.
        """
        updates: list[str] = []
        params: list[Any] = [config_id]
        param_idx = 2

        if is_enabled is not None:
            updates.append(f"is_enabled = ${param_idx}")
            params.append(is_enabled)
            param_idx += 1

        if display_name is not None:
            updates.append(f"display_name = ${param_idx}")
            params.append(display_name)
            param_idx += 1

        if not updates:
            return await self.get_sso_config_by_id(config_id)

        updates.append("updated_at = NOW()")
        query = f"""
            UPDATE sso_configs
            SET {', '.join(updates)}
            WHERE id = $1
            RETURNING id, org_id, provider_type, display_name, is_enabled,
                      oidc_issuer_url, oidc_client_id,
                      saml_idp_metadata_url, saml_idp_entity_id, saml_certificate,
                      created_at, updated_at
        """
        row = await self._conn.fetchrow(query, *params)
        if not row:
            return None
        return self._row_to_sso_config(row)

    async def get_sso_config_by_id(self, config_id: UUID) -> SSOConfig | None:
        """Get SSO configuration by ID.

        Args:
            config_id: SSO config ID.

        Returns:
            SSO configuration if found.
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, org_id, provider_type, display_name, is_enabled,
                   oidc_issuer_url, oidc_client_id,
                   saml_idp_metadata_url, saml_idp_entity_id, saml_certificate,
                   created_at, updated_at
            FROM sso_configs
            WHERE id = $1
            """,
            config_id,
        )
        if not row:
            return None
        return self._row_to_sso_config(row)

    async def delete_sso_config(self, org_id: UUID) -> bool:
        """Delete SSO configuration for an organization.

        Args:
            org_id: Organization ID.

        Returns:
            True if deleted, False if not found.
        """
        result: str = await self._conn.execute("DELETE FROM sso_configs WHERE org_id = $1", org_id)
        return result == "DELETE 1"

    # Domain claim methods

    async def get_domain_claim(self, domain: str) -> DomainClaim | None:
        """Get domain claim by domain name.

        Args:
            domain: Domain name (e.g., 'acme.com').

        Returns:
            Domain claim if found.
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, org_id, domain, is_verified, verification_token,
                   verified_at, expires_at, created_at
            FROM domain_claims
            WHERE domain = $1
            """,
            domain.lower(),
        )
        if not row:
            return None
        return self._row_to_domain_claim(row)

    async def get_domain_claims_for_org(self, org_id: UUID) -> list[DomainClaim]:
        """Get all domain claims for an organization.

        Args:
            org_id: Organization ID.

        Returns:
            List of domain claims.
        """
        rows = await self._conn.fetch(
            """
            SELECT id, org_id, domain, is_verified, verification_token,
                   verified_at, expires_at, created_at
            FROM domain_claims
            WHERE org_id = $1
            ORDER BY created_at DESC
            """,
            org_id,
        )
        return [self._row_to_domain_claim(row) for row in rows]

    async def create_domain_claim(
        self, org_id: UUID, domain: str, verification_token: str, expires_at: datetime
    ) -> DomainClaim:
        """Create a new domain claim.

        Args:
            org_id: Organization ID.
            domain: Domain name.
            verification_token: Token for DNS verification.
            expires_at: Expiration time for verification.

        Returns:
            Created domain claim.
        """
        row = await self._conn.fetchrow(
            """
            INSERT INTO domain_claims (org_id, domain, verification_token, expires_at)
            VALUES ($1, $2, $3, $4)
            RETURNING id, org_id, domain, is_verified, verification_token,
                      verified_at, expires_at, created_at
            """,
            org_id,
            domain.lower(),
            verification_token,
            expires_at,
        )
        return self._row_to_domain_claim(row)

    async def verify_domain_claim(self, claim_id: UUID) -> DomainClaim | None:
        """Mark a domain claim as verified.

        Args:
            claim_id: Domain claim ID.

        Returns:
            Updated domain claim if found.
        """
        row = await self._conn.fetchrow(
            """
            UPDATE domain_claims
            SET is_verified = true, verified_at = NOW(), expires_at = NULL
            WHERE id = $1
            RETURNING id, org_id, domain, is_verified, verification_token,
                      verified_at, expires_at, created_at
            """,
            claim_id,
        )
        if not row:
            return None
        return self._row_to_domain_claim(row)

    async def delete_domain_claim(self, claim_id: UUID) -> bool:
        """Delete a domain claim.

        Args:
            claim_id: Domain claim ID.

        Returns:
            True if deleted.
        """
        result: str = await self._conn.execute("DELETE FROM domain_claims WHERE id = $1", claim_id)
        return result == "DELETE 1"

    # SSO Identity methods

    async def get_sso_identity(self, sso_config_id: UUID, idp_user_id: str) -> SSOIdentity | None:
        """Get SSO identity by IdP user ID.

        Args:
            sso_config_id: SSO config ID.
            idp_user_id: User ID from the IdP.

        Returns:
            SSO identity if found.
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, user_id, sso_config_id, idp_user_id, created_at
            FROM sso_identities
            WHERE sso_config_id = $1 AND idp_user_id = $2
            """,
            sso_config_id,
            idp_user_id,
        )
        if not row:
            return None
        return self._row_to_sso_identity(row)

    async def create_sso_identity(
        self, user_id: UUID, sso_config_id: UUID, idp_user_id: str
    ) -> SSOIdentity:
        """Create SSO identity linking IdP user to local user.

        Args:
            user_id: Local user ID.
            sso_config_id: SSO config ID.
            idp_user_id: User ID from the IdP.

        Returns:
            Created SSO identity.
        """
        row = await self._conn.fetchrow(
            """
            INSERT INTO sso_identities (user_id, sso_config_id, idp_user_id)
            VALUES ($1, $2, $3)
            RETURNING id, user_id, sso_config_id, idp_user_id, created_at
            """,
            user_id,
            sso_config_id,
            idp_user_id,
        )
        return self._row_to_sso_identity(row)

    # Helper methods

    def _row_to_sso_config(self, row: dict[str, Any]) -> SSOConfig:
        """Convert database row to SSOConfig."""
        return SSOConfig(
            id=row["id"],
            org_id=row["org_id"],
            provider_type=SSOProviderType(row["provider_type"]),
            display_name=row["display_name"],
            is_enabled=row["is_enabled"],
            oidc_issuer_url=row["oidc_issuer_url"],
            oidc_client_id=row["oidc_client_id"],
            saml_idp_metadata_url=row["saml_idp_metadata_url"],
            saml_idp_entity_id=row["saml_idp_entity_id"],
            saml_certificate=row["saml_certificate"],
            created_at=row["created_at"].replace(tzinfo=UTC),
            updated_at=row["updated_at"].replace(tzinfo=UTC),
        )

    def _row_to_domain_claim(self, row: dict[str, Any]) -> DomainClaim:
        """Convert database row to DomainClaim."""
        return DomainClaim(
            id=row["id"],
            org_id=row["org_id"],
            domain=row["domain"],
            is_verified=row["is_verified"],
            verification_token=row["verification_token"],
            verified_at=(row["verified_at"].replace(tzinfo=UTC) if row["verified_at"] else None),
            expires_at=(row["expires_at"].replace(tzinfo=UTC) if row["expires_at"] else None),
            created_at=row["created_at"].replace(tzinfo=UTC),
        )

    def _row_to_sso_identity(self, row: dict[str, Any]) -> SSOIdentity:
        """Convert database row to SSOIdentity."""
        return SSOIdentity(
            id=row["id"],
            user_id=row["user_id"],
            sso_config_id=row["sso_config_id"],
            idp_user_id=row["idp_user_id"],
            created_at=row["created_at"].replace(tzinfo=UTC),
        )
