"""Tests for audit repository."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dataing.adapters.audit.repository import AuditRepository
from dataing.adapters.audit.types import AuditLogCreate


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

    async def test_record_creates_entry(self, repository: AuditRepository) -> None:
        """Test recording an audit log entry."""
        create = AuditLogCreate(
            tenant_id=uuid4(),
            actor_id=uuid4(),
            actor_email="test@example.com",
            action="team.create",
            resource_type="team",
            resource_id=uuid4(),
            resource_name="Engineering",
        )

        # Should not raise
        await repository.record(create)

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
