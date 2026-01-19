# Schema Toolset Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create an on-demand schema lookup toolset that replaces upfront context dumping, allowing agents to fetch table schemas as needed.

**Architecture:** Protocol-based tools in bond (decoupled), concrete adapter in dataing. Pre-load target table + lineage names, agent fetches details on demand via tools.

**Tech Stack:** Python, Pydantic, PydanticAI Tools, existing BaseAdapter and LineageAdapter

---

## Task 1: Create Schema Tool Protocol

**Files:**
- Create: `bond/src/bond/tools/schema/__init__.py`
- Create: `bond/src/bond/tools/schema/_protocols.py`
- Test: `bond/tests/unit/tools/schema/test_protocols.py`

**Step 1: Create directory structure**

```bash
mkdir -p bond/src/bond/tools/schema
mkdir -p bond/tests/unit/tools/schema
touch bond/tests/unit/tools/schema/__init__.py
```

**Step 2: Write the protocol test**

Create `bond/tests/unit/tools/schema/test_protocols.py`:

```python
"""Tests for schema lookup protocol."""

from typing import Protocol, runtime_checkable

import pytest

from bond.tools.schema._protocols import SchemaLookupProtocol


def test_protocol_is_runtime_checkable():
    """Protocol should be runtime checkable for isinstance."""
    assert hasattr(SchemaLookupProtocol, "__protocol_attrs__")


def test_mock_implements_protocol():
    """A mock class should satisfy the protocol."""

    class MockSchemaLookup:
        async def get_table_schema(self, table_name: str) -> dict | None:
            return None

        async def list_tables(self) -> list[str]:
            return []

        async def get_upstream(self, table_name: str) -> list[str]:
            return []

        async def get_downstream(self, table_name: str) -> list[str]:
            return []

    mock = MockSchemaLookup()
    assert isinstance(mock, SchemaLookupProtocol)
```

**Step 3: Run test to verify it fails**

Run: `uv run pytest bond/tests/unit/tools/schema/test_protocols.py -v`
Expected: FAIL with "No module named 'bond.tools.schema'"

**Step 4: Write the protocol**

Create `bond/src/bond/tools/schema/_protocols.py`:

```python
"""Protocol definitions for schema lookup tools.

This module defines the interface that schema lookup implementations
must satisfy. The protocol is runtime-checkable for flexibility.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SchemaLookupProtocol(Protocol):
    """Protocol for schema lookup operations.

    Implementations provide access to database schema information
    and lineage data for agent tools.
    """

    async def get_table_schema(self, table_name: str) -> dict[str, Any] | None:
        """Get schema for a specific table.

        Args:
            table_name: Name of the table (can be qualified like schema.table).

        Returns:
            Table schema as dict with columns, types, etc. or None if not found.
        """
        ...

    async def list_tables(self) -> list[str]:
        """List all available table names.

        Returns:
            List of table names (may be qualified).
        """
        ...

    async def get_upstream(self, table_name: str) -> list[str]:
        """Get upstream dependencies for a table.

        Args:
            table_name: Name of the table.

        Returns:
            List of upstream table names.
        """
        ...

    async def get_downstream(self, table_name: str) -> list[str]:
        """Get downstream dependencies for a table.

        Args:
            table_name: Name of the table.

        Returns:
            List of downstream table names.
        """
        ...
```

**Step 5: Create __init__.py**

Create `bond/src/bond/tools/schema/__init__.py`:

```python
"""Schema toolset for Bond agents.

Provides on-demand schema lookup for database tables and lineage.
"""

from bond.tools.schema._protocols import SchemaLookupProtocol

__all__ = [
    "SchemaLookupProtocol",
]
```

**Step 6: Run test to verify it passes**

Run: `uv run pytest bond/tests/unit/tools/schema/test_protocols.py -v`
Expected: PASS

**Step 7: Commit**

```bash
git add bond/src/bond/tools/schema/ bond/tests/unit/tools/schema/
git commit -m "feat(bond): add schema lookup protocol"
```

---

## Task 2: Create Pydantic Models for Tool Requests/Responses

