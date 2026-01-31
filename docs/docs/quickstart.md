# Quickstart

**Zero to first investigation in 5 minutes.**

---

## Prerequisites

!!! info "What you need"
    === "Docker Path (Recommended)"
        - **Docker** with Docker Compose v2
        - **Anthropic API key** ([get one here](https://console.anthropic.com))

    === "pip Path"
        - **Python 3.11+**
        - **Anthropic API key** ([get one here](https://console.anthropic.com))

---

## Step 1: Install

=== "Docker Compose (Recommended)"

    The fastest way to get started. Runs the full stack locally.

    ```bash
    # Clone the repository
    git clone https://github.com/bordumb/dataing.git
    cd dataing

    # Configure environment
    cp .env.example .env
    ```

    Edit `.env` and add your Anthropic API key:

    ```bash
    ANTHROPIC_API_KEY=sk-ant-api03-...
    ```

    Generate an encryption key (required for storing datasource credentials):

    ```bash
    python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ```

    Add the generated key to `.env`:

    ```bash
    DATADR_ENCRYPTION_KEY=<paste-key-here>
    ```

    Start the stack:

    ```bash
    docker compose up -d
    ```

    !!! success "That's it!"
        - **Frontend**: [http://localhost:3000](http://localhost:3000)
        - **API**: [http://localhost:8000](http://localhost:8000)
        - **Temporal UI**: [http://localhost:8233](http://localhost:8233)

=== "pip install"

    For developers who want to integrate into existing tooling.

    ```bash
    pip install dataing
    ```

    Verify the installation:

    ```bash
    python -c "from dataing import __version__; print(__version__)"
    ```

    !!! note "Additional setup required"
        The pip path requires you to run PostgreSQL, Redis, and Temporal separately.
        See the [Self-Host Guide](guides/self-host.md) for details.

---

## Step 2: Connect Demo Datasource

=== "Docker Compose"

    The demo datasource is **automatically configured** when you start the stack.

    The demo API key `dd_demo_12345` is pre-seeded and ready to use.

    Verify the API is running:

    ```bash
    curl http://localhost:8000/health
    ```

    Expected output:

    ```json
    {"status":"healthy"}
    ```

=== "pip install"

    Download and load the demo fixtures:

    ```bash
    # Download demo fixtures
    curl -L https://github.com/bordumb/dataing/releases/latest/download/demo-fixtures.tar.gz | tar xz

    # Load into DuckDB (included with dataing)
    python -c "
    import duckdb
    conn = duckdb.connect('demo.db')
    conn.execute(open('demo-fixtures/load_duckdb.sql').read())
    print('Demo data loaded!')
    "
    ```

---

## Step 3: Verify Connection

=== "Docker Compose"

    List available datasources:

    ```bash
    curl -H "X-API-Key: dd_demo_12345" http://localhost:8000/api/v1/datasources
    ```

    Expected output:

    ```json
    {
      "datasources": [
        {
          "id": "demo-ecommerce",
          "name": "Demo E-commerce",
          "type": "duckdb",
          "status": "connected"
        }
      ]
    }
    ```

=== "pip install"

    ```python
    from dataing.adapters.datasource import DuckDBAdapter

    adapter = DuckDBAdapter(database="demo.db")
    await adapter.connect()

    # Verify connection
    result = await adapter.execute_query("SELECT COUNT(*) FROM orders")
    print(f"Orders table has {result.rows[0][0]} rows")
    ```

---

## Demo Scenarios

The demo datasource includes pre-seeded anomalies for testing:

| Scenario | Table | Description |
|----------|-------|-------------|
| `null_spike` | `orders` | Mobile app bug causes NULL `user_id` values |
| `volume_drop` | `orders` | Weekend traffic drop pattern |
| `schema_drift` | `customers` | Column renamed from `email` to `contact_email` |
| `duplicates` | `orders` | Duplicate orders from retry logic |
| `late_arriving` | `orders` | ETL delay causing missing recent data |
| `orphaned_records` | `order_items` | Foreign key violations |

---

## Step 4: Run Your First Investigation

Let's investigate the `null_spike` anomaly — a simulated bug where a mobile app update started sending NULL user IDs.

=== "curl"

    ```bash
    curl -X POST http://localhost:8000/api/v1/investigations \
      -H "Content-Type: application/json" \
      -H "X-API-Key: dd_demo_12345" \
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

    Expected response (202 Accepted):

    ```json
    {
      "investigation_id": "inv_abc123...",
      "status": "running"
    }
    ```

=== "Python"

    ```python
    import httpx

    response = httpx.post(
        "http://localhost:8000/api/v1/investigations",
        headers={"X-API-Key": "dd_demo_12345"},
        json={
            "alert": {
                "table": "orders",
                "column": "user_id",
                "metric": "null_rate",
                "anomaly_type": "spike",
                "description": "NULL rate increased from 1% to 15%"
            }
        }
    )
    print(response.json())
    # {"investigation_id": "inv_abc123...", "status": "running"}
    ```

---

## Step 5: Watch the Investigation

The investigation runs asynchronously. Poll for status:

```bash
curl -H "X-API-Key: dd_demo_12345" \
  http://localhost:8000/api/v1/investigations/{investigation_id}
```

While running, you'll see:

```json
{
  "investigation_id": "inv_abc123...",
  "status": "investigating",
  "phase": "evaluating_hypotheses",
  "progress": {
    "hypotheses_total": 4,
    "hypotheses_evaluated": 2
  }
}
```

!!! tip "Temporal UI"
    Watch the investigation workflow in real-time at [http://localhost:8233](http://localhost:8233).
    You'll see parallel hypothesis evaluation and the evidence chain being built.

---

## Step 6: View Results

When complete, you'll get the full analysis:

```json
{
  "investigation_id": "inv_abc123...",
  "status": "completed",
  "duration_seconds": 45,
  "synthesis": {
    "root_cause": "Mobile app v2.3.1 introduced a bug where the checkout API fails to pass user context for guest checkouts",
    "confidence": 0.92,
    "supporting_evidence": [
      "NULL user_ids occur exclusively on channel='mobile_app'",
      "100% of affected orders have app_version='2.3.1'",
      "Web orders and mobile v2.3.0 orders are unaffected",
      "Issue started exactly when v2.3.1 was released (2024-01-15 09:00 UTC)"
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
      "query": "SELECT channel, COUNT(*) as total, SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as nulls FROM orders WHERE created_at > '2024-01-15' GROUP BY channel",
      "result": {"mobile_app": "85% NULL", "web": "1% NULL"},
      "interpretation": "Strong evidence - NULLs are isolated to mobile_app channel"
    }
  ]
}
```

!!! info "What just happened?"
    Dataing performed an autonomous investigation:

    1. **Context Gathering** — Analyzed table schema, statistics, and recent changes
    2. **Hypothesis Generation** — LLM generated 4 potential root causes
    3. **Parallel Evaluation** — Each hypothesis tested with SQL queries simultaneously
    4. **Synthesis** — Evidence combined into root cause with confidence score

    The entire process took ~45 seconds and ran 12 SQL queries across 4 hypotheses.

---

## Next Steps

<div class="grid cards" markdown>

-   :material-book: **[Architecture](architecture.md)**

    ---

    Understand how Dataing works under the hood

-   :material-connection: **[Connect Your Data](integrations/warehouses/snowflake.md)**

    ---

    Connect to your production warehouse

-   :material-shield: **[Security](security/data-privacy.md)**

    ---

    Learn about read-only safety guarantees

</div>

---

## Troubleshooting

### Docker: "port already in use"

Another service is using port 8000, 3000, or 5432. Stop it or change ports in `docker-compose.yml`.

```bash
# Find what's using the port
lsof -i :8000
```

### Docker: "unhealthy" containers

Check the logs for the failing service:

```bash
docker compose logs api
docker compose logs worker
```

Common causes:
- Missing `ANTHROPIC_API_KEY` in `.env`
- Missing `DATADR_ENCRYPTION_KEY` in `.env`

### pip: "No module named dataing"

Make sure you installed the package:

```bash
pip install dataing
```

### "ANTHROPIC_API_KEY not set"

Add your API key to the environment:

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
```

Or add it to your `.env` file.

---

!!! question "Need help?"
    - [GitHub Issues](https://github.com/bordumb/dataing/issues)
    - [Architecture Overview](architecture.md)
