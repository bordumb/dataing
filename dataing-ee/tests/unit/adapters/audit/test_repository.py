"""Tests for audit repository."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing_ee.adapters.audit.repository import AuditRepository
from dataing_ee.adapters.audit.types import AuditLogCreate


class TestAuditRepository:
    """Tests for AuditRepository."""

    @pytest.fixture
    def mock_pool(self) -> MagicMock:
        """Create a mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=AsyncMock())
        return pool

    @pytest.fixture
    def repository(self, mock_pool: MagicMock) -> AuditRepository:
        """Create repository with mock pool."""
        return AuditRepository(pool=mock_pool)

    async def test_record_creates_entry(
        self, repository: AuditRepository, mock_pool: MagicMock
    ) -> None:
        """Test recording an audit log entry."""
        entry_id = uuid4()
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={"id": entry_id})
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        create = AuditLogCreate(
            tenant_id=uuid4(),
            actor_id=uuid4(),
            actor_email="test@example.com",
            action="team.create",
            resource_type="team",
            resource_id=uuid4(),
            resource_name="Engineering",
        )

        result = await repository.record(create)

        assert result == entry_id
        mock_conn.fetchrow.assert_called_once()

    async def test_list_returns_entries(
        self, repository: AuditRepository, mock_pool: MagicMock
    ) -> None:
        """Test listing audit log entries."""
        tenant_id = uuid4()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.fetchval = AsyncMock(return_value=0)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        entries, total = await repository.list(
            tenant_id=tenant_id,
            limit=50,
            offset=0,
        )

        assert entries == []
        assert total == 0

    async def test_get_returns_entry(
        self, repository: AuditRepository, mock_pool: MagicMock
    ) -> None:
        """Test getting a single audit log entry."""
        tenant_id = uuid4()
        entry_id = uuid4()
        now = datetime.now(UTC)
        mock_row = {
            "id": entry_id,
            "timestamp": now,
            "tenant_id": tenant_id,
            "actor_id": uuid4(),
            "actor_email": "test@example.com",
            "actor_ip": "127.0.0.1",
            "actor_user_agent": "TestAgent/1.0",
            "action": "team.create",
            "resource_type": "team",
            "resource_id": uuid4(),
            "resource_name": "Engineering",
            "request_method": "POST",
            "request_path": "/api/teams",
            "status_code": 201,
            "changes": {"name": "Engineering"},
            "metadata": None,
            "created_at": now,
        }
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await repository.get(tenant_id, entry_id)

        assert result is not None
        assert result.id == entry_id
        assert result.tenant_id == tenant_id
        assert result.action == "team.create"
        mock_conn.fetchrow.assert_called_once()

    async def test_get_returns_none_when_not_found(
        self, repository: AuditRepository, mock_pool: MagicMock
    ) -> None:
        """Test getting a non-existent audit log entry returns None."""
        tenant_id = uuid4()
        entry_id = uuid4()
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await repository.get(tenant_id, entry_id)

        assert result is None
        mock_conn.fetchrow.assert_called_once()

    async def test_delete_before_removes_old_entries(
        self, repository: AuditRepository, mock_pool: MagicMock
    ) -> None:
        """Test deleting entries before a cutoff date."""
        cutoff = datetime.now(UTC) - timedelta(days=730)
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 100")
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        count = await repository.delete_before(cutoff)

        assert count == 100
