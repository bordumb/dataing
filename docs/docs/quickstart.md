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

## Next Steps

You're ready to run your first investigation! Continue to:

<div class="grid cards" markdown>

-   :material-magnify: **[Run Your First Investigation](guides/first-investigation.md)**

    ---

    Trigger an investigation and understand the results

-   :material-book: **[Architecture](architecture.md)**

    ---

    Understand how Dataing works under the hood

-   :material-connection: **[Connect Your Data](integrations/warehouses/snowflake.md)**

    ---

    Connect to your production warehouse

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
