"""SCIM token and provisioning repository."""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


@dataclass
class SCIMToken:
    """SCIM bearer token for provisioning."""

    id: UUID
    org_id: UUID
    token_hash: str
    description: str | None
    last_used_at: datetime | None
    created_at: datetime


def generate_scim_token() -> tuple[str, str]:
    """Generate a new SCIM bearer token.

    Returns:
        Tuple of (plain_token, token_hash).
        The plain token should be shown once to the user.
        The hash is stored in the database.
    """
    plain_token = f"scim_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(plain_token.encode()).hexdigest()
    return plain_token, token_hash


def hash_token(token: str) -> str:
    """Hash a SCIM token for database lookup.

    Args:
        token: Plain SCIM token.

    Returns:
        SHA256 hash of the token.
    """
    return hashlib.sha256(token.encode()).hexdigest()


class SCIMRepository:
    """Repository for SCIM tokens and operations."""

    def __init__(self, conn: "Connection") -> None:
        """Initialize the repository.

        Args:
            conn: AsyncPG database connection.
        """
        self._conn = conn

    async def create_token(
        self, org_id: UUID, description: str | None = None
    ) -> tuple[str, SCIMToken]:
        """Create a new SCIM token for an organization.

        Args:
            org_id: Organization ID.
            description: Optional description (e.g., "Okta SCIM").

        Returns:
            Tuple of (plain_token, SCIMToken).
            The plain token should be shown once to the user.
        """
        plain_token, token_hash = generate_scim_token()

        row = await self._conn.fetchrow(
            """
            INSERT INTO scim_tokens (org_id, token_hash, description)
            VALUES ($1, $2, $3)
            RETURNING id, org_id, token_hash, description, last_used_at, created_at
            """,
            org_id,
            token_hash,
            description,
        )

        return plain_token, self._row_to_scim_token(row)

    async def validate_token(self, token: str) -> UUID | None:
        """Validate a SCIM token and return the org ID.

        Also updates the last_used_at timestamp.

        Args:
            token: Plain SCIM bearer token.

        Returns:
            Organization ID if valid, None otherwise.
        """
        token_hash = hash_token(token)

        row = await self._conn.fetchrow(
            """
            UPDATE scim_tokens
            SET last_used_at = NOW()
            WHERE token_hash = $1
            RETURNING org_id
            """,
            token_hash,
        )

        if row:
            org_id: UUID = row["org_id"]
            return org_id
        return None

    async def list_tokens(self, org_id: UUID) -> list[SCIMToken]:
        """List all SCIM tokens for an organization.

        Args:
            org_id: Organization ID.

        Returns:
            List of SCIM tokens (hashes only, not plain tokens).
        """
        rows = await self._conn.fetch(
            """
            SELECT id, org_id, token_hash, description, last_used_at, created_at
            FROM scim_tokens
            WHERE org_id = $1
            ORDER BY created_at DESC
            """,
            org_id,
        )

        return [self._row_to_scim_token(row) for row in rows]

    async def revoke_token(self, token_id: UUID, org_id: UUID) -> bool:
        """Revoke (delete) a SCIM token.

        Args:
            token_id: Token ID.
            org_id: Organization ID (for authorization check).

        Returns:
            True if revoked, False if not found.
        """
        result: str = await self._conn.execute(
            "DELETE FROM scim_tokens WHERE id = $1 AND org_id = $2",
            token_id,
            org_id,
        )
        return result == "DELETE 1"

    async def get_token_by_id(self, token_id: UUID) -> SCIMToken | None:
        """Get a SCIM token by ID.

        Args:
            token_id: Token ID.

        Returns:
            SCIM token if found.
        """
        row = await self._conn.fetchrow(
            """
            SELECT id, org_id, token_hash, description, last_used_at, created_at
            FROM scim_tokens
            WHERE id = $1
            """,
            token_id,
        )

        if not row:
            return None
        return self._row_to_scim_token(row)

    def _row_to_scim_token(self, row: dict[str, Any]) -> SCIMToken:
        """Convert database row to SCIMToken."""
        return SCIMToken(
            id=row["id"],
            org_id=row["org_id"],
            token_hash=row["token_hash"],
            description=row["description"],
            last_used_at=(row["last_used_at"].replace(tzinfo=UTC) if row["last_used_at"] else None),
            created_at=row["created_at"].replace(tzinfo=UTC),
        )
