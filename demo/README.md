# Dataing Demo Fixtures

Realistic e-commerce data with pre-baked anomalies for demonstrating Dataing's detection capabilities.

## Quick Start

```bash
# Run the full demo stack (from repo root)
just demo

# This will:
# 1. Generate fixtures if not present
# 2. Start all services via Docker Compose
# 3. Seed demo user/org for login
# 4. Start DuckDB server with fixtures on port 5433
```

## Demo Workflow

After running `just demo`:

1. **Login** at http://localhost:3000
   - Email: `demo@dataing.io`
   - Password: `demo123456` <!-- pragma: allowlist secret -->

2. **Add DuckDB datasource** via the UI (Datasources page)
   - Type: PostgreSQL (pg_duckdb - real PostgreSQL with DuckDB)
   - Host: `duckdb`
   - Port: `5432` (internal Docker port)
   - Database: `demo`
   - Username: `demo`
   - Password: `demo` <!-- pragma: allowlist secret -->

   Note: Use port 5433 when connecting from outside Docker (e.g., `psql -h localhost -p 5433 -U demo -d demo`)

3. **Run an investigation** on the connected datasource

## Fixtures

| Fixture | Anomaly | Description |
|---------|---------|-------------|
| `baseline` | None | Clean data for comparison |
| `null_spike` | NULL values | 40% of orders.user_id NULL on days 3-5 |
| `volume_drop` | Missing data | 80% of EU events missing on days 5-6 |
| `schema_drift` | Type changes | 28% of products.price stored as string |
| `duplicates` | Duplicate rows | 15% of order_items duplicated on day 6 |
| `late_arriving` | Late data | 3% of day 2 events arrive on day 5 |
| `orphaned_records` | Broken references | 8% of day 4 orders reference deleted users |

## Data Model

```
users (10,000 rows)
  |-- orders (5,000 rows)
  |     +-- order_items (12,500 rows)
  +-- events (500,000 rows)

products (500 rows)
  +-- categories (50 rows)
```

## Demo Scenarios

### Scenario: NULL Spike in Orders

| Field | Value |
|-------|-------|
| **Dataset** | `orders` table |
| **Anomaly Date** | `2024-01-10` (middle of anomaly window) |
| **Metric Name** | `null_count` |
| **Expected Value** | `5` |
| **Actual Value** | `200` |
| **Deviation %** | `3900` |
| **Severity** | High |
| **Description** | "Spike in NULL user_id values in the orders table" |

Root cause: "Mobile app v2.3.1 shipped with a bug that doesn't pass user context to the checkout API."

### Scenario: Volume Drop in Events

| Field | Value |
|-------|-------|
| **Dataset** | `events` table |
| **Anomaly Date** | `2024-01-12` |
| **Metric Name** | `row_count` |
| **Expected Value** | `70000` |
| **Actual Value** | `14000` |
| **Deviation %** | `-80` |
| **Severity** | Critical |
| **Description** | "Significant drop in EU event volume" |

Root cause: "CDN misconfiguration blocked the tracking pixel for EU users."

## Generate Fixtures

```bash
# Generate all fixtures
just demo-fixtures

# Regenerate (force)
just demo-regenerate

# Or directly
cd demo && uv run python generate.py
```

## Using Fixtures Directly with DuckDB

```sql
-- Load fixture
CREATE TABLE orders AS SELECT * FROM 'fixtures/null_spike/orders.parquet';

-- Show NULL spike anomaly
SELECT
    DATE_TRUNC('day', created_at) as day,
    ROUND(100.0 * SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as null_pct
FROM orders
GROUP BY 1
ORDER BY 1;

-- Expected output:
-- Day 1:  0.1%
-- Day 2:  0.1%
-- Day 3:  41.2%  <- ANOMALY STARTS
-- Day 4:  39.8%
-- Day 5:  40.1%
-- Day 6:  0.2%   <- FIXED
-- Day 7:  0.1%
```

## Validate Fixtures

```bash
duckdb demo.db < validate.sql
```

## File Structure

```
demo/
  fixtures/
    baseline/           # Clean data
    null_spike/         # NULL spike anomaly (default for demo)
    volume_drop/        # Volume drop anomaly
    schema_drift/       # Schema drift anomaly
    duplicates/         # Duplicate records
    late_arriving/      # Late arriving data
    orphaned_records/   # Orphaned records
  generate.py           # Fixture generator
  init-duckdb.sql       # DuckDB initialization for compose
  load_duckdb.sql       # Manual DuckDB loading
  quickstart-load.sql   # Quickstart loader
  validate.sql          # Validation queries
  demo_notebook.ipynb   # Jupyter notebook demo
  README.md             # This file
```

## Manifest Format

Each fixture includes a `manifest.json`:

```json
{
  "name": "null_spike",
  "description": "Mobile app bug causes NULL user_id in orders",
  "simulation_period": {
    "start": "2024-01-08",
    "end": "2024-01-14"
  },
  "tables": {
    "orders": {"row_count": 5023, "file": "orders.parquet"}
  },
  "anomalies": [
    {
      "type": "null_spike",
      "table": "orders",
      "column": "user_id",
      "start_day": 3,
      "end_day": 5,
      "severity": 0.41,
      "root_cause": "Mobile app v2.3.1 bug"
    }
  ],
  "ground_truth": {
    "affected_row_count": 892
  }
}
```

## Just Commands

```bash
just demo           # Start full demo stack
just demo-stop      # Stop demo
just demo-clean     # Stop and remove volumes + fixtures
just demo-fixtures  # Generate fixtures only
just demo-regenerate # Force regenerate fixtures
```

## Access Points

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API Docs | http://localhost:8000/docs |
| Temporal UI | http://localhost:8233 |
| DuckDB (from host) | localhost:5433 |
| DuckDB (in Docker) | duckdb:5432 |
