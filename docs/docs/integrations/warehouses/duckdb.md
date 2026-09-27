# DuckDB Integration

Connect dataing to DuckDB for local development, testing, and small-scale investigations.

---

## Overview

DuckDB is perfect for:

- **Local development** - No cloud credentials needed
- **Testing** - Fast, in-process database
- **Small datasets** - Files up to a few GB
- **Demo scenarios** - Pre-built anomaly fixtures

---

## Prerequisites

- Python 3.11+
- `duckdb` package (installed with dataing)

No external services or credentials required!

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=duckdb
    export DATAING_DUCKDB_PATH=./data/analytics.duckdb
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.sql.duckdb import DuckDBAdapter

    # File-based database
    adapter = DuckDBAdapter(path="./data/analytics.duckdb")

    # In-memory database
    adapter = DuckDBAdapter(path=":memory:")
    ```

=== "With Parquet Files"

    ```python
    # DuckDB can query Parquet files directly
    adapter = DuckDBAdapter(path=":memory:")

    # Then use SQL to query files
    # SELECT * FROM 'data/*.parquet' LIMIT 100
    ```

### Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `path` | Yes | Path to DuckDB file or `:memory:` |

### Allowed Directory

DuckDB sources read the disk of the hosts that run the dataing API and worker, so the
operator decides where they may look. Set `DATAING_LOCAL_DATA_ROOT` on both to the
directory that holds the data. A source's `path` must resolve inside it, following
symlinks, and a relative `path` is taken relative to it. While the variable is unset,
the server refuses DuckDB and local file sources, `:memory:` ones included.

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Discovery | :material-check-circle:{ .green } | Full table/column metadata |
| Column Statistics | :material-check-circle:{ .green } | Via `SUMMARIZE` |
| Query Execution | :material-check-circle:{ .green } | SELECT only |
| Parquet Files | :material-check-circle:{ .green } | Direct file queries |
| CSV Files | :material-check-circle:{ .green } | Direct file queries |
| JSON Files | :material-check-circle:{ .green } | Direct file queries |

---

## Demo Scenarios

The dataing demo uses DuckDB with pre-built anomaly scenarios:

```bash
# Run the demo
just demo

# This creates demo.duckdb with these scenarios:
# - null_spike: NULL user_id from mobile app bug
# - volume_drop: Weekend traffic drop
# - schema_drift: Column rename
# - duplicates: Duplicate orders from retry logic
# - late_arriving: ETL delay
# - orphaned_records: FK violations
```

### Loading Demo Data

```python
import duckdb

con = duckdb.connect("demo.duckdb")

# Load from Parquet files
con.execute("""
    CREATE TABLE orders AS
    SELECT * FROM 'demo/fixtures/null_spike/orders.parquet'
""")

# Check the data
con.execute("SELECT COUNT(*) FROM orders").fetchone()
```

---

## Use Cases

### Local Development

```python
# Create a test database
import duckdb

con = duckdb.connect("test.duckdb")
con.execute("""
    CREATE TABLE orders (
        id UUID PRIMARY KEY,
        user_id UUID,
        total DECIMAL(10, 2),
        created_at TIMESTAMP
    )
""")

# Insert test data
con.execute("""
    INSERT INTO orders VALUES
    (gen_random_uuid(), NULL, 99.99, NOW()),
    (gen_random_uuid(), gen_random_uuid(), 149.99, NOW())
""")
```

### Testing Investigations

```python
import asyncio
from dataing.core.investigation.service import InvestigationService
from dataing.core.domain_types import AnomalyAlert

async def test_investigation():
    alert = AnomalyAlert(
        table="orders",
        column="user_id",
        metric="null_rate",
        anomaly_type="spike",
        description="NULL rate at 50%"
    )

    service = InvestigationService()
    result = await service.investigate(alert)

    assert result.synthesis.confidence > 0.5

asyncio.run(test_investigation())
```

---

## Limitations

DuckDB is not suitable for:

- **Large datasets** (>10 GB) - Use Snowflake/BigQuery
- **Production workloads** - Single-user, in-process
- **Concurrent access** - Limited write concurrency

---

## Learn More

<div class="grid cards" markdown>

-   :material-snowflake: **[Snowflake Integration](snowflake.md)**

    ---

    Connect to Snowflake

-   :material-google-cloud: **[BigQuery Integration](bigquery.md)**

    ---

    Connect to Google BigQuery

-   :material-rocket-launch: **[Quickstart](../../quickstart.md)**

    ---

    Get started in 5 minutes

</div>
