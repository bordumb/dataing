"""Query Gateway for principal-bound query execution.

This module provides the single point of entry for all SQL execution,
ensuring that every query is executed with user credentials and
properly audited.

The gateway never falls back to the datasource's stored connection user: the
stored config supplies host, port and database only, and the login always comes
from the principal's own credentials.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable
from uuid import UUID

import structlog

from dataing.adapters.datasource.encryption import decrypt_config, get_encryption_key
from dataing.adapters.datasource.errors import (
    AuthenticationFailedError,
    CredentialsInvalidError,
    CredentialsNotConfiguredError,
    CredentialsNotSupportedError,
    DatasourceNotFoundError,
    QueryTimeoutError,
)
from dataing.adapters.datasource.registry import AdapterRegistry, get_registry
from dataing.adapters.datasource.types import (
    QueryResult,
    SchemaFilter,
    SchemaResponse,
    SourceType,
)
from dataing.core.credentials import CredentialsService, DecryptedCredentials

if TYPE_CHECKING:
    from dataing.adapters.datasource.base import BaseAdapter
    from dataing.adapters.db.app_db import AppDatabase

logger = structlog.get_logger(__name__)

T = TypeVar("T")

# Substrings of driver errors that mean the database rejected the login itself.
# Kept specific so that errors naming columns like "author" or "last_login" don't match.
_AUTH_ERROR_KEYWORDS = (
    "authentication failed",
    "password authentication",
    "incorrect username or password",
    "invalid username or password",
    "invalid credentials",
    "access denied for user",
    "login failed",
)


def ensure_user_credentials_supported(source_type: SourceType) -> None:
    """Refuse per-user credentials for a source type that has no database login.

    A user's own credentials replace the stored login under ``username`` (see
    ``DecryptedCredentials.apply_to``). A source type whose config schema has no
    ``username`` field ignores them and connects with its stored config.

    Args:
        source_type: The datasource's source type.

    Raises:
        CredentialsNotSupportedError: If the source type's config has no ``username``.
    """
    definition = get_registry().get_definition(source_type)
    fields = definition.config_schema.fields if definition else []
    if not any(field.name == "username" for field in fields):
        raise CredentialsNotSupportedError(source_type.value)


@dataclass(frozen=True)
class UserPrincipal:
    """The user a query runs as.

    Every query must have a principal that identifies who is
    executing it. The gateway connects with this user's own credentials
    for the datasource, so the database enforces their permissions.
    """

    user_id: UUID
    tenant_id: UUID
    datasource_id: UUID


QueryPrincipal = UserPrincipal
"""Alias of UserPrincipal."""


@dataclass(frozen=True)
class QueryContext:
    """Additional context for query execution."""

    investigation_id: UUID | None = None
    source: str = "api"  # 'agent', 'api', 'preview', etc.


SqlPreparer = Callable[[str, str | None], str]
"""Checks SQL before it runs and returns the SQL to run.

