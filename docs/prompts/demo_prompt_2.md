# Dataing Demo Integration: Technical Specification

## Acceptance Criteria

**The demo is complete when:**

1. `make demo` starts the full stack with demo data pre-loaded
2. Opening `localhost:3000` shows a pre-configured "E-Commerce Demo" data source
3. User can click "New Investigation" → select a table → run investigation
4. Investigation completes in <30 seconds showing detected anomaly
5. Results page shows the anomaly, severity, affected rows, and root cause hypothesis
6. Zero manual setup required beyond `make demo`

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEMO ARCHITECTURE                                  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                              FRONTEND                                    ││
│  │                          localhost:3000                                  ││
│  │                                                                          ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    ││
│  │  │ Data Sources│  │ New Invest. │  │  Results    │  │  Dashboard  │    ││
│  │  │   Page      │  │   Dialog    │  │   Page      │  │             │    ││
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────────────┘    ││
│  │         │                │                │                             ││
│  └─────────┼────────────────┼────────────────┼─────────────────────────────┘│
│            │                │                │                               │
│            ▼                ▼                ▼                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                              BACKEND                                     ││
│  │                          localhost:8000                                  ││
│  │                                                                          ││
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    ││
│  │  │ /api/v1/    │  │ /api/v1/    │  │ /api/v1/    │  │ Connector   │    ││
│  │  │ datasources │  │ investigate │  │ results     │  │  Registry   │    ││
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘    ││
│  │         │                │                │                │            ││
│  │         │                ▼                │                │            ││
│  │         │         ┌─────────────┐         │                │            ││
│  │         │         │Investigation│         │                │            ││
│  │         │         │   Engine    │◀────────┼────────────────┘            ││
│  │         │         └──────┬──────┘         │                             ││
│  │         │                │                │                             ││
│  └─────────┼────────────────┼────────────────┼─────────────────────────────┘│
│            │                │                │                               │
│            ▼                ▼                ▼                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                           DATA LAYER                                     ││
│  │                                                                          ││
│  │  ┌─────────────────────┐      ┌─────────────────────────────────────┐  ││
│  │  │   PostgreSQL        │      │         DuckDB                       │  ││
│  │  │   (App State)       │      │         (Demo Data)                  │  ││
│  │  │                     │      │                                      │  ││
│  │  │ • datasources       │      │ • users.parquet                     │  ││
│  │  │ • investigations    │      │ • orders.parquet                    │  ││
│  │  │ • results           │      │ • events.parquet                    │  ││
│  │  │ • api_keys          │      │ • ...                               │  ││
│  │  └─────────────────────┘      └─────────────────────────────────────┘  ││
│  │                                                                          ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. DuckDB Connector

### 2.1 Connector Interface

The DuckDB connector implements the same interface as PostgreSQL, Trino, etc.

```
┌─────────────────────────────────────────────────────────────┐
│                   CONNECTOR REGISTRY                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  BaseConnector (ABC)                                         │
│  ├── PostgresConnector                                       │
│  ├── TrinoConnector                                         │
│  ├── SnowflakeConnector                                     │
│  ├── BigQueryConnector                                      │
│  └── DuckDBConnector  ◀── NEW                               │
│                                                              │
│  All implement:                                              │
│  • connect() -> None                                        │
│  • disconnect() -> None                                     │
│  • list_tables() -> list[TableInfo]                        │
│  • get_table_schema(table) -> TableSchema                  │
│  • execute_query(sql) -> ResultSet                         │
│  • get_column_statistics(table, column) -> ColumnStats     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 DuckDB Connector Configuration

```python
# Configuration schema for DuckDB data source
DuckDBConfig:
    type: "duckdb"
    path: str              # Path to .duckdb file OR directory of parquet files
    read_only: bool = True # Always true for demo safety

# Example configurations:

# Option 1: Directory of parquet files (recommended for demo)
{
    "type": "duckdb",
    "name": "E-Commerce Demo",
    "path": "./demo/fixtures/null_spike",
    "read_only": true
}

