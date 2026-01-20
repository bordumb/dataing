"""PostgreSQL repository for SDK bundles and runs.

Provides persistence for SDK context bundles and investigation runs,
replacing the in-memory stores in the API routes.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from dataing.core.json_utils import to_json_string

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase


class BundleRepository:
    """Repository for SDK context bundles."""

    def __init__(self, db: AppDatabase) -> None:
        """Initialize the repository.

        Args:
            db: Application database instance.
        """
        self.db = db

    async def create_bundle(
        self,
        tenant_id: UUID,
        bundle_hash: str,
        assets: list[dict[str, Any]],
        window: str | None = None,
        lineage: dict[str, Any] | None = None,
        operational: dict[str, Any] | None = None,
        anomalies: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a new bundle or return existing one with same hash.

        Args:
            tenant_id: Tenant ID.
            bundle_hash: Content-addressable hash.
            assets: List of asset references.
            window: Time window specification.
            lineage: Lineage graph data.
            operational: Operational facts.
            anomalies: Anomaly summaries.

        Returns:
            Bundle record dict.
        """
        # Try to get existing bundle first
        existing = await self.get_bundle_by_hash(tenant_id, bundle_hash)
        if existing:
            return existing

        result = await self.db.execute_returning(
            """
            INSERT INTO sdk_bundles (tenant_id, bundle_hash, assets, window, lineage, operational, anomalies)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (tenant_id, bundle_hash) DO UPDATE SET
                tenant_id = EXCLUDED.tenant_id
            RETURNING id, tenant_id, bundle_hash, assets, window, lineage, operational, anomalies, created_at, expires_at
            """,
            tenant_id,
            bundle_hash,
            to_json_string(assets),
            window,
            to_json_string(lineage) if lineage else None,
            to_json_string(operational) if operational else None,
            to_json_string(anomalies) if anomalies else None,
        )
        if result is None:
            raise RuntimeError("Failed to create bundle")
        return self._row_to_bundle(result)

    async def get_bundle(self, bundle_id: UUID) -> dict[str, Any] | None:
        """Get bundle by ID.

        Args:
            bundle_id: Bundle UUID.

        Returns:
            Bundle record or None if not found.
        """
        result = await self.db.fetch_one(
            """
            SELECT id, tenant_id, bundle_hash, assets, window, lineage, operational, anomalies, created_at, expires_at
            FROM sdk_bundles
            WHERE id = $1
            """,
            bundle_id,
        )
        if result is None:
            return None
        return self._row_to_bundle(result)

    async def get_bundle_by_hash(
        self, tenant_id: UUID, bundle_hash: str
    ) -> dict[str, Any] | None:
        """Get bundle by hash (content-addressable lookup).

        Args:
            tenant_id: Tenant ID.
            bundle_hash: Content hash.

        Returns:
            Bundle record or None if not found.
        """
        result = await self.db.fetch_one(
            """
            SELECT id, tenant_id, bundle_hash, assets, window, lineage, operational, anomalies, created_at, expires_at
            FROM sdk_bundles
            WHERE tenant_id = $1 AND bundle_hash = $2
            """,
            tenant_id,
            bundle_hash,
        )
        if result is None:
            return None
        return self._row_to_bundle(result)

    def _row_to_bundle(self, row: Any) -> dict[str, Any]:
        """Convert database row to bundle dict."""
        return {
            "id": str(row["id"]),
            "tenant_id": str(row["tenant_id"]),
            "bundle_hash": row["bundle_hash"],
            "assets": json.loads(row["assets"]) if isinstance(row["assets"], str) else row["assets"],
            "window": row["window"],
            "lineage": json.loads(row["lineage"]) if row["lineage"] and isinstance(row["lineage"], str) else row["lineage"],
            "operational": json.loads(row["operational"]) if row["operational"] and isinstance(row["operational"], str) else row["operational"],
            "anomalies": json.loads(row["anomalies"]) if row["anomalies"] and isinstance(row["anomalies"], str) else row["anomalies"],
            "created_at": row["created_at"],
            "expires_at": row["expires_at"],
        }


