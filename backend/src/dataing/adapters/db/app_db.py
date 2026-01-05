"""Application database adapter using asyncpg."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import asyncpg
import structlog

logger = structlog.get_logger()


class AppDatabase:
    """Application database for storing tenants, users, investigations, etc."""

    def __init__(self, dsn: str):
        """Initialize the app database adapter."""
        self.dsn = dsn
        self.pool: asyncpg.Pool[asyncpg.Connection[asyncpg.Record]] | None = None

    async def connect(self) -> None:
        """Create connection pool."""
        self.pool = await asyncpg.create_pool(
            self.dsn,
            min_size=2,
            max_size=10,
            command_timeout=60,
        )
        logger.info("app_database_connected", dsn=self.dsn.split("@")[-1])

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
            json.dumps(settings or {}),
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
            json.dumps(scopes),
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
            json.dumps(metadata or {}),
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
            args.append(json.dumps(events))
            idx += 1

        if finding is not None:
            updates.append(f"finding = ${idx}")
            args.append(json.dumps(finding))
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
        user_id: UUID | None = None,
        api_key_id: UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_body: dict[str, Any] | None = None,
        response_status: int | None = None,
    ) -> None:
        """Create an audit log entry."""
        await self.execute(
            """INSERT INTO audit_logs
               (tenant_id, user_id, api_key_id, action, resource_type, resource_id,
                request_id, ip_address, user_agent, request_body, response_status)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8::inet, $9, $10, $11)""",
            tenant_id,
            user_id,
            api_key_id,
            action,
            resource_type,
            resource_id,
            request_id,
            ip_address,
            user_agent,
            json.dumps(request_body) if request_body else None,
            response_status,
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
            json.dumps(events),
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
            json.dumps(metadata or {}),
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
            json.dumps(context),
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
            json.dumps(modifications) if modifications else None,
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