**Files:**
- Create: `bond/src/bond/tools/schema/_models.py`
- Modify: `bond/src/bond/tools/schema/__init__.py`
- Test: `bond/tests/unit/tools/schema/test_models.py`

**Step 1: Write the model tests**

Create `bond/tests/unit/tools/schema/test_models.py`:

```python
"""Tests for schema tool models."""

import pytest
from pydantic import ValidationError

from bond.tools.schema._models import (
    GetTableSchemaRequest,
    ListTablesRequest,
    GetUpstreamRequest,
    GetDownstreamRequest,
    TableSchema,
    ColumnSchema,
)


class TestGetTableSchemaRequest:
    def test_creates_request(self):
        req = GetTableSchemaRequest(table_name="orders")
        assert req.table_name == "orders"

    def test_requires_table_name(self):
        with pytest.raises(ValidationError):
            GetTableSchemaRequest()


class TestListTablesRequest:
    def test_creates_request_with_defaults(self):
        req = ListTablesRequest()
        assert req.pattern is None

    def test_accepts_pattern(self):
        req = ListTablesRequest(pattern="order*")
        assert req.pattern == "order*"


class TestGetUpstreamRequest:
    def test_creates_request(self):
        req = GetUpstreamRequest(table_name="orders")
        assert req.table_name == "orders"


class TestGetDownstreamRequest:
    def test_creates_request(self):
        req = GetDownstreamRequest(table_name="orders")
        assert req.table_name == "orders"


class TestColumnSchema:
    def test_creates_column(self):
        col = ColumnSchema(
            name="id",
            data_type="integer",
            nullable=False,
        )
        assert col.name == "id"
        assert col.is_primary_key is False  # default

    def test_creates_column_with_all_fields(self):
        col = ColumnSchema(
            name="id",
            data_type="integer",
            native_type="BIGINT",
            nullable=False,
            is_primary_key=True,
            is_partition_key=False,
            description="Primary key",
        )
        assert col.is_primary_key is True
        assert col.native_type == "BIGINT"


class TestTableSchema:
    def test_creates_table(self):
        table = TableSchema(
            name="orders",
            columns=[
                ColumnSchema(name="id", data_type="integer", nullable=False),
            ],
        )
        assert table.name == "orders"
        assert len(table.columns) == 1

    def test_creates_table_with_qualified_name(self):
        table = TableSchema(
            name="orders",
            schema_name="public",
            catalog_name="main",
            columns=[],
        )
        assert table.qualified_name == "main.public.orders"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest bond/tests/unit/tools/schema/test_models.py -v`
Expected: FAIL with "cannot import name 'GetTableSchemaRequest'"

**Step 3: Write the models**

Create `bond/src/bond/tools/schema/_models.py`:

```python
"""Pydantic models for schema tools."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GetTableSchemaRequest(BaseModel):
    """Request to get schema for a specific table."""

    table_name: str = Field(..., description="Table name (can be qualified like schema.table)")


class ListTablesRequest(BaseModel):
    """Request to list available tables."""

    pattern: str | None = Field(None, description="Optional glob pattern to filter tables")


class GetUpstreamRequest(BaseModel):
    """Request to get upstream dependencies."""

    table_name: str = Field(..., description="Table name to get upstream for")


class GetDownstreamRequest(BaseModel):
    """Request to get downstream dependencies."""

    table_name: str = Field(..., description="Table name to get downstream for")


class ColumnSchema(BaseModel):
    """Schema information for a single column."""

    name: str
    data_type: str
    native_type: str | None = None
    nullable: bool = True
    is_primary_key: bool = False
    is_partition_key: bool = False
    description: str | None = None
    default_value: str | None = None


class TableSchema(BaseModel):
    """Schema information for a table."""

    name: str
    columns: list[ColumnSchema]
    schema_name: str | None = None
    catalog_name: str | None = None
    description: str | None = None

    @property
    def qualified_name(self) -> str:
        """Get fully qualified table name."""
        parts = []
        if self.catalog_name:
            parts.append(self.catalog_name)
        if self.schema_name:
            parts.append(self.schema_name)
        parts.append(self.name)
        return ".".join(parts)
```

**Step 4: Update __init__.py**

Modify `bond/src/bond/tools/schema/__init__.py`:

