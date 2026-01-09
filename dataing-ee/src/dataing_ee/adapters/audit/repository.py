"""Audit log repository."""

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from asyncpg import Pool

from dataing_ee.adapters.audit.types import AuditLogCreate, AuditLogEntry

logger = structlog.get_logger()


class AuditRepository:
    """Repository for audit log operations."""

    def __init__(self, pool: Pool) -> None:
        """Initialize the repository.

        Args:
            pool: Database connection pool.
        """
        self._pool = pool

    async def record(self, entry: AuditLogCreate) -> UUID:
        """Record an audit log entry.

        Args:
            entry: Audit log entry to record.

        Returns:
            ID of the created entry.
        """
        query = """
            INSERT INTO audit_logs (
                tenant_id, actor_id, actor_email, actor_ip, actor_user_agent,
                action, resource_type, resource_id, resource_name,
                request_method, request_path, status_code, changes, metadata
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
            )
            RETURNING id
        """
        async with self._pool.acquire() as conn:
            # Convert UUIDs to strings at database boundary
            # Domain model uses UUID, but asyncpg needs str for parameterized queries
            row = await conn.fetchrow(
                query,
                str(entry.tenant_id),
                str(entry.actor_id) if entry.actor_id else None,
                entry.actor_email,
                entry.actor_ip,
                entry.actor_user_agent,
                entry.action,
                entry.resource_type,
                str(entry.resource_id) if entry.resource_id else None,
                entry.resource_name,
                entry.request_method,
                entry.request_path,
                entry.status_code,
                entry.changes,
                entry.metadata,
            )
            result: UUID = row["id"]
            return result

    async def list(
        self,
        tenant_id: UUID,
        limit: int = 50,
        offset: int = 0,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        action: str | None = None,
        actor_id: UUID | None = None,
        resource_type: str | None = None,
        search: str | None = None,
    ) -> tuple[list[AuditLogEntry], int]:
        """List audit log entries with filters.

        Args:
            tenant_id: Tenant to filter by.
            limit: Maximum entries to return.
            offset: Number of entries to skip.
            start_date: Filter entries after this date.
            end_date: Filter entries before this date.
            action: Filter by action type.
            actor_id: Filter by actor.
            resource_type: Filter by resource type.
            search: Search in resource_name and action.

        Returns:
            Tuple of (entries, total_count).
        """
        # Convert UUIDs to strings at database boundary
        conditions = ["tenant_id = $1"]
        params: list[Any] = [str(tenant_id)]
        param_idx = 2

        if start_date:
            conditions.append(f"timestamp >= ${param_idx}")
            params.append(start_date)
            param_idx += 1

        if end_date:
            conditions.append(f"timestamp <= ${param_idx}")
            params.append(end_date)
            param_idx += 1

        if action:
            conditions.append(f"action = ${param_idx}")
            params.append(action)
            param_idx += 1

        if actor_id:
            conditions.append(f"actor_id = ${param_idx}")
            params.append(str(actor_id))
            param_idx += 1

        if resource_type:
            conditions.append(f"resource_type = ${param_idx}")
            params.append(resource_type)
            param_idx += 1

        if search:
            conditions.append(f"(resource_name ILIKE ${param_idx} OR action ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1

        where_clause = " AND ".join(conditions)

        count_query = f"SELECT COUNT(*) FROM audit_logs WHERE {where_clause}"
        list_query = f"""
            SELECT * FROM audit_logs
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])

        async with self._pool.acquire() as conn:
            total = await conn.fetchval(count_query, *params[:-2])
            rows = await conn.fetch(list_query, *params)

        entries = [
            AuditLogEntry(
                id=row["id"],
                timestamp=row["timestamp"],
                tenant_id=row["tenant_id"],
                actor_id=row["actor_id"],
                actor_email=row["actor_email"],
                actor_ip=row["actor_ip"],
                actor_user_agent=row["actor_user_agent"],
                action=row["action"],
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                resource_name=row["resource_name"],
                request_method=row["request_method"],
                request_path=row["request_path"],
                status_code=row["status_code"],
                changes=row["changes"],
                metadata=row["metadata"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        total_count: int = total or 0
        return entries, total_count

    async def get(self, tenant_id: UUID, entry_id: UUID) -> AuditLogEntry | None:
        """Get a single audit log entry.

        Args:
            tenant_id: Tenant ID for access control.
            entry_id: Entry ID to fetch.

        Returns:
            Audit log entry or None if not found.
        """
        query = "SELECT * FROM audit_logs WHERE tenant_id = $1 AND id = $2"
        async with self._pool.acquire() as conn:
            # Convert UUIDs to strings at database boundary
            row = await conn.fetchrow(query, str(tenant_id), str(entry_id))

        if not row:
            return None

        return AuditLogEntry(
            id=row["id"],
            timestamp=row["timestamp"],
            tenant_id=row["tenant_id"],
            actor_id=row["actor_id"],
            actor_email=row["actor_email"],
            actor_ip=row["actor_ip"],
            actor_user_agent=row["actor_user_agent"],
            action=row["action"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            resource_name=row["resource_name"],
            request_method=row["request_method"],
            request_path=row["request_path"],
            status_code=row["status_code"],
            changes=row["changes"],
            metadata=row["metadata"],
            created_at=row["created_at"],
        )

    async def delete_before(self, cutoff: datetime) -> int:
        """Delete audit logs before cutoff date.

        Args:
            cutoff: Delete entries older than this.

        Returns:
            Number of entries deleted.
        """
        query = "DELETE FROM audit_logs WHERE timestamp < $1"
        async with self._pool.acquire() as conn:
            result = await conn.execute(query, cutoff)

        # Result is like "DELETE 100"
        count_str = result.split()[-1]
        return int(count_str)
