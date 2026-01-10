# SQLite Adapter Design

**Date**: 2026-01-10
**Status**: Ready for implementation

## Overview

Add SQLite as a data source adapter for local/demo databases and file-based investigations.

## Use Cases

1. **Local/demo data source** - Users connect to SQLite databases for testing or small-scale investigations
2. **File-based data import** - Users query `.sqlite` or `.db` files they have locally

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Connection config | File path + URI support | Flexibility for advanced options like `?mode=ro` |
| Schema handling | Single flat namespace | SQLite has no schemas; keeps UX honest |
| Python library | Built-in `sqlite3` | No extra dependency needed |
| Default mode | Read-only | Safety for investigations |

## Configuration Schema

```python
SQLITE_CONFIG_SCHEMA = ConfigSchema(
    field_groups=[
        FieldGroup(id="connection", label="Connection", collapsed_by_default=False),
    ],
    fields=[
        ConfigField(
            name="path",
            label="Database Path",
            type="string",
            required=True,
            group="connection",
            placeholder="/path/to/database.sqlite",
            description="Path to SQLite file, or file: URI (e.g., file:db.sqlite?mode=ro)",
        ),
        ConfigField(
            name="read_only",
            label="Read Only",
            type="boolean",
            required=False,
            group="connection",
            default_value=True,
            description="Open database in read-only mode (recommended for investigations)",
        ),
    ],
)
```

## Capabilities

```python
SQLITE_CAPABILITIES = AdapterCapabilities(
    supports_sql=True,
    supports_sampling=True,
    supports_row_count=True,
    supports_column_stats=True,
    supports_preview=True,
    supports_schema_discovery=True,
    max_query_rows=10000,
    query_languages=[QueryLanguage.SQL],
)
```

## Implementation

### Connection

```python
async def connect(self) -> None:
    path = self.config.get("path", "")
    read_only = self.config.get("read_only", True)

    # Handle file: URI or plain path
    if path.startswith("file:"):
        uri = path
    else:
        uri = f"file:{path}{'?mode=ro' if read_only else ''}"

    self._conn = sqlite3.connect(uri, uri=True)
    self._conn.row_factory = sqlite3.Row
```

### Schema Discovery

```python
async def get_schemas(self, filter: SchemaFilter | None = None) -> SchemaResponse:
    cursor = self._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    tables = []
    for row in cursor:
        tables.append(TableInfo(
            name=row["name"],
            schema=None,
            type="table",
        ))
    return SchemaResponse(tables=tables, schemas=[])

async def get_columns(self, table: str, schema: str | None = None) -> list[ColumnInfo]:
    cursor = self._conn.execute(f"PRAGMA table_info('{table}')")
    columns = []
    for row in cursor:
        columns.append(ColumnInfo(
            name=row["name"],
            data_type=normalize_type(row["type"], "sqlite"),
            nullable=not row["notnull"],
            primary_key=bool(row["pk"]),
        ))
    return columns
```

### Query Execution

```python
async def execute_query(
    self,
    query: str,
    limit: int | None = None,
    timeout: float | None = None,
) -> QueryResult:
    start_time = time.time()

    if limit and "LIMIT" not in query.upper():
        query = f"{query} LIMIT {limit}"

    try:
        cursor = self._conn.execute(query)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description] if cursor.description else []

        return QueryResult(
            columns=columns,
            rows=[dict(row) for row in rows],
            row_count=len(rows),
            execution_time=time.time() - start_time,
        )
    except sqlite3.OperationalError as e:
        raise QuerySyntaxError(str(e)) from e

async def get_row_count(self, table: str, schema: str | None = None) -> int:
    cursor = self._conn.execute(f"SELECT COUNT(*) FROM '{table}'")
    return cursor.fetchone()[0]
```

## Files to Modify

| File | Action |
|------|--------|
| `dataing/src/dataing/adapters/datasource/sql/sqlite.py` | Create (~150 lines) |
| `dataing/src/dataing/adapters/datasource/types.py` | Add `SQLITE` to `SourceType` enum |
| `dataing/src/dataing/adapters/datasource/sql/__init__.py` | Export `SQLiteAdapter` |
| `dataing/src/dataing/adapters/datasource/type_mapping.py` | Add SQLite type mappings |

## SQLite Type Mappings

| SQLite Type | Normalized Type |
|-------------|-----------------|
| `INTEGER` | `integer` |
| `REAL` | `float` |
| `TEXT` | `string` |
| `BLOB` | `binary` |
| `NUMERIC` | `decimal` |
| `BOOLEAN` | `boolean` |
| `DATE` | `date` |
| `DATETIME` | `timestamp` |

## Testing

- Unit tests for connection (file path and URI modes)
- Unit tests for schema discovery (tables, columns)
- Unit tests for query execution
- Integration test with sample `.sqlite` file
