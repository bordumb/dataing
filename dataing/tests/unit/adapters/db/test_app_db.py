"""Unit tests for AppDatabase."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataing.adapters.db.app_db import AppDatabase


class TestAppDatabase:
    """Tests for AppDatabase."""

    @pytest.fixture
    def db(self) -> AppDatabase:
        """Return an AppDatabase instance."""
        return AppDatabase(dsn="postgresql://localhost/test")

    @pytest.fixture
    def mock_conn(self) -> AsyncMock:
        """Return a mock connection."""
        return AsyncMock()

    @pytest.fixture
    def db_with_pool(self, mock_conn: AsyncMock) -> AppDatabase:
        """Return an AppDatabase instance with a mocked pool."""
        db = AppDatabase(dsn="postgresql://localhost/test")

        # Create a mock pool that works with async context managers
        mock_pool = MagicMock()

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        mock_pool.acquire = mock_acquire
        mock_pool.close = AsyncMock()
        db.pool = mock_pool
        return db

    def test_init(self, db: AppDatabase) -> None:
        """Test database initialization."""
        assert db.dsn == "postgresql://localhost/test"
        assert db.pool is None

    async def test_connect_creates_pool(self, db: AppDatabase) -> None:
        """Test that connect creates a connection pool."""
        mock_pool = MagicMock()

        async def mock_create_pool(*args, **kwargs):
            return mock_pool

        with patch("dataing.adapters.db.app_db.asyncpg.create_pool", side_effect=mock_create_pool):
            await db.connect()

            assert db.pool == mock_pool

    async def test_close_closes_pool(self, db: AppDatabase) -> None:
        """Test that close closes the connection pool."""
        mock_pool = AsyncMock()
        db.pool = mock_pool

        await db.close()

        mock_pool.close.assert_called_once()

    async def test_close_noop_when_no_pool(self, db: AppDatabase) -> None:
        """Test that close is a no-op when pool doesn't exist."""
        await db.close()  # Should not raise

    async def test_execute_runs_query(
        self,
        db_with_pool: AppDatabase,
        mock_conn: AsyncMock,
    ) -> None:
        """Test that execute runs a query."""
        mock_conn.execute.return_value = "DELETE 1"

        result = await db_with_pool.execute("DELETE FROM test WHERE id = $1", uuid.uuid4())

        mock_conn.execute.assert_called_once()
        assert result == "DELETE 1"

    async def test_fetch_one_returns_row(
        self,
        db_with_pool: AppDatabase,
        mock_conn: AsyncMock,
    ) -> None:
        """Test that fetch_one returns a single row."""
        mock_conn.fetchrow.return_value = {"id": 1, "name": "test"}

        result = await db_with_pool.fetch_one("SELECT * FROM test WHERE id = $1", 1)

        assert result["id"] == 1
        assert result["name"] == "test"

    async def test_fetch_one_returns_none(
        self,
        db_with_pool: AppDatabase,
        mock_conn: AsyncMock,
    ) -> None:
        """Test that fetch_one returns None when no row found."""
        mock_conn.fetchrow.return_value = None

        result = await db_with_pool.fetch_one("SELECT * FROM test WHERE id = $1", 999)

        assert result is None

    async def test_fetch_all_returns_rows(
        self,
        db_with_pool: AppDatabase,
        mock_conn: AsyncMock,
    ) -> None:
        """Test that fetch_all returns all rows."""
        mock_conn.fetch.return_value = [
            {"id": 1, "name": "test1"},
            {"id": 2, "name": "test2"},
        ]

        result = await db_with_pool.fetch_all("SELECT * FROM test")

        assert len(result) == 2

    async def test_execute_returning(
        self,
        db_with_pool: AppDatabase,
        mock_conn: AsyncMock,
    ) -> None:
        """Test execute_returning returns the result."""
        mock_conn.fetchrow.return_value = {"id": uuid.uuid4(), "name": "new"}

        result = await db_with_pool.execute_returning(
            "INSERT INTO test (name) VALUES ($1) RETURNING *",
            "new",
        )

        assert result["name"] == "new"


