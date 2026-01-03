"""Application database adapter using asyncpg."""

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