# Option 2: Pre-built DuckDB database file
{
    "type": "duckdb",
    "name": "E-Commerce Demo",
    "path": "./demo/fixtures/demo.duckdb",
    "read_only": true
}
```

### 2.3 Connector Implementation Notes

**Key behaviors:**

1. **Parquet Directory Mode**: If `path` is a directory, connector auto-registers all `.parquet` files as tables:
   ```sql
   -- Auto-generated on connect
   CREATE VIEW users AS SELECT * FROM './fixtures/null_spike/users.parquet';
   CREATE VIEW orders AS SELECT * FROM './fixtures/null_spike/orders.parquet';
   -- etc.
   ```

2. **Read-Only Enforcement**: Connector opens DuckDB in read-only mode. No writes possible.

3. **In-Memory Option**: For fastest demo performance, load parquet into memory:
   ```sql
   CREATE TABLE users AS SELECT * FROM './fixtures/null_spike/users.parquet';
   ```

4. **Thread Safety**: DuckDB connections are not thread-safe. Use connection pooling or connection-per-request.

### 2.4 Implementation Skeleton

```python
# Location: backend/src/dataing/adapters/connectors/duckdb_connector.py

"""
DuckDB Connector for Dataing.

Supports two modes:
1. Parquet directory: Auto-registers all .parquet files as views
2. DuckDB file: Opens existing .duckdb database

Always read-only for safety.
"""

# Key imports needed:
# - duckdb (pip install duckdb)
# - pathlib.Path
# - Your BaseConnector ABC

# Implementation requirements:
#
# 1. __init__(config: DuckDBConfig)
#    - Store config
#    - Don't connect yet (lazy connection)
#
# 2. connect()
#    - If path is directory:
#      - Create in-memory DuckDB
#      - Register each .parquet as a view
#    - If path is .duckdb file:
#      - Open in read_only mode
#    - Verify connection works with simple query
#
# 3. list_tables()
#    - Query information_schema or SHOW TABLES
#    - Return list of TableInfo(name, schema, row_count_approx)
#
# 4. get_table_schema(table_name)
#    - Query DESCRIBE {table} or information_schema.columns
#    - Return TableSchema with column names, types, nullability
#
# 5. execute_query(sql)
#    - Execute read-only query
#    - Return results as list of dicts or DataFrame
#    - Enforce query timeout (30s default)
#
# 6. get_column_statistics(table, column)
#    - Run statistical queries:
#      - COUNT(*), COUNT(column), NULL rate
#      - APPROX_COUNT_DISTINCT for cardinality
#      - MIN, MAX, AVG for numerics
#    - Return ColumnStats dataclass
#
# 7. disconnect()
#    - Close connection
#    - Release resources
```

### 2.5 Registration

Add DuckDB to the connector registry:

```python
# Location: backend/src/dataing/adapters/connectors/__init__.py

CONNECTOR_REGISTRY = {
    "postgresql": PostgresConnector,
    "trino": TrinoConnector,
    "snowflake": SnowflakeConnector,
    "bigquery": BigQueryConnector,
    "redshift": RedshiftConnector,
    "duckdb": DuckDBConnector,  # ← Add this
}
```

---

## 3. Demo Seed Data

### 3.1 Seed Script Purpose

On demo startup, we need to:

1. Create a demo tenant/API key (if multi-tenant)
2. Create a pre-configured "E-Commerce Demo" data source
3. Optionally pre-run an investigation so results are instant

### 3.2 Seed Data Structure

```python
# Location: backend/src/dataing/demo/seed.py

"""
Demo seed data.

Run with: python -m dataing.demo.seed
Or automatically on startup when DATADR_DEMO_MODE=true
"""

DEMO_TENANT = {
    "id": "demo-tenant-001",
    "name": "Demo Account",
    "plan_tier": "enterprise",  # Full features for demo
}

