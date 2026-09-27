"""Unit tests for the QueryGateway."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet

from dataing.adapters.datasource.encryption import encrypt_config
from dataing.adapters.datasource.errors import (
    CredentialsNotConfiguredError,
)
from dataing.adapters.datasource.gateway import (
    QueryContext,
    QueryGateway,
    QueryPrincipal,
)
from dataing.core.credentials import DecryptedCredentials


@pytest.fixture
def mock_app_db() -> AsyncMock:
    """Create a mock app database."""
    db = AsyncMock()
    db.get_user_credentials.return_value = None
    db.get_data_source.return_value = {
        "id": uuid.uuid4(),
        "name": "Test Datasource",
        "type": "postgresql",
        "connection_config_encrypted": "encrypted_config",
    }
    db.insert_query_audit_log.return_value = {"id": uuid.uuid4()}
    return db


@pytest.fixture
def query_principal() -> QueryPrincipal:
    """Create a test query principal."""
    return QueryPrincipal(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        datasource_id=uuid.uuid4(),
    )


class TestQueryPrincipal:
    """Tests for QueryPrincipal dataclass."""

    def test_creation(self) -> None:
        """Test creating a query principal."""
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        datasource_id = uuid.uuid4()

        principal = QueryPrincipal(
            user_id=user_id,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
        )

        assert principal.user_id == user_id
        assert principal.tenant_id == tenant_id
        assert principal.datasource_id == datasource_id

    def test_frozen(self) -> None:
        """Test that QueryPrincipal is frozen."""
        principal = QueryPrincipal(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            datasource_id=uuid.uuid4(),
        )

        with pytest.raises(AttributeError):
            principal.user_id = uuid.uuid4()  # type: ignore[misc]


class TestQueryContext:
    """Tests for QueryContext dataclass."""

    def test_defaults(self) -> None:
        """Test default values."""
        ctx = QueryContext()

        assert ctx.investigation_id is None
        assert ctx.source == "api"

    def test_custom_values(self) -> None:
        """Test custom values."""
        inv_id = uuid.uuid4()
        ctx = QueryContext(
            investigation_id=inv_id,
            source="agent",
        )

        assert ctx.investigation_id == inv_id
        assert ctx.source == "agent"


class TestQueryGatewayTableExtraction:
    """Tests for SQL table extraction."""

    def test_extract_tables_from_select(self) -> None:
        """Test extracting tables from SELECT statement."""
        tables = QueryGateway._extract_tables("SELECT * FROM users WHERE id = 1")
        assert tables == ["users"]

    def test_extract_tables_from_join(self) -> None:
        """Test extracting tables from JOIN statement."""
        tables = QueryGateway._extract_tables(
            "SELECT * FROM users u JOIN orders o ON u.id = o.user_id"
        )
        assert tables == ["users", "orders"]

    def test_extract_tables_from_multiple_joins(self) -> None:
        """Test extracting tables from multiple JOINs."""
        tables = QueryGateway._extract_tables(
            """
            SELECT * FROM users u
            JOIN orders o ON u.id = o.user_id
            LEFT JOIN products p ON o.product_id = p.id
            """
        )
        assert tables == ["users", "orders", "products"]

    def test_extract_tables_with_schema(self) -> None:
        """Test extracting tables with schema prefix."""
        tables = QueryGateway._extract_tables("SELECT * FROM public.users")
        assert tables == ["public.users"]

    def test_extract_tables_deduplicates(self) -> None:
        """Test that duplicate tables are deduplicated."""
        tables = QueryGateway._extract_tables(
            "SELECT * FROM users WHERE id IN (SELECT user_id FROM users)"
        )
        assert tables == ["users"]

    def test_extract_tables_from_insert(self) -> None:
        """Test extracting table from INSERT statement."""
        tables = QueryGateway._extract_tables("INSERT INTO users (name) VALUES ('test')")
        assert tables == ["users"]

    def test_extract_tables_from_update(self) -> None:
        """Test extracting table from UPDATE statement."""
        tables = QueryGateway._extract_tables("UPDATE users SET name = 'test' WHERE id = 1")
        assert tables == ["users"]

    def test_extract_tables_returns_none_for_no_tables(self) -> None:
        """Test that None is returned when no tables found."""
        tables = QueryGateway._extract_tables("SELECT 1")
        assert tables is None


class TestQueryGatewaySqlHash:
    """Tests for SQL hashing."""

    def test_hash_is_deterministic(self) -> None:
        """Test that same SQL produces same hash."""
        sql = "SELECT * FROM users"
        hash1 = QueryGateway._hash_sql(sql)
        hash2 = QueryGateway._hash_sql(sql)
        assert hash1 == hash2

    def test_hash_normalizes_whitespace(self) -> None:
        """Test that whitespace is normalized before hashing."""
        sql1 = "SELECT * FROM users"
        sql2 = "SELECT  *  FROM  users"
        sql3 = """
            SELECT *
            FROM users
        """
        assert QueryGateway._hash_sql(sql1) == QueryGateway._hash_sql(sql2)
        assert QueryGateway._hash_sql(sql1) == QueryGateway._hash_sql(sql3)

    def test_hash_is_sha256(self) -> None:
        """Test that hash is 64 characters (SHA256 hex)."""
        sql = "SELECT * FROM users"
        hash_value = QueryGateway._hash_sql(sql)
        assert len(hash_value) == 64


class TestQueryGatewayExecute:
    """Tests for QueryGateway.execute method."""

    @pytest.mark.asyncio
    async def test_execute_raises_when_no_credentials(
        self,
        mock_app_db: AsyncMock,
        query_principal: QueryPrincipal,
    ) -> None:
        """Test that execute raises when credentials not configured."""
        # Patch get_encryption_key in both modules
        with (
            patch(
                "dataing.adapters.datasource.gateway.get_encryption_key",
                return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
            ),
            patch(
                "dataing.core.credentials.get_encryption_key",
                return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
            ),
        ):
            gateway = QueryGateway(mock_app_db)

            with pytest.raises(CredentialsNotConfiguredError):
                await gateway.execute(
                    principal=query_principal,
                    sql="SELECT 1",
                )

            # Verify audit log was written
            mock_app_db.insert_query_audit_log.assert_called_once()
            call_kwargs = mock_app_db.insert_query_audit_log.call_args.kwargs
            assert call_kwargs["status"] == "denied"

    @pytest.mark.asyncio
    async def test_execute_audits_on_error(
        self,
        mock_app_db: AsyncMock,
        query_principal: QueryPrincipal,
    ) -> None:
        """Test that errors are properly audited."""
        with (
            patch(
                "dataing.adapters.datasource.gateway.get_encryption_key",
                return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
            ),
            patch(
                "dataing.core.credentials.get_encryption_key",
                return_value=b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M=",
            ),
        ):
            gateway = QueryGateway(mock_app_db)

            try:
                await gateway.execute(
                    principal=query_principal,
                    sql="SELECT 1",
                )
            except CredentialsNotConfiguredError:
                pass

            # Verify audit log was written with error status
            mock_app_db.insert_query_audit_log.assert_called_once()
            call_kwargs = mock_app_db.insert_query_audit_log.call_args.kwargs
            assert call_kwargs["status"] == "denied"
            assert call_kwargs["user_id"] == query_principal.user_id
            assert call_kwargs["datasource_id"] == query_principal.datasource_id


class TestQueryGatewayUserAdapter:
    """Tests for building adapters from the user's own credentials."""

    @pytest.mark.asyncio
    async def test_connects_as_user_not_stored_login(
        self,
        mock_app_db: AsyncMock,
        query_principal: QueryPrincipal,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The adapter connects with the user's login, not the datasource's."""
        key = Fernet.generate_key()
        monkeypatch.delenv("DATADR_ENCRYPTION_KEY", raising=False)
        monkeypatch.setenv("ENCRYPTION_KEY", key.decode())
        mock_app_db.get_data_source.return_value = {
            "id": query_principal.datasource_id,
            "name": "Warehouse",
            "type": "postgresql",
            "connection_config_encrypted": encrypt_config(
                {
                    "host": "db.internal",
                    "port": 5432,
                    "database": "analytics",
                    "username": "svc_dataing",
                    "password": "svc-secret",
                },
                key,
            ),
        }
        credentials = DecryptedCredentials(username="alice", password="alice-secret")

        gateway = QueryGateway(mock_app_db)
        adapter = await gateway._create_user_adapter(query_principal, credentials)
        with patch("asyncpg.create_pool", new_callable=AsyncMock) as create_pool:
            await adapter.connect()

        pool_kwargs = create_pool.call_args.kwargs
        assert (pool_kwargs["user"], pool_kwargs["password"]) == ("alice", "alice-secret")
        assert (pool_kwargs["host"], pool_kwargs["port"], pool_kwargs["database"]) == (
            "db.internal",
            5432,
            "analytics",
        )