```python
"""Schema toolset for Bond agents.

Provides on-demand schema lookup for database tables and lineage.
"""

from bond.tools.schema._models import (
    ColumnSchema,
    GetDownstreamRequest,
    GetTableSchemaRequest,
    GetUpstreamRequest,
    ListTablesRequest,
    TableSchema,
)
from bond.tools.schema._protocols import SchemaLookupProtocol

__all__ = [
    # Protocol
    "SchemaLookupProtocol",
    # Models
    "GetTableSchemaRequest",
    "ListTablesRequest",
    "GetUpstreamRequest",
    "GetDownstreamRequest",
    "TableSchema",
    "ColumnSchema",
]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest bond/tests/unit/tools/schema/test_models.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add bond/src/bond/tools/schema/_models.py bond/src/bond/tools/schema/__init__.py bond/tests/unit/tools/schema/test_models.py
git commit -m "feat(bond): add schema tool pydantic models"
```

---

## Task 3: Create Tool Functions

**Files:**
- Create: `bond/src/bond/tools/schema/tools.py`
- Modify: `bond/src/bond/tools/schema/__init__.py`
- Test: `bond/tests/unit/tools/schema/test_tools.py`

**Step 1: Write the tool tests**

Create `bond/tests/unit/tools/schema/test_tools.py`:

```python
"""Tests for schema tool functions."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from bond.tools.schema._models import (
    GetDownstreamRequest,
    GetTableSchemaRequest,
    GetUpstreamRequest,
    ListTablesRequest,
)
from bond.tools.schema._protocols import SchemaLookupProtocol
from bond.tools.schema.tools import (
    get_table_schema,
    list_tables,
    get_upstream_tables,
    get_downstream_tables,
)


class MockSchemaLookup:
    """Test implementation of SchemaLookupProtocol."""

    def __init__(
        self,
        tables: dict[str, dict[str, Any]] | None = None,
        upstream: dict[str, list[str]] | None = None,
        downstream: dict[str, list[str]] | None = None,
    ):
        self.tables = tables or {}
        self.upstream = upstream or {}
        self.downstream = downstream or {}

    async def get_table_schema(self, table_name: str) -> dict[str, Any] | None:
        return self.tables.get(table_name)

    async def list_tables(self) -> list[str]:
        return list(self.tables.keys())

    async def get_upstream(self, table_name: str) -> list[str]:
        return self.upstream.get(table_name, [])

    async def get_downstream(self, table_name: str) -> list[str]:
        return self.downstream.get(table_name, [])


@pytest.fixture
def mock_ctx():
    """Create a mock RunContext with schema lookup deps."""
    ctx = MagicMock()
    ctx.deps = MockSchemaLookup(
        tables={
            "orders": {
                "name": "orders",
                "columns": [{"name": "id", "data_type": "integer"}],
            },
        },
        upstream={"orders": ["customers"]},
        downstream={"orders": ["order_items"]},
    )
    return ctx


@pytest.mark.asyncio
async def test_get_table_schema_returns_table(mock_ctx):
    request = GetTableSchemaRequest(table_name="orders")
    result = await get_table_schema(mock_ctx, request)
    assert result is not None
    assert result["name"] == "orders"


@pytest.mark.asyncio
async def test_get_table_schema_returns_none_for_missing(mock_ctx):
    request = GetTableSchemaRequest(table_name="nonexistent")
    result = await get_table_schema(mock_ctx, request)
    assert result is None


@pytest.mark.asyncio
async def test_list_tables_returns_names(mock_ctx):
    request = ListTablesRequest()
    result = await list_tables(mock_ctx, request)
    assert result == ["orders"]


@pytest.mark.asyncio
async def test_get_upstream_tables_returns_dependencies(mock_ctx):
    request = GetUpstreamRequest(table_name="orders")
    result = await get_upstream_tables(mock_ctx, request)
    assert result == ["customers"]


@pytest.mark.asyncio
async def test_get_downstream_tables_returns_dependencies(mock_ctx):
    request = GetDownstreamRequest(table_name="orders")
    result = await get_downstream_tables(mock_ctx, request)
    assert result == ["order_items"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest bond/tests/unit/tools/schema/test_tools.py -v`