DEMO_API_KEY = {
    "id": "demo-api-key-001",
    "tenant_id": "demo-tenant-001",
    "key_prefix": "dd_demo",
    "key_hash": "<hash of 'dd_demo_12345'>",  # Hardcoded for demo
    "name": "Demo API Key",
}

DEMO_DATASOURCE = {
    "id": "demo-datasource-001",
    "tenant_id": "demo-tenant-001",
    "name": "E-Commerce Demo",
    "type": "duckdb",
    "config": {
        "path": "./demo/fixtures/null_spike",
        "read_only": True,
    },
    "status": "active",
}

# Optional: Pre-computed investigation result for instant demo
DEMO_INVESTIGATION = {
    "id": "demo-investigation-001",
    "datasource_id": "demo-datasource-001",
    "target_table": "orders",
    "target_column": "user_id",
    "status": "completed",
    "started_at": "2024-01-15T10:00:00Z",
    "completed_at": "2024-01-15T10:00:23Z",
    "result": {
        "pattern_type": "NULL_SPIKE",
        "severity": 0.85,
        "confidence": 0.94,
        "affected_rows": 892,
        "total_rows": 5023,
        "temporal_range": {
            "start": "2024-01-10T00:00:00Z",
            "end": "2024-01-12T23:59:59Z",
        },
        "root_cause_hypothesis": {
            "description": "NULL spike correlates with mobile device traffic",
            "evidence": [
                "41% of orders on days 3-5 have NULL user_id",
                "92% of affected orders originated from mobile devices",
                "Spike begins exactly at 14:00 UTC on day 3",
            ],
            "suggested_action": "Check mobile app v2.3.x checkout flow for user context propagation",
        },
    },
}
```

### 3.3 Seed Execution

```python
# Seed function to run on startup

async def seed_demo_data(db: Database) -> None:
    """
    Seed demo data if not already present.

    Idempotent - safe to run multiple times.
    """
    # Check if already seeded
    existing = await db.fetch_one(
        "SELECT id FROM datasources WHERE id = $1",
        DEMO_DATASOURCE["id"]
    )

    if existing:
        logger.info("Demo data already seeded, skipping")
        return

    logger.info("Seeding demo data...")

    # Insert tenant
    await db.execute(
        "INSERT INTO tenants (id, name, plan_tier) VALUES ($1, $2, $3)",
        DEMO_TENANT["id"], DEMO_TENANT["name"], DEMO_TENANT["plan_tier"]
    )

    # Insert API key
    await db.execute(
        """INSERT INTO api_keys (id, tenant_id, key_prefix, key_hash, name)
           VALUES ($1, $2, $3, $4, $5)""",
        DEMO_API_KEY["id"], DEMO_API_KEY["tenant_id"],
        DEMO_API_KEY["key_prefix"], DEMO_API_KEY["key_hash"], DEMO_API_KEY["name"]
    )

    # Insert datasource
    await db.execute(
        """INSERT INTO datasources (id, tenant_id, name, type, config, status)
           VALUES ($1, $2, $3, $4, $5, $6)""",
        DEMO_DATASOURCE["id"], DEMO_DATASOURCE["tenant_id"],
        DEMO_DATASOURCE["name"], DEMO_DATASOURCE["type"],
        json.dumps(DEMO_DATASOURCE["config"]), DEMO_DATASOURCE["status"]
    )

    logger.info("Demo data seeded successfully")
```

---

## 4. Demo Startup Flow

### 4.1 Makefile Target

```makefile
# Location: Makefile (root)

.PHONY: demo demo-fixtures demo-backend demo-frontend

# Main entry point
demo: demo-fixtures demo-backend demo-frontend
	@echo "Demo running at http://localhost:3000"
	@echo "API key for testing: dd_demo_12345"

# Generate fixtures if not present
demo-fixtures:
	@if [ ! -d "demo/fixtures/null_spike" ]; then \
		echo "Generating demo fixtures..."; \
		cd demo && uv run python generate.py; \
	fi

