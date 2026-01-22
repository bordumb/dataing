"""Application database adapter using asyncpg."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from dataing.core.json_utils import to_json_string

logger = structlog.get_logger()

# Retry configuration for database connection
MAX_RETRIES = 10
INITIAL_BACKOFF = 1.0  # seconds
MAX_BACKOFF = 30.0  # seconds


class AppDatabase:
    """Application database for storing tenants, users, investigations, etc."""

    def __init__(self, dsn: str):
        """Initialize the app database adapter."""
        self.dsn = dsn
        self.pool: asyncpg.Pool[asyncpg.Connection[asyncpg.Record]] | None = None

    async def connect(self) -> None:
        """Create connection pool with retry logic.

        Uses exponential backoff to handle container startup race conditions
        where the database may not be immediately available.
        """
        backoff = INITIAL_BACKOFF
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self.pool = await asyncpg.create_pool(
                    self.dsn,
                    min_size=2,
                    max_size=10,
                    command_timeout=60,
                )
                logger.info(
                    "app_database_connected",
                    dsn=self.dsn.split("@")[-1],
                    attempt=attempt,
                )
                return
            except (OSError, asyncpg.PostgresError) as e:
                last_error = e
                logger.warning(
                    "app_database_connection_failed",
                    attempt=attempt,
                    max_retries=MAX_RETRIES,
                    backoff_seconds=backoff,
                    error=str(e),
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF)

        # All retries exhausted
        logger.error(
            "app_database_connection_exhausted",
            max_retries=MAX_RETRIES,
            error=str(last_error),
        )
        raise ConnectionError(
            f"Failed to connect to database after {MAX_RETRIES} attempts: {last_error}"
        ) from last_error

    async def close(self) -> None:
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("app_database_disconnected")

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[asyncpg.Connection[asyncpg.Record]]:
        """Acquire a connection from the pool."""
        if self.pool is None:
            raise RuntimeError("Database pool not initialized")
        async with self.pool.acquire() as conn:
            yield conn

    async def fetch_one(self, query: str, *args: Any) -> dict[str, Any] | None:
        """Fetch a single row."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            if row:
                return dict(row)
            return None

    async def fetch_all(self, query: str, *args: Any) -> list[dict[str, Any]]:
        """Fetch all rows."""
        async with self.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]

    async def execute(self, query: str, *args: Any) -> str:
        """Execute a query and return status."""
        async with self.acquire() as conn:
            result: str = await conn.execute(query, *args)
            return result

    async def execute_returning(self, query: str, *args: Any) -> dict[str, Any] | None:
        """Execute a query with RETURNING clause."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            if row:
                return dict(row)
            return None

    # Tenant operations
    async def get_tenant(self, tenant_id: UUID) -> dict[str, Any] | None:
        """Get tenant by ID."""
        return await self.fetch_one(
            "SELECT * FROM tenants WHERE id = $1",
            tenant_id,
        )

    async def get_tenant_by_slug(self, slug: str) -> dict[str, Any] | None:
        """Get tenant by slug."""
        return await self.fetch_one(
            "SELECT * FROM tenants WHERE slug = $1",
            slug,
        )

    async def create_tenant(
        self, name: str, slug: str, settings: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Create a new tenant."""
        result = await self.execute_returning(
            """INSERT INTO tenants (name, slug, settings)
               VALUES ($1, $2, $3)
               RETURNING *""",
            name,
            slug,
            to_json_string(settings or {}),
        )
        if result is None:
            raise RuntimeError("Failed to create tenant")
        return result

    # API Key operations
    async def get_api_key_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        """Get API key by hash."""
        return await self.fetch_one(
            """SELECT ak.*, t.slug as tenant_slug, t.name as tenant_name
               FROM api_keys ak
               JOIN tenants t ON t.id = ak.tenant_id
               WHERE ak.key_hash = $1 AND ak.is_active = true""",
            key_hash,
        )

    async def update_api_key_last_used(self, key_id: UUID) -> None:
        """Update API key last used timestamp."""
        await self.execute(
            "UPDATE api_keys SET last_used_at = NOW() WHERE id = $1",
            key_id,
        )

    async def create_api_key(
        self,
        tenant_id: UUID,
        key_hash: str,
        key_prefix: str,
        name: str,
        scopes: list[str],
        user_id: UUID | None = None,
        expires_at: Any = None,
    ) -> dict[str, Any]:
        """Create a new API key."""
        result = await self.execute_returning(
            """INSERT INTO api_keys
            (tenant_id, user_id, key_hash, key_prefix, name, scopes, expires_at)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               RETURNING *""",
            tenant_id,
            user_id,
            key_hash,
            key_prefix,
            name,
            to_json_string(scopes),
            expires_at,
        )
        if result is None:
            raise RuntimeError("Failed to create API key")
        return result

    async def list_api_keys(self, tenant_id: UUID) -> list[dict[str, Any]]:
        """List all API keys for a tenant."""
        return await self.fetch_all(
            """SELECT id, key_prefix, name, scopes, is_active, last_used_at, expires_at, created_at
               FROM api_keys
               WHERE tenant_id = $1
               ORDER BY created_at DESC""",
            tenant_id,
        )

    async def revoke_api_key(self, key_id: UUID, tenant_id: UUID) -> bool:
        """Revoke an API key."""
        result = await self.execute(
            "UPDATE api_keys SET is_active = false WHERE id = $1 AND tenant_id = $2",
            key_id,
            tenant_id,
        )
        return "UPDATE 1" in result

    # Data Source operations
    async def list_data_sources(self, tenant_id: UUID) -> list[dict[str, Any]]:
        """List all data sources for a tenant."""
        return await self.fetch_all(
            """SELECT id, name, type, is_default, is_active,
                      connection_config_encrypted,
                      last_health_check_at, last_health_check_status, created_at
               FROM data_sources
               WHERE tenant_id = $1 AND is_active = true
               ORDER BY is_default DESC, name""",
            tenant_id,
        )

    async def get_data_source(self, data_source_id: UUID, tenant_id: UUID) -> dict[str, Any] | None:
        """Get a data source by ID."""
        return await self.fetch_one(
            "SELECT * FROM data_sources WHERE id = $1 AND tenant_id = $2",
            data_source_id,
            tenant_id,
        )

    async def create_data_source(
        self,
        tenant_id: UUID,
        name: str,
        type: str,
        connection_config_encrypted: str,
        is_default: bool = False,
    ) -> dict[str, Any]:
        """Create a new data source."""
        result = await self.execute_returning(
            """INSERT INTO data_sources
                (tenant_id, name, type, connection_config_encrypted, is_default)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING *""",
            tenant_id,
            name,
            type,
            connection_config_encrypted,
            is_default,
        )
        if result is None:
            raise RuntimeError("Failed to create data source")
        return result

    async def update_data_source_health(
        self,
        data_source_id: UUID,
        status: str,
    ) -> None:
        """Update data source health check status."""
        await self.execute(
            """UPDATE data_sources
               SET last_health_check_at = NOW(), last_health_check_status = $2
               WHERE id = $1""",
            data_source_id,
            status,
        )

    async def delete_data_source(self, data_source_id: UUID, tenant_id: UUID) -> bool:
        """Soft delete a data source."""
        result = await self.execute(
            "UPDATE data_sources SET is_active = false WHERE id = $1 AND tenant_id = $2",
            data_source_id,
            tenant_id,
        )
        return "UPDATE 1" in result

    async def find_datasources_by_platform(
        self, tenant_id: UUID, platform: str
    ) -> list[dict[str, Any]]:
        """Find data sources by platform type.

        Args:
            tenant_id: Tenant ID.
            platform: Platform type (e.g., 'postgresql', 'snowflake').

        Returns:
            List of matching data sources.
        """
        return await self.fetch_all(
            """SELECT id, name, type as platform, is_default, is_active,
                      last_health_check_at, created_at
               FROM data_sources
               WHERE tenant_id = $1 AND type = $2 AND is_active = true
               ORDER BY is_default DESC, name""",
            tenant_id,
            platform,
        )

    async def get_datasource(self, datasource_id: str, tenant_id: UUID) -> dict[str, Any] | None:
        """Get a datasource by ID (string version for SDK compatibility).

        Args:
            datasource_id: Datasource ID as string.
            tenant_id: Tenant ID.

        Returns:
            Datasource record or None.
        """
        try:
            ds_uuid = UUID(datasource_id)
        except ValueError:
            return None
        return await self.get_data_source(ds_uuid, tenant_id)

    # Dataset operations
    async def upsert_datasets(
        self,
        tenant_id: UUID,
        datasource_id: UUID,
        datasets: list[dict[str, Any]],
    ) -> int:
        """Upsert datasets during schema sync.

        Args:
            tenant_id: The tenant ID.
            datasource_id: The datasource ID.
            datasets: List of dataset dictionaries containing native_path, name, etc.

        Returns:
            Number of datasets upserted.
        """
        if not datasets:
            return 0

        query = """
            INSERT INTO datasets (
                tenant_id, datasource_id, native_path, name, table_type,
                schema_name, catalog_name, row_count, size_bytes, column_count,
                description, is_active, last_synced_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, true, NOW())
            ON CONFLICT (datasource_id, native_path)
            DO UPDATE SET
                name = EXCLUDED.name,
                table_type = EXCLUDED.table_type,
                schema_name = EXCLUDED.schema_name,
                catalog_name = EXCLUDED.catalog_name,
                row_count = EXCLUDED.row_count,
                size_bytes = EXCLUDED.size_bytes,
                column_count = EXCLUDED.column_count,
                description = EXCLUDED.description,
                is_active = true,
                last_synced_at = NOW(),
                updated_at = NOW()
        """

        async with self.acquire() as conn:
            await conn.executemany(
                query,
                [
                    (
                        tenant_id,
                        datasource_id,
                        dataset["native_path"],
                        dataset["name"],
                        dataset.get("table_type", "table"),
                        dataset.get("schema_name"),
                        dataset.get("catalog_name"),
                        dataset.get("row_count"),
                        dataset.get("size_bytes"),
                        dataset.get("column_count"),
                        dataset.get("description"),
                    )
                    for dataset in datasets
                ],
            )

        return len(datasets)

    async def get_datasets_by_datasource(
        self,
        tenant_id: UUID,
        datasource_id: UUID,
    ) -> list[dict[str, Any]]:
        """Get all active datasets for a datasource.

        Args:
            tenant_id: The tenant ID.
            datasource_id: The datasource ID.

        Returns:
            List of dataset dictionaries.
        """
        query = """
            SELECT id, datasource_id, native_path, name, table_type, schema_name,
                   catalog_name, row_count, size_bytes, column_count, description,
                   last_synced_at, created_at, updated_at
            FROM datasets
            WHERE tenant_id = $1 AND datasource_id = $2 AND is_active = true
            ORDER BY name
        """
        return await self.fetch_all(query, tenant_id, datasource_id)

    async def get_dataset_by_id(
        self,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> dict[str, Any] | None:
        """Get a single dataset by ID.

        Args:
            tenant_id: The tenant ID.
            dataset_id: The dataset ID.

        Returns:
            Dataset dictionary or None if not found.
        """
        query = """
            SELECT d.id, d.native_path, d.name, d.table_type, d.schema_name,
                   d.catalog_name, d.row_count, d.size_bytes, d.column_count,
                   d.description, d.last_synced_at, d.created_at, d.updated_at,
                   d.datasource_id, ds.name as datasource_name, ds.type as datasource_type
            FROM datasets d
            JOIN data_sources ds ON d.datasource_id = ds.id
            WHERE d.tenant_id = $1 AND d.id = $2 AND d.is_active = true
        """
        return await self.fetch_one(query, tenant_id, dataset_id)

    async def deactivate_stale_datasets(
        self,
        tenant_id: UUID,
        datasource_id: UUID,
        active_paths: set[str],
    ) -> int:
        """Mark datasets as inactive if they no longer exist in the datasource.

        Args:
            tenant_id: The tenant ID.
            datasource_id: The datasource ID.
            active_paths: Set of native paths that are still active.

        Returns:
            Number of datasets deactivated.
        """
        if not active_paths:
            # Deactivate all datasets for this datasource
            query = """
                WITH updated AS (
                    UPDATE datasets SET is_active = false, updated_at = NOW()
                    WHERE tenant_id = $1 AND datasource_id = $2 AND is_active = true
                    RETURNING 1
                )
                SELECT COUNT(*)::int as count FROM updated
            """
            result = await self.fetch_one(query, tenant_id, datasource_id)
            return result["count"] if result else 0

        # Deactivate datasets not in active_paths
        query = """
            WITH updated AS (
                UPDATE datasets SET is_active = false, updated_at = NOW()
                WHERE tenant_id = $1 AND datasource_id = $2
                AND is_active = true AND native_path != ALL($3::text[])
                RETURNING 1
            )
            SELECT COUNT(*)::int as count FROM updated
        """
        result = await self.fetch_one(query, tenant_id, datasource_id, list(active_paths))
        return result["count"] if result else 0

    async def list_datasets(
        self,
        tenant_id: UUID,
        datasource_id: UUID,
        table_type: str | None = None,
        search: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List datasets for a datasource with optional filtering.

        Args:
            tenant_id: The tenant ID.
            datasource_id: The datasource ID.
            table_type: Optional filter by table type.
            search: Optional search term for name or native_path.
            limit: Maximum number of datasets to return.
            offset: Number of datasets to skip.

        Returns:
            List of dataset dictionaries.
        """
        base_query = """
            SELECT id, datasource_id, native_path, name, table_type,
                   schema_name, catalog_name, row_count, column_count,
                   last_synced_at, created_at
            FROM datasets
            WHERE tenant_id = $1 AND datasource_id = $2 AND is_active = true
        """
        args: list[Any] = [tenant_id, datasource_id]
        idx = 3

        if table_type:
            base_query += f" AND table_type = ${idx}"
            args.append(table_type)
            idx += 1

        if search:
            base_query += f" AND (name ILIKE ${idx} OR native_path ILIKE ${idx})"
            args.append(f"%{search}%")
            idx += 1

        base_query += f" ORDER BY native_path LIMIT ${idx} OFFSET ${idx + 1}"
        args.extend([limit, offset])

        return await self.fetch_all(base_query, *args)

    async def get_dataset_count(
        self,
        tenant_id: UUID,
        datasource_id: UUID,
        table_type: str | None = None,
        search: str | None = None,
    ) -> int:
        """Get count of active datasets for a datasource with optional filtering.

        Args:
            tenant_id: The tenant ID.
            datasource_id: The datasource ID.
            table_type: Optional filter by table type.
            search: Optional search term for name or native_path.

        Returns:
            Number of active datasets matching the filters.
        """
        base_query = """
            SELECT COUNT(*)::int as count FROM datasets
            WHERE tenant_id = $1 AND datasource_id = $2 AND is_active = true
        """
        args: list[Any] = [tenant_id, datasource_id]
        idx = 3

        if table_type:
            base_query += f" AND table_type = ${idx}"
            args.append(table_type)
            idx += 1

        if search:
            base_query += f" AND (name ILIKE ${idx} OR native_path ILIKE ${idx})"
            args.append(f"%{search}%")

        result = await self.fetch_one(base_query, *args)
        return result["count"] if result else 0

    # Investigation operations
    async def create_investigation(
        self,
        tenant_id: UUID,
        dataset_id: str,
        metric_name: str,
        data_source_id: UUID | None = None,
        created_by: UUID | None = None,
        expected_value: float | None = None,
        actual_value: float | None = None,
        deviation_pct: float | None = None,
        anomaly_date: str | None = None,
        severity: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new investigation."""
        result = await self.execute_returning(
            """INSERT INTO investigations
               (tenant_id, data_source_id, created_by, dataset_id, metric_name,
                expected_value, actual_value, deviation_pct, anomaly_date, severity, metadata)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
               RETURNING *""",
            tenant_id,
            data_source_id,
            created_by,
            dataset_id,
            metric_name,
            expected_value,
            actual_value,
            deviation_pct,
            anomaly_date,
            severity,
            to_json_string(metadata or {}),
        )
        if result is None:
            raise RuntimeError("Failed to create investigation")
        return result

    async def get_investigation(
        self, investigation_id: UUID, tenant_id: UUID
    ) -> dict[str, Any] | None:
        """Get an investigation by ID."""
        return await self.fetch_one(
            "SELECT * FROM investigations WHERE id = $1 AND tenant_id = $2",
            investigation_id,
            tenant_id,
        )

    async def list_investigations(
        self,
        tenant_id: UUID,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List investigations for a tenant."""
        if status:
            return await self.fetch_all(
                """SELECT * FROM investigations
                   WHERE tenant_id = $1 AND status = $2
                   ORDER BY created_at DESC
                   LIMIT $3 OFFSET $4""",
                tenant_id,
                status,
                limit,
                offset,
            )
        return await self.fetch_all(
            """SELECT * FROM investigations
               WHERE tenant_id = $1
               ORDER BY created_at DESC
               LIMIT $2 OFFSET $3""",
            tenant_id,
            limit,
            offset,
        )

    async def list_investigations_for_dataset(
        self,
        tenant_id: UUID,
        dataset_native_path: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List investigations that reference a dataset.

        Args:
            tenant_id: The tenant ID.
            dataset_native_path: The native path of the dataset.
            limit: Maximum number of investigations to return.

        Returns:
            List of investigation dictionaries.
        """
        query = """
            SELECT id, dataset_id, metric_name, status, severity,
                   created_at, completed_at
            FROM investigations
            WHERE tenant_id = $1 AND dataset_id = $2
            ORDER BY created_at DESC
            LIMIT $3
        """
        return await self.fetch_all(query, tenant_id, dataset_native_path, limit)

    async def update_investigation_status(
        self,
        investigation_id: UUID,
        status: str,
        events: list[Any] | None = None,
        finding: dict[str, Any] | None = None,
        started_at: Any = None,
        completed_at: Any = None,
        duration_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        """Update investigation status and optionally other fields."""
        updates = ["status = $2"]
        args: list[Any] = [investigation_id, status]
        idx = 3

        if events is not None:
            updates.append(f"events = ${idx}")
            args.append(to_json_string(events))
            idx += 1

        if finding is not None:
            updates.append(f"finding = ${idx}")
            args.append(to_json_string(finding))
            idx += 1

        if started_at is not None:
            updates.append(f"started_at = ${idx}")
            args.append(started_at)
            idx += 1

        if completed_at is not None:
            updates.append(f"completed_at = ${idx}")
            args.append(completed_at)
            idx += 1

        if duration_seconds is not None:
            updates.append(f"duration_seconds = ${idx}")
            args.append(duration_seconds)
            idx += 1

        query = f"""UPDATE investigations SET {", ".join(updates)}
                    WHERE id = $1 RETURNING *"""

        return await self.execute_returning(query, *args)

    # Audit log operations
    async def create_audit_log(
        self,
        tenant_id: UUID,
        action: str,
        actor_id: UUID | None = None,
        actor_email: str | None = None,
        actor_ip: str | None = None,
        actor_user_agent: str | None = None,
        resource_type: str | None = None,
        resource_id: UUID | None = None,
        resource_name: str | None = None,
        request_method: str | None = None,
        request_path: str | None = None,
        status_code: int | None = None,
        changes: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Create an audit log entry.

        Args:
            tenant_id: The tenant this log belongs to.
            action: Action performed (e.g., "teams.created", "investigations.read").
            actor_id: User ID who performed the action.
            actor_email: Email of the user who performed the action.
            actor_ip: IP address of the request.
            actor_user_agent: User agent string from the request.
            resource_type: Type of resource affected (e.g., "teams", "investigations").
            resource_id: ID of the specific resource affected.
            resource_name: Human-readable name of the resource.
            request_method: HTTP method (GET, POST, PUT, DELETE).
            request_path: Full request path.
            status_code: HTTP response status code.
            changes: JSON object with request body or changes made.
            metadata: Additional metadata about the request.
        """
        await self.execute(
            """INSERT INTO audit_logs
               (tenant_id, action, actor_id, actor_email, actor_ip, actor_user_agent,
                resource_type, resource_id, resource_name, request_method, request_path,
                status_code, changes, metadata)
               VALUES ($1, $2, $3, $4, $5::inet, $6, $7, $8, $9, $10, $11, $12, $13, $14)""",
            tenant_id,
            action,
            actor_id,
            actor_email,
            actor_ip,
            actor_user_agent,
            resource_type,
            resource_id,
            resource_name,
            request_method,
            request_path,
            status_code,
            to_json_string(changes) if changes else None,
            to_json_string(metadata) if metadata else None,
        )

    # Webhook operations
    async def list_webhooks(self, tenant_id: UUID) -> list[dict[str, Any]]:
        """List all webhooks for a tenant."""
        return await self.fetch_all(
            """SELECT * FROM webhooks WHERE tenant_id = $1 ORDER BY created_at DESC""",
            tenant_id,
        )

    async def get_webhooks_for_event(
        self, tenant_id: UUID, event_type: str
    ) -> list[dict[str, Any]]:
        """Get active webhooks that subscribe to an event type."""
        return await self.fetch_all(
            """SELECT * FROM webhooks
               WHERE tenant_id = $1 AND is_active = true AND events ? $2""",
            tenant_id,
            event_type,
        )

    async def create_webhook(
        self,
        tenant_id: UUID,
        url: str,
        events: list[str],
        secret: str | None = None,
    ) -> dict[str, Any]:
        """Create a new webhook."""
        result = await self.execute_returning(
            """INSERT INTO webhooks (tenant_id, url, secret, events)
               VALUES ($1, $2, $3, $4)
               RETURNING *""",
            tenant_id,
            url,
            secret,
            to_json_string(events),
        )
        if result is None:
            raise RuntimeError("Failed to create webhook")
        return result

    async def update_webhook_status(
        self,
        webhook_id: UUID,
        status: int,
    ) -> None:
        """Update webhook last triggered status."""
        await self.execute(
            """UPDATE webhooks SET last_triggered_at = NOW(), last_status = $2
               WHERE id = $1""",
            webhook_id,
            status,
        )

    # Usage tracking
    async def record_usage(
        self,
        tenant_id: UUID,
        resource_type: str,
        quantity: int,
        unit_cost: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a usage event."""
        await self.execute(
            """INSERT INTO usage_records (tenant_id, resource_type, quantity, unit_cost, metadata)
               VALUES ($1, $2, $3, $4, $5)""",
            tenant_id,
            resource_type,
            quantity,
            unit_cost,
            to_json_string(metadata or {}),
        )

    async def get_monthly_usage(
        self, tenant_id: UUID, year: int, month: int
    ) -> list[dict[str, Any]]:
        """Get usage summary for a specific month."""
        return await self.fetch_all(
            """SELECT resource_type, SUM(quantity) as total_quantity, SUM(unit_cost) as total_cost
               FROM usage_records
               WHERE tenant_id = $1
                 AND EXTRACT(YEAR FROM timestamp) = $2
                 AND EXTRACT(MONTH FROM timestamp) = $3
               GROUP BY resource_type""",
            tenant_id,
            year,
            month,
        )

    # Approval requests
    async def create_approval_request(
        self,
        investigation_id: UUID,
        tenant_id: UUID,
        request_type: str,
        context: dict[str, Any],
        requested_by: str = "system",
    ) -> dict[str, Any]:
        """Create an approval request."""
        result = await self.execute_returning(
            """INSERT INTO approval_requests
                (investigation_id, tenant_id, request_type, context, requested_by)
               VALUES ($1, $2, $3, $4, $5)
               RETURNING *""",
            investigation_id,
            tenant_id,
            request_type,
            to_json_string(context),
            requested_by,
        )
        if result is None:
            raise RuntimeError("Failed to create approval request")
        return result

    async def get_pending_approvals(self, tenant_id: UUID) -> list[dict[str, Any]]:
        """Get all pending approval requests for a tenant."""
        return await self.fetch_all(
            """SELECT ar.*, i.dataset_id, i.metric_name, i.severity
               FROM approval_requests ar
               JOIN investigations i ON i.id = ar.investigation_id
               WHERE ar.tenant_id = $1 AND ar.decision IS NULL
               ORDER BY ar.requested_at DESC""",
            tenant_id,
        )

    async def make_approval_decision(
        self,
        approval_id: UUID,
        tenant_id: UUID,
        decision: str,
        decided_by: UUID,
        comment: str | None = None,
        modifications: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Record an approval decision."""
        return await self.execute_returning(
            """UPDATE approval_requests
               SET decision = $3, decided_by = $4, decided_at = NOW(),
                   comment = $5, modifications = $6
               WHERE id = $1 AND tenant_id = $2
               RETURNING *""",
            approval_id,
            tenant_id,
            decision,
            decided_by,
            comment,
            to_json_string(modifications) if modifications else None,
        )

    # Dashboard stats
    async def get_dashboard_stats(self, tenant_id: UUID) -> dict[str, Any]:
        """Get dashboard statistics for a tenant."""
        # Active investigations
        active_result = await self.fetch_one(
            """SELECT COUNT(*) as count FROM investigations
               WHERE tenant_id = $1 AND status IN ('pending', 'in_progress')""",
            tenant_id,
        )

        # Completed today
        completed_result = await self.fetch_one(
            """SELECT COUNT(*) as count FROM investigations
               WHERE tenant_id = $1 AND status = 'completed'
                 AND completed_at >= CURRENT_DATE""",
            tenant_id,
        )

        # Data sources
        ds_result = await self.fetch_one(
            """SELECT COUNT(*) as count FROM data_sources
               WHERE tenant_id = $1 AND is_active = true""",
            tenant_id,
        )

        # Pending approvals
        approvals_result = await self.fetch_one(
            """SELECT COUNT(*) as count FROM approval_requests
               WHERE tenant_id = $1 AND decision IS NULL""",
            tenant_id,
        )

        return {
            "activeInvestigations": active_result["count"] if active_result else 0,
            "completedToday": completed_result["count"] if completed_result else 0,
            "dataSources": ds_result["count"] if ds_result else 0,
            "pendingApprovals": approvals_result["count"] if approvals_result else 0,
        }

    # Feedback event operations
    async def list_feedback_events(
        self,
        tenant_id: UUID,
        investigation_id: UUID | None = None,
        dataset_id: UUID | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List feedback events with optional filtering.

        Args:
            tenant_id: The tenant ID.
            investigation_id: Optional investigation ID filter.
            dataset_id: Optional dataset ID filter.
            event_type: Optional event type filter.
            limit: Maximum events to return.
            offset: Number of events to skip.

        Returns:
            List of feedback event dictionaries.
        """
        base_query = """
            SELECT id, investigation_id, dataset_id, event_type,
                   event_data, actor_id, actor_type, created_at
            FROM investigation_feedback_events
            WHERE tenant_id = $1
        """
        args: list[Any] = [tenant_id]
        idx = 2

        if investigation_id:
            base_query += f" AND investigation_id = ${idx}"
            args.append(investigation_id)
            idx += 1

        if dataset_id:
            base_query += f" AND dataset_id = ${idx}"
            args.append(dataset_id)
            idx += 1

        if event_type:
            base_query += f" AND event_type = ${idx}"
            args.append(event_type)
            idx += 1

        base_query += f" ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
        args.extend([limit, offset])

        return await self.fetch_all(base_query, *args)

    async def count_feedback_events(
        self,
        tenant_id: UUID,
        investigation_id: UUID | None = None,
        dataset_id: UUID | None = None,
        event_type: str | None = None,
    ) -> int:
        """Count feedback events with optional filtering.

        Args:
            tenant_id: The tenant ID.
            investigation_id: Optional investigation ID filter.
            dataset_id: Optional dataset ID filter.
            event_type: Optional event type filter.

        Returns:
            Number of matching events.
        """
        base_query = """
            SELECT COUNT(*)::int as count FROM investigation_feedback_events
            WHERE tenant_id = $1
        """
        args: list[Any] = [tenant_id]
        idx = 2

        if investigation_id:
            base_query += f" AND investigation_id = ${idx}"
            args.append(investigation_id)
            idx += 1

        if dataset_id:
            base_query += f" AND dataset_id = ${idx}"
            args.append(dataset_id)
            idx += 1

        if event_type:
            base_query += f" AND event_type = ${idx}"
            args.append(event_type)

        result = await self.fetch_one(base_query, *args)
        return result["count"] if result else 0

    # Schema comment operations
    async def create_schema_comment(
        self,
        tenant_id: UUID,
        dataset_id: UUID,
        field_name: str,
        content: str,
        parent_id: UUID | None = None,
        author_id: UUID | None = None,
        author_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a schema comment.

        Args:
            tenant_id: The tenant ID.
            dataset_id: The dataset ID.
            field_name: The schema field name.
            content: The comment content (markdown).
            parent_id: Parent comment ID for replies.
            author_id: The author's user ID.
            author_name: The author's display name.

        Returns:
            The created comment as a dict.
        """
        query = """
            INSERT INTO schema_comments
                (tenant_id, dataset_id, field_name, parent_id, content, author_id, author_name)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING id, tenant_id, dataset_id, field_name, parent_id, content,
                      author_id, author_name, upvotes, downvotes, created_at, updated_at
        """
        result = await self.execute_returning(
            query, tenant_id, dataset_id, field_name, parent_id, content, author_id, author_name
        )
        if result is None:
            raise RuntimeError("Failed to create schema comment")
        return result

    async def list_schema_comments(
        self,
        tenant_id: UUID,
        dataset_id: UUID,
        field_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List schema comments for a dataset.

        Args:
            tenant_id: The tenant ID.
            dataset_id: The dataset ID.
            field_name: Optional filter by field name.

        Returns:
            List of comments ordered by votes then recency.
        """
        if field_name:
            query = """
                SELECT id, tenant_id, dataset_id, field_name, parent_id, content,
                       author_id, author_name, upvotes, downvotes, created_at, updated_at
                FROM schema_comments
                WHERE tenant_id = $1 AND dataset_id = $2 AND field_name = $3
                ORDER BY (upvotes - downvotes) DESC, created_at DESC
            """
            return await self.fetch_all(query, tenant_id, dataset_id, field_name)
        else:
            query = """
                SELECT id, tenant_id, dataset_id, field_name, parent_id, content,
                       author_id, author_name, upvotes, downvotes, created_at, updated_at
                FROM schema_comments
                WHERE tenant_id = $1 AND dataset_id = $2
                ORDER BY field_name, (upvotes - downvotes) DESC, created_at DESC
            """
            return await self.fetch_all(query, tenant_id, dataset_id)

    async def get_schema_comment(
        self,
        tenant_id: UUID,
        comment_id: UUID,
    ) -> dict[str, Any] | None:
        """Get a single schema comment.

        Args:
            tenant_id: The tenant ID.
            comment_id: The comment ID.

        Returns:
            The comment or None if not found.
        """
        query = """
            SELECT id, tenant_id, dataset_id, field_name, parent_id, content,
                   author_id, author_name, upvotes, downvotes, created_at, updated_at
            FROM schema_comments
            WHERE tenant_id = $1 AND id = $2
        """
        return await self.fetch_one(query, tenant_id, comment_id)

    async def update_schema_comment(
        self,
        tenant_id: UUID,
        comment_id: UUID,
        content: str,
    ) -> dict[str, Any] | None:
        """Update a schema comment's content.

        Args:
            tenant_id: The tenant ID.
            comment_id: The comment ID.
            content: The new content.

        Returns:
            The updated comment or None if not found.
        """
        query = """
            UPDATE schema_comments
            SET content = $3, updated_at = now()
            WHERE tenant_id = $1 AND id = $2
            RETURNING id, tenant_id, dataset_id, field_name, parent_id, content,
                      author_id, author_name, upvotes, downvotes, created_at, updated_at
        """
        return await self.execute_returning(query, tenant_id, comment_id, content)

    async def delete_schema_comment(
        self,
        tenant_id: UUID,
        comment_id: UUID,
    ) -> bool:
        """Delete a schema comment.

        Args:
            tenant_id: The tenant ID.
            comment_id: The comment ID.

        Returns:
            True if deleted, False if not found.
        """
        query = """
            DELETE FROM schema_comments
            WHERE tenant_id = $1 AND id = $2
        """
        result = await self.execute(query, tenant_id, comment_id)
        return result == "DELETE 1"

    # Knowledge comment operations
    async def create_knowledge_comment(
        self,
        tenant_id: UUID,
        dataset_id: UUID,
        content: str,
        parent_id: UUID | None = None,
        author_id: UUID | None = None,
        author_name: str | None = None,
    ) -> dict[str, Any]:
        """Create a knowledge comment.

        Args:
            tenant_id: The tenant ID.
            dataset_id: The dataset ID.
            content: The comment content (markdown).
            parent_id: Parent comment ID for replies.
            author_id: The author's user ID.
            author_name: The author's display name.

        Returns:
            The created comment as a dict.
        """
        query = """
            INSERT INTO knowledge_comments
                (tenant_id, dataset_id, parent_id, content, author_id, author_name)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, tenant_id, dataset_id, parent_id, content,
                      author_id, author_name, upvotes, downvotes, created_at, updated_at
        """
        result = await self.execute_returning(
            query, tenant_id, dataset_id, parent_id, content, author_id, author_name
        )
        if result is None:
            raise RuntimeError("Failed to create knowledge comment")
        return result

    async def list_knowledge_comments(
        self,
        tenant_id: UUID,
        dataset_id: UUID,
    ) -> list[dict[str, Any]]:
        """List knowledge comments for a dataset.

        Args:
            tenant_id: The tenant ID.
            dataset_id: The dataset ID.

        Returns:
            List of comments ordered by votes then recency.
        """
        query = """
            SELECT id, tenant_id, dataset_id, parent_id, content,
                   author_id, author_name, upvotes, downvotes, created_at, updated_at
            FROM knowledge_comments
            WHERE tenant_id = $1 AND dataset_id = $2
            ORDER BY (upvotes - downvotes) DESC, created_at DESC
        """
        return await self.fetch_all(query, tenant_id, dataset_id)

    async def get_knowledge_comment(
        self,
        tenant_id: UUID,
        comment_id: UUID,
    ) -> dict[str, Any] | None:
        """Get a single knowledge comment.

        Args:
            tenant_id: The tenant ID.
            comment_id: The comment ID.

        Returns:
            The comment or None if not found.
        """
        query = """
            SELECT id, tenant_id, dataset_id, parent_id, content,
                   author_id, author_name, upvotes, downvotes, created_at, updated_at
            FROM knowledge_comments
            WHERE tenant_id = $1 AND id = $2
        """
        return await self.fetch_one(query, tenant_id, comment_id)

    async def update_knowledge_comment(
        self,
        tenant_id: UUID,
        comment_id: UUID,
        content: str,
    ) -> dict[str, Any] | None:
        """Update a knowledge comment's content.

        Args:
            tenant_id: The tenant ID.
            comment_id: The comment ID.
            content: The new content.

        Returns:
            The updated comment or None if not found.
        """
        query = """
            UPDATE knowledge_comments
            SET content = $3, updated_at = now()
            WHERE tenant_id = $1 AND id = $2
            RETURNING id, tenant_id, dataset_id, parent_id, content,
                      author_id, author_name, upvotes, downvotes, created_at, updated_at
        """
        return await self.execute_returning(query, tenant_id, comment_id, content)

    async def delete_knowledge_comment(
        self,
        tenant_id: UUID,
        comment_id: UUID,
    ) -> bool:
        """Delete a knowledge comment.

        Args:
            tenant_id: The tenant ID.
            comment_id: The comment ID.

        Returns:
            True if deleted, False if not found.
        """
        query = """
            DELETE FROM knowledge_comments
            WHERE tenant_id = $1 AND id = $2
        """
        result = await self.execute(query, tenant_id, comment_id)
        return result == "DELETE 1"

    # Comment vote operations
    async def upsert_comment_vote(
        self,
        tenant_id: UUID,
        comment_type: str,
        comment_id: UUID,
        user_id: UUID,
        vote: int,
    ) -> None:
        """Create or update a comment vote.

        Args:
            tenant_id: The tenant ID.
            comment_type: 'schema' or 'knowledge'.
            comment_id: The comment ID.
            user_id: The user ID.
            vote: 1 for upvote, -1 for downvote.
        """
        # Upsert vote
        vote_query = """
            INSERT INTO comment_votes (tenant_id, comment_type, comment_id, user_id, vote)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (comment_type, comment_id, user_id)
            DO UPDATE SET vote = $5
        """
        await self.execute(vote_query, tenant_id, comment_type, comment_id, user_id, vote)

        # Update vote counts on the comment
        await self._update_comment_vote_counts(comment_type, comment_id)

    async def delete_comment_vote(
        self,
        tenant_id: UUID,
        comment_type: str,
        comment_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Delete a comment vote.

        Args:
            tenant_id: The tenant ID.
            comment_type: 'schema' or 'knowledge'.
            comment_id: The comment ID.
            user_id: The user ID.

        Returns:
            True if deleted, False if not found.
        """
        query = """
            DELETE FROM comment_votes
            WHERE tenant_id = $1 AND comment_type = $2 AND comment_id = $3 AND user_id = $4
        """
        result = await self.execute(query, tenant_id, comment_type, comment_id, user_id)
        if result == "DELETE 1":
            await self._update_comment_vote_counts(comment_type, comment_id)
            return True
        return False

    async def _update_comment_vote_counts(self, comment_type: str, comment_id: UUID) -> None:
        """Recalculate vote counts for a comment.

        Args:
            comment_type: 'schema' or 'knowledge'.
            comment_id: The comment ID.
        """
        table = "schema_comments" if comment_type == "schema" else "knowledge_comments"
        query = f"""
            UPDATE {table}
            SET upvotes = (
                    SELECT COUNT(*) FROM comment_votes
                    WHERE comment_type = $1 AND comment_id = $2 AND vote = 1
                ),
                downvotes = (
                    SELECT COUNT(*) FROM comment_votes
                    WHERE comment_type = $1 AND comment_id = $2 AND vote = -1
                )
            WHERE id = $2
        """
        await self.execute(query, comment_type, comment_id)

    # Notification operations
    async def create_notification(
        self,
        tenant_id: UUID,
        type: str,
        title: str,
        body: str | None = None,
        resource_kind: str | None = None,
        resource_id: UUID | None = None,
        severity: str = "info",
    ) -> dict[str, Any]:
        """Create a new notification.

        Args:
            tenant_id: The tenant ID.
            type: Notification type (e.g., 'investigation_completed').
            title: Notification title.
            body: Optional notification body.
            resource_kind: Optional resource type (e.g., 'investigation').
            resource_id: Optional resource ID for linking.
            severity: Notification severity ('info', 'success', 'warning', 'error').

        Returns:
            The created notification as a dict.
        """
        result = await self.execute_returning(
            """INSERT INTO notifications
               (tenant_id, type, title, body, resource_kind, resource_id, severity)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               RETURNING *""",
            tenant_id,
            type,
            title,
            body,
            resource_kind,
            resource_id,
            severity,
        )
        if result is None:
            raise RuntimeError("Failed to create notification")
        return result

    async def list_notifications(
        self,
        tenant_id: UUID,
        user_id: UUID,
        limit: int = 50,
        cursor: str | None = None,
        unread_only: bool = False,
    ) -> tuple[list[dict[str, Any]], str | None, bool]:
        """List notifications with cursor pagination.

        Uses cursor-based pagination with base64(created_at|id) format.
        Returns notifications with read_at populated from the user's read state.

        Args:
            tenant_id: The tenant ID.
            user_id: The user ID (for read state).
            limit: Maximum notifications to return (max 100).
            cursor: Pagination cursor (base64 encoded created_at|id).
            unread_only: If True, only return unread notifications.

        Returns:
            Tuple of (notifications, next_cursor, has_more).
        """
        import base64
        from datetime import datetime

        # Cap limit at 100
        limit = min(limit, 100)

        # Parse cursor if provided
        cursor_created_at: datetime | None = None
        cursor_id: UUID | None = None
        if cursor:
            try:
                decoded = base64.b64decode(cursor).decode()
                parts = decoded.split("|")
                cursor_created_at = datetime.fromisoformat(parts[0])
                cursor_id = UUID(parts[1])
            except (ValueError, IndexError):
                pass  # Invalid cursor, start from beginning

        # Build query
        base_query = """
            SELECT n.id, n.tenant_id, n.type, n.title, n.body,
                   n.resource_kind, n.resource_id, n.severity, n.created_at,
                   nr.read_at
            FROM notifications n
            LEFT JOIN notification_reads nr
                ON n.id = nr.notification_id AND nr.user_id = $2
            WHERE n.tenant_id = $1
        """
        args: list[Any] = [tenant_id, user_id]
        idx = 3

        # Add cursor filter
        if cursor_created_at and cursor_id:
            base_query += f"""
                AND (n.created_at, n.id) < (${idx}, ${idx + 1})
            """
            args.extend([cursor_created_at, cursor_id])
            idx += 2

        # Add unread filter
        if unread_only:
            base_query += " AND nr.read_at IS NULL"

        # Order and limit (fetch one extra to check has_more)
        base_query += f"""
            ORDER BY n.created_at DESC, n.id DESC
            LIMIT ${idx}
        """
        args.append(limit + 1)

        rows = await self.fetch_all(base_query, *args)

        # Check if there are more results
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        # Build next cursor from last row
        next_cursor: str | None = None
        if has_more and rows:
            last = rows[-1]
            cursor_str = f"{last['created_at'].isoformat()}|{last['id']}"
            next_cursor = base64.b64encode(cursor_str.encode()).decode()

        return rows, next_cursor, has_more

    async def get_notification(
        self,
        notification_id: UUID,
        tenant_id: UUID,
    ) -> dict[str, Any] | None:
        """Get a notification by ID.

        Args:
            notification_id: The notification ID.
            tenant_id: The tenant ID.

        Returns:
            The notification or None if not found.
        """
        return await self.fetch_one(
            "SELECT * FROM notifications WHERE id = $1 AND tenant_id = $2",
            notification_id,
            tenant_id,
        )

    async def mark_notification_read(
        self,
        notification_id: UUID,
        user_id: UUID,
        tenant_id: UUID,
    ) -> bool:
        """Mark a notification as read for a user.

        Idempotent - if already read, does nothing.

        Args:
            notification_id: The notification ID.
            user_id: The user ID.
            tenant_id: The tenant ID.

        Returns:
            True if notification exists and was marked read, False if not found.
        """
        # First verify notification exists and belongs to tenant
        notification = await self.get_notification(notification_id, tenant_id)
        if not notification:
            return False

        # Insert read record (idempotent via ON CONFLICT DO NOTHING)
        await self.execute(
            """INSERT INTO notification_reads (notification_id, user_id, read_at)
               VALUES ($1, $2, NOW())
               ON CONFLICT (notification_id, user_id) DO NOTHING""",
            notification_id,
            user_id,
        )
        return True

    async def mark_all_notifications_read(
        self,
        tenant_id: UUID,
        user_id: UUID,
    ) -> tuple[int, str | None]:
        """Mark all notifications as read for a user.

        Returns cursor pointing to newest marked notification for resumability.

        Args:
            tenant_id: The tenant ID.
            user_id: The user ID.

        Returns:
            Tuple of (count marked, cursor of newest notification).
        """
        import base64

        # Get all unread notification IDs for tenant (ordered by created_at DESC)
        unread_query = """
            SELECT n.id, n.created_at
            FROM notifications n
            LEFT JOIN notification_reads nr
                ON n.id = nr.notification_id AND nr.user_id = $2
            WHERE n.tenant_id = $1 AND nr.read_at IS NULL
            ORDER BY n.created_at DESC, n.id DESC
        """
        unread = await self.fetch_all(unread_query, tenant_id, user_id)

        if not unread:
            return 0, None

        # Batch insert read records
        insert_query = """
            INSERT INTO notification_reads (notification_id, user_id, read_at)
            SELECT id, $2, NOW()
            FROM notifications n
            WHERE n.tenant_id = $1
            AND NOT EXISTS (
                SELECT 1 FROM notification_reads nr
                WHERE nr.notification_id = n.id AND nr.user_id = $2
            )
        """
        await self.execute(insert_query, tenant_id, user_id)

        # Build cursor from newest notification
        newest = unread[0]
        cursor_str = f"{newest['created_at'].isoformat()}|{newest['id']}"
        cursor = base64.b64encode(cursor_str.encode()).decode()

        return len(unread), cursor

    async def get_unread_notification_count(
        self,
        tenant_id: UUID,
        user_id: UUID,
    ) -> int:
        """Get count of unread notifications for a user.

        Args:
            tenant_id: The tenant ID.
            user_id: The user ID.

        Returns:
            Number of unread notifications.
        """
        result = await self.fetch_one(
            """SELECT COUNT(*)::int as count
               FROM notifications n
               LEFT JOIN notification_reads nr
                   ON n.id = nr.notification_id AND nr.user_id = $2
               WHERE n.tenant_id = $1 AND nr.read_at IS NULL""",
            tenant_id,
            user_id,
        )
        return result["count"] if result else 0

    async def get_new_notifications(
        self,
        tenant_id: UUID,
        since_id: UUID | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get new notifications since a given notification ID.

        Used by SSE endpoint to poll for new notifications.
        Returns notifications created after the given ID, ordered by created_at ASC
        so clients can process them in chronological order.

        Args:
            tenant_id: The tenant ID.
            since_id: Optional notification ID to get notifications after.
            limit: Maximum notifications to return.

        Returns:
            List of notification dictionaries.
        """
        if since_id:
            # Get notifications created after the reference notification
            query = """
                SELECT n.id, n.tenant_id, n.type, n.title, n.body,
                       n.resource_kind, n.resource_id, n.severity, n.created_at
                FROM notifications n
                WHERE n.tenant_id = $1
                AND (n.created_at, n.id) > (
                    SELECT created_at, id FROM notifications WHERE id = $2
                )
                ORDER BY n.created_at ASC, n.id ASC
                LIMIT $3
            """
            return await self.fetch_all(query, tenant_id, since_id, limit)
        else:
            # No cursor - get most recent notifications
            query = """
                SELECT n.id, n.tenant_id, n.type, n.title, n.body,
                       n.resource_kind, n.resource_id, n.severity, n.created_at
                FROM notifications n
                WHERE n.tenant_id = $1
                ORDER BY n.created_at DESC, n.id DESC
                LIMIT $2
            """
            # Return in chronological order (oldest first)
            rows = await self.fetch_all(query, tenant_id, limit)
            return list(reversed(rows))

    # User Datasource Credentials operations

    async def get_user_credentials(
        self,
        user_id: UUID,
        datasource_id: UUID,
    ) -> dict[str, Any] | None:
        """Get user credentials for a datasource.

        Args:
            user_id: The user ID.
            datasource_id: The datasource ID.

        Returns:
            Credentials record or None if not found.
        """
        return await self.fetch_one(
            """SELECT id, user_id, datasource_id, credentials_encrypted,
                      db_username, last_used_at, created_at, updated_at
               FROM user_datasource_credentials
               WHERE user_id = $1 AND datasource_id = $2""",
            user_id,
            datasource_id,
        )

    async def upsert_user_credentials(
        self,
        user_id: UUID,
        datasource_id: UUID,
        credentials_encrypted: bytes,
        db_username: str | None = None,
    ) -> dict[str, Any]:
        """Upsert user credentials for a datasource.

        Args:
            user_id: The user ID.
            datasource_id: The datasource ID.
            credentials_encrypted: Encrypted credentials blob.
            db_username: Optional username for display.

        Returns:
            Created or updated credentials record.
        """
        result = await self.execute_returning(
            """INSERT INTO user_datasource_credentials
                   (user_id, datasource_id, credentials_encrypted, db_username)
               VALUES ($1, $2, $3, $4)
               ON CONFLICT (user_id, datasource_id) DO UPDATE SET
                   credentials_encrypted = EXCLUDED.credentials_encrypted,
                   db_username = EXCLUDED.db_username,
                   updated_at = NOW()
               RETURNING *""",
            user_id,
            datasource_id,
            credentials_encrypted,
            db_username,
        )
        if result is None:
            raise RuntimeError("Failed to upsert user credentials")
        return result

    async def delete_user_credentials(
        self,
        user_id: UUID,
        datasource_id: UUID,
    ) -> bool:
        """Delete user credentials for a datasource.

        Args:
            user_id: The user ID.
            datasource_id: The datasource ID.

        Returns:
            True if deleted, False if not found.
        """
        result = await self.execute(
            """DELETE FROM user_datasource_credentials
               WHERE user_id = $1 AND datasource_id = $2""",
            user_id,
            datasource_id,
        )
        return "DELETE 1" in result

    async def update_credentials_last_used(
        self,
        user_id: UUID,
        datasource_id: UUID,
        last_used_at: Any,
    ) -> None:
        """Update credentials last_used_at timestamp.

        Args:
            user_id: The user ID.
            datasource_id: The datasource ID.
            last_used_at: The timestamp to set.
        """
        await self.execute(
            """UPDATE user_datasource_credentials
               SET last_used_at = $3
               WHERE user_id = $1 AND datasource_id = $2""",
            user_id,
            datasource_id,
            last_used_at,
        )

    # Query Audit Log operations

    async def insert_query_audit_log(
        self,
        tenant_id: UUID,
        user_id: UUID,
        datasource_id: UUID,
        sql_hash: str,
        sql_text: str | None,
        tables_accessed: list[str] | None,
        executed_at: Any,
        duration_ms: int,
        row_count: int | None,
        status: str,
        error_message: str | None,
        investigation_id: UUID | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Insert a query audit log entry.

        Args:
            tenant_id: The tenant ID.
            user_id: The user ID.
            datasource_id: The datasource ID.
            sql_hash: Hash of the SQL query.
            sql_text: The SQL query text.
            tables_accessed: List of table names accessed.
            executed_at: When the query was executed.
            duration_ms: Query duration in milliseconds.
            row_count: Number of rows returned.
            status: Query status (success, denied, error, timeout).
            error_message: Error message if any.
            investigation_id: Optional investigation ID.
            source: Query source (agent, api, preview, etc.).

        Returns:
            Created audit log record.
        """
        result = await self.execute_returning(
            """INSERT INTO query_audit_log
                   (tenant_id, user_id, datasource_id, sql_hash, sql_text,
                    tables_accessed, executed_at, duration_ms, row_count,
                    status, error_message, investigation_id, source)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
               RETURNING *""",
            tenant_id,
            user_id,
            datasource_id,
            sql_hash,
            sql_text,
            tables_accessed,
            executed_at,
            duration_ms,
            row_count,
            status,
            error_message,
            investigation_id,
            source,
        )
        if result is None:
            raise RuntimeError("Failed to insert query audit log")
        return result

    async def search_asset_instances(
        self,
        tenant_id: UUID,
        query: str,
        limit: int = 10,
        cursor: str | None = None,
        datasource_id: UUID | None = None,
    ) -> tuple[list[dict[str, Any]], str | None, int | None]:
        """Search for asset instances (datasets) across all tenant datasources.

        Args:
            tenant_id: The tenant ID.
            query: Search query (matched against name and native_path).
            limit: Maximum results to return (max 100).
            cursor: Opaque pagination cursor (base64 encoded).
            datasource_id: Optional filter to single datasource.

        Returns:
            Tuple of (results, next_cursor, total_hint).
        """
        import base64

        # Cap limit at 100
        limit = min(limit, 100)

        # Parse cursor if provided (format: base64(native_path|datasource_id|dataset_id))
        cursor_path: str | None = None
        cursor_ds_id: UUID | None = None
        cursor_dataset_id: UUID | None = None
        if cursor:
            try:
                decoded = base64.b64decode(cursor).decode()
                parts = decoded.split("|")
                cursor_path = parts[0]
                cursor_ds_id = UUID(parts[1])
                cursor_dataset_id = UUID(parts[2])
            except (ValueError, IndexError):
                pass  # Invalid cursor, start from beginning

        # Build the search query
        search_pattern = f"%{query}%"

        # Base query with datasource join
        base_query = """
            SELECT d.id, d.datasource_id, d.native_path, d.name, d.table_type,
                   d.schema_name, d.catalog_name, d.row_count, d.column_count,
                   ds.name as datasource_name, ds.type as platform,
                   CASE
                       WHEN d.name ILIKE $2 THEN 'name_prefix'
                       WHEN d.native_path ILIKE $2 THEN 'path_match'
                       ELSE 'fuzzy'
                   END as match_reason
            FROM datasets d
            JOIN data_sources ds ON d.datasource_id = ds.id
            WHERE d.tenant_id = $1
              AND ds.is_active = true
              AND d.is_active = true
              AND (d.name ILIKE $3 OR d.native_path ILIKE $3)
        """
        args: list[Any] = [tenant_id, f"{query}%", search_pattern]
        idx = 4

        # Add datasource filter if provided
        if datasource_id:
            base_query += f" AND d.datasource_id = ${idx}"
            args.append(datasource_id)
            idx += 1

        # Add cursor filter
        if cursor_path and cursor_ds_id and cursor_dataset_id:
            base_query += f"""
                AND (d.native_path, d.datasource_id, d.id) > (${idx}, ${idx + 1}, ${idx + 2})
            """
            args.extend([cursor_path, cursor_ds_id, cursor_dataset_id])
            idx += 3

        # Order and limit (fetch one extra to check has_more)
        base_query += f"""
            ORDER BY d.native_path, d.datasource_id, d.id
            LIMIT ${idx}
        """
        args.append(limit + 1)

        rows = await self.fetch_all(base_query, *args)

        # Check if there are more results
        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        # Build next cursor from last row
        next_cursor: str | None = None
        if has_more and rows:
            last = rows[-1]
            cursor_str = f"{last['native_path']}|{last['datasource_id']}|{last['id']}"
            next_cursor = base64.b64encode(cursor_str.encode()).decode()

        # Get total hint (approximate count for UI)
        count_query = """
            SELECT COUNT(*)::int as count
            FROM datasets d
            JOIN data_sources ds ON d.datasource_id = ds.id
            WHERE d.tenant_id = $1
              AND ds.is_active = true
              AND d.is_active = true
              AND (d.name ILIKE $2 OR d.native_path ILIKE $2)
        """
        count_args: list[Any] = [tenant_id, search_pattern]
        if datasource_id:
            count_query += " AND d.datasource_id = $3"
            count_args.append(datasource_id)

        count_result = await self.fetch_one(count_query, *count_args)
        total_hint = count_result["count"] if count_result else None

        return rows, next_cursor, total_hint

    async def get_query_audit_logs(
        self,
        tenant_id: UUID,
        user_id: UUID | None = None,
        datasource_id: UUID | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Get query audit logs with optional filters.

        Args:
            tenant_id: The tenant ID.
            user_id: Optional user ID filter.
            datasource_id: Optional datasource ID filter.
            status: Optional status filter.
            limit: Maximum records to return.
            offset: Number of records to skip.

        Returns:
            List of audit log records.
        """
        conditions = ["tenant_id = $1"]
        params: list[Any] = [tenant_id]
        param_idx = 2

        if user_id:
            conditions.append(f"user_id = ${param_idx}")
            params.append(user_id)
            param_idx += 1

        if datasource_id:
            conditions.append(f"datasource_id = ${param_idx}")
            params.append(datasource_id)
            param_idx += 1

        if status:
            conditions.append(f"status = ${param_idx}")
            params.append(status)
            param_idx += 1

        where_clause = " AND ".join(conditions)
        params.extend([limit, offset])

        query = f"""
            SELECT id, tenant_id, user_id, datasource_id, sql_hash, sql_text,
                   tables_accessed, executed_at, duration_ms, row_count,
                   status, error_message, investigation_id, source
            FROM query_audit_log
            WHERE {where_clause}
            ORDER BY executed_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        return await self.fetch_all(query, *params)
