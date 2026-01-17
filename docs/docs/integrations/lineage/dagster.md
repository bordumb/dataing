# Dagster Integration

Connect dataing to Dagster for first-class asset lineage and software-defined data pipelines.

---

## What It Enables

With Dagster lineage, dataing can:

- **Trace asset dependencies** - See the full asset graph upstream and downstream
- **Identify materializations** - Track when assets were last computed
- **Find related assets** - Discover assets in the same group or with shared dependencies
- **Access run history** - View recent job executions and their status

---

## Prerequisites

- Dagster 1.0+ with assets
- Dagster webserver running (for GraphQL API)
- Optional: Dagster Cloud API token

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_LINEAGE_PROVIDER=dagster
    export DATAING_DAGSTER_URL=http://localhost:3000
    # For Dagster Cloud:
    export DATAING_DAGSTER_API_TOKEN=your-token
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.lineage.adapters.dagster import DagsterAdapter

    # Dagster Open Source
    adapter = DagsterAdapter({
        "base_url": "http://localhost:3000",
    })

    # Dagster Cloud
    adapter = DagsterAdapter({
        "base_url": "https://your-org.dagster.cloud",
        "api_token": "your-token",
    })
    ```

### Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `base_url` | Yes | Dagster webserver URL |
| `api_token` | No | API token (required for Dagster Cloud) |

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Upstream Lineage | :material-check-circle:{ .green } | Via asset dependencies |
| Downstream Lineage | :material-check-circle:{ .green } | Via dependedBy |
| Job Runs | :material-check-circle:{ .green } | Materialization history |
| Freshness Tracking | :material-check-circle:{ .green } | Materialization timestamps |
| Search | :material-check-circle:{ .green } | Asset name search |
| Owners | :material-check-circle:{ .green } | Asset owners |
| Tags | :material-check-circle:{ .green } | Asset groups |
| Column Lineage | :material-close-circle:{ .red } | Not yet supported |
| Real-time Updates | :material-check-circle:{ .green } | GraphQL subscriptions |

---

## How It Works

Dagster uses Software-Defined Assets where dependencies are declared explicitly:

```python
from dagster import asset

@asset
def raw_orders():
    """Load raw orders from source."""
    return load_from_source()

@asset
def cleaned_orders(raw_orders):
    """Clean and validate orders."""
    return clean(raw_orders)

@asset
def daily_revenue(cleaned_orders):
    """Compute daily revenue metrics."""
    return aggregate(cleaned_orders)
```

dataing queries Dagster's GraphQL API to discover:
- Asset dependency keys (upstream)
- Assets that depend on a given asset (downstream)
- Ops and jobs that produce assets
- Materialization timestamps

---

## Integration Points

### During Context Gathering

When investigating an anomaly, dataing queries Dagster:

```python
# Example lineage context
{
    "asset": "daily_revenue",
    "upstream": [
        {"name": "cleaned_orders", "group": "orders"},
        {"name": "raw_orders", "group": "orders"},
    ],
    "downstream": [
        {"name": "revenue_dashboard", "group": "analytics"},
    ],
    "last_materialized": "2024-01-15T10:30:00Z",
    "owners": ["data-team"],
}
```

### Hypothesis Generation

Asset lineage helps trace issues:

> "The `daily_revenue` asset depends on `cleaned_orders`.
> The last successful materialization of `cleaned_orders` was
> 2 hours before the anomaly, and it shows a significant
> change in row count."

---

## GraphQL Queries

dataing uses Dagster's GraphQL API for lineage:

```graphql
query GetAssetLineage($assetKey: AssetKeyInput!) {
    assetOrError(assetKey: $assetKey) {
        ... on Asset {
            definition {
                dependencyKeys { path }
                dependedByKeys { path }
                opNames
                groupName
                owners { ... on TeamAssetOwner { team } }
            }
        }
    }
}
```

---

## Troubleshooting

### "Connection refused"

Verify Dagster webserver is running:

```bash
# Check health
curl http://localhost:3000/server_info
```

### "Asset not found"

Check that:
- The asset exists in your Dagster repository
- The asset path is correct (use dots for nested paths)
- The webserver has loaded your repository

### "GraphQL errors"

Enable debug logging to see the full query:

```python
import logging
logging.getLogger("dataing.adapters.lineage").setLevel(logging.DEBUG)
```

---

## Learn More

<div class="grid cards" markdown>

-   :material-database-cog: **[dbt Integration](dbt.md)**

    ---

    Model-based lineage from dbt

-   :material-airplane: **[Airflow Integration](airflow.md)**

    ---

    DAG-based lineage from Airflow

-   :material-hexagon-outline: **[Architecture](../../architecture/overview.md)**

    ---

    System overview and design

</div>
