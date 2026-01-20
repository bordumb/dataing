"""Context object for Dataing SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .exceptions import ValidationError
from .types import AssetRef, ContextBundle, ResolvedAsset

if TYPE_CHECKING:
    from .client import DataingClient


class Context:
    """SDK Context object wrapping a ContextBundle.

    Provides access to resolved assets, lineage, and context data.
    Uses server-derived bundle_hash for caching.

    Example:
        ctx = client.context("postgres://db.schema.orders")
        print(ctx.resolved_assets)
        print(ctx.lineage)
    """

    def __init__(self, bundle: ContextBundle, client: DataingClient) -> None:
        """Initialize context from a bundle.

        Args:
            bundle: The underlying ContextBundle.
            client: Parent client for making additional API calls.
        """
        self._bundle = bundle
        self._client = client

    @property
    def bundle_id(self) -> str:
        """Get the bundle ID."""
        return self._bundle.bundle_id

    @property
    def bundle_hash(self) -> str:
        """Get the server-derived bundle hash (cache key)."""
        return self._bundle.bundle_hash

    @property
    def resolved_assets(self) -> list[ResolvedAsset]:
        """Get the per-asset resolution list."""
        return self._bundle.resolved_assets

    @property
    def default_datasource_id(self) -> str | None:
        """Get the default datasource ID."""
        return self._bundle.default_datasource_id

    @property
    def lineage(self) -> dict | None:
        """Get the lineage graph."""
        return self._bundle.lineage

    @property
    def operational(self) -> dict | None:
        """Get operational facts."""
        return self._bundle.operational

    @property
    def anomalies(self) -> list[dict] | None:
        """Get anomaly summaries."""
        return self._bundle.anomalies

    @property
    def assets(self) -> list[AssetRef]:
        """Get the original asset references."""
        return [ra.asset for ra in self._bundle.resolved_assets]

    def __repr__(self) -> str:
        """String representation."""
        asset_count = len(self._bundle.resolved_assets)
        return f"<Context bundle={self.bundle_id[:8]}... assets={asset_count}>"


def from_sql(
    sql: str,
    *,
    datasource_id: str | None = None,
    default_platform: str | None = None,
    dialect: str | None = None,
    default_database: str | None = None,
    default_schema: str | None = None,
) -> list[AssetRef]:
    """Extract asset references from SQL query.

    Parses SQL to find table references and converts them to AssetRefs.
    Requires either datasource_id or default_platform to be specified.

    Args:
        sql: SQL query to parse.
        datasource_id: Datasource ID to use for all extracted assets.
        default_platform: Platform to use if datasource_id not provided.
        dialect: SQL dialect for parsing (e.g., 'postgres', 'snowflake').
            Defaults to ANSI SQL if not specified.
        default_database: Default database for unqualified table names.
        default_schema: Default schema for unqualified table names.

    Returns:
        List of AssetRef objects for tables referenced in the SQL.

    Raises:
        ValidationError: If neither datasource_id nor default_platform is provided.
        ImportError: If sqlglot is not installed (install with [sql] extra).

    Example:
        assets = from_sql(
            "SELECT * FROM orders JOIN customers ON ...",
            default_platform="postgres",
            default_schema="public"
        )
    """
    if datasource_id is None and default_platform is None:
        raise ValidationError(
            "from_sql requires either datasource_id or default_platform. "
            "Without a platform, we cannot construct valid URNs."
        )

    try:
        import sqlglot
    except ImportError as e:
        raise ImportError(
            "sqlglot is required for from_sql(). "
            "Install with: pip install 'dataing-sdk[sql]'"
        ) from e

    # Parse SQL
    try:
        parsed = sqlglot.parse(sql, dialect=dialect)
    except Exception as e:
        raise ValidationError(f"Failed to parse SQL: {e}") from e

    # Extract table references
    tables: set[str] = set()
    for statement in parsed:
        if statement is None:
            continue
        for table in statement.find_all(sqlglot.exp.Table):
            # Build qualified name
            parts: list[str] = []

            # Database (catalog)
            if table.catalog:
                parts.append(table.catalog)
            elif default_database:
                parts.append(default_database)

            # Schema
            if table.db:
                parts.append(table.db)
            elif default_schema:
                parts.append(default_schema)

            # Table name
            if table.name:
                parts.append(table.name)

            if parts:
                tables.add(".".join(parts))

    # Convert to AssetRefs
    platform = default_platform or "unknown"
    assets: list[AssetRef] = []
    for table_name in sorted(tables):
        assets.append(
            AssetRef(
                platform=platform,
                name=table_name,
                datasource_id=datasource_id,
            )
        )

    return assets