class TestAppDatabaseTenantOperations:
    """Tests for tenant-related database operations."""

    @pytest.fixture
    def mock_conn(self) -> AsyncMock:
        """Return a mock connection."""
        return AsyncMock()

    @pytest.fixture
    def db(self, mock_conn: AsyncMock) -> AppDatabase:
        """Return an AppDatabase instance with mock pool."""
        db = AppDatabase(dsn="postgresql://localhost/test")

        mock_pool = MagicMock()

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        mock_pool.acquire = mock_acquire
        db.pool = mock_pool
        return db

    async def test_get_tenant(self, db: AppDatabase, mock_conn: AsyncMock) -> None:
        """Test getting a tenant by ID."""
        tenant_id = uuid.uuid4()
        mock_conn.fetchrow.return_value = {
            "id": tenant_id,
            "name": "Test",
            "slug": "test",
        }

        result = await db.get_tenant(tenant_id)

        assert result["id"] == tenant_id

    async def test_get_tenant_by_slug(self, db: AppDatabase, mock_conn: AsyncMock) -> None:
        """Test getting a tenant by slug."""
        mock_conn.fetchrow.return_value = {
            "id": uuid.uuid4(),
            "name": "Test",
            "slug": "test-slug",
        }

        result = await db.get_tenant_by_slug("test-slug")

        assert result["slug"] == "test-slug"

    async def test_create_tenant(self, db: AppDatabase, mock_conn: AsyncMock) -> None:
        """Test creating a tenant."""
        mock_conn.fetchrow.return_value = {
            "id": uuid.uuid4(),
            "name": "New Tenant",
            "slug": "new-tenant",
        }

        result = await db.create_tenant(
            name="New Tenant",
            slug="new-tenant",
        )

        assert result["name"] == "New Tenant"


class TestAppDatabaseApiKeyOperations:
    """Tests for API key database operations."""

    @pytest.fixture
    def mock_conn(self) -> AsyncMock:
        """Return a mock connection."""
        return AsyncMock()

    @pytest.fixture
    def db(self, mock_conn: AsyncMock) -> AppDatabase:
        """Return an AppDatabase instance with mock pool."""
        db = AppDatabase(dsn="postgresql://localhost/test")

        mock_pool = MagicMock()

        @asynccontextmanager
        async def mock_acquire():
            yield mock_conn

        mock_pool.acquire = mock_acquire
        db.pool = mock_pool
        return db

    async def test_get_api_key_by_hash(self, db: AppDatabase, mock_conn: AsyncMock) -> None:
        """Test getting an API key by hash."""
        mock_conn.fetchrow.return_value = {
            "id": uuid.uuid4(),
            "key_hash": "abc123",
            "tenant_id": uuid.uuid4(),
        }

        result = await db.get_api_key_by_hash("abc123")

        assert result["key_hash"] == "abc123"

    async def test_create_api_key(self, db: AppDatabase, mock_conn: AsyncMock) -> None:
        """Test creating an API key."""
        key_id = uuid.uuid4()
        mock_conn.fetchrow.return_value = {"id": key_id}

        result = await db.create_api_key(
            tenant_id=uuid.uuid4(),
            key_hash="hash",
            key_prefix="ddr_",
            name="Test Key",
            scopes=["read"],
        )

        assert result["id"] == key_id

    async def test_list_api_keys(self, db: AppDatabase, mock_conn: AsyncMock) -> None:
        """Test listing API keys for a tenant."""
        mock_conn.fetch.return_value = [
            {"id": uuid.uuid4(), "name": "Key 1"},
            {"id": uuid.uuid4(), "name": "Key 2"},
        ]

        result = await db.list_api_keys(uuid.uuid4())

        assert len(result) == 2

    async def test_revoke_api_key(self, db: AppDatabase, mock_conn: AsyncMock) -> None:
        """Test revoking an API key."""
        mock_conn.execute.return_value = "UPDATE 1"

        result = await db.revoke_api_key(uuid.uuid4(), uuid.uuid4())

        assert result is True

    async def test_update_api_key_last_used(self, db: AppDatabase, mock_conn: AsyncMock) -> None:
        """Test updating API key last used timestamp."""
        await db.update_api_key_last_used(uuid.uuid4())

        mock_conn.execute.assert_called_once()