Expected: FAIL with "cannot import name 'get_table_schema'"

**Step 3: Write the tool functions**

Create `bond/src/bond/tools/schema/tools.py`:

```python
"""Schema tools for PydanticAI agents.

This module provides agent-facing tool functions that use
RunContext to access schema lookup via dependency injection.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import Tool

from bond.tools.schema._models import (
    GetDownstreamRequest,
    GetTableSchemaRequest,
    GetUpstreamRequest,
    ListTablesRequest,
)
from bond.tools.schema._protocols import SchemaLookupProtocol


async def get_table_schema(
    ctx: RunContext[SchemaLookupProtocol],
    request: GetTableSchemaRequest,
) -> dict[str, Any] | None:
    """Get the full schema for a specific table.

    Agent Usage:
        Call this tool to get column details for a table you need to query:
        - Get join columns: "What columns does the customers table have?"
        - Check types: "What's the data type of the created_at column?"
        - Find keys: "Which columns are primary/partition keys?"

    Example:
        get_table_schema({"table_name": "customers"})

    Returns:
        Full table schema as JSON with columns, types, keys, etc.
        Returns None if table not found.
    """
    return await ctx.deps.get_table_schema(request.table_name)


async def list_tables(
    ctx: RunContext[SchemaLookupProtocol],
    request: ListTablesRequest,
) -> list[str]:
    """List all available tables in the database.

    Agent Usage:
        Call this tool to discover what tables exist:
        - Find tables: "What tables are available?"
        - Explore schema: "List all tables to understand the data model"

    Example:
        list_tables({})

    Returns:
        List of table names (may be qualified like schema.table).
    """
    return await ctx.deps.list_tables()


async def get_upstream_tables(
    ctx: RunContext[SchemaLookupProtocol],
    request: GetUpstreamRequest,
) -> list[str]:
    """Get tables that feed data into the specified table.

    Agent Usage:
        Call this tool to understand data lineage:
        - Find sources: "Where does the orders table get its data from?"
        - Trace issues: "What upstream tables might cause this anomaly?"

    Example:
        get_upstream_tables({"table_name": "orders"})

    Returns:
        List of upstream table names (data sources for this table).
    """
    return await ctx.deps.get_upstream(request.table_name)


async def get_downstream_tables(
    ctx: RunContext[SchemaLookupProtocol],
    request: GetDownstreamRequest,
) -> list[str]:
    """Get tables that consume data from the specified table.

    Agent Usage:
        Call this tool to understand data impact:
        - Find dependents: "What tables use data from orders?"
        - Assess impact: "What would be affected by this anomaly?"

    Example:
        get_downstream_tables({"table_name": "orders"})

    Returns:
        List of downstream table names (tables that depend on this one).
    """
    return await ctx.deps.get_downstream(request.table_name)


# Export as toolset for BondAgent
schema_toolset: list[Tool[SchemaLookupProtocol]] = [
    Tool(get_table_schema),
    Tool(list_tables),
    Tool(get_upstream_tables),
    Tool(get_downstream_tables),
]
```

**Step 4: Update __init__.py**

Modify `bond/src/bond/tools/schema/__init__.py`:

```python
"""Schema toolset for Bond agents.

Provides on-demand schema lookup for database tables and lineage.
"""

from bond.tools.schema._models import (
    ColumnSchema,
    GetDownstreamRequest,
    GetTableSchemaRequest,
    GetUpstreamRequest,
    ListTablesRequest,
    TableSchema,
)
from bond.tools.schema._protocols import SchemaLookupProtocol
from bond.tools.schema.tools import schema_toolset

__all__ = [
    # Protocol
    "SchemaLookupProtocol",
    # Models
    "GetTableSchemaRequest",
    "ListTablesRequest",
    "GetUpstreamRequest",
    "GetDownstreamRequest",
    "TableSchema",
    "ColumnSchema",
    # Toolset
    "schema_toolset",
]
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest bond/tests/unit/tools/schema/test_tools.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add bond/src/bond/tools/schema/tools.py bond/src/bond/tools/schema/__init__.py bond/tests/unit/tools/schema/test_tools.py
git commit -m "feat(bond): add schema tool functions"
```

