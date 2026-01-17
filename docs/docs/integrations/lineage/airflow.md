# Airflow Integration

Connect dataing to Apache Airflow for lineage context from DAGs and data-driven scheduling.

---

## What It Enables

With Airflow lineage, dataing can:

- **Trace task dependencies** - Understand which DAGs and tasks produce data
- **Track data freshness** - See when datasets were last updated by Airflow
- **Identify upstream failures** - Correlate anomalies with failed DAG runs
- **Access run history** - View recent task execution status and timing

---

## Prerequisites

- Apache Airflow 2.4+ (for Datasets feature) or 2.x with inlets/outlets
- Airflow REST API enabled
- Read access to Airflow API

### Enable the REST API

Ensure the REST API is enabled in your `airflow.cfg`:

```ini
[api]
auth_backends = airflow.api.auth.backend.basic_auth
```

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_LINEAGE_PROVIDER=airflow
    export DATAING_AIRFLOW_URL=http://localhost:8080
    export DATAING_AIRFLOW_USERNAME=admin
    export DATAING_AIRFLOW_PASSWORD=your-password
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.lineage.adapters.airflow import AirflowAdapter

    adapter = AirflowAdapter({
        "base_url": "http://localhost:8080",
        "username": "admin",
        "password": "your-password",  # pragma: allowlist secret
    })
    ```

### Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `base_url` | Yes | Airflow REST API URL |
| `username` | Yes | Airflow username |
| `password` | Yes | Airflow password |

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Upstream Lineage | :material-check-circle:{ .green } | Via inlets/outlets |
| Downstream Lineage | :material-check-circle:{ .green } | Via consuming DAGs |
| Job Runs | :material-check-circle:{ .green } | DAG run history |
| Freshness Tracking | :material-check-circle:{ .green } | Last update times |
| Search | :material-check-circle:{ .green } | Dataset URI search |
| Column Lineage | :material-close-circle:{ .red } | Not supported |

---

## How It Works

### Airflow Datasets (2.4+)

Airflow 2.4 introduced the Datasets feature for data-driven scheduling:

```python
# In your DAG file
from airflow.datasets import Dataset

orders_dataset = Dataset("s3://bucket/orders/")

@dag(schedule=[orders_dataset])  # Triggered by upstream
def downstream_dag():
    ...
```

dataing queries the Airflow API to discover:
- Which tasks produce datasets (producing_tasks)
- Which DAGs consume datasets (consuming_dags)
- Task inlets and outlets for lineage

### Inlets/Outlets (Legacy)

For Airflow < 2.4, use operator inlets/outlets:

```python
task = PythonOperator(
    task_id="process_orders",
    python_callable=process_orders,
    inlets=[Dataset("orders")],
    outlets=[Dataset("processed_orders")],
)
```

---

## Integration Points

### During Context Gathering

When investigating an anomaly, dataing queries Airflow:

```python
# Example lineage context
{
    "table": "orders",
    "airflow_dataset": "s3://bucket/orders/",
    "producing_tasks": [
        {"dag_id": "etl_pipeline", "task_id": "load_orders"}
    ],
    "consuming_dags": [
        {"dag_id": "analytics_daily"}
    ],
    "last_updated": "2024-01-15T10:30:00Z"
}
```

### Hypothesis Generation

Lineage context helps identify upstream issues:

> "The `orders` table is produced by `etl_pipeline.load_orders`.
> Recent DAG runs show 3 failures in the past 24 hours, which
> correlates with the anomaly detection time."

---

## Troubleshooting

### "Connection refused"

Verify the Airflow webserver is running and accessible:

```bash
curl http://localhost:8080/api/v1/health
```

### "Authentication failed"

Check credentials and ensure basic auth is enabled:

```bash
# Test authentication
curl -u admin:password http://localhost:8080/api/v1/dags
```

### "No datasets found"

Ensure your DAGs define datasets or use inlets/outlets:

```python
# Check if datasets are registered
curl http://localhost:8080/api/v1/datasets
```

---

## Learn More

<div class="grid cards" markdown>

-   :material-database-cog: **[dbt Integration](dbt.md)**

    ---

    Model-based lineage from dbt

-   :material-database-search: **[DataHub Integration](datahub.md)**

    ---

    Enterprise data catalog lineage

-   :material-hexagon-outline: **[Architecture](../../architecture/overview.md)**

    ---

    System overview and design

</div>
