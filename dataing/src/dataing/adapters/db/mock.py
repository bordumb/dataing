"""Mock database adapter for testing."""

from __future__ import annotations

from datetime import UTC, datetime

from dataing.adapters.datasource.types import (
    Catalog,
    Column,
    NormalizedType,
    QueryResult,
    Schema,
    SchemaResponse,
    SourceCategory,
    SourceType,
    Table,
)


class MockDatabaseAdapter:
    """Mock adapter for testing - returns canned responses.

    This adapter is useful for:
    - Unit testing without a real database
    - Integration testing with deterministic responses
    - Development without database setup

    Attributes:
        responses: Map of query patterns to responses.
        executed_queries: Log of all executed queries.
    """

    def __init__(
        self,
        responses: dict[str, QueryResult] | None = None,
        schema: SchemaResponse | None = None,
    ) -> None:
        """Initialize the mock adapter.

        Args:
            responses: Map of query patterns to responses.
            schema: Mock schema to return from get_schema.
        """
        self.responses = responses or {}
        self._mock_schema = schema or self._default_schema()
        self.executed_queries: list[str] = []

    def _default_schema(self) -> SchemaResponse:
        """Create a default mock schema for testing."""
        return SchemaResponse(
            source_id="mock",
            source_type=SourceType.POSTGRESQL,
            source_category=SourceCategory.DATABASE,
            fetched_at=datetime.now(UTC),
            catalogs=[
                Catalog(
                    name="main",
                    schemas=[
                        Schema(
                            name="public",
                            tables=[
                                Table(
                                    name="users",
                                    table_type="table",
                                    native_type="table",
                                    native_path="public.users",
                                    columns=[
                                        Column(
                                            name="id",
                                            data_type=NormalizedType.INTEGER,
                                            native_type="integer",
                                        ),
                                        Column(
                                            name="email",
                                            data_type=NormalizedType.STRING,
                                            native_type="varchar",
                                        ),
                                        Column(
                                            name="created_at",
                                            data_type=NormalizedType.TIMESTAMP,
                                            native_type="timestamp",
                                        ),
                                        Column(
                                            name="updated_at",
                                            data_type=NormalizedType.TIMESTAMP,
                                            native_type="timestamp",
                                        ),
                                    ],
                                ),
                                Table(
                                    name="orders",
                                    table_type="table",
                                    native_type="table",
                                    native_path="public.orders",
                                    columns=[
                                        Column(
                                            name="id",
                                            data_type=NormalizedType.INTEGER,
                                            native_type="integer",
                                        ),
                                        Column(
                                            name="user_id",
                                            data_type=NormalizedType.INTEGER,
                                            native_type="integer",
                                        ),
                                        Column(
                                            name="total",
                                            data_type=NormalizedType.DECIMAL,
                                            native_type="numeric",
                                        ),
                                        Column(
                                            name="status",
                                            data_type=NormalizedType.STRING,
                                            native_type="varchar",
                                        ),
                                        Column(
                                            name="created_at",
                                            data_type=NormalizedType.TIMESTAMP,
                                            native_type="timestamp",
                                        ),
                                    ],
                                ),
                                Table(
                                    name="products",
                                    table_type="table",
                                    native_type="table",
                                    native_path="public.products",
                                    columns=[
                                        Column(
                                            name="id",
                                            data_type=NormalizedType.INTEGER,
                                            native_type="integer",
                                        ),
                                        Column(
                                            name="name",
                                            data_type=NormalizedType.STRING,
                                            native_type="varchar",
                                        ),
                                        Column(
                                            name="price",
                                            data_type=NormalizedType.DECIMAL,
                                            native_type="numeric",
                                        ),
                                        Column(
                                            name="category",
                                            data_type=NormalizedType.STRING,
                                            native_type="varchar",
                                        ),
                                    ],
                                ),
                            ],
                        )
                    ],
                )
            ],
        )

    async def connect(self) -> None:
        """No-op for mock adapter."""
        pass

    async def close(self) -> None:
        """No-op for mock adapter."""
        pass

    async def execute_query(self, sql: str, timeout_seconds: int = 30) -> QueryResult:
        """Execute a mock query.

        Matches the SQL against registered patterns and returns
        the corresponding response.

        Args:
            sql: The SQL query to execute.
            timeout_seconds: Ignored for mock.

        Returns:
            Matching QueryResult or empty result.
        """
        self.executed_queries.append(sql)

        # Find matching response by substring (case-insensitive)
        for pattern, response in self.responses.items():
            if pattern.lower() in sql.lower():
                return response

        # Default empty response
        return QueryResult(columns=[], rows=[], row_count=0)

    async def get_schema(self, table_pattern: str | None = None) -> SchemaResponse:
        """Return mock schema.

        Args:
            table_pattern: Optional filter pattern.

        Returns:
            Mock SchemaResponse.
        """
        if table_pattern:
            # Filter tables by pattern
            filtered_catalogs = []
            for catalog in self._mock_schema.catalogs:
                filtered_schemas = []
                for schema in catalog.schemas:
                    filtered_tables = [
                        t for t in schema.tables if table_pattern.lower() in t.native_path.lower()
                    ]
                    if filtered_tables:
                        filtered_schemas.append(Schema(name=schema.name, tables=filtered_tables))
                if filtered_schemas:
                    filtered_catalogs.append(Catalog(name=catalog.name, schemas=filtered_schemas))

            return SchemaResponse(
                source_id=self._mock_schema.source_id,
                source_type=self._mock_schema.source_type,
                source_category=self._mock_schema.source_category,
                fetched_at=self._mock_schema.fetched_at,
                catalogs=filtered_catalogs,
            )
        return self._mock_schema

    def add_response(self, pattern: str, response: QueryResult) -> None:
        """Add a canned response for a query pattern.

        Args:
            pattern: Substring to match in queries.
            response: QueryResult to return when pattern matches.
        """
        self.responses[pattern] = response

    def add_row_count_response(
        self,
        pattern: str,
        count: int,
    ) -> None:
        """Add a simple row count response.

        Args:
            pattern: Substring to match in queries.
            count: Row count to return.
        """
        self.responses[pattern] = QueryResult(
            columns=[{"name": "count", "data_type": "integer"}],
            rows=[{"count": count}],
            row_count=1,
        )

    def clear_queries(self) -> None:
        """Clear the executed queries log."""
        self.executed_queries = []

    def get_query_count(self) -> int:
        """Get the number of queries executed."""
        return len(self.executed_queries)

    def was_query_executed(self, pattern: str) -> bool:
        """Check if a query matching pattern was executed.

        Args:
            pattern: Substring to search for.

        Returns:
            True if any executed query contains the pattern.
        """
        return any(pattern.lower() in q.lower() for q in self.executed_queries)
