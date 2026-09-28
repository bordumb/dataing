"""Unit tests for the AgentQueryService (chat agent queries run as the asking user)."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from cryptography.fernet import Fernet

from dataing.adapters.datasource.encryption import encrypt_config
from dataing.adapters.datasource.errors import QueryTimeoutError
from dataing.adapters.datasource.gateway import QueryGateway, UserPrincipal
from dataing.adapters.datasource.types import (
    AdapterCapabilities,
    NormalizedType,
    QueryResult,
    SchemaFilter,
    SchemaResponse,
    SourceCategory,
    SourceType,
)
from dataing.core.agent_query import (
    MODEL_VIEW_MAX_ROWS,
    QUERY_ROW_LIMIT,
    QUERY_TIMEOUT_SECONDS,
    SNAPSHOT_MAX_BYTES,
    SNAPSHOT_MAX_ROWS,
    AgentQueryError,
    AgentQueryErrorCode,
    AgentQueryService,
)
from dataing.core.credentials import DecryptedCredentials

KEY = Fernet.generate_key()
STORED_CONFIG = {"host": "db.internal", "port": 5432, "database": "analytics", "username": "svc"}


class FakeAdapter:
    """Adapter double that records what it was asked to do."""

    def __init__(
        self,
        config: dict[str, Any],
        *,
        dialect: str | None = "postgres",
        rows: list[dict[str, Any]] | None = None,
        schema: SchemaResponse | None = None,
        error: Exception | None = None,
    ) -> None:
        """Initialize the fake."""
        self.config = config
        self.dialect = dialect
        self.rows = rows if rows is not None else [{"id": 1}]
        self.schema = schema
        self.error = error
        self.connected = False
        self.connect_count = 0
        self.executed: list[str] = []
        self.timeouts: list[int] = []
        self.schema_filters: list[SchemaFilter | None] = []

    @property
    def capabilities(self) -> AdapterCapabilities:
        """Declare the configured dialect."""
        return AdapterCapabilities(supports_sql=True, sql_dialect=self.dialect)

    async def __aenter__(self) -> FakeAdapter:
        """Connect."""
        self.connected = True
        self.connect_count += 1
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Disconnect."""
        self.connected = False

    async def execute_query(
        self,
        sql: str,
        params: Any = None,
        timeout_seconds: int = 30,
        limit: int | None = None,
    ) -> QueryResult:
        """Record and answer a query."""
        self.executed.append(sql)
        self.timeouts.append(timeout_seconds)
        if self.error:
            raise self.error
        columns = [{"name": k, "data_type": "string"} for k in (self.rows[0] if self.rows else {})]
        return QueryResult(columns=columns, rows=self.rows, row_count=len(self.rows))

    async def get_schema(self, filter: SchemaFilter | None = None) -> SchemaResponse:
        """Record and answer a schema request."""
        self.schema_filters.append(filter)
        assert self.schema is not None
        return self.schema


class FakeRegistry:
    """Registry double that hands out one prepared adapter per create call."""

    def __init__(self, **adapter_kwargs: Any) -> None:
        """Initialize the fake."""
        self.adapter_kwargs = adapter_kwargs
        self.created: list[FakeAdapter] = []

    def create(self, source_type: SourceType | str, config: dict[str, Any]) -> FakeAdapter:
        """Create an adapter with the given config."""
        adapter = FakeAdapter(config, **self.adapter_kwargs)
        self.created.append(adapter)
        return adapter