---

## Task 4: Create Concrete Adapter in Dataing

**Files:**
- Create: `dataing/src/dataing/adapters/context/schema_lookup.py`
- Modify: `dataing/src/dataing/adapters/context/__init__.py`
- Test: `dataing/tests/unit/adapters/context/test_schema_lookup.py`

**Step 1: Write the adapter tests**

Create `dataing/tests/unit/adapters/context/test_schema_lookup.py`:

```python
"""Tests for SchemaLookupAdapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from bond.tools.schema import SchemaLookupProtocol
from dataing.adapters.context.schema_lookup import SchemaLookupAdapter
from dataing.adapters.datasource.types import (
    Catalog,
    Column,
    DataType,
    Schema,
    SchemaResponse,
    Table,
)


@pytest.fixture
def mock_schema_response():
    """Create a mock schema response."""
    return SchemaResponse(
        catalogs=[
            Catalog(
                name="main",
                schemas=[
                    Schema(
                        name="public",
                        tables=[
                            Table(
                                name="orders",
                                native_path="public.orders",
                                columns=[
                                    Column(
                                        name="id",
                                        data_type=DataType.INTEGER,
                                        nullable=False,
                                    ),
                                    Column(
                                        name="customer_id",
                                        data_type=DataType.INTEGER,
                                        nullable=False,
                                    ),
                                ],
                            ),
                            Table(
                                name="customers",
                                native_path="public.customers",
                                columns=[
                                    Column(
                                        name="id",
                                        data_type=DataType.INTEGER,
                                        nullable=False,
                                    ),
                                ],
                            ),
                        ],
                    )
                ],
            )
        ]
    )


@pytest.fixture
def mock_db_adapter(mock_schema_response):
    """Create a mock database adapter."""
    adapter = AsyncMock()
    adapter.get_schema.return_value = mock_schema_response
    return adapter


@pytest.fixture
def mock_lineage_adapter():
    """Create a mock lineage adapter."""
    adapter = AsyncMock()
    adapter.get_upstream.return_value = []
    adapter.get_downstream.return_value = []
    return adapter


def test_implements_protocol(mock_db_adapter):
    """SchemaLookupAdapter should implement SchemaLookupProtocol."""
    lookup = SchemaLookupAdapter(mock_db_adapter)
    assert isinstance(lookup, SchemaLookupProtocol)


@pytest.mark.asyncio
async def test_get_table_schema_returns_table(mock_db_adapter):
    lookup = SchemaLookupAdapter(mock_db_adapter)
    result = await lookup.get_table_schema("orders")

    assert result is not None
    assert result["name"] == "orders"
    assert len(result["columns"]) == 2


@pytest.mark.asyncio
async def test_get_table_schema_returns_none_for_missing(mock_db_adapter):
    lookup = SchemaLookupAdapter(mock_db_adapter)
    result = await lookup.get_table_schema("nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_get_table_schema_caches_schema(mock_db_adapter):
    lookup = SchemaLookupAdapter(mock_db_adapter)

    await lookup.get_table_schema("orders")
    await lookup.get_table_schema("customers")

    # Should only call get_schema once (cached)
    mock_db_adapter.get_schema.assert_called_once()


@pytest.mark.asyncio
async def test_list_tables_returns_all_names(mock_db_adapter):
    lookup = SchemaLookupAdapter(mock_db_adapter)
    result = await lookup.list_tables()

    assert "orders" in result or "public.orders" in result
    assert len(result) == 2


@pytest.mark.asyncio
async def test_get_upstream_without_lineage_returns_empty(mock_db_adapter):
    lookup = SchemaLookupAdapter(mock_db_adapter, lineage_adapter=None)
    result = await lookup.get_upstream("orders")

    assert result == []


@pytest.mark.asyncio
async def test_get_upstream_with_lineage(mock_db_adapter, mock_lineage_adapter):
    mock_lineage_adapter.get_upstream.return_value = [
        MagicMock(qualified_name="customers")
    ]
    lookup = SchemaLookupAdapter(mock_db_adapter, mock_lineage_adapter)
    result = await lookup.get_upstream("orders")

    assert result == ["customers"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest dataing/tests/unit/adapters/context/test_schema_lookup.py -v`
