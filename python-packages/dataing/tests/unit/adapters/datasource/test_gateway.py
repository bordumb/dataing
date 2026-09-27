"""Unit tests for the QueryGateway."""

from __future__ import annotations

import sys
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlsplit

import pytest

from dataing.adapters.datasource.base import BaseAdapter
from dataing.adapters.datasource.encryption import encrypt_config
from dataing.adapters.datasource.errors import (
    CredentialsNotConfiguredError,
    CredentialsNotSupportedError,
)
from dataing.adapters.datasource.gateway import (
    QueryContext,
    QueryGateway,
    QueryPrincipal,
)
from dataing.adapters.datasource.types import SourceType
from dataing.core.credentials import DecryptedCredentials

ENCRYPTION_KEY = b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M="

# The user's own database login, which must replace the datasource's stored service login.
USER_CREDENTIALS = DecryptedCredentials(username="alice", password="alice-secret")

Login = tuple[str | None, str | None]


async def _asyncpg_login(adapter: BaseAdapter) -> Login:
    """Connect through a fake asyncpg and return the login in the DSN."""
    asyncpg = MagicMock(create_pool=AsyncMock())
    with patch.dict(sys.modules, {"asyncpg": asyncpg}):
        await adapter.connect()
    dsn = urlsplit(asyncpg.create_pool.call_args.args[0])
    return dsn.username, dsn.password


async def _aiomysql_login(adapter: BaseAdapter) -> Login:
    """Connect through a fake aiomysql and return the login it was given."""
    aiomysql = MagicMock(create_pool=AsyncMock())
    with patch.dict(sys.modules, {"aiomysql": aiomysql}):
        await adapter.connect()
    kwargs = aiomysql.create_pool.call_args.kwargs
    return kwargs["user"], kwargs["password"]


async def _snowflake_login(adapter: BaseAdapter) -> Login:
    """Connect through a fake snowflake-connector and return the login it was given."""
    connector = MagicMock()
    fake_modules = {"snowflake": MagicMock(connector=connector), "snowflake.connector": connector}
    with patch.dict(sys.modules, fake_modules):
        await adapter.connect()
    kwargs = connector.connect.call_args.kwargs
    return kwargs["user"], kwargs["password"]


async def _trino_login(adapter: BaseAdapter) -> Login:
    """Connect through a fake trino client and return the login it was given."""
    auth, dbapi = MagicMock(), MagicMock()
    fake_modules = {
        "trino": MagicMock(auth=auth, dbapi=dbapi),
        "trino.auth": auth,
        "trino.dbapi": dbapi,
    }
    with patch.dict(sys.modules, fake_modules):
        await adapter.connect()
    _, password = auth.BasicAuthentication.call_args.args
    return dbapi.connect.call_args.kwargs["user"], password


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


@pytest.fixture
def gateway(mock_app_db: AsyncMock) -> QueryGateway:
    """Create a gateway that decrypts datasource configs with the test key."""
    with (
        patch(
            "dataing.adapters.datasource.gateway.get_encryption_key",
            return_value=ENCRYPTION_KEY,
        ),
        patch("dataing.core.credentials.get_encryption_key", return_value=ENCRYPTION_KEY),
    ):
        return QueryGateway(mock_app_db)


def _store_datasource(app_db: AsyncMock, source_type: SourceType, config: dict[str, Any]) -> None:
    """Make the app database return a datasource with this encrypted config."""
    app_db.get_data_source.return_value = {
        "id": uuid.uuid4(),
        "name": "Warehouse",
        "type": source_type.value,
        "connection_config_encrypted": encrypt_config(config, ENCRYPTION_KEY),
    }


class TestQueryGatewayUserAdapter:
    """Tests that the gateway connects with the user's login, not the service account."""

    # Stored configs are keyed as each adapter's config_schema names its login fields.
    @pytest.mark.parametrize(
        ("source_type", "stored_config", "login_of"),
        [
            pytest.param(
                SourceType.POSTGRESQL,
                {"host": "db", "database": "shop", "username": "svc", "password": "svc-pw"},
                _asyncpg_login,
                id="postgresql",
            ),
            pytest.param(
                SourceType.REDSHIFT,
                {"host": "db", "database": "shop", "username": "svc", "password": "svc-pw"},
                _asyncpg_login,
                id="redshift",
                marks=pytest.mark.xfail(
                    raises=TypeError,
                    strict=True,
                    reason="RedshiftAdapter is abstract: it lacks _fetch_table_metadata",
                ),
            ),
            pytest.param(
                SourceType.MYSQL,
                {"host": "db", "database": "shop", "username": "svc", "password": "svc-pw"},
                _aiomysql_login,
                id="mysql",
            ),
            pytest.param(
                SourceType.SNOWFLAKE,
                {"account": "xy123", "database": "SHOP", "user": "svc", "password": "svc-pw"},
                _snowflake_login,
                id="snowflake",
            ),
            pytest.param(
                SourceType.TRINO,
                {"host": "trino", "catalog": "hive", "user": "svc", "password": "svc-pw"},
                _trino_login,
                id="trino",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_user_adapter_logs_in_as_the_user(
        self,
        gateway: QueryGateway,
        mock_app_db: AsyncMock,
        query_principal: QueryPrincipal,
        source_type: SourceType,
        stored_config: dict[str, Any],
        login_of: Callable[[BaseAdapter], Awaitable[Login]],
    ) -> None:
        """The adapter connects with the user's username and password."""
        _store_datasource(mock_app_db, source_type, stored_config)

        adapter = await gateway._create_user_adapter(query_principal, USER_CREDENTIALS)

        assert await login_of(adapter) == ("alice", "alice-secret")

    @pytest.mark.asyncio
    async def test_user_adapter_rejects_source_without_a_login(
        self,
        gateway: QueryGateway,
        mock_app_db: AsyncMock,
        query_principal: QueryPrincipal,
    ) -> None:
        """A source with no database login can't run as the user, so it must not run at all."""
        _store_datasource(mock_app_db, SourceType.SQLITE, {"path": "file::memory:"})

        with pytest.raises(CredentialsNotSupportedError):
            await gateway._create_user_adapter(query_principal, USER_CREDENTIALS)
