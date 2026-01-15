# Quickstart

Get up and running with dataing in under 5 minutes. You'll install the package, configure a data source, and run your first investigation.

---

## Prerequisites

- **Python 3.11+** (check with `python --version`)
- **Redis** (for durable job queue)
- **pip** or **uv** package manager
- **Data warehouse access** (or use DuckDB for local testing)

---

## Step 1: Install dataing

=== "pip"

    ```bash
    pip install dataing-core redis arq
    ```

=== "uv"

    ```bash
    uv add dataing-core redis arq
    ```

Verify the installation:

```bash
python -c "import dataing; print(dataing.__version__)"
```

---

## Step 2: Configure Your Data Source

dataing connects to your data warehouse using environment variables.

### Common Configuration

All setups require Redis:

```bash
export REDIS_URL=redis://localhost:6379
```

=== "DuckDB (Local Testing)"

    DuckDB is perfect for trying dataing without cloud credentials:

    ```bash
    # No configuration needed for local DuckDB
    export DATAING_DATASOURCE=duckdb
    export DATAING_DUCKDB_PATH=./demo.duckdb
    ```

=== "BigQuery"

    ```bash
    export DATAING_DATASOURCE=bigquery
    export DATAING_BIGQUERY_PROJECT=your-project-id
    export DATAING_BIGQUERY_DATASET=your_dataset
    export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
    ```

=== "Snowflake"

    ```bash
    export DATAING_DATASOURCE=snowflake
    export DATAING_SNOWFLAKE_ACCOUNT=your-account
    export DATAING_SNOWFLAKE_USER=your-user
    export DATAING_SNOWFLAKE_PASSWORD=your-password
    export DATAING_SNOWFLAKE_DATABASE=your_db
    export DATAING_SNOWFLAKE_SCHEMA=your_schema
    export DATAING_SNOWFLAKE_WAREHOUSE=your_warehouse
    ```

=== "PostgreSQL"

    ```bash
    export DATAING_DATASOURCE=postgres
    export DATAING_POSTGRES_HOST=localhost
    export DATAING_POSTGRES_PORT=5432
    export DATAING_POSTGRES_USER=your_user
    export DATAING_POSTGRES_PASSWORD=your_password
    export DATAING_POSTGRES_DATABASE=your_db
    ```

---

## Step 3: Configure the LLM

dataing uses Claude for hypothesis generation and analysis:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

!!! tip "Get an API Key"
    Sign up at [console.anthropic.com](https://console.anthropic.com) to get your API key.

---

## Step 4: Run Your First Investigation

Investigations run asynchronously using Redis and Workers.

### 1. Start Infrastructure

Start Redis (if not running):

```bash
docker run -d -p 6379:6379 redis
```

Start the Worker (in a separate terminal):

```bash
# Processes the investigation queue
python -m dataing.entrypoints.worker
```

### 2. Start the API

Start the API server (in another terminal):

```bash
# Start the development server
uvicorn dataing.entrypoints.api.app:app --host 0.0.0.0 --port 8000
```

### 3. Trigger Investigation

Send an investigation request:

```bash
curl -X POST http://localhost:8000/api/v1/investigations \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -d '{
    "alert": {
      "table": "orders",
      "column": "user_id",
      "metric": "null_rate",
      "anomaly_type": "spike",
      "detected_at": "2024-01-15T10:00:00Z",
      "description": "NULL rate increased from 1% to 15%"
    }
  }'
```

The API will return a `202 Accepted` response with an `investigation_id`.

### Using Python SDK

```python
import asyncio
from uuid import UUID
from dataing.core.investigation.service import InvestigationService
from dataing.core.domain_types import AnomalyAlert

async def trigger_investigation():
    # Create an anomaly alert
    alert = AnomalyAlert(
        table="orders",
        column="user_id",
        metric="null_rate",
        anomaly_type="spike",
        description="NULL rate spiked from 1% to 15%"
    )

    # Initialize the service
    service = InvestigationService(...) # Requires dependencies

    # Start the investigation (returns immediately)
    investigation_id, _, status = await service.start_investigation(
        tenant_id=UUID("..."),
        alert=alert,
        data_adapter=...,
    )

    print(f"Investigation started: {investigation_id} (Status: {status})")
    print("Check the worker logs for progress.")

asyncio.run(trigger_investigation())
```

---

## Step 5: View Results

When the worker completes the investigation, results are available via the API:

```bash
curl http://localhost:8000/api/v1/investigations/{investigation_id}
```

Response:

```json
{
  "investigation_id": "inv_abc123",
  "status": "completed",
  "synthesis": {
    "root_cause": "Mobile app v2.3.1 bug - checkout API not passing user context",
    "confidence": 0.95,
    "supporting_evidence": [
      "NULLs occur exclusively on channel='mobile_app'",
      "Affected orders have app_version='2.3.1'",
      "Web orders and v2.3.0 mobile orders are unaffected"
    ],
    "recommended_actions": [
      "Roll back mobile app to v2.3.0",
      "Fix user context passing in checkout API",
      "Backfill user_id from session data where possible"
    ]
  },
  "evidence": [
    {
      "hypothesis": "Issue is channel-specific",
      "query": "SELECT channel, COUNT(*) as total, SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as nulls FROM orders GROUP BY channel",
      "result": "mobile_app: 85% NULL, web: 1% NULL"
    }
  ]
}
```

---

## Try the Demo

We provide pre-built demo scenarios to explore dataing's capabilities:

```bash
# Clone the repository
git clone https://github.com/bordumb/dataing.git
cd dataing

# Set up the demo environment (starts API, Worker, Redis, DB)
just demo
```

The demo includes these scenarios:

| Scenario | Description |
|----------|-------------|
| `null_spike` | Mobile app bug causes NULL user_id |
| `volume_drop` | Weekend traffic drop in orders |
| `schema_drift` | Column renamed from `email` to `contact_email` |
| `duplicates` | Duplicate orders from retry logic |
| `late_arriving` | ETL delay causing missing recent data |
| `orphaned_records` | Foreign key violations in order_items |

---

## Next Steps

Now that you've run your first investigation:

<div class="grid cards" markdown>

-   :material-book: **[Architecture](architecture.md)**

    ---

    Understand how dataing works under the hood

-   :material-shield: **[Security](security/data-privacy.md)**

    ---

    Learn about our read-only safety guarantees

-   :material-connection: **[Integrations](integrations/warehouses/snowflake.md)**

    ---

    Connect to your production warehouse

-   :material-lightbulb: **[Concepts](concepts/investigations.md)**

    ---

    Deep dive into investigation workflows

</div>

---

## Troubleshooting

### "No module named dataing"

Make sure you installed the package:

```bash
pip install dataing-core
```

### "ANTHROPIC_API_KEY not set"

Set your API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### "Connection refused" errors

Check that your data warehouse credentials are correct and the server is reachable.
Ensure Redis is running if starting manually.

### Need help?

- [GitHub Issues](https://github.com/bordumb/dataing/issues)
- [Architecture Overview](architecture.md)
- [Security FAQ](security/data-privacy.md)
