"""Unit tests for the QueryGateway."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dataing.adapters.datasource.errors import (
    CredentialsInvalidError,
    CredentialsNotConfiguredError,
    DatasourceNotFoundError,
)
from dataing.adapters.datasource.gateway import (
    QueryContext,
    QueryGateway,
    QueryPrincipal,
    UserPrincipal,
)
from dataing.adapters.datasource.types import AdapterCapabilities, QueryResult
from dataing.core.credentials import DecryptedCredentials

TEST_KEY = b"Ug_OGzRGbeFOYC2ANwtmmroRE87szZDtGhwSIZRFX4M="


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
def query_principal() -> UserPrincipal:
    """Create a test query principal."""
    return UserPrincipal(
        user_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        datasource_id=uuid.uuid4(),
    )


class TestUserPrincipal:
    """Tests for UserPrincipal dataclass."""

    def test_query_principal_is_alias(self) -> None:
        """QueryPrincipal is the same class as UserPrincipal."""
        assert QueryPrincipal is UserPrincipal

    def test_creation(self) -> None:
        """Test creating a query principal."""
        user_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        datasource_id = uuid.uuid4()

        principal = UserPrincipal(
            user_id=user_id,
            tenant_id=tenant_id,
            datasource_id=datasource_id,
        )

        assert principal.user_id == user_id
        assert principal.tenant_id == tenant_id
        assert principal.datasource_id == datasource_id

    def test_frozen(self) -> None:
        """Test that UserPrincipal is frozen."""
        principal = UserPrincipal(
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
        query_principal: UserPrincipal,
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
        query_principal: UserPrincipal,
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


class _Adapter:
    """Minimal SQL adapter double."""

    def __init__(self, error: Exception | None = None) -> None:
        """Initialize the double."""
        self.error = error
        self.executed: list[str] = []
        self.connected = 0

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Declare a dialect."""
        return AdapterCapabilities(supports_sql=True, sql_dialect="postgres")

    async def __aenter__(self) -> _Adapter:
        """Connect."""
        self.connected += 1
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Disconnect."""

    async def execute_query(self, sql: str, timeout_seconds: int = 30) -> QueryResult:
        """Record the query."""
        self.executed.append(sql)
        if self.error:
            raise self.error
        return QueryResult(columns=[], rows=[], row_count=0)


def _gateway(mock_app_db: AsyncMock, adapter: _Adapter) -> QueryGateway:
    credentials = MagicMock()
    credentials.get_credentials = AsyncMock(
        return_value=DecryptedCredentials(username="u", password="p")
    )
    credentials.update_last_used = AsyncMock()
    registry = MagicMock()
    registry.create.return_value = adapter
    return QueryGateway(
        mock_app_db,
        credentials_service=credentials,
        registry=registry,
        encryption_key=TEST_KEY,
    )


class TestQueryGatewayPrepareAndErrors:
    """Tests for the prepare hook and error translation."""

    async def test_prepare_rewrites_sql(
        self, mock_app_db: AsyncMock, query_principal: UserPrincipal
    ) -> None:
        """The prepare hook gets the adapter dialect and its result is what runs."""
        adapter = _Adapter()
        gateway = _gateway(mock_app_db, adapter)
        seen: list[str | None] = []

        def prepare(sql: str, dialect: str | None) -> str:
            seen.append(dialect)
            return sql + " LIMIT 1"

        with patch("dataing.adapters.datasource.gateway.decrypt_config", return_value={}):
            await gateway.execute(query_principal, "SELECT 1", prepare=prepare)

        assert seen == ["postgres"]
        assert adapter.executed == ["SELECT 1 LIMIT 1"]
        assert mock_app_db.insert_query_audit_log.call_args.kwargs["sql_text"] == (
            "SELECT 1 LIMIT 1"
        )

    async def test_prepare_refusal_never_connects(
        self, mock_app_db: AsyncMock, query_principal: UserPrincipal
    ) -> None:
        """A refused query is audited as rejected and never connects."""
        adapter = _Adapter()
        gateway = _gateway(mock_app_db, adapter)

        def prepare(sql: str, dialect: str | None) -> str:
            raise ValueError("nope")

        with (
            patch("dataing.adapters.datasource.gateway.decrypt_config", return_value={}),
            pytest.raises(ValueError),
        ):
            await gateway.execute(query_principal, "DROP TABLE x", prepare=prepare)

        assert adapter.connected == 0
        assert mock_app_db.insert_query_audit_log.call_args.kwargs["status"] == "rejected"

    async def test_missing_datasource(
        self, mock_app_db: AsyncMock, query_principal: UserPrincipal
    ) -> None:
        """A datasource the tenant does not have raises DatasourceNotFoundError."""
        mock_app_db.get_data_source.return_value = None
        gateway = _gateway(mock_app_db, _Adapter())

        with pytest.raises(DatasourceNotFoundError):
            await gateway.execute(query_principal, "SELECT 1")

    async def test_login_failure_is_credentials_invalid(
        self, mock_app_db: AsyncMock, query_principal: UserPrincipal
    ) -> None:
        """A rejected login becomes CredentialsInvalidError, audited as denied."""
        gateway = _gateway(mock_app_db, _Adapter(RuntimeError("password authentication failed")))

        with (
            patch("dataing.adapters.datasource.gateway.decrypt_config", return_value={}),
            pytest.raises(CredentialsInvalidError),
        ):
            await gateway.execute(query_principal, "SELECT 1")

        assert mock_app_db.insert_query_audit_log.call_args.kwargs["status"] == "denied"

    async def test_column_named_author_is_not_a_login_failure(
        self, mock_app_db: AsyncMock, query_principal: UserPrincipal
    ) -> None:
        """Errors that merely mention auth-like words are not credential errors."""
        error = RuntimeError('column "author_id" does not exist')
        gateway = _gateway(mock_app_db, _Adapter(error))

        with (
            patch("dataing.adapters.datasource.gateway.decrypt_config", return_value={}),
            pytest.raises(RuntimeError, match="author_id"),
        ):
            await gateway.execute(query_principal, "SELECT author_id FROM t")

        assert mock_app_db.insert_query_audit_log.call_args.kwargs["status"] == "error"