def _schema() -> SchemaResponse:
    return SchemaResponse(
        source_id="ds",
        source_type=SourceType.POSTGRESQL,
        source_category=SourceCategory.DATABASE,
        fetched_at=datetime.now(UTC),
        catalogs=[
            {
                "name": "analytics",
                "schemas": [
                    {
                        "name": "public",
                        "tables": [
                            {
                                "name": "orders",
                                "table_type": "table",
                                "native_type": "BASE TABLE",
                                "native_path": "analytics.public.orders",
                                "row_count": 1200,
                                "columns": [
                                    {
                                        "name": "id",
                                        "data_type": NormalizedType.INTEGER,
                                        "native_type": "int4",
                                        "nullable": False,
                                        "is_primary_key": True,
                                    },
                                    {
                                        "name": "email",
                                        "data_type": NormalizedType.STRING,
                                        "native_type": "text",
                                    },
                                ],
                            },
                            {
                                "name": "customers",
                                "table_type": "view",
                                "native_type": "VIEW",
                                "native_path": "analytics.public.customers",
                                "columns": [],
                            },
                        ],
                    },
                    {
                        "name": "raw",
                        "tables": [
                            {
                                "name": "orders",
                                "table_type": "table",
                                "native_type": "BASE TABLE",
                                "native_path": "analytics.raw.orders",
                                "columns": [],
                            }
                        ],
                    },
                ],
            }
        ],
    )


def _app_db(*, datasource: bool = True) -> MagicMock:
    db = MagicMock()
    db.get_data_source = AsyncMock(
        return_value=(
            {
                "id": uuid.uuid4(),
                "name": "Warehouse",
                "type": "postgresql",
                "connection_config_encrypted": encrypt_config(STORED_CONFIG, KEY),
            }
            if datasource
            else None
        )
    )
    db.insert_query_audit_log = AsyncMock(return_value={"id": uuid.uuid4()})
    return db


def _credentials(configured: bool = True) -> MagicMock:
    service = MagicMock()
    service.get_credentials = AsyncMock(
        return_value=DecryptedCredentials(username="alice", password="alice-pw")
        if configured
        else None
    )
    service.update_last_used = AsyncMock()
    return service


def _service(
    *,
    configured: bool = True,
    datasource: bool = True,
    **adapter_kwargs: Any,
) -> tuple[AgentQueryService, FakeRegistry, MagicMock]:
    app_db = _app_db(datasource=datasource)
    registry = FakeRegistry(**adapter_kwargs)
    gateway = QueryGateway(
        app_db,
        credentials_service=_credentials(configured),
        registry=registry,  # type: ignore[arg-type]
        encryption_key=KEY,
    )
    return AgentQueryService(app_db, gateway=gateway), registry, app_db


@pytest.fixture
def principal() -> UserPrincipal:
    """Create the asking user's principal."""
    return UserPrincipal(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), datasource_id=uuid.uuid4())


def _executed(registry: FakeRegistry) -> list[str]:
    return [sql for adapter in registry.created for sql in adapter.executed]


def _connected(registry: FakeRegistry) -> int:
    return sum(adapter.connect_count for adapter in registry.created)