class RunRepository:
    """Repository for SDK investigation runs."""

    def __init__(self, db: AppDatabase) -> None:
        """Initialize the repository.

        Args:
            db: Application database instance.
        """
        self.db = db

    async def create_run(
        self,
        run_id: UUID,
        tenant_id: UUID,
        bundle_id: UUID | None,
        bundle_hash: str,
        goal: str,
    ) -> dict[str, Any]:
        """Create a new run.

        Args:
            run_id: Pre-generated run ID.
            tenant_id: Tenant ID.
            bundle_id: Optional bundle reference.
            bundle_hash: Bundle hash for quick lookups.
            goal: Investigation goal/question.

        Returns:
            Run record dict.
        """
        result = await self.db.execute_returning(
            """
            INSERT INTO sdk_runs (id, tenant_id, bundle_id, bundle_hash, goal, status)
            VALUES ($1, $2, $3, $4, $5, 'running')
            RETURNING id, tenant_id, bundle_id, bundle_hash, goal, status, created_at, completed_at
            """,
            run_id,
            tenant_id,
            bundle_id,
            bundle_hash,
            goal,
        )
        if result is None:
            raise RuntimeError("Failed to create run")
        return self._row_to_run(result)

    async def get_run(self, run_id: UUID) -> dict[str, Any] | None:
        """Get run by ID.

        Args:
            run_id: Run UUID.

        Returns:
            Run record or None if not found.
        """
        result = await self.db.fetch_one(
            """
            SELECT id, tenant_id, bundle_id, bundle_hash, goal, status, created_at, completed_at
            FROM sdk_runs
            WHERE id = $1
            """,
            run_id,
        )
        if result is None:
            return None
        return self._row_to_run(result)

    async def update_run_status(
        self,
        run_id: UUID,
        status: str,
    ) -> None:
        """Update run status.

        Args:
            run_id: Run UUID.
            status: New status (running, completed, failed, cancelled).
        """
        completed_at = datetime.now(UTC) if status in ("completed", "failed", "cancelled") else None
        await self.db.execute(
            """
            UPDATE sdk_runs
            SET status = $2, completed_at = $3
            WHERE id = $1
            """,
            run_id,
            status,
            completed_at,
        )

    async def store_event(
        self,
        run_id: UUID,
        seq: int,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Store an SSE event.

        Args:
            run_id: Run UUID.
            seq: Sequence number.
            event_type: Event type string.
            data: Event payload.
        """
        await self.db.execute(
            """
            INSERT INTO sdk_run_events (run_id, seq, event_type, data)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (run_id, seq) DO NOTHING
            """,
            run_id,
            seq,
            event_type,
            to_json_string(data),
        )

    async def get_events_after(
        self,
        run_id: UUID,
        after_seq: int,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get events after a sequence number (for SSE replay).

        Args:
            run_id: Run UUID.
            after_seq: Get events with seq > this value.
            limit: Max events to return.

        Returns:
            List of event records.
        """
        results = await self.db.fetch_all(
            """
            SELECT id, run_id, seq, event_type, data, timestamp
            FROM sdk_run_events
            WHERE run_id = $1 AND seq > $2
            ORDER BY seq ASC
            LIMIT $3
            """,
            run_id,
            after_seq,
            limit,
        )
        return [self._row_to_event(row) for row in results]

    async def get_all_events(self, run_id: UUID) -> list[dict[str, Any]]:
        """Get all events for a run.

        Args:
            run_id: Run UUID.

        Returns:
            List of all event records ordered by seq.
        """
        results = await self.db.fetch_all(
            """
            SELECT id, run_id, seq, event_type, data, timestamp
            FROM sdk_run_events
            WHERE run_id = $1
            ORDER BY seq ASC
            """,
            run_id,
        )
        return [self._row_to_event(row) for row in results]

    async def get_max_seq(self, run_id: UUID) -> int:
        """Get the maximum sequence number for a run.

        Args:
            run_id: Run UUID.

        Returns:
            Max seq or 0 if no events.
        """
        result = await self.db.fetch_one(
            """
            SELECT COALESCE(MAX(seq), 0) as max_seq
            FROM sdk_run_events
            WHERE run_id = $1
            """,
            run_id,
        )
        return result["max_seq"] if result else 0

    def _row_to_run(self, row: Any) -> dict[str, Any]:
        """Convert database row to run dict."""
        return {
            "run_id": str(row["id"]),
            "tenant_id": str(row["tenant_id"]),
            "bundle_id": str(row["bundle_id"]) if row["bundle_id"] else None,
            "bundle_hash": row["bundle_hash"],
            "goal": row["goal"],
            "status": row["status"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }

    def _row_to_event(self, row: Any) -> dict[str, Any]:
        """Convert database row to event dict."""
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)
        return {
            "id": row["id"],
            "run_id": str(row["run_id"]),
            "seq": row["seq"],
            "event": row["event_type"],
            "data": data,
            "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
        }
