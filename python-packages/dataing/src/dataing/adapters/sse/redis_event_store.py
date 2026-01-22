"""Redis-backed SSE event store.

This module provides persistent storage for SSE run events with:
- Event storage with automatic sequencing
- Metadata tracking per run
- Configurable replay window with TTL
- Atomic operations for concurrent access
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger()


@dataclass
class SSEEvent:
    """An SSE event."""

    seq: int
    event: str
    run_id: str
    data: dict[str, Any]
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dictionary."""
        return {
            "seq": self.seq,
            "event": self.event,
            "run_id": self.run_id,
            "data": self.data,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SSEEvent:
        """Deserialize event from dictionary."""
        return cls(
            seq=data["seq"],
            event=data["event"],
            run_id=data["run_id"],
            data=data["data"],
            timestamp=data["timestamp"],
        )


@dataclass
class SSEEventStoreConfig:
    """Configuration for the SSE event store."""

    key_prefix: str = "dataing:sse"
    replay_window_seconds: int = 300  # 5 minutes
    event_ttl_seconds: int = 3600  # 1 hour for events
    metadata_ttl_seconds: int = 3600  # 1 hour for metadata


@dataclass
class RunMetadata:
    """Metadata for a run."""

    run_id: str
    bundle_id: str | None = None
    bundle_hash: str | None = None
    status: str = "running"
    goal: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    completed_at: str | None = None
    tenant_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize metadata to dictionary."""
        return {
            "run_id": self.run_id,
            "bundle_id": self.bundle_id,
            "bundle_hash": self.bundle_hash,
            "status": self.status,
            "goal": self.goal,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "tenant_id": self.tenant_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RunMetadata:
        """Deserialize metadata from dictionary."""
        return cls(
            run_id=data.get("run_id", ""),
            bundle_id=data.get("bundle_id"),
            bundle_hash=data.get("bundle_hash"),
            status=data.get("status", "running"),
            goal=data.get("goal"),
            created_at=data.get("created_at", ""),
            completed_at=data.get("completed_at"),
            tenant_id=data.get("tenant_id"),
        )


class RedisSSEEventStore:
    """Redis-backed SSE event store with replay support."""

    def __init__(
        self,
        redis: Redis,
        config: SSEEventStoreConfig | None = None,
    ) -> None:
        """Initialize the SSE event store."""
        self.redis = redis
        self.config = config or SSEEventStoreConfig()

    def _events_key(self, run_id: str) -> str:
        """Get the key for run events (sorted set by seq)."""
        return f"{self.config.key_prefix}:events:{run_id}"

    def _metadata_key(self, run_id: str) -> str:
        """Get the key for run metadata (hash)."""
        return f"{self.config.key_prefix}:metadata:{run_id}"

    def _seq_key(self, run_id: str) -> str:
        """Get the key for sequence counter."""
        return f"{self.config.key_prefix}:seq:{run_id}"

    async def store_event(
        self,
        run_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> int:
        """Store an event and return its sequence number.

        Args:
            run_id: The run ID.
            event_type: The event type.
            data: The event data.

        Returns:
            The sequence number of the stored event.
        """
        events_key = self._events_key(run_id)
        seq_key = self._seq_key(run_id)

        # Atomically increment sequence number
        seq = await self.redis.incr(seq_key)

        event = SSEEvent(
            seq=seq,
            event=event_type,
            run_id=run_id,
            data=data,
            timestamp=datetime.now(UTC).isoformat(),
        )

        # Store event in sorted set (score = seq for ordering)
        event_json = json.dumps(event.to_dict())
        await self.redis.zadd(events_key, {event_json: seq})

        # Set TTL on events
        await self.redis.expire(events_key, self.config.event_ttl_seconds)
        await self.redis.expire(seq_key, self.config.event_ttl_seconds)

        logger.debug(
            "sse_event_stored",
            run_id=run_id,
            event_type=event_type,
            seq=seq,
        )

        seq_int: int = seq
        return seq_int

    async def get_events_after(
        self,
        run_id: str,
        after_seq: int,
    ) -> list[dict[str, Any]]:
        """Get events after a sequence number.

        Args:
            run_id: The run ID.
            after_seq: Return events with seq > after_seq.

        Returns:
            List of event dictionaries ordered by sequence.
        """
        events_key = self._events_key(run_id)

        # Get events with score > after_seq (exclusive)
        # zrangebyscore returns events ordered by score (seq)
        event_jsons = await self.redis.zrangebyscore(
            events_key,
            min=f"({after_seq}",  # ( means exclusive
            max="+inf",
        )

        events = []
        for event_json in event_jsons:
            event_str = event_json.decode() if isinstance(event_json, bytes) else event_json
            events.append(json.loads(event_str))

        return events

    async def store_metadata(
        self,
        run_id: str,
        metadata: RunMetadata,
    ) -> None:
        """Store run metadata.

        Args:
            run_id: The run ID.
            metadata: The run metadata.
        """
        metadata_key = self._metadata_key(run_id)

        # Store as hash fields
        metadata_dict = metadata.to_dict()
        # Convert None values to empty strings for Redis
        redis_dict = {k: v if v is not None else "" for k, v in metadata_dict.items()}

        await self.redis.hset(metadata_key, mapping=redis_dict)  # type: ignore[misc]
        await self.redis.expire(metadata_key, self.config.metadata_ttl_seconds)

        logger.debug("sse_metadata_stored", run_id=run_id, status=metadata.status)

    async def get_metadata(self, run_id: str) -> RunMetadata | None:
        """Get run metadata.

        Args:
            run_id: The run ID.

        Returns:
            The run metadata or None if not found.
        """
        metadata_key = self._metadata_key(run_id)

        data: dict[bytes, bytes] = await self.redis.hgetall(metadata_key)  # type: ignore[misc]
        if not data:
            return None

        # Decode bytes and convert empty strings back to None
        decoded = {}
        for k, v in data.items():
            key = k.decode() if isinstance(k, bytes) else k
            val = v.decode() if isinstance(v, bytes) else v
            decoded[key] = val if val else None

        return RunMetadata.from_dict(decoded)

    async def update_status(
        self,
        run_id: str,
        status: str,
        completed_at: str | None = None,
    ) -> None:
        """Update run status.

        Args:
            run_id: The run ID.
            status: The new status.
            completed_at: Optional completion timestamp.
        """
        metadata_key = self._metadata_key(run_id)

        updates: dict[str, str] = {"status": status}
        if completed_at:
            updates["completed_at"] = completed_at

        await self.redis.hset(metadata_key, mapping=updates)  # type: ignore[misc]

        logger.debug("sse_status_updated", run_id=run_id, status=status)

    async def is_replay_window_expired(self, run_id: str) -> bool:
        """Check if the replay window has expired for a run.

        A run's replay window expires when:
        1. The run is completed/failed, AND
        2. More than replay_window_seconds have passed since completion

        Args:
            run_id: The run ID.

        Returns:
            True if replay window has expired.
        """
        metadata = await self.get_metadata(run_id)
        if not metadata:
            return True  # No metadata = expired

        # If run is still active, window is not expired
        if metadata.status not in ("completed", "failed", "cancelled"):
            return False

        # Check if completion time exceeds replay window
        completed_at = metadata.completed_at
        if not completed_at:
            return False

        try:
            completed_dt = datetime.fromisoformat(completed_at)
            elapsed = (datetime.now(UTC) - completed_dt).total_seconds()
            return elapsed > self.config.replay_window_seconds
        except (ValueError, TypeError):
            return False

    async def exists(self, run_id: str) -> bool:
        """Check if a run exists in the store.

        Args:
            run_id: The run ID.

        Returns:
            True if the run exists.
        """
        metadata_key = self._metadata_key(run_id)
        exists_result = await self.redis.exists(metadata_key)
        return bool(exists_result)

    async def get_latest_seq(self, run_id: str) -> int:
        """Get the latest sequence number for a run.

        Args:
            run_id: The run ID.

        Returns:
            The latest sequence number or 0 if no events.
        """
        seq_key = self._seq_key(run_id)
        seq = await self.redis.get(seq_key)
        if seq:
            return int(seq.decode() if isinstance(seq, bytes) else seq)
        return 0

    async def cleanup_run(self, run_id: str) -> None:
        """Clean up all data for a run.

        Args:
            run_id: The run ID.
        """
        events_key = self._events_key(run_id)
        metadata_key = self._metadata_key(run_id)
        seq_key = self._seq_key(run_id)

        await self.redis.delete(events_key, metadata_key, seq_key)

        logger.debug("sse_run_cleaned_up", run_id=run_id)


class InMemoryFallbackSSEEventStore:
    """In-memory fallback when Redis is not available.

    Provides the same interface as RedisSSEEventStore for local development.
    """

    def __init__(self, config: SSEEventStoreConfig | None = None) -> None:
        """Initialize the in-memory store."""
        self.config = config or SSEEventStoreConfig()
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._metadata: dict[str, RunMetadata] = {}
        self._seq: dict[str, int] = {}

    async def store_event(
        self,
        run_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> int:
        """Store an event and return its sequence number."""
        if run_id not in self._events:
            self._events[run_id] = []
            self._seq[run_id] = 0

        self._seq[run_id] += 1
        seq = self._seq[run_id]

        event = SSEEvent(
            seq=seq,
            event=event_type,
            run_id=run_id,
            data=data,
            timestamp=datetime.now(UTC).isoformat(),
        )
        self._events[run_id].append(event.to_dict())

        return seq

    async def get_events_after(
        self,
        run_id: str,
        after_seq: int,
    ) -> list[dict[str, Any]]:
        """Get events after a sequence number."""
        events = self._events.get(run_id, [])
        return [e for e in events if e["seq"] > after_seq]

    async def store_metadata(self, run_id: str, metadata: RunMetadata) -> None:
        """Store run metadata."""
        self._metadata[run_id] = metadata

    async def get_metadata(self, run_id: str) -> RunMetadata | None:
        """Get run metadata."""
        return self._metadata.get(run_id)

    async def update_status(
        self,
        run_id: str,
        status: str,
        completed_at: str | None = None,
    ) -> None:
        """Update run status."""
        if run_id in self._metadata:
            self._metadata[run_id].status = status
            if completed_at:
                self._metadata[run_id].completed_at = completed_at

    async def is_replay_window_expired(self, run_id: str) -> bool:
        """Check if the replay window has expired."""
        metadata = self._metadata.get(run_id)
        if not metadata:
            return True

        if metadata.status not in ("completed", "failed", "cancelled"):
            return False

        if not metadata.completed_at:
            return False

        try:
            completed_dt = datetime.fromisoformat(metadata.completed_at)
            elapsed = (datetime.now(UTC) - completed_dt).total_seconds()
            return elapsed > self.config.replay_window_seconds
        except (ValueError, TypeError):
            return False

    async def exists(self, run_id: str) -> bool:
        """Check if a run exists."""
        return run_id in self._metadata

    async def get_latest_seq(self, run_id: str) -> int:
        """Get the latest sequence number."""
        return self._seq.get(run_id, 0)

    async def cleanup_run(self, run_id: str) -> None:
        """Clean up all data for a run."""
        self._events.pop(run_id, None)
        self._metadata.pop(run_id, None)
        self._seq.pop(run_id, None)
