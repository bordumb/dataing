"""Unit tests for RedisSSEEventStore."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from dataing.adapters.sse.redis_event_store import (
    InMemoryFallbackSSEEventStore,
    RedisSSEEventStore,
    RunMetadata,
    SSEEvent,
    SSEEventStoreConfig,
)


class TestSSEEvent:
    """Tests for SSEEvent."""

    def test_event_to_dict(self) -> None:
        """Test event serialization."""
        event = SSEEvent(
            seq=1,
            event="run_started",
            run_id="test-run-1",
            data={"goal": "test goal"},
            timestamp="2024-01-01T00:00:00+00:00",
        )

        data = event.to_dict()

        assert data["seq"] == 1
        assert data["event"] == "run_started"
        assert data["run_id"] == "test-run-1"
        assert data["data"] == {"goal": "test goal"}

    def test_event_from_dict(self) -> None:
        """Test event deserialization."""
        data = {
            "seq": 2,
            "event": "run_completed",
            "run_id": "test-run-2",
            "data": {"result": "success"},
            "timestamp": "2024-01-01T00:00:00+00:00",
        }

        event = SSEEvent.from_dict(data)

        assert event.seq == 2
        assert event.event == "run_completed"
        assert event.run_id == "test-run-2"


class TestRunMetadata:
    """Tests for RunMetadata."""

    def test_metadata_to_dict(self) -> None:
        """Test metadata serialization."""
        metadata = RunMetadata(
            run_id="test-run",
            bundle_id="bundle-1",
            bundle_hash="hash123",
            status="running",
            goal="test goal",
            tenant_id="tenant-1",
        )

        data = metadata.to_dict()

        assert data["run_id"] == "test-run"
        assert data["bundle_id"] == "bundle-1"
        assert data["status"] == "running"

    def test_metadata_from_dict(self) -> None:
        """Test metadata deserialization."""
        data = {
            "run_id": "test-run",
            "bundle_id": "bundle-1",
            "bundle_hash": "hash123",
            "status": "completed",
            "goal": "test goal",
            "created_at": "2024-01-01T00:00:00",
            "completed_at": "2024-01-01T00:01:00",
            "tenant_id": "tenant-1",
        }

        metadata = RunMetadata.from_dict(data)

        assert metadata.run_id == "test-run"
        assert metadata.status == "completed"
        assert metadata.completed_at == "2024-01-01T00:01:00"


class TestRedisSSEEventStore:
    """Tests for RedisSSEEventStore."""

    @pytest.fixture
    def mock_redis(self) -> AsyncMock:
        """Create a mock Redis client."""
        mock = AsyncMock()
        mock.incr = AsyncMock(return_value=1)
        mock.zadd = AsyncMock()
        mock.zrangebyscore = AsyncMock(return_value=[])
        mock.expire = AsyncMock()
        mock.hset = AsyncMock()
        mock.hgetall = AsyncMock(return_value={})
        mock.exists = AsyncMock(return_value=0)
        mock.get = AsyncMock(return_value=None)
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def event_store(self, mock_redis: AsyncMock) -> RedisSSEEventStore:
        """Create an event store with mock Redis."""
        return RedisSSEEventStore(mock_redis, SSEEventStoreConfig())

    async def test_store_event(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test storing an event."""
        seq = await event_store.store_event(
            run_id="test-run",
            event_type="run_started",
            data={"goal": "test"},
        )

        assert seq == 1
        mock_redis.incr.assert_called()
        mock_redis.zadd.assert_called()
        mock_redis.expire.assert_called()

    async def test_store_event_increments_seq(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test that storing events increments sequence."""
        mock_redis.incr.side_effect = [1, 2, 3]

        seq1 = await event_store.store_event("run-1", "event1", {})
        seq2 = await event_store.store_event("run-1", "event2", {})
        seq3 = await event_store.store_event("run-1", "event3", {})

        assert seq1 == 1
        assert seq2 == 2
        assert seq3 == 3

    async def test_get_events_after(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test getting events after a sequence."""
        event1 = {"seq": 2, "event": "progress", "run_id": "run-1", "data": {}, "timestamp": ""}
        event2 = {"seq": 3, "event": "completed", "run_id": "run-1", "data": {}, "timestamp": ""}
        mock_redis.zrangebyscore.return_value = [
            json.dumps(event1).encode(),
            json.dumps(event2).encode(),
        ]

        events = await event_store.get_events_after("run-1", after_seq=1)

        assert len(events) == 2
        assert events[0]["seq"] == 2
        assert events[1]["seq"] == 3

    async def test_get_events_after_empty(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test getting events when none exist after sequence."""
        mock_redis.zrangebyscore.return_value = []

        events = await event_store.get_events_after("run-1", after_seq=10)

        assert events == []

    async def test_store_metadata(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test storing run metadata."""
        metadata = RunMetadata(
            run_id="test-run",
            status="running",
            goal="test goal",
        )

        await event_store.store_metadata("test-run", metadata)

        mock_redis.hset.assert_called()
        mock_redis.expire.assert_called()

    async def test_get_metadata(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test getting run metadata."""
        mock_redis.hgetall.return_value = {
            b"run_id": b"test-run",
            b"status": b"completed",
            b"goal": b"test goal",
            b"created_at": b"2024-01-01T00:00:00",
            b"completed_at": b"",
            b"bundle_id": b"",
            b"bundle_hash": b"",
            b"tenant_id": b"",
        }

        metadata = await event_store.get_metadata("test-run")

        assert metadata is not None
        assert metadata.run_id == "test-run"
        assert metadata.status == "completed"

    async def test_get_metadata_not_found(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test getting metadata for nonexistent run."""
        mock_redis.hgetall.return_value = {}

        metadata = await event_store.get_metadata("nonexistent")

        assert metadata is None

    async def test_update_status(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test updating run status."""
        await event_store.update_status("test-run", "completed", "2024-01-01T00:00:00")

        mock_redis.hset.assert_called()

    async def test_is_replay_window_expired_no_metadata(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test replay window check when no metadata exists."""
        mock_redis.hgetall.return_value = {}

        expired = await event_store.is_replay_window_expired("test-run")

        assert expired is True

    async def test_is_replay_window_expired_still_running(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test replay window for still-running job."""
        mock_redis.hgetall.return_value = {
            b"run_id": b"test-run",
            b"status": b"running",
            b"completed_at": b"",
            b"created_at": b"",
            b"goal": b"",
            b"bundle_id": b"",
            b"bundle_hash": b"",
            b"tenant_id": b"",
        }

        expired = await event_store.is_replay_window_expired("test-run")

        assert expired is False

    async def test_is_replay_window_expired_recently_completed(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test replay window for recently completed job."""
        recent_time = datetime.now(UTC).isoformat()
        mock_redis.hgetall.return_value = {
            b"run_id": b"test-run",
            b"status": b"completed",
            b"completed_at": recent_time.encode(),
            b"created_at": b"",
            b"goal": b"",
            b"bundle_id": b"",
            b"bundle_hash": b"",
            b"tenant_id": b"",
        }

        expired = await event_store.is_replay_window_expired("test-run")

        assert expired is False

    async def test_is_replay_window_expired_old_completion(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test replay window for job completed long ago."""
        old_time = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        mock_redis.hgetall.return_value = {
            b"run_id": b"test-run",
            b"status": b"completed",
            b"completed_at": old_time.encode(),
            b"created_at": b"",
            b"goal": b"",
            b"bundle_id": b"",
            b"bundle_hash": b"",
            b"tenant_id": b"",
        }

        expired = await event_store.is_replay_window_expired("test-run")

        assert expired is True

    async def test_exists(self, event_store: RedisSSEEventStore, mock_redis: AsyncMock) -> None:
        """Test checking if run exists."""
        mock_redis.exists.return_value = 1

        exists = await event_store.exists("test-run")

        assert exists is True

    async def test_not_exists(self, event_store: RedisSSEEventStore, mock_redis: AsyncMock) -> None:
        """Test checking if run does not exist."""
        mock_redis.exists.return_value = 0

        exists = await event_store.exists("nonexistent")

        assert exists is False

    async def test_get_latest_seq(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test getting latest sequence number."""
        mock_redis.get.return_value = b"5"

        seq = await event_store.get_latest_seq("test-run")

        assert seq == 5

    async def test_get_latest_seq_not_found(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test getting latest sequence when no events."""
        mock_redis.get.return_value = None

        seq = await event_store.get_latest_seq("nonexistent")

        assert seq == 0

    async def test_cleanup_run(
        self, event_store: RedisSSEEventStore, mock_redis: AsyncMock
    ) -> None:
        """Test cleaning up run data."""
        await event_store.cleanup_run("test-run")

        mock_redis.delete.assert_called()


class TestInMemoryFallbackSSEEventStore:
    """Tests for InMemoryFallbackSSEEventStore."""

    @pytest.fixture
    def store(self) -> InMemoryFallbackSSEEventStore:
        """Create an in-memory store."""
        return InMemoryFallbackSSEEventStore()

    async def test_store_and_retrieve_events(self, store: InMemoryFallbackSSEEventStore) -> None:
        """Test storing and retrieving events."""
        seq1 = await store.store_event("run-1", "started", {"goal": "test"})
        seq2 = await store.store_event("run-1", "progress", {"step": 1})
        seq3 = await store.store_event("run-1", "completed", {})

        assert seq1 == 1
        assert seq2 == 2
        assert seq3 == 3

        events = await store.get_events_after("run-1", 0)
        assert len(events) == 3

        events = await store.get_events_after("run-1", 2)
        assert len(events) == 1
        assert events[0]["seq"] == 3

    async def test_store_and_retrieve_metadata(self, store: InMemoryFallbackSSEEventStore) -> None:
        """Test storing and retrieving metadata."""
        metadata = RunMetadata(run_id="run-1", status="running")
        await store.store_metadata("run-1", metadata)

        retrieved = await store.get_metadata("run-1")
        assert retrieved is not None
        assert retrieved.status == "running"

    async def test_update_status(self, store: InMemoryFallbackSSEEventStore) -> None:
        """Test updating status."""
        metadata = RunMetadata(run_id="run-1", status="running")
        await store.store_metadata("run-1", metadata)

        await store.update_status("run-1", "completed", "2024-01-01T00:00:00")

        retrieved = await store.get_metadata("run-1")
        assert retrieved is not None
        assert retrieved.status == "completed"
        assert retrieved.completed_at == "2024-01-01T00:00:00"

    async def test_cleanup(self, store: InMemoryFallbackSSEEventStore) -> None:
        """Test cleanup."""
        await store.store_event("run-1", "started", {})
        metadata = RunMetadata(run_id="run-1", status="running")
        await store.store_metadata("run-1", metadata)

        await store.cleanup_run("run-1")

        assert await store.exists("run-1") is False
        assert await store.get_latest_seq("run-1") == 0