# Start backend in demo mode
demo-backend:
	DATADR_DEMO_MODE=true \
	DATADR_DB_URL=postgresql://localhost:5432/dataing_demo \
	cd backend && uv run python -m dataing.main &

# Start frontend
demo-frontend:
	cd frontend && pnpm dev &

# Clean demo data
demo-clean:
	rm -rf demo/fixtures/*/
	dropdb dataing_demo --if-exists
```

### 4.2 Docker Compose (Alternative)

```yaml
# Location: docker-compose.demo.yml

version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: dataing_demo
      POSTGRES_USER: dataing
      POSTGRES_PASSWORD: dataing
    volumes:
      - demo-pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dataing -d dataing_demo"]
      interval: 5s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    environment:
      DATADR_DEMO_MODE: "true"
      DATADR_DB_URL: postgresql://dataing:dataing@postgres:5432/dataing_demo
      DATADR_FIXTURE_PATH: /app/fixtures
    volumes:
      - ./demo/fixtures:/app/fixtures:ro
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      fixtures:
        condition: service_completed_successfully

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    environment:
      VITE_API_URL: http://localhost:8000
    ports:
      - "3000:3000"
    depends_on:
      - backend

  fixtures:
    build:
      context: ./demo
      dockerfile: Dockerfile
    volumes:
      - ./demo/fixtures:/app/fixtures
    command: python generate.py --output /app/fixtures

volumes:
  demo-pgdata:
```

### 4.3 Backend Demo Mode

```python
# Location: backend/src/dataing/main.py

import os
from dataing.demo.seed import seed_demo_data

async def lifespan(app: FastAPI):
    """Application lifespan handler."""

    # Standard startup
    await database.connect()
    await run_migrations()

    # Demo mode: seed demo data
    if os.getenv("DATADR_DEMO_MODE") == "true":
        logger.info("Running in DEMO MODE")
        await seed_demo_data(database)

    yield

    # Shutdown
    await database.disconnect()
```

---

## 5. Frontend Adjustments

### 5.1 Demo Data Source Display

The demo data source should be visually distinct:

```
┌─────────────────────────────────────────────────────────────┐
│                      DATA SOURCES                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  🎭  E-Commerce Demo                          DEMO      ││
│  │      DuckDB • 6 tables • Last synced: just now         ││
│  │                                                         ││
│  │      [View Tables]  [New Investigation]                 ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐│
│  │                                                         ││
│       + Add Data Source                                     │
│  │                                                         ││
│  └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘│
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Demo Badge Component

```typescript
// Location: frontend/src/components/shared/demo-badge.tsx

// Simple badge to indicate demo data sources
// Shows "DEMO" pill next to demo data source names
// Tooltip: "This is sample data for demonstration purposes"
```

### 5.3 Demo Mode Detection

```typescript
// Location: frontend/src/hooks/use-demo-mode.ts

// Check if a data source is a demo source
// Based on: datasource.id starts with "demo-" OR datasource.config.path contains "fixtures"

// Usage:
// const { isDemo } = useDemoMode(datasource)
// {isDemo && <DemoBadge />}
```

### 5.4 New Investigation Flow

No changes needed to the investigation flow itself. The frontend already:

1. Lists tables from the selected data source
2. Lets user pick a table/column
3. Submits investigation request
4. Polls for results
5. Displays results

The DuckDB connector makes the demo fixtures look like any other data source.

---

## 6. Demo Script (Sales Call Flow)

### 6.1 Pre-Call Setup (5 minutes before)

```bash
# Terminal 1: Start everything
make demo

# Verify:
# - http://localhost:3000 loads
# - "E-Commerce Demo" data source visible
# - Can click into it and see tables
```

### 6.2 Demo Script

**[0:00] Introduction**

> "Let me show you how Dataing works. I've got a sample e-commerce dataset here - 7 days of orders, events, user data."

**[0:30] Show Data Source**

> "Here's our data source. You can see the tables - users, orders, events, products. Pretty standard e-commerce schema."

*Click on "E-Commerce Demo" → Show tables list*

**[1:00] Start Investigation**

> "Let's say your data team noticed something weird with user attribution. Let's investigate the orders table."

*Click "New Investigation" → Select "orders" table → Click "Run"*

**[1:30] While Running**

> "Dataing is now analyzing the orders table. It's looking at schema, data distributions, temporal patterns, checking for anomalies."

*Show the investigation progress indicator*

**[2:00] Results**

> "Here we go. Dataing found a NULL spike in the user_id column. 41% of orders from January 10th to 12th have no user ID."

*Show results page with:*
- *Pattern type: NULL_SPIKE*
- *Severity: High (0.85)*
- *Affected rows: 892 of 5,023*

**[2:30] Root Cause**

> "And look at this - it's already identified the likely cause. 92% of affected orders came from mobile devices. This is probably a bug in the mobile app's checkout flow."

*Show root cause hypothesis section*

**[3:00] Impact**

> "Without Dataing, you'd find this when your marketing attribution dashboard shows weird numbers in 3 days. With Dataing, you'd catch it in minutes."

**[3:30] Close**

> "Want to see this on your actual data? We can set up a pilot in about an hour."

---

## 7. Directory Structure

```
dataing/
├── backend/
│   └── src/
│       └── dataing/
│           ├── adapters/
│           │   └── connectors/
│           │       ├── __init__.py        # Registry
│           │       ├── base.py            # ABC
│           │       ├── postgres.py
│           │       ├── trino.py
│           │       └── duckdb.py          # ← NEW
│           ├── demo/
│           │   ├── __init__.py
│           │   └── seed.py                # ← NEW
│           └── main.py                    # Demo mode check
│
├── frontend/
│   └── src/
│       └── components/
│           └── shared/
│               └── demo-badge.tsx         # ← NEW (optional)
│
├── demo/
│   ├── fixtures/
│   │   ├── baseline/
│   │   │   ├── users.parquet
│   │   │   ├── orders.parquet
│   │   │   └── ...
│   │   ├── null_spike/
│   │   │   └── ...
│   │   └── volume_drop/
│   │       └── ...
│   ├── generate.py                        # Fixture generator
│   ├── Dockerfile                         # For docker-compose
│   └── README.md
│
├── docker-compose.demo.yml                # ← NEW
├── Makefile                               # demo target
└── README.md
```

---

## 8. Implementation Checklist

### Phase 1: DuckDB Connector (Day 1 Morning)

- [ ] Install duckdb dependency in backend
- [ ] Create `duckdb.py` connector implementing BaseConnector
- [ ] Implement `connect()` with parquet directory auto-registration
- [ ] Implement `list_tables()`
- [ ] Implement `get_table_schema()`
- [ ] Implement `execute_query()` with timeout
- [ ] Implement `get_column_statistics()`
- [ ] Register in connector registry
- [ ] Unit test: connector can read parquet fixtures

### Phase 2: Demo Seed (Day 1 Afternoon)

- [ ] Create `demo/seed.py` with seed data constants
- [ ] Implement `seed_demo_data()` function
- [ ] Add demo mode check to `main.py` lifespan
- [ ] Test: `DATADR_DEMO_MODE=true` seeds data on startup
- [ ] Test: Seed is idempotent (can run twice safely)

### Phase 3: Demo Infrastructure (Day 2 Morning)

- [ ] Create `docker-compose.demo.yml`
- [ ] Add `demo` target to Makefile
- [ ] Test: `make demo` starts full stack
- [ ] Test: Frontend can see demo data source
- [ ] Test: Can list tables from demo data source

### Phase 4: End-to-End Test (Day 2 Afternoon)

- [ ] Generate fixtures (run fixture generator)
- [ ] Start demo stack
- [ ] Create new investigation via UI
- [ ] Verify investigation runs successfully
- [ ] Verify results show expected NULL spike
- [ ] Run through demo script once
- [ ] Fix any rough edges

### Phase 5: Polish (Day 3)

- [ ] Add demo badge to frontend (optional)
- [ ] Write demo README with troubleshooting
- [ ] Record demo video for async sharing
- [ ] Test on fresh machine (no cached state)

---

## 9. Troubleshooting Guide

### "Demo data source not showing"

```bash
# Check if seed ran
psql -d dataing_demo -c "SELECT * FROM datasources WHERE id LIKE 'demo%';"

# If empty, re-run seed
DATADR_DEMO_MODE=true python -m dataing.demo.seed
```

### "Can't connect to DuckDB"

```bash
# Check fixture path exists
ls -la demo/fixtures/null_spike/

# Should see:
# users.parquet
# orders.parquet
# ...

# If missing, generate fixtures
cd demo && python generate.py
```

### "Investigation takes forever"

```bash
# Check DuckDB is loading in-memory
# In backend logs, should see:
# "Loading parquet files into memory..."

# If loading from disk each query, check connector config
```

### "Results don't show anomaly"

```bash
# Verify fixtures have the anomaly
duckdb -c "
SELECT
    DATE_TRUNC('day', created_at) as day,
    ROUND(100.0 * SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) / COUNT(*), 1) as null_pct
FROM 'demo/fixtures/null_spike/orders.parquet'
GROUP BY 1
ORDER BY 1;
"

# Should show ~40% NULL on days 3-5
```

---

## 10. Future Enhancements (Post-Demo)

Not needed for initial demo, but nice to have:

1. **Scenario Switcher**: Dropdown in UI to switch between `null_spike`, `volume_drop`, etc.

2. **Reset Button**: "Reset Demo" button that clears investigations and re-seeds

3. **Guided Tour**: Tooltip walkthrough for first-time users ("Click here to start an investigation")

4. **Pre-computed Results**: Cache investigation results so they appear instantly (no 30s wait)

5. **Demo Analytics**: Track which demo scenarios prospects interact with most

---

## Acceptance Test Script

Run this after implementation to verify demo works:

```bash
#!/bin/bash
set -e

echo "=== Dataing Demo Acceptance Test ==="

# 1. Clean slate
echo "[1/7] Cleaning previous state..."
make demo-clean 2>/dev/null || true

# 2. Generate fixtures
echo "[2/7] Generating fixtures..."
cd demo && python generate.py && cd ..

# 3. Verify fixtures exist
echo "[3/7] Verifying fixtures..."
test -f demo/fixtures/null_spike/orders.parquet || (echo "FAIL: orders.parquet missing" && exit 1)

# 4. Start stack
echo "[4/7] Starting demo stack..."
docker compose -f docker-compose.demo.yml up -d

# 5. Wait for healthy
echo "[5/7] Waiting for services..."
sleep 10  # Replace with proper health check

# 6. Verify API
echo "[6/7] Checking API..."
curl -s http://localhost:8000/api/v1/health | grep -q "ok" || (echo "FAIL: API not healthy" && exit 1)

# 7. Verify demo data source
echo "[7/7] Checking demo data source..."
curl -s -H "X-API-Key: dd_demo_12345" http://localhost:8000/api/v1/datasources | grep -q "E-Commerce Demo" || (echo "FAIL: Demo datasource not found" && exit 1)

echo "=== ALL TESTS PASSED ==="
echo "Demo running at http://localhost:3000"
```

---

## Summary

| Component | Effort | Owner |
|-----------|--------|-------|
| DuckDB Connector | 3-4 hours | Backend |
| Demo Seed Script | 1-2 hours | Backend |
| docker-compose.demo.yml | 1 hour | DevOps/Backend |
| Makefile targets | 30 min | DevOps |
| Demo Badge (optional) | 1 hour | Frontend |
| End-to-end testing | 2-3 hours | QA/You |
| **Total** | **~1.5 days** | |

After this, `make demo` gives you a working sales demo with zero manual setup.
