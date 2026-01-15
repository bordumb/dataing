"""Factory for reconstructing adapters from stored datasource configurations.

This module provides functions for workers to recreate adapter instances
from encrypted datasource configurations stored in the database.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING
from uuid import UUID

from cryptography.fernet import Fernet

from dataing.adapters.datasource.base import BaseAdapter
from dataing.adapters.datasource.errors import DatasourceNotFoundError
from dataing.adapters.datasource.registry import get_registry
from dataing.adapters.datasource.types import SourceType

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase


def get_encryption_key() -> bytes:
    """Get the encryption key for data source configs.

    Checks DATADR_ENCRYPTION_KEY first (used by demo), then ENCRYPTION_KEY.
    """
    key = os.getenv("DATADR_ENCRYPTION_KEY") or os.getenv("ENCRYPTION_KEY")
    if not key:
        raise ValueError(
            "ENCRYPTION_KEY or DATADR_ENCRYPTION_KEY environment variable must be set"
        )
    return key.encode() if isinstance(key, str) else key


def decrypt_config(encrypted: str, key: bytes) -> dict:
    """Decrypt datasource configuration.

    Args:
        encrypted: The encrypted configuration string.
        key: The Fernet encryption key.

    Returns:
        Decrypted configuration dictionary.
    """
    f = Fernet(key)
    decrypted = f.decrypt(encrypted.encode())
    result: dict = json.loads(decrypted.decode())
    return result


async def create_adapter_for_datasource(
    db: AppDatabase,
    tenant_id: UUID,
    datasource_id: UUID,
) -> BaseAdapter:
    """Reconstruct an adapter from stored datasource configuration.

    This function enables workers to create adapter instances without
    API request context by querying the datasource configuration from
    the database and decrypting the connection credentials.

    Args:
        db: The application database connection.
        tenant_id: The tenant ID that owns the datasource.
        datasource_id: The ID of the datasource to create an adapter for.

    Returns:
        A BaseAdapter instance configured for the datasource.

    Raises:
        DatasourceNotFoundError: If the datasource doesn't exist or
            doesn't belong to the tenant.
        ValueError: If encryption key is not configured.
    """
    row = await db.get_data_source(datasource_id, tenant_id)

    if not row:
        raise DatasourceNotFoundError(
            datasource_id=str(datasource_id),
            tenant_id=str(tenant_id),
        )

    # Get encryption key and decrypt config
    encryption_key = get_encryption_key()
    config = decrypt_config(row["connection_config_encrypted"], encryption_key)

    # Get adapter class from registry
    source_type = SourceType(row["type"])
    registry = get_registry()

    if not registry.is_registered(source_type):
        raise ValueError(f"No adapter registered for source type: {source_type}")

    return registry.create(source_type, config)