class TestValidation:
    """SQL is validated in the adapter's dialect before anything runs."""

    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT 1; DROP TABLE orders",
            "SELECT 1; SELECT 2",
            "DELETE FROM orders",
            "UPDATE orders SET id = 1",
            "COPY orders TO '/tmp/x.csv'",
            "",
        ],
    )
    async def test_rejects_unsafe_sql_before_execution(
        self, principal: UserPrincipal, sql: str
    ) -> None:
        """Multi-statement and non-SELECT queries never reach the database."""
        service, registry, app_db = _service()

        with pytest.raises(AgentQueryError) as exc:
            await service.run(principal, sql, purpose="check")

        assert exc.value.code == AgentQueryErrorCode.VALIDATION_FAILED
        assert _executed(registry) == []
        assert _connected(registry) == 0

    async def test_refuses_unknown_dialect(self, principal: UserPrincipal) -> None:
        """An adapter that declares no SQL dialect cannot be validated, so it is refused."""
        service, registry, _ = _service(dialect=None)

        with pytest.raises(AgentQueryError) as exc:
            await service.run(principal, "SELECT 1", purpose="check")

        assert exc.value.code == AgentQueryErrorCode.VALIDATION_FAILED
        assert "dialect" in exc.value.message
        assert _executed(registry) == []
        assert _connected(registry) == 0

    async def test_validation_failure_is_audited(self, principal: UserPrincipal) -> None:
        """A refused query still leaves an audit row with the agent as source."""
        service, _, app_db = _service()

        with pytest.raises(AgentQueryError):
            await service.run(principal, "DROP TABLE orders", purpose="check")

        kwargs = app_db.insert_query_audit_log.call_args.kwargs
        assert kwargs["status"] == "rejected"
        assert kwargs["source"] == "agent"

    async def test_adds_limit_when_missing(self, principal: UserPrincipal) -> None:
        """A query without LIMIT gets the 1,000-row cap."""
        service, registry, _ = _service()

        result = await service.run(principal, "SELECT id FROM orders", purpose="check")

        (sql,) = _executed(registry)
        assert f"LIMIT {QUERY_ROW_LIMIT}" in sql
        assert result.sql == sql
        assert result.dialect == "postgres"

    async def test_keeps_existing_limit(self, principal: UserPrincipal) -> None:
        """A query that already has a LIMIT keeps it."""
        service, registry, _ = _service()

        await service.run(principal, "SELECT id FROM orders LIMIT 5", purpose="check")

        (sql,) = _executed(registry)
        assert "LIMIT 5" in sql
        assert str(QUERY_ROW_LIMIT) not in sql

    async def test_lowers_limit_above_cap(self, principal: UserPrincipal) -> None:
        """A LIMIT above 1,000 rows is lowered to the cap."""
        service, registry, _ = _service()

        await service.run(principal, "SELECT id FROM orders LIMIT 50000", purpose="check")

        (sql,) = _executed(registry)
        assert f"LIMIT {QUERY_ROW_LIMIT}" in sql
        assert "50000" not in sql

    async def test_limits_set_operations(self, principal: UserPrincipal) -> None:
        """A UNION without LIMIT is capped too."""
        service, registry, _ = _service()

        await service.run(principal, "SELECT a FROM t UNION ALL SELECT b FROM u", purpose="x")

        (sql,) = _executed(registry)
        assert sql.endswith(f"LIMIT {QUERY_ROW_LIMIT}")

    async def test_validates_in_adapter_dialect(self, principal: UserPrincipal) -> None:
        """Dialect-specific syntax is parsed with the adapter's dialect."""
        service, registry, _ = _service(dialect="bigquery")

        await service.run(principal, "SELECT `id` FROM `proj.ds.orders`", purpose="check")

        (sql,) = _executed(registry)
        assert "`proj.ds.orders`" in sql or "`proj`.`ds`.`orders`" in sql


