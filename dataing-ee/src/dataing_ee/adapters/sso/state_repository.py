"""SSO state repository for CSRF protection and replay prevention."""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing_ee.core.sso import SSOState

if TYPE_CHECKING:
    from asyncpg import Connection

logger = logging.getLogger(__name__)


class StateValidationError(Exception):
    """Raised when SSO state validation fails."""

    pass


class StateNotFoundError(StateValidationError):
    """Raised when SSO state is not found."""

    pass


class StateExpiredError(StateValidationError):
    """Raised when SSO state has expired."""

    pass


class StateConsumedError(StateValidationError):
    """Raised when SSO state has already been used."""

    pass


class SSOStateRepository:
    """Repository for SSO authentication state management.

    Provides secure, single-use state tokens for CSRF protection
    during the SSO authentication flow.
    """

    DEFAULT_TTL_SECONDS = 600  # 10 minutes

    def __init__(self, conn: "Connection") -> None:
        """Initialize the repository.

        Args:
            conn: AsyncPG database connection.
        """
        self._conn = conn

    async def create_state(
        self,
        org_id: UUID,
        redirect_uri: str | None = None,
        ttl_seconds: int | None = None,
    ) -> SSOState:
        """Create a new SSO state for authentication.

        Args:
            org_id: Organization ID initiating SSO.
            redirect_uri: Optional URI to redirect after auth.
            ttl_seconds: Time-to-live in seconds (default: 10 minutes).

        Returns:
            Created SSO state with state_id and nonce.
        """
        state_id = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        now = datetime.now(UTC)
        ttl = ttl_seconds or self.DEFAULT_TTL_SECONDS
        expires_at = now + timedelta(seconds=ttl)

        row = await self._conn.fetchrow(
            """
            INSERT INTO sso_states (state_id, nonce, org_id, redirect_uri, created_at, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING state_id, nonce, org_id, redirect_uri, created_at, expires_at, consumed_at
            """,
            state_id,
            nonce,
            org_id,
            redirect_uri,
            now,
            expires_at,
        )
        return self._row_to_sso_state(row)

    async def validate_and_consume(
        self,
        state_id: str,
        nonce: str | None = None,
    ) -> SSOState:
        """Validate and consume an SSO state (single-use).

        This method atomically validates the state and marks it as consumed
        to prevent replay attacks.

        Args:
            state_id: State ID from callback.
            nonce: Expected nonce value (optional, for additional verification).

        Returns:
            Validated SSO state.

        Raises:
            StateNotFoundError: If state is not found.
            StateExpiredError: If state has expired.
            StateConsumedError: If state was already used.
            StateValidationError: If nonce doesn't match.
        """
        # Fetch and lock the state row
        row = await self._conn.fetchrow(
            """
            SELECT state_id, nonce, org_id, redirect_uri, created_at, expires_at, consumed_at
            FROM sso_states
            WHERE state_id = $1
            FOR UPDATE
            """,
            state_id,
        )

        if not row:
            raise StateNotFoundError(f"SSO state not found: {state_id}")

        state = self._row_to_sso_state(row)

        # Check if already consumed
        if state.is_consumed:
            logger.warning(f"SSO state replay attempt: {state_id}")
            raise StateConsumedError("SSO state has already been used")

        # Check if expired
        if state.is_expired:
            raise StateExpiredError("SSO state has expired")

        # Validate nonce if provided
        if nonce is not None and state.nonce != nonce:
            raise StateValidationError(
                f"Nonce mismatch: expected '{state.nonce}', got '{nonce}'"
            )

        # Mark as consumed
        now = datetime.now(UTC)
        await self._conn.execute(
            "UPDATE sso_states SET consumed_at = $1 WHERE state_id = $2",
            now,
            state_id,
        )

        # Return the state with consumed_at set
        return SSOState(
            state_id=state.state_id,
            nonce=state.nonce,
            org_id=state.org_id,
            redirect_uri=state.redirect_uri,
            created_at=state.created_at,
            expires_at=state.expires_at,
            consumed_at=now,
        )

    async def get_state(self, state_id: str) -> SSOState | None:
        """Get SSO state by ID without consuming it.

        Args:
            state_id: State ID.

        Returns:
            SSO state if found, None otherwise.
        """
        row = await self._conn.fetchrow(
            """
            SELECT state_id, nonce, org_id, redirect_uri, created_at, expires_at, consumed_at
            FROM sso_states
            WHERE state_id = $1
            """,
            state_id,
        )
        if not row:
            return None
        return self._row_to_sso_state(row)

    async def cleanup_expired(self) -> int:
        """Delete expired SSO states.

        Returns:
            Number of states deleted.
        """
        now = datetime.now(UTC)
        result = await self._conn.execute(
            "DELETE FROM sso_states WHERE expires_at < $1",
            now,
        )
        # Result format: "DELETE N"
        count = int(result.split()[-1])
        if count > 0:
            logger.info(f"Cleaned up {count} expired SSO states")
        return count

    async def cleanup_consumed(self, older_than_hours: int = 24) -> int:
        """Delete consumed SSO states older than specified hours.

        Args:
            older_than_hours: Delete states consumed more than this many hours ago.

        Returns:
            Number of states deleted.
        """
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        result = await self._conn.execute(
            "DELETE FROM sso_states WHERE consumed_at IS NOT NULL AND consumed_at < $1",
            cutoff,
        )
        count = int(result.split()[-1])
        if count > 0:
            logger.info(f"Cleaned up {count} consumed SSO states")
        return count

    def _row_to_sso_state(self, row: dict[str, Any]) -> SSOState:
        """Convert database row to SSOState."""
        return SSOState(
            state_id=row["state_id"],
            nonce=row["nonce"],
            org_id=row["org_id"],
            redirect_uri=row["redirect_uri"],
            created_at=row["created_at"].replace(tzinfo=UTC),
            expires_at=row["expires_at"].replace(tzinfo=UTC),
            consumed_at=(
                row["consumed_at"].replace(tzinfo=UTC) if row["consumed_at"] else None
            ),
        )