Called with the SQL and the sqlglot dialect declared by the adapter that will run
it (None when the adapter declares none). Raise to refuse the query; the gateway
audits the refusal as ``rejected`` and never connects.
"""


@runtime_checkable
class SqlExecutor(Protocol):
    """An adapter that can run SQL."""

    async def execute_query(
        self,
        sql: str,
        params: Any = None,
        timeout_seconds: int = 30,
    ) -> QueryResult:
        """Execute SQL and return its result."""
        ...


class QueryGateway:
    """Single point of entry for all SQL execution.

    ALL query paths must go through this gateway:
    - Agent tool calls
    - API endpoints
    - Background jobs (must have a principal)

    The gateway ensures:
    1. User credentials are used (not service accounts)
    2. Every query is audited
    3. DB-native permission enforcement
    """

    def __init__(
        self,
        app_db: AppDatabase,
        *,
        credentials_service: CredentialsService | None = None,
        registry: AdapterRegistry | None = None,
        encryption_key: bytes | None = None,
    ) -> None:
        """Initialize the query gateway.

        Args:
            app_db: Application database for persistence.
            credentials_service: Resolves user credentials. Defaults to one on app_db.
            registry: Adapter registry. Defaults to the global registry.
            encryption_key: Key for datasource configs. Defaults to the configured key.
        """
        self._app_db = app_db
        self._credentials_service = credentials_service or CredentialsService(app_db)
        self._registry = registry or get_registry()
        self._encryption_key = encryption_key or get_encryption_key()

    async def execute(
        self,
        principal: UserPrincipal,
        sql: str,
        params: Sequence[Any] | None = None,
        timeout_seconds: int = 30,
        context: QueryContext | None = None,
        prepare: SqlPreparer | None = None,
    ) -> QueryResult:
        """Execute a SQL query with the user's credentials.

        Args:
            principal: The identity executing the query.
            sql: The SQL query to execute.
            params: Optional values bound to the query's placeholders.
            timeout_seconds: Hard limit on connecting plus running the query.
            context: Additional execution context.
            prepare: Optional check run with the adapter's dialect before connecting;
                its return value is the SQL that runs (see SqlPreparer).

        Returns:
            QueryResult with columns, rows, and metadata.

        Raises:
            DatasourceNotFoundError: The tenant has no such datasource.
            CredentialsNotConfiguredError: User hasn't configured credentials.
            CredentialsInvalidError: User's credentials were rejected.
            CredentialsNotSupportedError: The datasource has no database login.
            QueryTimeoutError: The query did not finish within timeout_seconds.
        """
        ctx = context or QueryContext()
        start = time.monotonic()
        audited_sql = sql
        status = "success"
        error_msg: str | None = None
        row_count: int | None = None

        try:
            adapter = await self._open_user_adapter(principal)

            if prepare is not None:
                try:
                    audited_sql = prepare(sql, adapter.capabilities.sql_dialect)
                except Exception:
                    status = "rejected"
                    raise

            if not isinstance(adapter, SqlExecutor):
                raise TypeError(f"{type(adapter).__name__} cannot run SQL")
            executor = adapter
            run_sql = audited_sql

            async def run(_: Any) -> QueryResult:
                if params is None:
                    return await executor.execute_query(run_sql, timeout_seconds=timeout_seconds)
                return await executor.execute_query(
                    run_sql, params=params, timeout_seconds=timeout_seconds
                )

            result = await self._call_connected(principal, adapter, run, timeout_seconds)
            row_count = result.row_count

            await self._credentials_service.update_last_used(
                principal.user_id,
                principal.datasource_id,
            )
            return result

        except Exception as e:
            if status == "success":
                status = self._audit_status(e)
            error_msg = str(e)
            raise
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            await self._audit_log(
                principal=principal,
                sql=audited_sql,
                sql_hash=self._hash_sql(audited_sql),
                row_count=row_count,
                status=status,
                error_message=error_msg,
                duration_ms=duration_ms,
                context=ctx,
            )

    async def get_schema(
        self,
        principal: UserPrincipal,
        filter: SchemaFilter | None = None,
        timeout_seconds: int = 30,
    ) -> SchemaResponse:
        """Discover the datasource's schema as the user.

        The adapter connects with the user's credentials, so the result lists
        what that user can see.

        Args:
            principal: The identity reading the schema.
            filter: Optional filter passed to the adapter.
            timeout_seconds: Hard limit on connecting plus discovery.

        Returns:
            The schema the user can see.

        Raises:
            DatasourceNotFoundError: The tenant has no such datasource.
            CredentialsNotConfiguredError: User hasn't configured credentials.
            CredentialsInvalidError: User's credentials were rejected.
            CredentialsNotSupportedError: The datasource has no database login.
            QueryTimeoutError: Discovery did not finish within timeout_seconds.
        """
        adapter = await self._open_user_adapter(principal)

        async def discover(connected: Any) -> SchemaResponse:
            schema: SchemaResponse = await connected.get_schema(filter)
            return schema

        schema = await self._call_connected(principal, adapter, discover, timeout_seconds)
        await self._credentials_service.update_last_used(
            principal.user_id,
            principal.datasource_id,
        )
        return schema

    async def _call_connected(
        self,
        principal: UserPrincipal,
        adapter: BaseAdapter,
        call: Callable[[Any], Awaitable[T]],
        timeout_seconds: int,
    ) -> T:
        """Connect the adapter, run a call on it and disconnect, within a time limit.

        Translates login failures to CredentialsInvalidError and time-outs to
        QueryTimeoutError.
        """
        try:
            async with asyncio.timeout(timeout_seconds), adapter:
                return await call(adapter)
        except (QueryTimeoutError, CredentialsInvalidError):
            raise
        except TimeoutError as e:
            raise QueryTimeoutError(
                message=f"Query timed out after {timeout_seconds}s",
                timeout_seconds=timeout_seconds,
            ) from e
        except Exception as e:
            if isinstance(e, AuthenticationFailedError) or any(
                keyword in str(e).lower() for keyword in _AUTH_ERROR_KEYWORDS
            ):
                raise CredentialsInvalidError(
                    datasource_id=str(principal.datasource_id),
                    db_message=str(e),
                    action_url=self._credentials_url(principal),
                ) from e
            raise

    async def _open_user_adapter(self, principal: UserPrincipal) -> BaseAdapter:
        """Build an unconnected adapter that logs in with the user's credentials.

        Args:
            principal: The query principal.

        Returns:
            An adapter configured with the stored connection details and the
            user's own login.

        Raises:
            DatasourceNotFoundError: The tenant has no such datasource.
            CredentialsNotSupportedError: The datasource has no database login.
            CredentialsNotConfiguredError: User hasn't configured credentials.
        """
        ds_info = await self._app_db.get_data_source(
            principal.datasource_id,
            principal.tenant_id,
        )
        if not ds_info:
            raise DatasourceNotFoundError(
                datasource_id=str(principal.datasource_id),
                tenant_id=str(principal.tenant_id),
            )

        # Configuring credentials can't help a source type with no login
        source_type = SourceType(ds_info["type"])
        ensure_user_credentials_supported(source_type)

        credentials = await self._credentials_service.get_credentials(
            principal.user_id,
            principal.datasource_id,
        )
        if not credentials:
            raise CredentialsNotConfiguredError(
                datasource_id=str(principal.datasource_id),
                datasource_name=ds_info.get("name"),
                action_url=self._credentials_url(principal),
            )

        return self._create_user_adapter(ds_info, credentials)

    def _create_user_adapter(
        self,
        ds_info: dict[str, Any],
        credentials: DecryptedCredentials,
    ) -> BaseAdapter:
        """Create an adapter using the user's credentials.

        Args:
            ds_info: The datasource row (type and encrypted connection config).
            credentials: Decrypted user credentials.

        Returns:
            A configured, unconnected adapter.
        """
        base_config = decrypt_config(
            ds_info["connection_config_encrypted"],
            self._encryption_key,
        )
        # The user's login replaces the stored one
        connection_config = credentials.apply_to(base_config)
        return self._registry.create(SourceType(ds_info["type"]), connection_config)

    @staticmethod
    def _credentials_url(principal: UserPrincipal) -> str:
        """Return the page where the user manages credentials for the datasource."""
        return f"/settings/datasources/{principal.datasource_id}/credentials"

    @staticmethod
    def _audit_status(error: Exception) -> str:
        """Map an execution failure to its audit status."""
        if isinstance(error, CredentialsNotConfiguredError | CredentialsInvalidError):
            return "denied"
        if isinstance(error, QueryTimeoutError):
            return "timeout"
        return "error"

    async def _audit_log(
        self,
        principal: UserPrincipal,
        sql: str,
        sql_hash: str,
        row_count: int | None,
        status: str,
        error_message: str | None,
        duration_ms: int,
        context: QueryContext,
    ) -> None:
        """Log query execution to audit log.

        Args:
            principal: The query principal.
            sql: The SQL query text.
            sql_hash: Hash of the SQL query.
            row_count: Number of rows returned.
            status: Query status (success, denied, rejected, error, timeout).
            error_message: Error message if any.
            duration_ms: Query duration in milliseconds.
            context: Additional execution context.
        """
        try:
            await self._app_db.insert_query_audit_log(
                tenant_id=principal.tenant_id,
                user_id=principal.user_id,
                datasource_id=principal.datasource_id,
                sql_hash=sql_hash,
                sql_text=sql[:10000] if sql else None,  # Truncate very long queries
                tables_accessed=self._extract_tables(sql),
                executed_at=datetime.now(UTC),
                duration_ms=duration_ms,
                row_count=row_count,
                status=status,
                error_message=error_message[:1000] if error_message else None,
                investigation_id=context.investigation_id,
                source=context.source,
            )
        except Exception as e:
            # Log but don't fail the query
            logger.warning(
                "Failed to write audit log",
                error=str(e),
                user_id=str(principal.user_id),
                datasource_id=str(principal.datasource_id),
            )

    @staticmethod
    def _hash_sql(sql: str) -> str:
        """Create a hash of the SQL query for deduplication.

        Args:
            sql: The SQL query text.

        Returns:
            SHA256 hash of the normalized query.
        """
        # Normalize whitespace for consistent hashing
        normalized = " ".join(sql.split())
        return hashlib.sha256(normalized.encode()).hexdigest()

    @staticmethod
    def _extract_tables(sql: str) -> list[str] | None:
        """Extract table names from a SQL query.

        This is a simple extraction for audit purposes.
        Does not handle all SQL dialects perfectly.

        Args:
            sql: The SQL query text.

        Returns:
            List of table names found, or None.
        """
        tables = []

        # Match FROM and JOIN clauses
        patterns = [
            r"FROM\s+([a-zA-Z_][a-zA-Z0-9_\.]*)",
            r"JOIN\s+([a-zA-Z_][a-zA-Z0-9_\.]*)",
            r"INTO\s+([a-zA-Z_][a-zA-Z0-9_\.]*)",
            r"UPDATE\s+([a-zA-Z_][a-zA-Z0-9_\.]*)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, sql, re.IGNORECASE)
            tables.extend(matches)

        # Deduplicate while preserving order
        seen = set()
        unique_tables = []
        for table in tables:
            if table.lower() not in seen:
                seen.add(table.lower())
                unique_tables.append(table)

        return unique_tables if unique_tables else None