class TestExecution:
    """Execution goes through the gateway with the user's credentials."""

    async def test_runs_with_user_credentials_and_timeout(self, principal: UserPrincipal) -> None:
        """The adapter gets the asker's credentials merged over the stored connection."""
        service, registry, _ = _service()

        await service.run(principal, "SELECT 1", purpose="check")

        (adapter,) = registry.created
        assert adapter.config["username"] == "alice"
        assert adapter.config["password"] == "alice-pw"
        assert adapter.config["host"] == "db.internal"
        assert adapter.timeouts == [QUERY_TIMEOUT_SECONDS]

    async def test_audit_source_is_agent(self, principal: UserPrincipal) -> None:
        """The audit log records the agent as the source."""
        service, _, app_db = _service()

        await service.run(principal, "SELECT 1", purpose="check")

        kwargs = app_db.insert_query_audit_log.call_args.kwargs
        assert kwargs["source"] == "agent"
        assert kwargs["status"] == "success"
        assert kwargs["user_id"] == principal.user_id

    async def test_credentials_missing(self, principal: UserPrincipal) -> None:
        """No credentials: a typed error with the credentials page, and nothing runs."""
        service, registry, app_db = _service(configured=False)

        with pytest.raises(AgentQueryError) as exc:
            await service.run(principal, "SELECT 1", purpose="check")

        assert exc.value.code == AgentQueryErrorCode.CREDENTIALS_MISSING
        assert exc.value.details["action_url"] == (
            f"/settings/datasources/{principal.datasource_id}/credentials"
        )
        # Never falls back to the datasource's stored connection
        assert registry.created == []
        assert app_db.insert_query_audit_log.call_args.kwargs["status"] == "denied"

    async def test_credentials_invalid(self, principal: UserPrincipal) -> None:
        """The database rejecting the user's login becomes credentials_invalid."""
        service, _, _ = _service(error=RuntimeError("password authentication failed"))

        with pytest.raises(AgentQueryError) as exc:
            await service.run(principal, "SELECT 1", purpose="check")

        assert exc.value.code == AgentQueryErrorCode.CREDENTIALS_INVALID
        assert "action_url" in exc.value.details

    def test_source_without_a_login_is_credentials_not_supported(self) -> None:
        """A source the asker can't log in to is its own error, not a failed query."""
        from dataing.adapters.datasource.errors import CredentialsNotSupportedError
        from dataing.core.agent_query import _to_agent_error

        error = _to_agent_error(CredentialsNotSupportedError("duckdb"))

        assert error.code == AgentQueryErrorCode.CREDENTIALS_NOT_SUPPORTED
        assert error.details == {"source_type": "duckdb"}

    async def test_no_datasource(self, principal: UserPrincipal) -> None:
        """A datasource the tenant does not have is no_datasource."""
        service, registry, _ = _service(datasource=False)

        with pytest.raises(AgentQueryError) as exc:
            await service.run(principal, "SELECT 1", purpose="check")

        assert exc.value.code == AgentQueryErrorCode.NO_DATASOURCE
        assert registry.created == []

    async def test_timeout(self, principal: UserPrincipal) -> None:
        """An adapter timeout becomes a timeout error and is audited as such."""
        service, _, app_db = _service(error=QueryTimeoutError(timeout_seconds=30))

        with pytest.raises(AgentQueryError) as exc:
            await service.run(principal, "SELECT 1", purpose="check")

        assert exc.value.code == AgentQueryErrorCode.TIMEOUT
        assert app_db.insert_query_audit_log.call_args.kwargs["status"] == "timeout"

    async def test_asyncio_timeout(self, principal: UserPrincipal) -> None:
        """A raw TimeoutError from the driver is also a timeout error."""
        service, _, _ = _service(error=TimeoutError())

        with pytest.raises(AgentQueryError) as exc:
            await service.run(principal, "SELECT 1", purpose="check")

        assert exc.value.code == AgentQueryErrorCode.TIMEOUT

    async def test_execution_failed(self, principal: UserPrincipal) -> None:
        """Other database errors are execution_failed."""
        service, _, _ = _service(error=RuntimeError('relation "nope" does not exist'))

        with pytest.raises(AgentQueryError) as exc:
            await service.run(principal, "SELECT 1", purpose="check")

        assert exc.value.code == AgentQueryErrorCode.EXECUTION_FAILED
        assert "nope" in exc.value.message

    async def test_error_to_dict(self) -> None:
        """Errors serialize to a tool-friendly dict."""
        err = AgentQueryError(AgentQueryErrorCode.TIMEOUT, "slow", {"timeout_seconds": 30})
        assert err.to_dict() == {
            "error": "timeout",
            "message": "slow",
            "details": {"timeout_seconds": 30},
        }


