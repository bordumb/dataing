# OpenLineage Integration

Connect dataing to OpenLineage/Marquez for runtime lineage from Spark, Airflow, dbt, and more.

---

## What It Enables

With OpenLineage, dataing can:

- **Capture runtime lineage** - Track actual data flows during job execution
- **Aggregate multiple sources** - Combine lineage from Spark, Airflow, dbt in one place
- **Track job runs** - See execution history with timing and status
- **Access column-level lineage** - Understand column-level data flows

---

## Prerequisites

- Marquez server running (reference OpenLineage backend)
- OpenLineage integrations configured for your tools

### Marquez Quick Start

```bash
# Start Marquez with Docker
docker run -d \
  -p 5000:5000 \
  -p 5001:5001 \
  marquezproject/marquez:latest
```

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_LINEAGE_PROVIDER=openlineage
    export DATAING_OPENLINEAGE_URL=http://localhost:5000
    export DATAING_OPENLINEAGE_NAMESPACE=default
    # Optional: API key for secured deployments
    export DATAING_OPENLINEAGE_API_KEY=your-key
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.lineage.adapters.openlineage import OpenLineageAdapter

    adapter = OpenLineageAdapter({
        "base_url": "http://localhost:5000",
        "namespace": "default",
        "api_key": "optional-key",  # pragma: allowlist secret
    })
    ```

### Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `base_url` | Yes | Marquez API URL |
| `namespace` | Yes | Default namespace for queries |
| `api_key` | No | API key for authentication |

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Upstream Lineage | :material-check-circle:{ .green } | Full graph traversal |
| Downstream Lineage | :material-check-circle:{ .green } | Full graph traversal |
| Column Lineage | :material-check-circle:{ .green } | When emitted by source |
| Job Runs | :material-check-circle:{ .green } | Complete run history |
| Freshness Tracking | :material-check-circle:{ .green } | Last update times |
| Search | :material-check-circle:{ .green } | Dataset search |
| Tags | :material-check-circle:{ .green } | Dataset tags |
| Real-time Updates | :material-check-circle:{ .green } | Event-driven |

---

## How It Works

OpenLineage is an open standard for lineage metadata collection:

```
[Spark Job]    →  OpenLineage Events  →  [Marquez]  →  [dataing]
[Airflow DAG]  →  OpenLineage Events  →  [Marquez]  →  [dataing]
[dbt run]      →  OpenLineage Events  →  [Marquez]  →  [dataing]
```

### Configuring Sources

#### Spark

```python
spark = SparkSession.builder \
    .config("spark.openlineage.transport.type", "http") \
    .config("spark.openlineage.transport.url", "http://marquez:5000/api/v1/lineage") \
    .config("spark.openlineage.namespace", "spark") \
    .getOrCreate()
```

#### Airflow

```bash
pip install openlineage-airflow

# In airflow.cfg
[openlineage]
transport = {"type": "http", "url": "http://marquez:5000/api/v1/lineage"}
namespace = airflow
```

#### dbt

```bash
pip install openlineage-dbt

# Run with lineage
dbt run && dbt-ol
```

---

## Integration Points

### During Context Gathering

When investigating an anomaly, dataing queries Marquez:

```python
# Example lineage context
{
    "dataset": "orders",
    "namespace": "warehouse",
    "upstream": [
        {"name": "raw_checkout_events", "source": "spark"},
        {"name": "raw_users", "source": "airflow"},
    ],
    "downstream": [
        {"name": "daily_revenue", "source": "dbt"},
    ],
    "producing_job": "etl_orders",
    "last_run_status": "COMPLETED",
    "last_updated": "2024-01-15T10:30:00Z",
}
```

### Column-Level Lineage

When available, OpenLineage provides column-level tracking:

```python
# Column lineage context
{
    "column": "user_id",
    "source_columns": [
        {"dataset": "raw_users", "column": "id"},
        {"dataset": "raw_checkout", "column": "customer_id"},
    ],
    "transformation": "COALESCE(u.id, c.customer_id)",
}
```

---

## Marquez API

dataing uses the Marquez REST API:

```bash
# Get dataset
curl http://localhost:5000/api/v1/namespaces/default/datasets/orders

# Get lineage graph
curl "http://localhost:5000/api/v1/lineage?nodeId=dataset:default:orders&depth=2"

# Search datasets
curl "http://localhost:5000/api/v1/search?q=orders&filter=dataset"
```

---

## Troubleshooting

### "No lineage data"

Verify events are being received:

```bash
# Check Marquez API
curl http://localhost:5000/api/v1/namespaces

# Check for datasets
curl http://localhost:5000/api/v1/namespaces/default/datasets
```

### "Namespace not found"

Ensure your namespace matches:

```bash
# List all namespaces
curl http://localhost:5000/api/v1/namespaces

# Use correct namespace in dataing config
export DATAING_OPENLINEAGE_NAMESPACE=your-namespace
```

### "Incomplete lineage"

OpenLineage quality depends on source integrations:
- Ensure all jobs emit OpenLineage events
- Check that jobs complete successfully
- Verify events include input/output datasets

---

## Learn More

<div class="grid cards" markdown>

-   :material-database-cog: **[dbt Integration](dbt.md)**

    ---

    Model-based lineage from dbt

-   :material-airplane: **[Airflow Integration](airflow.md)**

    ---

    DAG-based lineage from Airflow

-   :material-web: **[OpenLineage Docs](https://openlineage.io)**

    ---

    Official OpenLineage documentation

</div>
