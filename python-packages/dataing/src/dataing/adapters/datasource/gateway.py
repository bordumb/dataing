"""Query Gateway for principal-bound query execution.

This module provides the single point of entry for all SQL execution,
ensuring that every query is executed with user credentials and
properly audited.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from dataing.adapters.datasource.encryption import decrypt_config, get_encryption_key
from dataing.adapters.datasource.errors import (
    CredentialsInvalidError,
    CredentialsNotConfiguredError,
    CredentialsNotSupportedError,
)
from dataing.adapters.datasource.registry import get_registry
from dataing.adapters.datasource.types import QueryResult, SourceType
from dataing.core.credentials import CredentialsService, DecryptedCredentials

if TYPE_CHECKING:
    from dataing.adapters.db.app_db import AppDatabase

logger = structlog.get_logger(__name__)


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
class QueryPrincipal:
    """The identity executing a query.

    Every query must have a principal that identifies who is
    executing it. This enables DB-native permission enforcement.
    """

    user_id: UUID
    tenant_id: UUID
    datasource_id: UUID


@dataclass(frozen=True)
class QueryContext:
    """Additional context for query execution."""

    investigation_id: UUID | None = None
    source: str = "api"  # 'agent', 'api', 'preview', etc.


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

    def __init__(self, app_db: AppDatabase) -> None:
        """Initialize the query gateway.

        Args:
            app_db: Application database for persistence.
        """
        self._app_db = app_db
        self._credentials_service = CredentialsService(app_db)
        self._registry = get_registry()
        self._encryption_key = get_encryption_key()

    async def execute(
        self,
        principal: QueryPrincipal,
        sql: str,
        params: dict[str, Any] | None = None,
        timeout_seconds: int = 30,
        context: QueryContext | None = None,
    ) -> QueryResult:
        """Execute a SQL query with the user's credentials.

        Args:
            principal: The identity executing the query.
            sql: The SQL query to execute.
            params: Optional query parameters.
            timeout_seconds: Query timeout in seconds.
            context: Additional execution context.

        Returns:
            QueryResult with columns, rows, and metadata.

        Raises:
            CredentialsNotConfiguredError: User hasn't configured credentials.
            CredentialsInvalidError: User's credentials were rejected.
            CredentialsNotSupportedError: The datasource has no database login.
        """
        ctx = context or QueryContext()
        sql_hash = self._hash_sql(sql)
        start = time.monotonic()
        result: QueryResult | None = None
        status = "success"
        error_msg: str | None = None
        row_count: int | None = None

        try:
            # 1. Get user's credentials for this datasource
            credentials = await self._credentials_service.get_credentials(
                principal.user_id,
                principal.datasource_id,
            )
            if not credentials:
                ds_info = await self._app_db.get_data_source(
                    principal.datasource_id,
                    principal.tenant_id,
                )
                ds_name = ds_info["name"] if ds_info else None
                raise CredentialsNotConfiguredError(
                    datasource_id=str(principal.datasource_id),
                    datasource_name=ds_name,
                    action_url=f"/settings/datasources/{principal.datasource_id}/credentials",
                )

            # 2. Create adapter with USER's credentials
            adapter = await self._create_user_adapter(principal, credentials)

            # 3. Execute query - DB enforces permissions
            try:
                async with adapter:
                    result = await adapter.execute_query(
                        sql,
                        timeout_seconds=timeout_seconds,
                    )
                    row_count = result.row_count
            except Exception as e:
                # Check if this is an auth error
                error_str = str(e).lower()
                if any(
                    keyword in error_str
                    for keyword in ["auth", "password", "credential", "login", "access denied"]
                ):
                    status = "denied"
                    error_msg = str(e)
                    raise CredentialsInvalidError(
                        datasource_id=str(principal.datasource_id),
                        db_message=str(e),
                        action_url=f"/settings/datasources/{principal.datasource_id}/credentials",
                    ) from e
                raise

            # Update last used timestamp (async, don't block)
            await self._credentials_service.update_last_used(
                principal.user_id,
                principal.datasource_id,
            )

            return result

        except CredentialsNotConfiguredError:
            status = "denied"
            error_msg = "Credentials not configured"
            raise
        except CredentialsInvalidError:
            # Already set status above
            raise
        except Exception as e:
            status = "error"
            error_msg = str(e)
            raise
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            # 4. Audit log (async, don't block)
            await self._audit_log(
                principal=principal,
                sql=sql,
                sql_hash=sql_hash,
                row_count=row_count,
                status=status,
                error_message=error_msg,
                duration_ms=duration_ms,
                context=ctx,
            )

    async def _create_user_adapter(
        self,
        principal: QueryPrincipal,
        credentials: DecryptedCredentials,
    ) -> Any:
        """Create an adapter using the user's credentials.

        Args:
            principal: The query principal with datasource_id.
            credentials: Decrypted user credentials.

        Returns:
            A configured SQL adapter.

        Raises:
            CredentialsNotSupportedError: The datasource has no database login.
        """
        # Get datasource config (host, port, database, etc.)
        ds_info = await self._app_db.get_data_source(
            principal.datasource_id,
            principal.tenant_id,
        )
        if not ds_info:
            raise ValueError(f"Datasource not found: {principal.datasource_id}")

        source_type = SourceType(ds_info["type"])
        ensure_user_credentials_supported(source_type)

        # Decrypt base connection config
        base_config = decrypt_config(
            ds_info["connection_config_encrypted"],
            self._encryption_key,
        )
        connection_config = credentials.apply_to(base_config)

        # Create fresh adapter with user's credentials
        adapter = self._registry.create(source_type, connection_config)

        return adapter

    async def _audit_log(
        self,
        principal: QueryPrincipal,
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
            status: Query status (success, denied, error, timeout).
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
        import re

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