class TestSnapshotAndModelView:
    """The stored snapshot and what the model sees."""

    async def test_snapshot_caps_rows(self, principal: UserPrincipal) -> None:
        """More rows than the snapshot holds are cut and marked truncated."""
        rows = [{"id": i} for i in range(SNAPSHOT_MAX_ROWS + 50)]
        service, _, _ = _service(rows=rows)

        result = await service.run(principal, "SELECT id FROM orders", purpose="check")

        assert len(result.rows) == SNAPSHOT_MAX_ROWS
        assert result.row_count == SNAPSHOT_MAX_ROWS + 50
        assert result.truncated is True
        assert result.model_view.truncated is True
        assert len(result.model_view.rows) == MODEL_VIEW_MAX_ROWS
        assert result.model_view.row_count == SNAPSHOT_MAX_ROWS + 50

    async def test_snapshot_caps_bytes(self, principal: UserPrincipal) -> None:
        """Rows are cut so the snapshot JSON stays within the byte budget."""
        rows = [{"id": i, "blob": "x" * 10_000} for i in range(100)]
        service, _, _ = _service(rows=rows)

        result = await service.run(principal, "SELECT * FROM orders", purpose="check")

        assert len(json.dumps(result.rows).encode()) <= SNAPSHOT_MAX_BYTES
        assert 0 < len(result.rows) < 100
        assert result.truncated is True

    async def test_small_result_not_truncated(self, principal: UserPrincipal) -> None:
        """A small result is kept whole."""
        service, _, _ = _service(rows=[{"id": 1}, {"id": 2}])

        result = await service.run(principal, "SELECT id FROM orders", purpose="check")

        assert result.rows == [{"id": 1}, {"id": 2}]
        assert result.row_count == 2
        assert result.truncated is False
        assert result.duration_ms >= 0
        assert result.purpose == "check"

    async def test_snapshot_is_json_safe(self, principal: UserPrincipal) -> None:
        """Decimals, datetimes and bytes are converted to JSON-safe values."""
        rows = [
            {
                "amount": Decimal("12.50"),
                "at": datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
                "raw": b"\xff\x00",
                "ok": b"abc",
            }
        ]
        service, _, _ = _service(rows=rows)

        result = await service.run(principal, "SELECT * FROM orders", purpose="check")

        json.dumps(result.rows)
        json.dumps(result.columns)
        json.dumps(result.model_view.to_dict())
        (row,) = result.rows
        assert row["amount"] == "12.50"
        assert row["at"].startswith("2026-09-14T12:00:00")
        assert row["ok"] == "abc"
        assert isinstance(row["raw"], str)

    async def test_pii_redacted_in_model_view_only(self, principal: UserPrincipal) -> None:
        """The model sees redacted values; the stored snapshot keeps the originals."""
        rows = [{"id": 1, "email": "jane@example.com", "note": "call 555-123-4567"}]
        service, _, _ = _service(rows=rows)

        result = await service.run(principal, "SELECT * FROM customers", purpose="check")

        assert result.rows[0]["email"] == "jane@example.com"
        assert result.rows[0]["note"] == "call 555-123-4567"
        model_row = result.model_view.rows[0]
        assert model_row["email"] == "[REDACTED_EMAIL]"
        assert "555-123-4567" not in model_row["note"]
        assert model_row["id"] == 1
        assert "jane@example.com" not in json.dumps(result.model_view.to_dict())

    async def test_column_stats(self, principal: UserPrincipal) -> None:
        """Null count, distinct count and numeric min/max per column."""
        rows = [
            {"n": 3, "d": Decimal("1.5"), "s": "a"},
            {"n": None, "d": Decimal("-2"), "s": "a"},
            {"n": 10, "d": None, "s": "b"},
        ]
        service, _, _ = _service(rows=rows)

        result = await service.run(principal, "SELECT * FROM t", purpose="check")

        stats = result.model_view.column_stats
        assert stats["n"] == {"null_count": 1, "distinct_count": 2, "min": 3, "max": 10}
        assert stats["d"] == {"null_count": 1, "distinct_count": 2, "min": -2.0, "max": 1.5}
        assert stats["s"] == {"null_count": 0, "distinct_count": 2}

    async def test_model_view_columns(self, principal: UserPrincipal) -> None:
        """The model view lists the result's columns."""
        service, _, _ = _service(rows=[{"id": 1, "name": "x"}])

        result = await service.run(principal, "SELECT id, name FROM t", purpose="check")

        assert [c["name"] for c in result.model_view.columns] == ["id", "name"]
        view = result.model_view.to_dict()
        assert set(view) == {"columns", "rows", "row_count", "truncated", "column_stats"}


