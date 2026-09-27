"""Read-only queries the issue chat agent runs as the asking user.

Every query goes through QueryGateway as a UserPrincipal, so the database sees the
asker's own login and enforces their permissions. There is no fallback to the
datasource's stored connection user: without credentials the call fails with
``credentials_missing``.

``run`` validates SQL the same way as the investigation ``execute_query`` activity:
in the dialect declared by the adapter that runs it, refusing adapters that declare
none, allowing a single SELECT, and capping it with a LIMIT. The result is kept in
two forms:

- the snapshot (stored with the thread): at most SNAPSHOT_MAX_ROWS rows and
  SNAPSHOT_MAX_BYTES of JSON, not redacted;
- the model view (sent to the LLM): columns, the first MODEL_VIEW_MAX_ROWS snapshot
  rows with PII redacted, the row count, the truncation flag and column stats.
"""

from __future__ import annotations

import fnmatch
import math
import time
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

import sqlglot
import structlog
from sqlglot import exp

from dataing.adapters.datasource.errors import (
    AdapterError,
    CredentialsInvalidError,
    CredentialsNotConfiguredError,
    DatasourceNotFoundError,
    QueryTimeoutError,
)
from dataing.adapters.datasource.gateway import QueryContext, QueryGateway, UserPrincipal
from dataing.adapters.datasource.types import SchemaFilter, SchemaResponse, Table
from dataing.core.exceptions import QueryValidationError
from dataing.core.json_utils import to_json_safe, to_json_string
from dataing.safety.pii import redact_pii
from dataing.safety.validator import add_limit_if_missing, validate_query

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase

logger = structlog.get_logger(__name__)

AGENT_QUERY_SOURCE = "agent"
QUERY_ROW_LIMIT = 1000
QUERY_TIMEOUT_SECONDS = 30
SNAPSHOT_MAX_ROWS = 200
SNAPSHOT_MAX_BYTES = 256 * 1024
MODEL_VIEW_MAX_ROWS = 50
MODEL_VIEW_MAX_CELL_CHARS = 500
LIST_TABLES_MAX = 200


class AgentQueryErrorCode(StrEnum):
    """Why an agent query or schema lookup failed."""

    CREDENTIALS_MISSING = "credentials_missing"
    CREDENTIALS_INVALID = "credentials_invalid"
    VALIDATION_FAILED = "validation_failed"
    TIMEOUT = "timeout"
    NO_DATASOURCE = "no_datasource"
    TABLE_NOT_FOUND = "table_not_found"
    EXECUTION_FAILED = "execution_failed"


