"""Factory for reconstructing adapters from stored datasource configurations.

This module provides functions for workers to recreate adapter instances
from encrypted datasource configurations stored in the database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from dataing.adapters.datasource.base import BaseAdapter
from dataing.adapters.datasource.encryption import decrypt_config, get_encryption_key
from dataing.adapters.datasource.errors import DatasourceNotFoundError
from dataing.adapters.datasource.registry import get_registry
from dataing.adapters.datasource.types import SourceType

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase


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