class TestSchemaTools:
    """list_tables and describe_table run with the user's credentials."""

    async def test_list_tables_uses_user_credentials(self, principal: UserPrincipal) -> None:
        """Tables come from an adapter connected as the asker."""
        service, registry, _ = _service(schema=_schema())

        listing = await service.list_tables(principal, None)

        (adapter,) = registry.created
        assert adapter.config["username"] == "alice"
        assert adapter.connect_count == 1
        assert [t.native_path for t in listing.tables] == [
            "analytics.public.orders",
            "analytics.public.customers",
            "analytics.raw.orders",
        ]
        assert listing.truncated is False

    async def test_list_tables_pattern(self, principal: UserPrincipal) -> None:
        """A pattern filters by substring or glob, case-insensitively."""
        service, _, _ = _service(schema=_schema())

        by_substring = await service.list_tables(principal, "ORDER")
        by_glob = await service.list_tables(principal, "*.public.*")

        assert [t.native_path for t in by_substring.tables] == [
            "analytics.public.orders",
            "analytics.raw.orders",
        ]
        assert [t.native_path for t in by_glob.tables] == [
            "analytics.public.orders",
            "analytics.public.customers",
        ]

    async def test_list_tables_credentials_missing(self, principal: UserPrincipal) -> None:
        """Without credentials, nothing is listed and no adapter is built."""
        service, registry, _ = _service(configured=False, schema=_schema())

        with pytest.raises(AgentQueryError) as exc:
            await service.list_tables(principal, None)

        assert exc.value.code == AgentQueryErrorCode.CREDENTIALS_MISSING
        assert "action_url" in exc.value.details
        assert registry.created == []

    async def test_describe_table(self, principal: UserPrincipal) -> None:
        """Columns, types and a cheap row count for one table."""
        service, registry, _ = _service(schema=_schema())

        desc = await service.describe_table(principal, "public.orders")

        (adapter,) = registry.created
        assert adapter.config["username"] == "alice"
        assert desc.native_path == "analytics.public.orders"
        assert desc.row_count == 1200
        assert [(c["name"], c["type"], c["nullable"]) for c in desc.columns] == [
            ("id", "integer", False),
            ("email", "string", True),
        ]

    async def test_describe_table_ambiguous(self, principal: UserPrincipal) -> None:
        """A bare name that matches tables in several schemas asks for qualification."""
        service, _, _ = _service(schema=_schema())

        with pytest.raises(AgentQueryError) as exc:
            await service.describe_table(principal, "orders")

        assert exc.value.code == AgentQueryErrorCode.VALIDATION_FAILED
        assert set(exc.value.details["candidates"]) == {
            "analytics.public.orders",
            "analytics.raw.orders",
        }

    async def test_describe_table_not_found(self, principal: UserPrincipal) -> None:
        """An unknown table is table_not_found."""
        service, _, _ = _service(schema=_schema())

        with pytest.raises(AgentQueryError) as exc:
            await service.describe_table(principal, "public.nope")

        assert exc.value.code == AgentQueryErrorCode.TABLE_NOT_FOUND

    async def test_describe_table_credentials_missing(self, principal: UserPrincipal) -> None:
        """Without credentials, describe_table fails the same way."""
        service, registry, _ = _service(configured=False, schema=_schema())

        with pytest.raises(AgentQueryError) as exc:
            await service.describe_table(principal, "public.orders")

        assert exc.value.code == AgentQueryErrorCode.CREDENTIALS_MISSING
        assert registry.created == []
