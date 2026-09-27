# SQLite Integration

Connect dataing to SQLite databases for local development, testing, and file-based data investigations.

---

## Overview

SQLite is ideal for:

- **Local development** - Test dataing without cloud infrastructure
- **Demo environments** - Quick setup with sample data
- **Embedded analytics** - Investigate data in application databases
- **File-based data** - Query exported or archived data

---

## Prerequisites

- SQLite database file (.sqlite, .db, .sqlite3)
- Read access to the database file

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=sqlite
    export DATAING_SQLITE_PATH=/path/to/database.sqlite
    export DATAING_SQLITE_READ_ONLY=true
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.sql.sqlite import SQLiteAdapter

    adapter = SQLiteAdapter({
        "path": "/path/to/database.sqlite",
        "read_only": True,  # Recommended for investigations
    })
    ```

### Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `path` | Yes | - | Path to the SQLite file, inside `DATAING_LOCAL_DATA_ROOT` |
| `read_only` | No | true | Open in read-only mode |

### Allowed Directory

SQLite sources read the disk of the hosts that run the dataing API and worker, so the
operator decides where they may look. Set `DATAING_LOCAL_DATA_ROOT` on both to the
directory that holds the databases. A source's `path` must resolve inside it, following
symlinks, and a relative `path` is taken relative to it. `file:` URIs are refused, and
queries cannot `ATTACH` other database files. While the variable is unset, the server
refuses SQLite sources, `:memory:` ones included.

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Discovery | :material-check-circle:{ .green } | All tables and views |
| Column Statistics | :material-check-circle:{ .green } | Via SQL aggregates |
| Query Execution | :material-check-circle:{ .green } | SELECT only |
| Row Sampling | :material-check-circle:{ .green } | ORDER BY RANDOM() |
| Views | :material-check-circle:{ .green } | Included |
| Virtual Tables | :material-check-circle:{ .green } | FTS, R-Tree, etc. |

---

## Read-Only Mode

For investigations, read-only mode is recommended:

```python
# Explicit read-only
adapter = SQLiteAdapter({
    "path": "/path/to/production.sqlite",
    "read_only": True,
})
```

Benefits:
- Prevents accidental writes during investigations
- Allows multiple concurrent readers
- Works with read-only filesystem mounts

---

## In-Memory Databases

For testing, you can use in-memory databases:

```python
import sqlite3

# Create in-memory database
conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE orders (id INTEGER, amount REAL)")
conn.execute("INSERT INTO orders VALUES (1, 99.99)")

# Note: dataing adapter needs a file path, so for
# in-memory testing, save to a temp file first
```

---

## Demo Setup

Quick setup for testing dataing:

```python
import sqlite3
from pathlib import Path

# Create demo database
db_path = Path("demo.sqlite")
conn = sqlite3.connect(db_path)

# Create sample tables
conn.executescript("""
    CREATE TABLE orders (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        amount REAL,
        status TEXT,
        created_at TEXT
    );

    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        email TEXT,
        name TEXT
    );

    -- Insert sample data with anomalies
    INSERT INTO orders VALUES
        (1, 1, 99.99, 'completed', '2024-01-15'),
        (2, NULL, 149.99, 'completed', '2024-01-15'),  -- NULL user_id
        (3, 2, 0.00, 'completed', '2024-01-15'),        -- Zero amount
        (4, 999, 49.99, 'completed', '2024-01-15');     -- Orphan reference
""")
conn.commit()
conn.close()

# Connect with dataing
from dataing.adapters.datasource.sql.sqlite import SQLiteAdapter

adapter = SQLiteAdapter({"path": str(db_path)})
await adapter.connect()
```

---

## Schema Structure

SQLite has a simplified schema model:

- **Catalog**: `default` (SQLite has no catalog concept)
- **Schema**: `main` (the primary database)
- **Tables**: All user tables and views

dataing maps this to:

```
default (catalog)
└── main (schema)
    ├── orders (table)
    ├── users (table)
    └── order_summary (view)
```

---

## Query Execution

dataing uses standard SQL with SQLite-specific handling:

```sql
-- Column statistics (SQLite-compatible)
SELECT
    COUNT(*) as total_count,
    COUNT("user_id") as non_null_count,
    COUNT(DISTINCT "user_id") as distinct_count,
    MIN("user_id") as min_value,
    MAX("user_id") as max_value
FROM "orders";

-- Random sampling
SELECT * FROM orders ORDER BY RANDOM() LIMIT 100;
```

---

## Troubleshooting

### "Database file not found"

Verify the path exists:

```bash
ls -la /path/to/database.sqlite
```

### "Database is locked"

SQLite only allows one writer at a time:

- Use read-only mode: `"read_only": True`
- Close other applications accessing the database
- Use WAL mode for better concurrency

### "Unable to open database"

Check file permissions:

```bash
# Check permissions
ls -la database.sqlite

# Ensure read permission
chmod 644 database.sqlite
```

### "Corrupt database"

Run integrity check:

```bash
sqlite3 database.sqlite "PRAGMA integrity_check;"
```

---

## Learn More

<div class="grid cards" markdown>

-   :material-duck: **[DuckDB Integration](duckdb.md)**

    ---

    Analytical queries on files

-   :material-database: **[PostgreSQL Integration](postgres.md)**

    ---

    Production database integration

-   :material-hexagon-outline: **[Architecture](../../architecture/overview.md)**

    ---

    System overview and design

</div>
