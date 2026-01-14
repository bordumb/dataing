# Snowflake Integration

Connect dataing to Snowflake for AI-powered data quality investigations.

---

## Prerequisites

- Snowflake account with active warehouse
- User with SELECT access to target tables
- `USAGE` grant on warehouse, database, and schema

### Recommended Permissions

```sql
-- Create a dedicated role for dataing
CREATE ROLE dataing_role;

-- Grant access to warehouse
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE dataing_role;

-- Grant access to database and schema
GRANT USAGE ON DATABASE analytics TO ROLE dataing_role;
GRANT USAGE ON SCHEMA analytics.public TO ROLE dataing_role;

-- Grant SELECT on tables (read-only)
GRANT SELECT ON ALL TABLES IN SCHEMA analytics.public TO ROLE dataing_role;
GRANT SELECT ON FUTURE TABLES IN SCHEMA analytics.public TO ROLE dataing_role;

-- Create user for dataing
CREATE USER dataing_user
  PASSWORD = 'secure_password'
  DEFAULT_ROLE = dataing_role;

GRANT ROLE dataing_role TO USER dataing_user;
```

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=snowflake
    export DATAING_SNOWFLAKE_ACCOUNT=xy12345.us-east-1
    export DATAING_SNOWFLAKE_USER=dataing_user
    export DATAING_SNOWFLAKE_PASSWORD=secure_password
    export DATAING_SNOWFLAKE_DATABASE=analytics
    export DATAING_SNOWFLAKE_SCHEMA=public
    export DATAING_SNOWFLAKE_WAREHOUSE=COMPUTE_WH
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.sql.snowflake import SnowflakeAdapter

    adapter = SnowflakeAdapter(
        account="xy12345.us-east-1",
        user="dataing_user",
        password="secure_password",
        database="analytics",
        schema="public",
        warehouse="COMPUTE_WH",
    )
    ```

=== "Connection String"

    ```
    snowflake://dataing_user:password@xy12345.us-east-1/analytics/public?warehouse=COMPUTE_WH
    ```

### Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `account` | Yes | Snowflake account identifier (e.g., `xy12345.us-east-1`) |
| `user` | Yes | Username for authentication |
| `password` | Yes | Password for authentication |
| `database` | Yes | Default database |
| `schema` | No | Default schema (defaults to `PUBLIC`) |
| `warehouse` | Yes | Virtual warehouse to use |
| `role` | No | Role to assume (optional) |

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Discovery | :material-check-circle:{ .green } | Full table/column metadata |
| Column Statistics | :material-check-circle:{ .green } | Via INFORMATION_SCHEMA |
| Query Execution | :material-check-circle:{ .green } | SELECT only |
| Partitioned Tables | :material-check-circle:{ .green } | Clustering key aware |
| External Tables | :material-check-circle:{ .green } | Read-only access |
| Secure Views | :material-check-circle:{ .green } | Respects view permissions |

---

## Example Investigation

```python
import asyncio
from dataing.core.investigation.service import InvestigationService
from dataing.core.domain_types import AnomalyAlert

async def investigate_null_spike():
    alert = AnomalyAlert(
        table="orders",
        column="user_id",
        metric="null_rate",
        anomaly_type="spike",
        description="NULL rate increased from 1% to 15%"
    )

    service = InvestigationService()
    result = await service.investigate(alert)

    print(f"Root cause: {result.synthesis.root_cause}")

asyncio.run(investigate_null_spike())
```

---

## Troubleshooting

### "Authentication failed"

Check that:

- Account identifier includes region (e.g., `xy12345.us-east-1`)
- Password is correct
- User is not locked

### "Warehouse not found"

Ensure the warehouse exists and your user has `USAGE` grant:

```sql
SHOW WAREHOUSES;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE dataing_role;
```

### "Insufficient privileges"

Grant SELECT on the target tables:

```sql
GRANT SELECT ON TABLE analytics.public.orders TO ROLE dataing_role;
```

### Slow Queries

If queries are slow, consider:

- Using a larger warehouse size
- Adding clustering keys on filter columns
- Checking query history for concurrency issues

---

## Learn More

<div class="grid cards" markdown>

-   :material-google-cloud: **[BigQuery Integration](bigquery.md)**

    ---

    Connect to Google BigQuery

-   :material-hexagon-outline: **[Architecture](../../architecture.md)**

    ---

    System overview and design

-   :material-shield: **[Security](../../security/data-privacy.md)**

    ---

    Data privacy and protection

</div>