Expected: FAIL with "No module named 'dataing.adapters.context.schema_lookup'"

**Step 3: Write the adapter**

Create `dataing/src/dataing/adapters/context/schema_lookup.py`:

```python
"""Schema lookup adapter for agent tools.

Implements SchemaLookupProtocol from bond using existing
BaseAdapter and LineageAdapter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from dataing.adapters.datasource.types import SchemaResponse, Table
from dataing.adapters.lineage import DatasetId

if TYPE_CHECKING:
    from dataing.adapters.datasource.base import BaseAdapter
    from dataing.adapters.lineage import LineageAdapter

logger = structlog.get_logger()


class SchemaLookupAdapter:
    """Implements SchemaLookupProtocol using existing adapters.

    This adapter bridges the bond schema tools with dataing's
    database and lineage adapters. It caches schema discovery
    to avoid repeated queries.
    """

    def __init__(
        self,
        db_adapter: BaseAdapter,
        lineage_adapter: LineageAdapter | None = None,
    ) -> None:
        """Initialize the schema lookup adapter.

        Args:
            db_adapter: Connected database adapter for schema discovery.
            lineage_adapter: Optional lineage adapter for dependency info.
        """
        self.db_adapter = db_adapter
        self.lineage_adapter = lineage_adapter
        self._schema_cache: SchemaResponse | None = None

    async def _ensure_schema(self) -> SchemaResponse:
        """Ensure schema is loaded, fetching if needed."""
        if self._schema_cache is None:
            logger.info("fetching_schema")
            self._schema_cache = await self.db_adapter.get_schema()
            logger.info("schema_cached", table_count=self._count_tables())
        return self._schema_cache

    def _count_tables(self) -> int:
        """Count total tables in cached schema."""
        if self._schema_cache is None:
            return 0
        return sum(
            len(db_schema.tables)
            for catalog in self._schema_cache.catalogs
            for db_schema in catalog.schemas
        )

    def _get_all_tables(self, schema: SchemaResponse) -> list[Table]:
        """Extract all tables from nested schema structure."""
        tables = []
        for catalog in schema.catalogs:
            for db_schema in catalog.schemas:
                tables.extend(db_schema.tables)
        return tables

    def _find_table(self, schema: SchemaResponse, table_name: str) -> Table | None:
        """Find a table by name (qualified or unqualified)."""
        table_name_lower = table_name.lower()
        for table in self._get_all_tables(schema):
            if (
                table.name.lower() == table_name_lower
                or table.native_path.lower() == table_name_lower
            ):
                return table
        return None

    def _table_to_dict(self, table: Table) -> dict[str, Any]:
        """Convert Table to dict for JSON serialization."""
        return {
            "name": table.name,
            "native_path": table.native_path,
            "columns": [
                {
                    "name": col.name,
                    "data_type": col.data_type.value,
                    "native_type": col.native_type,
                    "nullable": col.nullable,
                    "is_primary_key": col.is_primary_key,
                    "is_partition_key": col.is_partition_key,
                    "description": col.description,
                    "default_value": col.default_value,
                }
                for col in table.columns
            ],
        }

    async def get_table_schema(self, table_name: str) -> dict[str, Any] | None:
        """Get schema for a specific table."""
        schema = await self._ensure_schema()
        table = self._find_table(schema, table_name)
        if table is None:
            return None
        return self._table_to_dict(table)

    async def list_tables(self) -> list[str]:
        """List all available table names."""
        schema = await self._ensure_schema()
        tables = self._get_all_tables(schema)
        return [t.native_path for t in tables]

    async def get_upstream(self, table_name: str) -> list[str]:
        """Get upstream dependencies for a table."""
        if self.lineage_adapter is None:
            return []

        try:
            dataset_id = DatasetId.from_urn(table_name)
            upstream = await self.lineage_adapter.get_upstream(dataset_id, depth=1)
            return [ds.qualified_name for ds in upstream]
        except Exception as e:
            logger.warning("get_upstream_failed", table=table_name, error=str(e))
            return []

    async def get_downstream(self, table_name: str) -> list[str]:
        """Get downstream dependencies for a table."""
        if self.lineage_adapter is None:
            return []

        try:
            dataset_id = DatasetId.from_urn(table_name)
            downstream = await self.lineage_adapter.get_downstream(dataset_id, depth=1)
            return [ds.qualified_name for ds in downstream]
        except Exception as e:
            logger.warning("get_downstream_failed", table=table_name, error=str(e))
            return []

    async def build_initial_context(self, target_table_name: str) -> dict[str, Any]:
        """Build initial context with target table + related names.

        This is the minimal context injected at investigation start.
        Agent can fetch more details on demand via tools.

        Args:
            target_table_name: Name of the table with the anomaly.

        Returns:
            Dict with target_table schema and related_tables names.
        """
        target_schema = await self.get_table_schema(target_table_name)
        upstream = await self.get_upstream(target_table_name)
        downstream = await self.get_downstream(target_table_name)

        return {
            "target_table": target_schema,
            "related_tables": upstream + downstream,
        }
```

