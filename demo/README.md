# Dataing Demo Fixtures

Realistic e-commerce data with pre-baked anomalies for demonstrating Dataing's detection capabilities.

## Quick Start

```bash
# Run the full demo (from repo root)
just demo

# This will:
# 1. Generate fixtures if not present
# 2. Start backend at http://localhost:8000
# 3. Start frontend at http://localhost:3000
# 4. Seed demo data source "E-Commerce Demo"

# Demo API key for testing: dd_demo_12345
```

## Running with Docker

```bash
# Start everything with Docker Compose
just demo-docker

# Stop
just demo-docker-down
```

## Generate Fixtures Only

```bash
# Generate all fixtures (from repo root)
cd demo && uv run python generate.py

# Or use just
just demo-fixtures

# Regenerate (force)
just demo-regenerate
```

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
  ├── orders (5,000 rows)
  │     └── order_items (12,500 rows)
  └── events (500,000 rows)

products (500 rows)
  └── categories (50 rows)
```

## Demo Script

### Scenario: NULL Spike

1. Load the fixture:
   ```sql
   CREATE TABLE orders AS SELECT * FROM 'fixtures/null_spike/orders.parquet';
   ```

2. Show the anomaly:
   ```sql
   SELECT
       DATE_TRUNC('day', created_at) as day,
       ROUND(100.0 * SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as null_pct
   FROM orders
   GROUP BY 1
   ORDER BY 1;
   ```

3. Expected output:
   ```
   Day 1:  0.1%
   Day 2:  0.1%
   Day 3:  41.2%  <- ANOMALY STARTS
   Day 4:  39.8%
   Day 5:  40.1%
   Day 6:  0.2%   <- FIXED
   Day 7:  0.1%
   ```

4. Root cause story: "Mobile app v2.3.1 shipped with a bug that doesn't pass user context to the checkout API."

### Scenario: Volume Drop

1. Load and query:
   ```sql
   SELECT
       DATE_TRUNC('day', created_at) as day,
       CASE WHEN country IN ('DE', 'FR', 'GB') THEN 'EU' ELSE 'Non-EU' END as region,
       COUNT(*) as events
   FROM events
   GROUP BY 1, 2
   ORDER BY 1, 2;
   ```

2. Root cause story: "CDN misconfiguration blocked the tracking pixel for EU users."

## Validation

Run validation queries to verify fixtures:

```bash
duckdb demo.db < validate.sql
```

## File Structure

```
demo/
├── fixtures/
│   ├── baseline/
│   │   ├── users.parquet
│   │   ├── categories.parquet
│   │   ├── products.parquet
│   │   ├── orders.parquet
│   │   ├── order_items.parquet
│   │   ├── events.parquet
│   │   └── manifest.json
│   ├── null_spike/
│   ├── volume_drop/
│   ├── schema_drift/
│   ├── duplicates/
│   ├── late_arriving/
│   └── orphaned_records/
├── generate.py        # Main generation script
├── load_duckdb.sql    # DuckDB loading script
├── validate.sql       # Validation queries
└── README.md
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

## Dependencies

- Python 3.11+
- polars >= 0.20.0
- faker >= 22.0.0
- pyarrow >= 15.0.0

Install with:
```bash
uv add polars faker pyarrow
```
