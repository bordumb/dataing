"""Database Context - Resolves tenant data source adapters.

This module handles the resolution of tenant-specific database adapters,
enabling investigations to query the actual data source (DuckDB, Postgres, etc.)
rather than just the application metadata database.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from cryptography.fernet import Fernet

from dataing.adapters.db.duckdb import DuckDBAdapter
from dataing.adapters.db.postgres import PostgresAdapter

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase
    from dataing.core.interfaces import DatabaseAdapter

logger = structlog.get_logger()


class DatabaseContext:
    """Resolves and caches tenant data source adapters.

    This class is responsible for:
    1. Looking up data source configuration from the app database
    2. Decrypting connection credentials
    3. Creating the appropriate adapter (DuckDB, Postgres, etc.)
    4. Caching adapters for reuse within a request

    Attributes:
        app_db: The application database for looking up data sources.
    """

    def __init__(self, app_db: AppDatabase) -> None:
        """Initialize the database context.

        Args:
            app_db: Application database for data source lookups.
        """
        self.app_db = app_db
        self._adapters: dict[str, DatabaseAdapter] = {}
        self._encryption_key = os.getenv("ENCRYPTION_KEY")

    async def get_adapter(
        self,
        tenant_id: UUID,
        data_source_id: UUID,
    ) -> DatabaseAdapter:
        """Get or create a database adapter for a tenant's data source.

        Args:
            tenant_id: The tenant's UUID.
            data_source_id: The data source UUID.

        Returns:
            A connected DatabaseAdapter for the data source.

        Raises:
            ValueError: If data source not found or type not supported.
            RuntimeError: If decryption fails.
        """
        cache_key = f"{tenant_id}:{data_source_id}"

        if cache_key in self._adapters:
            logger.debug("adapter_cache_hit", cache_key=cache_key)
            return self._adapters[cache_key]

        logger.info(
            "resolving_data_source",
            tenant_id=str(tenant_id),
            data_source_id=str(data_source_id),
        )

        # Look up data source from app database
        ds = await self.app_db.get_data_source(data_source_id, tenant_id)
        if not ds:
            raise ValueError(f"Data source {data_source_id} not found for tenant {tenant_id}")

        # Create and connect the adapter
        adapter = await self._create_adapter(ds)
        await adapter.connect()

        # Cache for reuse
        self._adapters[cache_key] = adapter
        logger.info("adapter_created", ds_type=ds["type"], ds_name=ds.get("name"))

        return adapter

    async def get_default_adapter(self, tenant_id: UUID) -> DatabaseAdapter:
        """Get the default data source adapter for a tenant.

        Args:
            tenant_id: The tenant's UUID.

        Returns:
            A connected DatabaseAdapter for the tenant's default data source.

        Raises:
            ValueError: If no data sources found for tenant.
        """
        # Get tenant's data sources and use the first active one
        data_sources = await self.app_db.list_data_sources(tenant_id)
        active_sources = [ds for ds in data_sources if ds.get("is_active", True)]

        if not active_sources:
            raise ValueError(f"No active data sources found for tenant {tenant_id}")

        ds = active_sources[0]
        ds_id = ds["id"] if isinstance(ds["id"], UUID) else UUID(str(ds["id"]))
        return await self.get_adapter(tenant_id, ds_id)

    async def _create_adapter(self, ds: dict[str, Any]) -> DatabaseAdapter:
        """Create a database adapter from data source config.

        Args:
            ds: Data source record from app database.

        Returns:
            Unconnected DatabaseAdapter instance.

        Raises:
            ValueError: If data source type not supported.
            RuntimeError: If decryption fails.
        """
        ds_type = ds["type"]
        config = self._decrypt_config(ds["connection_config_encrypted"])

        if ds_type == "duckdb":
            return DuckDBAdapter(
                path=config["path"],
                read_only=config.get("read_only", True),
            )
        elif ds_type == "postgres":
            return PostgresAdapter(
                host=config["host"],
                port=config.get("port", 5432),
                database=config["database"],
                user=config["user"],
                password=config["password"],
                schema=config.get("schema", "public"),
            )
        else:
            raise ValueError(f"Unsupported data source type: {ds_type}")

    def _decrypt_config(self, encrypted_config: str) -> dict[str, Any]:
        """Decrypt connection configuration.

        Args:
            encrypted_config: Fernet-encrypted JSON config string.

        Returns:
            Decrypted configuration dictionary.

        Raises:
            RuntimeError: If decryption fails or no encryption key.
        """
        if not self._encryption_key:
            raise RuntimeError("ENCRYPTION_KEY not set")

        try:
            f = Fernet(self._encryption_key.encode())
            decrypted = f.decrypt(encrypted_config.encode()).decode()
            result: dict[str, Any] = json.loads(decrypted)
            return result
        except Exception as e:
            raise RuntimeError(f"Failed to decrypt connection config: {e}") from e

    async def close_all(self) -> None:
        """Close all cached adapters.

        Should be called during application shutdown.
        """
        for cache_key, adapter in self._adapters.items():
            try:
                await adapter.close()
                logger.debug("adapter_closed", cache_key=cache_key)
            except Exception as e:
                logger.warning("adapter_close_failed", cache_key=cache_key, error=str(e))

        self._adapters.clear()
