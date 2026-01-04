# Context Module Cleanup Plan (Pre-Launch)

## Overview

Since we're pre-launch, we can do a clean replacement of the old adapter layer with the new unified system. No backward compatibility needed.

## What to DELETE

### Files to Remove Completely

```
backend/src/dataing/adapters/
├── db/
│   ├── duckdb.py      # DELETE - replaced by datasource/sql/duckdb.py
│   ├── postgres.py    # DELETE - replaced by datasource/sql/postgres.py
│   ├── trino.py       # DELETE - replaced by datasource/sql/trino.py
│   └── mock.py        # DELETE - use registry-based mocking instead
│
└── context/
    └── database_context.py  # DELETE - replaced by AdapterRegistry
```

### Files to KEEP

```
backend/src/dataing/adapters/
├── db/
│   └── app_db.py      # KEEP - this is the app's own metadata DB, not a data source adapter
│
└── context/
    ├── schema_context.py       # KEEP + UPDATE - LLM formatting logic
    ├── engine.py               # KEEP + UPDATE - investigation orchestration
    ├── anomaly_context.py      # KEEP - unique functionality
    ├── correlation_context.py  # KEEP - unique functionality
    ├── lineage.py              # KEEP - OpenLineage integration
    └── query_context.py        # KEEP - query tracking
```

## Required Updates

### 1. Update `schema_context.py`

Replace `SchemaContext` usage with `SchemaResponse`:

```python
# Before
from dataing.core.domain_types import SchemaContext, TableSchema

class SchemaContextBuilder:
    def build(self, adapter) -> SchemaContext:
        ...

# After
from dataing.adapters.datasource.types import SchemaResponse

class SchemaContextBuilder:
    def build(self, adapter) -> SchemaResponse:
        return await adapter.get_schema()

    def format_for_llm(self, schema: SchemaResponse) -> str:
        """Format schema as markdown for LLM prompts."""
        lines = []
        for catalog in schema.catalogs:
            for db_schema in catalog.schemas:
                for table in db_schema.tables:
                    lines.append(f"## {table.native_path}")
                    lines.append("")
                    lines.append("| Column | Type | Nullable |")
                    lines.append("|--------|------|----------|")
                    for col in table.columns:
                        nullable = "Yes" if col.nullable else "No"
                        lines.append(f"| {col.name} | {col.data_type.value} | {nullable} |")
                    lines.append("")
        return "\n".join(lines)
```

### 2. Update `engine.py` (ContextEngine)

Replace `DatabaseContext` with `AdapterRegistry`:

```python
# Before
from dataing.adapters.context.database_context import DatabaseContext

class ContextEngine:
    def __init__(self, database_context: DatabaseContext):
        self._db_context = database_context

    async def get_adapter(self, tenant_id: str, ds_id: str):
        return await self._db_context.resolve_adapter(tenant_id, ds_id)

# After
from dataing.adapters.datasource import AdapterRegistry
from dataing.adapters.db.app_db import AppDatabase

class ContextEngine:
    def __init__(self, app_db: AppDatabase):
        self._app_db = app_db

    async def get_adapter(self, tenant_id: str, ds_id: str):
        # Get data source config from app_db
        ds_config = await self._app_db.get_datasource(tenant_id, ds_id)

        # Create adapter from registry
        adapter = AdapterRegistry.create(ds_config["type"], ds_config["config"])
        await adapter.connect()
        return adapter
```

### 3. Update API Dependencies

Update `entrypoints/api/deps.py`:

```python
# Before
from dataing.adapters.context.database_context import DatabaseContext

def get_database_context() -> DatabaseContext:
    return DatabaseContext(app_db=get_app_db())

# After
from dataing.adapters.datasource import AdapterRegistry
from dataing.adapters.datasource.base import BaseAdapter

async def get_adapter(source_type: str, config: dict) -> BaseAdapter:
    adapter = AdapterRegistry.create(source_type, config)
    await adapter.connect()
    return adapter
```

## Implementation Steps

### Step 1: Delete Old Adapters
```bash
rm backend/src/dataing/adapters/db/duckdb.py
rm backend/src/dataing/adapters/db/postgres.py
rm backend/src/dataing/adapters/db/trino.py
rm backend/src/dataing/adapters/db/mock.py
rm backend/src/dataing/adapters/context/database_context.py
```

### Step 2: Update schema_context.py
- Change imports to use `SchemaResponse`
- Update `format_for_llm()` to handle nested catalog/schema/table structure
- Remove any `SchemaContext` references

### Step 3: Update engine.py
- Change imports to use `AdapterRegistry`
- Update adapter creation to use registry pattern
- Remove `DatabaseContext` dependency

### Step 4: Update API Routes
- Update any routes that use `DatabaseContext`
- Use `AdapterRegistry` directly for adapter creation

### Step 5: Update Tests
- Remove tests for deleted files
- Update tests for modified files
- All adapter tests should use `AdapterRegistry`

### Step 6: Clean Up Imports
- Remove unused imports from `__init__.py` files
- Update type hints in `core/interfaces.py` if needed

## File-by-File Checklist

| File | Action | Notes |
|------|--------|-------|
| `db/duckdb.py` | DELETE | Replaced by `datasource/sql/duckdb.py` |
| `db/postgres.py` | DELETE | Replaced by `datasource/sql/postgres.py` |
| `db/trino.py` | DELETE | Replaced by `datasource/sql/trino.py` |
| `db/mock.py` | DELETE | Use mock adapters in tests |
| `db/app_db.py` | KEEP | App metadata DB |
| `context/database_context.py` | DELETE | Use `AdapterRegistry` |
| `context/schema_context.py` | UPDATE | Use `SchemaResponse` |
| `context/engine.py` | UPDATE | Use `AdapterRegistry` |
| `context/anomaly_context.py` | KEEP | No changes needed |
| `context/correlation_context.py` | KEEP | No changes needed |
| `context/lineage.py` | KEEP | No changes needed |
| `context/query_context.py` | KEEP | No changes needed |

## Summary

Since we're pre-launch:
1. **Delete** the old `adapters/db/` layer (except `app_db.py`)
2. **Delete** `database_context.py` - replaced by `AdapterRegistry`
3. **Update** `schema_context.py` and `engine.py` to use new types
4. **Keep** all other context modules (anomaly, correlation, lineage, query)

The new `adapters/datasource/` layer is the single source of truth for all data source operations.