class AgentQueryError(Exception):
    """A typed failure the agent can explain and the UI can act on.

    Attributes:
        code: What went wrong.
        message: Human-readable message.
        details: Extra fields, e.g. ``action_url`` for credentials errors.
    """

    def __init__(
        self,
        code: AgentQueryErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the error."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, Any] = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Return the error as a tool result."""
        return {"error": self.code.value, "message": self.message, "details": self.details}


@dataclass(frozen=True)
class QueryModelView:
    """What the model sees of a query result. String values are PII-redacted."""

    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    column_stats: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Return the view as a JSON-safe dict."""
        return asdict(self)


@dataclass(frozen=True)
class AgentQueryResult:
    """A query the agent ran, as stored and as shown to the model.

    Attributes:
        sql: The SQL that ran (validated, with LIMIT applied).
        dialect: The sqlglot dialect it was validated in.
        purpose: Why the agent ran it.
        columns: Result columns, JSON-safe.
        rows: The snapshot rows, JSON-safe and NOT redacted.
        row_count: Rows the query returned, before the snapshot cap.
        truncated: True when the snapshot holds fewer rows than exist.
        duration_ms: Wall time of the gateway call.
        model_view: The redacted view for the model.
    """

    sql: str
    dialect: str
    purpose: str
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    duration_ms: int
    model_view: QueryModelView


@dataclass(frozen=True)
class TableSummary:
    """One table in a listing."""

    name: str
    schema: str
    catalog: str
    native_path: str
    table_type: str
    row_count: int | None = None


@dataclass(frozen=True)
class TableListing:
    """Tables the user can see, optionally filtered."""

    tables: list[TableSummary]
    truncated: bool

    def to_dict(self) -> dict[str, Any]:
        """Return the listing as a JSON-safe dict."""
        return asdict(self)


@dataclass(frozen=True)
class TableDescription:
    """Columns and types of one table, plus a row count when the adapter had one."""

    name: str
    native_path: str
    table_type: str
    columns: list[dict[str, Any]]
    row_count: int | None = None
    description: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the description as a JSON-safe dict."""
        return asdict(self)


@dataclass
class _Prepared:
    """What the gateway's prepare hook decided."""

    dialect: str = ""
    sql: str = ""


class AgentQueryService:
    """Runs the chat agent's read-only queries and schema lookups as the asking user."""

    def __init__(self, app_db: AppDatabase, gateway: QueryGateway | None = None) -> None:
        """Initialize the service.

        Args:
            app_db: Application database.
            gateway: Query gateway to run through. Defaults to one on app_db.
        """
        self._gateway = gateway or QueryGateway(app_db)

    async def run(self, principal: UserPrincipal, sql: str, purpose: str) -> AgentQueryResult:
        """Validate and run a read-only query as the user.

        Args:
            principal: The asking user and the datasource.
            sql: A single SELECT.
            purpose: Why the agent is running it (kept with the result).

        Returns:
            The snapshot and the model view.

        Raises:
            AgentQueryError: The query was refused or failed.
        """
        prepared = _Prepared()

        def prepare(raw_sql: str, dialect: str | None) -> str:
            if not dialect:
                raise QueryValidationError(
                    "This datasource declares no SQL dialect, so the query cannot be validated"
                )
            prepared.dialect = dialect
            prepared.sql = _limit_query(raw_sql, dialect)
            return prepared.sql

        start = time.monotonic()
        try:
            result = await self._gateway.execute(
                principal,
                sql,
                timeout_seconds=QUERY_TIMEOUT_SECONDS,
                context=QueryContext(source=AGENT_QUERY_SOURCE),
                prepare=prepare,
            )
        except Exception as e:
            raise _to_agent_error(e) from e
        duration_ms = int((time.monotonic() - start) * 1000)

        raw_rows = list(result.rows[:QUERY_ROW_LIMIT])
        row_count = len(raw_rows)
        columns = _columns(result.columns, raw_rows)
        snapshot_rows = _snapshot_rows(raw_rows)
        truncated = result.truncated or len(result.rows) > row_count
        truncated = truncated or len(snapshot_rows) < row_count

        model_view = QueryModelView(
            columns=columns,
            rows=[
                _model_row(row) for row in raw_rows[: min(len(snapshot_rows), MODEL_VIEW_MAX_ROWS)]
            ],
            row_count=row_count,
            truncated=truncated,
            column_stats=_column_stats([c["name"] for c in columns], raw_rows),
        )
        return AgentQueryResult(
            sql=prepared.sql,
            dialect=prepared.dialect,
            purpose=purpose,
            columns=columns,
            rows=snapshot_rows,
            row_count=row_count,
            truncated=truncated,
            duration_ms=duration_ms,
            model_view=model_view,
        )

    async def list_tables(self, principal: UserPrincipal, pattern: str | None) -> TableListing:
        """List the tables the user can see.

        Args:
            principal: The asking user and the datasource.
            pattern: Optional case-insensitive filter on the table's name or full
                path: a substring, or a glob when it contains ``*``, ``?`` or ``%``.

        Returns:
            Up to LIST_TABLES_MAX tables.

        Raises:
            AgentQueryError: The lookup failed.
        """
        schema = await self._get_schema(principal, None)
        matches = [
            summary
            for summary, _ in _iter_tables(schema)
            if pattern is None or _matches_pattern(pattern, summary)
        ]
        return TableListing(
            tables=matches[:LIST_TABLES_MAX],
            truncated=len(matches) > LIST_TABLES_MAX,
        )

    async def describe_table(self, principal: UserPrincipal, table: str) -> TableDescription:
        """Describe one table's columns as the user sees them.

        Args:
            principal: The asking user and the datasource.
            table: The table name, optionally qualified (``schema.table`` or
                ``catalog.schema.table``).

        Returns:
            The table's columns and, when the adapter reports one, its row count.

        Raises:
            AgentQueryError: The table is unknown or ambiguous, or the lookup failed.
        """
        wanted = [part.strip().strip('"`[]').lower() for part in table.split(".")]
        if not all(wanted):
            raise AgentQueryError(
                AgentQueryErrorCode.VALIDATION_FAILED, f"Invalid table name: {table!r}"
            )

        # Narrow discovery by name first; adapters match patterns differently
        # (LIKE, substring, case-sensitive), so fall back to a full listing on a miss.
        candidates = _find_tables(
            await self._get_schema(principal, SchemaFilter(table_pattern=wanted[-1])), wanted
        )
        if not candidates:
            candidates = _find_tables(await self._get_schema(principal, None), wanted)

        if not candidates:
            raise AgentQueryError(
                AgentQueryErrorCode.TABLE_NOT_FOUND,
                f"No table named {table!r} is visible with your credentials",
                {"table": table},
            )
        if len(candidates) > 1:
            raise AgentQueryError(
                AgentQueryErrorCode.VALIDATION_FAILED,
                f"{table!r} matches several tables; qualify it with its schema",
                {"candidates": [t.native_path for t in candidates]},
            )

        (found,) = candidates
        return TableDescription(
            name=found.name,
            native_path=found.native_path,
            table_type=found.table_type,
            columns=[
                {
                    "name": col.name,
                    "type": col.data_type.value,
                    "native_type": col.native_type,
                    "nullable": col.nullable,
                    "primary_key": col.is_primary_key,
                    "description": col.description,
                }
                for col in found.columns
            ],
            row_count=found.row_count,
            description=found.description,
        )

    async def _get_schema(
        self, principal: UserPrincipal, schema_filter: SchemaFilter | None
    ) -> SchemaResponse:
        """Read the schema through the gateway, mapping failures to AgentQueryError."""
        try:
            return await self._gateway.get_schema(
                principal, schema_filter, timeout_seconds=QUERY_TIMEOUT_SECONDS
            )
        except Exception as e:
            raise _to_agent_error(e) from e


def _to_agent_error(error: Exception) -> AgentQueryError:
    """Map a gateway, adapter or validation failure to a typed agent error."""
    if isinstance(error, AgentQueryError):
        return error
    if isinstance(error, QueryValidationError):
        return AgentQueryError(AgentQueryErrorCode.VALIDATION_FAILED, f"Unsafe SQL: {error}")
    if isinstance(error, CredentialsNotConfiguredError):
        return AgentQueryError(
            AgentQueryErrorCode.CREDENTIALS_MISSING, error.message, dict(error.details)
        )
    if isinstance(error, CredentialsInvalidError):
        return AgentQueryError(
            AgentQueryErrorCode.CREDENTIALS_INVALID, error.message, dict(error.details)
        )
    if isinstance(error, DatasourceNotFoundError):
        return AgentQueryError(
            AgentQueryErrorCode.NO_DATASOURCE, error.message, dict(error.details)
        )
    if isinstance(error, QueryTimeoutError | TimeoutError):
        return AgentQueryError(
            AgentQueryErrorCode.TIMEOUT,
            f"The query did not finish within {QUERY_TIMEOUT_SECONDS} seconds",
            {"timeout_seconds": QUERY_TIMEOUT_SECONDS},
        )
    logger.warning(f"Agent query failed: {type(error).__name__}: {error}")
    details = dict(error.details) if isinstance(error, AdapterError) else {}
    return AgentQueryError(AgentQueryErrorCode.EXECUTION_FAILED, str(error)[:1000], details)


def _limit_query(sql: str, dialect: str) -> str:
    """Validate a query and cap it at QUERY_ROW_LIMIT rows.

    Adds a LIMIT when missing and lowers a literal LIMIT above the cap, then
    validates the final SQL again, LIMIT required.

    Raises:
        QueryValidationError: The query is not a single safe SELECT.
    """
    validate_query(sql, dialect=dialect, require_limit=False)
    limited = add_limit_if_missing(sql, limit=QUERY_ROW_LIMIT, dialect=dialect)

    parsed = sqlglot.parse_one(limited, dialect=dialect)
    if isinstance(parsed, exp.Query):
        limit = parsed.args.get("limit")
        value = limit.expression if isinstance(limit, exp.Limit) else None
        too_many = (
            isinstance(value, exp.Literal) and value.is_int and int(value.this) > QUERY_ROW_LIMIT
        )
        if limit is None or too_many:
            limited = parsed.limit(QUERY_ROW_LIMIT).sql(dialect=dialect)

    validate_query(limited, dialect=dialect)
    return limited


def _json_safe_value(value: Any) -> Any:
    """Convert one value to JSON-safe types, falling back for what JSON can't hold."""
    try:
        return to_json_safe(value)
    except Exception:
        if isinstance(value, bytes | bytearray | memoryview):
            return "\\x" + bytes(value).hex()
        return str(value)


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a row to JSON-safe types, cell by cell when the row as a whole fails."""
    try:
        safe: dict[str, Any] = to_json_safe(row)
        return safe
    except Exception:
        return {str(k): _json_safe_value(v) for k, v in row.items()}


def _columns(columns: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return JSON-safe column descriptions, derived from the rows when the adapter gave none."""
    if columns:
        safe: list[dict[str, Any]] = [_json_safe_row(c) for c in columns]
        return safe
    return [{"name": name} for name in (rows[0] if rows else {})]


def _snapshot_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep at most SNAPSHOT_MAX_ROWS rows whose JSON array fits in SNAPSHOT_MAX_BYTES."""
    kept: list[dict[str, Any]] = []
    size = 2  # the enclosing brackets
    for row in rows[:SNAPSHOT_MAX_ROWS]:
        safe = _json_safe_row(row)
        row_bytes = len(to_json_string(safe).encode("utf-8")) + (1 if kept else 0)
        if size + row_bytes > SNAPSHOT_MAX_BYTES:
            break
        kept.append(safe)
        size += row_bytes
    return kept


def _model_value(value: Any) -> Any:
    """Convert a value for the model: numbers stay numbers, strings are redacted."""
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return float(value) if value.is_finite() else None
    if isinstance(value, bytes | bytearray | memoryview):
        return f"<{len(bytes(value))} bytes>"
    if isinstance(value, dict):
        return {str(k): _model_value(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [_model_value(v) for v in value]
    text = value if isinstance(value, str) else _json_safe_value(value)
    if not isinstance(text, str):
        return text
    # Redact before truncating, so a cut can't leave half of an email unmatched
    redacted = redact_pii(text)
    if len(redacted) > MODEL_VIEW_MAX_CELL_CHARS:
        return redacted[:MODEL_VIEW_MAX_CELL_CHARS] + "…"
    return redacted


def _model_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert one row for the model view."""
    return {str(k): _model_value(v) for k, v in row.items()}


def _column_stats(names: list[str], rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Null count, distinct count and numeric min/max per column, over the returned rows."""
    stats: dict[str, dict[str, Any]] = {}
    for name in names:
        values = [row.get(name) for row in rows]
        present = [v for v in values if v is not None]
        stat: dict[str, Any] = {
            "null_count": len(values) - len(present),
            "distinct_count": len({_distinct_key(v) for v in present}),
        }
        numbers = [_number(v) for v in present]
        finite = [n for n in numbers if n is not None]
        if present and len(finite) == len(present):
            stat["min"] = min(finite)
            stat["max"] = max(finite)
        stats[name] = stat
    return stats


def _number(value: Any) -> int | float | None:
    """Return a finite number for numeric values, else None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float | Decimal):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def _distinct_key(value: Any) -> Any:
    """Return a hashable key for counting distinct values."""
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


def _iter_tables(schema: SchemaResponse) -> list[tuple[TableSummary, Table]]:
    """Flatten a schema into (summary, table) pairs in discovery order."""
    return [
        (
            TableSummary(
                name=table.name,
                schema=db_schema.name,
                catalog=catalog.name,
                native_path=table.native_path,
                table_type=table.table_type,
                row_count=table.row_count,
            ),
            table,
        )
        for catalog in schema.catalogs
        for db_schema in catalog.schemas
        for table in db_schema.tables
    ]


def _matches_pattern(pattern: str, summary: TableSummary) -> bool:
    """Match a table against a substring or glob pattern, case-insensitively."""
    needle = pattern.strip().lower().replace("%", "*")
    if not needle:
        return True
    haystacks = (summary.name.lower(), summary.native_path.lower())
    if any(ch in needle for ch in "*?["):
        return any(fnmatch.fnmatchcase(h, needle) for h in haystacks)
    return any(needle in h for h in haystacks)


def _find_tables(schema: SchemaResponse, wanted: list[str]) -> list[Table]:
    """Find tables whose qualified name ends with the wanted parts."""
    found: list[Table] = []
    joined = ".".join(wanted)
    for summary, table in _iter_tables(schema):
        qualified = [summary.catalog.lower(), summary.schema.lower(), summary.name.lower()]
        if qualified[-len(wanted) :] == wanted or summary.native_path.lower() == joined:
            found.append(table)
    return found
