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
        See the [Deployment Guide](development/deployment.md) for details.

---

## Step 2: Create Your Account

=== "Docker Compose"

    The stack starts **clean** — no pre-seeded data. You'll create your own account and connect your datasources.

    1. Open [http://localhost:3000](http://localhost:3000) in your browser
    2. Click **Sign Up** to create a new organization and user account
    3. Enter your email, password, and organization name
    4. Log in with your new credentials

    Verify the API is running:

    ```bash
    curl http://localhost:8000/health
    ```

    Expected output:

    ```json
    {"status":"healthy"}
    ```

    !!! tip "Want pre-loaded demo data?"
        Use `just demo` instead of `docker compose up` to start with pre-seeded demo fixtures and the `dd_demo_12345` API key.

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

## Step 3: Connect a Datasource

=== "Docker Compose"

    After logging in, connect your own datasource:

    1. Go to [http://localhost:3000/datasources](http://localhost:3000/datasources)
    2. Click **Add Datasource**
    3. Choose your datasource type (e.g., DuckDB, PostgreSQL, Snowflake)
    4. Enter connection details and save

    For a quick test, you can connect a standalone DuckDB file:

    - **Type**: DuckDB
    - **Database Path**: `/path/to/your/data.duckdb`

    Verify the connection shows as "connected" in the datasources list.

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

## Step 4: Run Your First Investigation

With your datasource connected, you can investigate data quality issues. Here's an example investigating a NULL rate spike in an `orders` table.

!!! note "Get your API key"
    After logging in, go to **Settings → API Keys** to create an API key for programmatic access.

=== "curl"

    ```bash
    curl -X POST http://localhost:8000/api/v1/investigations \
      -H "Content-Type: application/json" \
      -H "X-API-Key: YOUR_API_KEY" \
      -d '{
        "alert": {
          "table": "orders",
          "column": "user_id",
          "metric": "null_rate",
          "anomaly_type": "spike",
          "description": "NULL rate increased from 1% to 15%",
          "expected_value": "0.01",
          "actual_value": "0.15",
          "deviation_pct": "1400",
          "anomaly_date": "2026-01-31"
        }
      }'
    ```

    Expected response:

    ```json
    {
      "investigation_id": "e19ac619-...",
      "main_branch_id": "e19ac619-...",
      "status": "queued"
    }
    ```

=== "Python"

    ```python
    import httpx

    response = httpx.post(
        "http://localhost:8000/api/v1/investigations",
        headers={"X-API-Key": "YOUR_API_KEY"},
        json={
            "alert": {
                "table": "orders",
                "column": "user_id",
                "metric": "null_rate",
                "anomaly_type": "spike",
                "description": "NULL rate increased from 1% to 15%",
                "expected_value": "0.01",
                "actual_value": "0.15",
                "deviation_pct": "1400",
                "anomaly_date": "2026-01-31",
            }
        }
    )
    print(response.json())
    # {"investigation_id": "e19ac619-...", "main_branch_id": "...", "status": "queued"}
    ```

---

## Demo Mode

For testing with pre-seeded data, use `just demo` instead of `docker compose up`. Demo mode includes:

| Scenario | Table | Description |
|----------|-------|-------------|
| `null_spike` | `orders` | Mobile app bug causes NULL `user_id` values |
| `volume_drop` | `orders` | Weekend traffic drop pattern |
| `schema_drift` | `customers` | Column renamed from `email` to `contact_email` |
| `duplicates` | `orders` | Duplicate orders from retry logic |
| `late_arriving` | `orders` | ETL delay causing missing recent data |
| `orphaned_records` | `order_items` | Foreign key violations |

Demo mode also pre-seeds the `dd_demo_12345` API key for immediate API access.

---

## Step 5: Watch the Investigation

The investigation runs asynchronously. Poll for status:

```bash
curl -H "X-API-Key: YOUR_API_KEY" \
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

### "ANTHROPIC_API_KEY not set"

**Symptom**: Investigation is created but immediately fails.

**Fix**: Set the key in `.env` and restart:

```bash
# Edit .env
ANTHROPIC_API_KEY=sk-ant-api03-...

# Restart services
docker compose restart api worker
```

!!! tip "Get an API key"
    Sign up at [console.anthropic.com](https://console.anthropic.com) to get your API key.

---

### "Cannot connect to Docker daemon"

**Symptom**: `docker compose up` fails immediately.

**Fix**: Ensure Docker is running:

=== "macOS"
    Open Docker Desktop from Applications.

=== "Linux"
    ```bash
    sudo systemctl start docker
    ```

=== "Windows"
    Open Docker Desktop from the Start menu. Ensure WSL2 backend is enabled.

---

### "Port already in use"

**Symptom**: Service fails to start with "address already in use" for ports 8000, 3000, 5432, or 7233.

**Fix**: Find and stop the conflicting process:

```bash
# Find what's using the port
lsof -i :8000

# Kill the process
kill -9 <PID>
```

Or change ports in `docker-compose.yml`.

---

### "Temporal server not ready"

**Symptom**: Worker logs show "failed to connect to temporal" or "connection refused".

**Cause**: Temporal takes 30-60 seconds to initialize its database schemas on first run.

**Fix**: Wait and check Temporal logs:

```bash
# Wait for Temporal to be healthy
docker compose ps temporal

# View Temporal logs
docker compose logs temporal
```

!!! info "First-run initialization"
    On first startup, Temporal creates database schemas in PostgreSQL. This is normal and only happens once.

---

### "Out of memory" / Docker crashing

**Symptom**: Containers are killed, Docker Desktop becomes unresponsive.

**Cause**: The full stack (Temporal + PostgreSQL + API + Worker) needs ~2GB RAM at minimum.

**Fix**: Increase Docker Desktop memory to at least **4GB** (6GB recommended):

=== "macOS / Windows"
    Docker Desktop → Settings → Resources → Memory → 6GB

=== "Linux"
    Edit `/etc/docker/daemon.json`:
    ```json
    {
      "default-ulimits": {
        "memlock": { "soft": -1, "hard": -1 }
      }
    }
    ```
    Then restart Docker: `sudo systemctl restart docker`

---

### "Database migration failed"

**Symptom**: API fails to start because the `db-migrate` service exited with an error.

**Fix**: Check the migration logs:

```bash
docker compose logs db-migrate
```

If the log says the database **has tables but no migration history**, it was created before
migrations were tracked. Recreate it (below) unless you need its data: adopting it keeps the
schema as it is, including damage from earlier restarts (emptied users and investigations,
missing foreign keys). To adopt it anyway, record the migrations it already has:

```bash
MIGRATIONS_BASELINE=034_code_changes_pr_metadata.sql docker compose up -d
```

Otherwise, fix the failing migration or try a clean start:

```bash
# Clean start (removes all data)
docker compose down -v
docker compose up -d
```

!!! warning "This removes all data"
    The `-v` flag removes volumes including database data. Only use for fresh starts.

---

### "Investigation stuck in 'running'"

**Symptom**: Investigation never completes, stays in "running" state.

**Fix**: Check worker logs and Temporal UI:

```bash
# Check worker logs
docker compose logs worker

# View workflows in Temporal UI
open http://localhost:8233
```

Common causes:
- Worker not running (check `docker compose ps`)
- LLM API errors (check worker logs for Anthropic errors)
- Database connectivity issues

---

### Platform-Specific Notes

=== "macOS"
    - Docker Desktop defaults to 2GB memory — increase to 6GB
    - Apple Silicon (M1/M2/M3): all images are arm64-native
    - Intel Macs: works without changes

=== "Linux"
    - Use Docker Compose v2: `docker compose` (not `docker-compose`)
    - Ensure your user is in the `docker` group:
      ```bash
      sudo usermod -aG docker $USER
      ```

=== "Windows"
    - WSL2 backend required for Docker Desktop
    - Run commands in PowerShell or WSL2 terminal
    - File paths in WSL2: `/mnt/c/Users/...`

---

## Getting Help

!!! question "Need more help?"
    - **GitHub Issues**: [github.com/bordumb/dataing/issues](https://github.com/bordumb/dataing/issues)
    - **Architecture**: [Architecture Overview](architecture.md) for deeper understanding
    - **Security**: [Security FAQ](security/data-privacy.md) for data handling questions
