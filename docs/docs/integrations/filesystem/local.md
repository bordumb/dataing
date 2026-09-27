# Local Files Integration

Query Parquet, CSV, and JSON files from your local filesystem using SQL.

---

## Overview

Local file integration enables:

- **Development and testing** - Quick setup without cloud infrastructure
- **Demo environments** - Sample data for demonstrations
- **Exported data** - Investigate exported/archived datasets
- **Local analytics** - Ad-hoc analysis on downloaded files

---

## Prerequisites

- Data files in supported formats (Parquet, CSV, JSON)
- Read access to the file directory

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=local_file
    export DATAING_LOCAL_PATH=/path/to/data
    export DATAING_LOCAL_RECURSIVE=false
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.filesystem.local import LocalFileAdapter

    adapter = LocalFileAdapter({
        "path": "/path/to/data",
        "recursive": False,
        "file_format": "auto",
    })
    ```

### Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `path` | Yes | - | Directory containing data files, inside `DATAING_LOCAL_DATA_ROOT` |
| `recursive` | No | false | Include subdirectories |
| `file_format` | No | auto | Default file format |

### Allowed Directory

Local file sources read the disk of the hosts that run the dataing API and worker, so
the operator decides where they may look. Set `DATAING_LOCAL_DATA_ROOT` on both to the
directory that holds the data. A source's `path` must resolve inside it, following
symlinks, and a relative `path` is taken relative to it. While the variable is unset,
the server refuses local file and DuckDB sources.

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Discovery | :material-check-circle:{ .green } | Per-file inference |
| SQL Queries | :material-check-circle:{ .green } | Via DuckDB |
| File Listing | :material-check-circle:{ .green } | With glob patterns |
| Parquet | :material-check-circle:{ .green } | Full support |
| CSV | :material-check-circle:{ .green } | Auto-header detection |
| JSON/JSONL | :material-check-circle:{ .green } | Line-delimited JSON |

---

## Querying Files

### Single File Query

```python
# Query a specific file
result = await adapter.execute_query("""
    SELECT *
    FROM read_parquet('/path/to/data/orders.parquet')
    LIMIT 100
""")
```

### Multiple Files

```python
# Query all Parquet files in directory
result = await adapter.execute_query("""
    SELECT *
    FROM read_parquet('/path/to/data/*.parquet')
    WHERE created_at >= '2024-01-01'
""")
```

### Recursive Query

```python
# Query files in subdirectories
result = await adapter.execute_query("""
    SELECT *
    FROM read_parquet('/path/to/data/**/*.parquet')
""")
```

---

## File Formats

### Parquet

```python
# Read Parquet (recommended for large files)
result = await adapter.execute_query("""
    SELECT *
    FROM read_parquet('/data/orders.parquet')
""")
```

### CSV

```python
# Auto-detect CSV settings
result = await adapter.execute_query("""
    SELECT *
    FROM read_csv_auto('/data/orders.csv')
""")

# Explicit CSV options
result = await adapter.execute_query("""
    SELECT *
    FROM read_csv('/data/orders.csv',
        header=true,
        delimiter=',',
        quote='"',
        escape='"'
    )
""")
```

### JSON

```python
# Read JSONL (line-delimited JSON)
result = await adapter.execute_query("""
    SELECT *
    FROM read_json_auto('/data/events.jsonl')
""")

# Read regular JSON array
result = await adapter.execute_query("""
    SELECT *
    FROM read_json('/data/events.json', array=true)
""")
```

---

## Demo Setup

Quick setup for testing dataing:

```python
import pandas as pd
from pathlib import Path

# Create demo data directory
data_dir = Path("./demo_data")
data_dir.mkdir(exist_ok=True)

# Create sample orders
orders = pd.DataFrame({
    "order_id": range(1, 101),
    "user_id": [None if i % 20 == 0 else f"user_{i % 10}" for i in range(100)],
    "amount": [99.99 if i % 5 == 0 else 49.99 for i in range(100)],
    "status": ["completed", "pending", "failed"][i % 3] for i in range(100)],
    "created_at": pd.date_range("2024-01-01", periods=100, freq="H"),
})

# Save as Parquet
orders.to_parquet(data_dir / "orders.parquet", index=False)

# Connect with dataing
from dataing.adapters.datasource.filesystem.local import LocalFileAdapter

adapter = LocalFileAdapter({"path": str(data_dir)})
await adapter.connect()

# Query the data
result = await adapter.execute_query("""
    SELECT status, COUNT(*), AVG(amount)
    FROM read_parquet('./demo_data/orders.parquet')
    GROUP BY status
""")
```

---

## Schema Discovery

```python
# List files in directory
files = await adapter.list_files(pattern="*.parquet")

for f in files:
    print(f"{f.name}: {f.size_bytes} bytes")

# Infer schema for a file
table = await adapter.infer_schema("/path/to/orders.parquet")

for col in table.columns:
    print(f"{col.name}: {col.data_type}")

# Get full schema
schema = await adapter.get_schema()
```

---

## Investigation Use Cases

### Data Quality Analysis

```python
result = await adapter.execute_query("""
    SELECT
        date_trunc('day', created_at) as day,
        COUNT(*) as total,
        SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as null_count,
        COUNT(DISTINCT user_id) as unique_users
    FROM read_parquet('/data/events/*.parquet')
    GROUP BY 1
    ORDER BY 1
""")
```

### File Comparison

```python
# Compare schemas across files
files = await adapter.list_files(pattern="*.parquet")

schemas = {}
for f in files:
    table = await adapter.infer_schema(f.path)
    schemas[f.name] = set(col.name for col in table.columns)

# Find schema differences
for name, cols in schemas.items():
    diff = all_columns - cols
    if diff:
        print(f"{name} missing: {diff}")
```

### Cross-File Joins

```python
result = await adapter.execute_query("""
    SELECT o.*, u.name, u.email
    FROM read_parquet('/data/orders.parquet') o
    LEFT JOIN read_csv_auto('/data/users.csv') u
        ON o.user_id = u.id
    WHERE o.status = 'completed'
""")
```

---

## Troubleshooting

### "File not found"

Verify the path exists:

```bash
ls -la /path/to/data/
```

### "Permission denied"

Check file permissions:

```bash
chmod 644 /path/to/data/*.parquet
```

### "Invalid file format"

Ensure format matches extension:

```python
# Force specific format
result = await adapter.read_file(
    "/data/file.dat",
    file_format="parquet",
)
```

### "Out of memory"

For large files, use sampling:

```python
result = await adapter.execute_query("""
    SELECT *
    FROM read_parquet('/data/large_file.parquet')
    USING SAMPLE 10%
""")
```

---

## Learn More

<div class="grid cards" markdown>

-   :material-aws: **[S3 Integration](s3.md)**

    ---

    Connect to Amazon S3

-   :material-google-cloud: **[GCS Integration](gcs.md)**

    ---

    Connect to Google Cloud Storage

-   :material-harddisk: **[HDFS Integration](hdfs.md)**

    ---

    Connect to Hadoop HDFS

</div>
