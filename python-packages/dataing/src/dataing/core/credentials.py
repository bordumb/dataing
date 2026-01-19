"""Credentials service for managing user datasource credentials.

This module provides encryption/decryption and storage operations
for user-specific database credentials.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from cryptography.fernet import Fernet

from dataing.adapters.datasource.encryption import get_encryption_key
from dataing.core.json_utils import to_json_string


@dataclass(frozen=True)
class DecryptedCredentials:
    """Decrypted credentials for a datasource connection."""

    username: str
    password: str
    role: str | None = None
    warehouse: str | None = None
    extra: dict[str, Any] | None = None


class CredentialsService:
    """Service for managing user datasource credentials.

    Handles encryption, decryption, storage, and retrieval of
    user-specific database credentials.
    """

    def __init__(self, app_db: Any) -> None:
        """Initialize the credentials service.

        Args:
            app_db: Application database for persistence operations.
        """
        self._app_db = app_db
        self._encryption_key = get_encryption_key()

    def encrypt_credentials(self, credentials: dict[str, Any]) -> bytes:
        """Encrypt credentials for storage.

        Args:
            credentials: Dictionary containing username, password, etc.

        Returns:
            Encrypted credentials as bytes.
        """
        f = Fernet(self._encryption_key)
        json_str = to_json_string(credentials)
        return f.encrypt(json_str.encode())

    def decrypt_credentials(self, encrypted: bytes) -> DecryptedCredentials:
        """Decrypt stored credentials.

        Args:
            encrypted: Encrypted credentials bytes.

        Returns:
            DecryptedCredentials object with username, password, etc.
        """
        f = Fernet(self._encryption_key)
        decrypted = f.decrypt(encrypted)
        data: dict[str, Any] = json.loads(decrypted.decode())

        # Extract known fields, put rest in extra
        known_fields = {"username", "password", "role", "warehouse"}
        extra = {k: v for k, v in data.items() if k not in known_fields}

        return DecryptedCredentials(
            username=data["username"],
            password=data["password"],
            role=data.get("role"),
            warehouse=data.get("warehouse"),
            extra=extra if extra else None,
        )

    async def get_credentials(
        self,
        user_id: UUID,
        datasource_id: UUID,
    ) -> DecryptedCredentials | None:
        """Get decrypted credentials for a user and datasource.

        Args:
            user_id: The user's ID.
            datasource_id: The datasource ID.

        Returns:
            DecryptedCredentials if configured, None otherwise.
        """
        record = await self._app_db.get_user_credentials(user_id, datasource_id)
        if not record:
            return None

        return self.decrypt_credentials(record["credentials_encrypted"])

    async def save_credentials(
        self,
        user_id: UUID,
        datasource_id: UUID,
        credentials: dict[str, Any],
    ) -> None:
        """Save or update credentials for a user and datasource.

        Args:
            user_id: The user's ID.
            datasource_id: The datasource ID.
            credentials: Dictionary with username, password, etc.
        """
        encrypted = self.encrypt_credentials(credentials)
        db_username = credentials.get("username")

        await self._app_db.upsert_user_credentials(
            user_id=user_id,
            datasource_id=datasource_id,
            credentials_encrypted=encrypted,
            db_username=db_username,
        )

    async def delete_credentials(
        self,
        user_id: UUID,
        datasource_id: UUID,
    ) -> bool:
        """Delete credentials for a user and datasource.

        Args:
            user_id: The user's ID.
            datasource_id: The datasource ID.

        Returns:
            True if credentials were deleted, False if not found.
        """
        result: bool = await self._app_db.delete_user_credentials(user_id, datasource_id)
        return result

    async def get_status(
        self,
        user_id: UUID,
        datasource_id: UUID,
    ) -> dict[str, Any]:
        """Get status of credentials for a user and datasource.

        Args:
            user_id: The user's ID.
            datasource_id: The datasource ID.

        Returns:
            Dictionary with configured, db_username, last_used_at, created_at.
        """
        record = await self._app_db.get_user_credentials(user_id, datasource_id)

        if not record:
            return {
                "configured": False,
                "db_username": None,
                "last_used_at": None,
                "created_at": None,
            }

        return {
            "configured": True,
            "db_username": record.get("db_username"),
            "last_used_at": record.get("last_used_at"),
            "created_at": record.get("created_at"),
        }

    async def update_last_used(
        self,
        user_id: UUID,
        datasource_id: UUID,
    ) -> None:
        """Update the last_used_at timestamp for credentials.

        Args:
            user_id: The user's ID.
            datasource_id: The datasource ID.
        """
        await self._app_db.update_credentials_last_used(
            user_id,
            datasource_id,
            datetime.now(UTC),
        )