**Step 4: Update __init__.py**

Modify `dataing/src/dataing/adapters/context/__init__.py` to add:

```python
from dataing.adapters.context.schema_lookup import SchemaLookupAdapter
```

And add to `__all__`:

```python
"SchemaLookupAdapter",
```

**Step 5: Run test to verify it passes**

Run: `uv run pytest dataing/tests/unit/adapters/context/test_schema_lookup.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add dataing/src/dataing/adapters/context/schema_lookup.py dataing/src/dataing/adapters/context/__init__.py dataing/tests/unit/adapters/context/test_schema_lookup.py
git commit -m "feat(dataing): add SchemaLookupAdapter implementing bond protocol"
```

---

## Task 5: Update ContextEngine to Use New Approach

**Files:**
- Modify: `dataing/src/dataing/adapters/context/engine.py`
- Modify: `dataing/src/dataing/adapters/context/schema_context.py`
- Test: `dataing/tests/unit/adapters/context/test_engine.py` (update existing)

**Step 1: Simplify SchemaContextBuilder**

Modify `dataing/src/dataing/adapters/context/schema_context.py`:

Remove `format_for_llm()` and `format_compact()` methods. Keep only:
- `build()` - for fetching schema
- `_get_all_tables()` - internal helper
- `get_table_info()` - for single table lookup
- `get_related_tables()` - for related table discovery

**Step 2: Update ContextEngine**

Modify `dataing/src/dataing/adapters/context/engine.py`:

Remove `schema_formatted` from `EnrichedContext`. The agent will use tools instead.

**Step 3: Run existing tests**

Run: `uv run pytest dataing/tests/unit/adapters/context/ -v`
Expected: Some tests may fail if they depend on removed methods

**Step 4: Fix failing tests**

Update any tests that depend on `format_for_llm()` or `schema_formatted`.

**Step 5: Commit**

```bash
git add dataing/src/dataing/adapters/context/
git commit -m "refactor(dataing): simplify ContextEngine for tool-based schema"
```

---

## Task 6: Run Full Test Suite

**Step 1: Run all bond tests**

Run: `uv run pytest bond/tests -v`
Expected: All PASS

**Step 2: Run all dataing context tests**

Run: `uv run pytest dataing/tests/unit/adapters/context/ -v`
Expected: All PASS

**Step 3: Run integration tests**

Run: `uv run pytest dataing/tests/integration/ -v -k context`
Expected: All PASS (or skip if not applicable)

**Step 4: Commit if any fixes needed**

```bash
git add -A
git commit -m "test: fix tests for schema toolset"
```

---

## Summary

After completing all tasks:

1. **bond/src/bond/tools/schema/** - New schema toolset with protocol, models, tools
2. **dataing/src/dataing/adapters/context/schema_lookup.py** - Concrete adapter
3. **Simplified ContextEngine** - No longer dumps full schema
4. **Full test coverage** - Unit tests for all components

The agent can now:
- Receive minimal initial context (target table + related names)
- Call `get_table_schema()` to fetch details on demand
- Use lineage tools to explore data dependencies
