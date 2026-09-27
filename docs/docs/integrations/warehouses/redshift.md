# Amazon Redshift Integration

Connect dataing to Amazon Redshift data warehouses for AI-powered data quality investigations.

---

## Prerequisites

- Amazon Redshift cluster (RA3, DC2, or Serverless)
- User with SELECT permissions on target schemas
- Network access (VPC peering, public endpoint, or bastion)

### Recommended Permissions

Create a read-only user for dataing:

```sql
-- Create user
CREATE USER dataing_reader PASSWORD 'secure-password';  -- pragma: allowlist secret

-- Grant schema usage
GRANT USAGE ON SCHEMA public TO dataing_reader;
GRANT USAGE ON SCHEMA analytics TO dataing_reader;

-- Grant table access
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dataing_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO dataing_reader;

-- For future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO dataing_reader;
```

Schema discovery lists only the tables this user has privileges on, so these grants
also decide which schemas dataing sees.

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=redshift
    export DATAING_REDSHIFT_HOST=cluster.region.redshift.amazonaws.com
    export DATAING_REDSHIFT_PORT=5439
    export DATAING_REDSHIFT_DATABASE=dev
    export DATAING_REDSHIFT_USERNAME=dataing_reader
    export DATAING_REDSHIFT_PASSWORD=secure-password
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.sql.redshift import RedshiftAdapter

    adapter = RedshiftAdapter({
        "host": "cluster.region.redshift.amazonaws.com",
        "port": 5439,
        "database": "dev",
        "username": "dataing_reader",
        "password": "secure-password",  # pragma: allowlist secret
        "ssl_mode": "require",  # Optional
    })
    ```

### Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `host` | Yes | - | Redshift cluster endpoint |
| `port` | Yes | 5439 | Redshift port |
| `database` | Yes | - | Database name |
| `username` | Yes | - | Database username |
| `password` | Yes | - | Database password |
| `ssl_mode` | No | require | SSL mode (disable, require, verify-ca, verify-full) |
| `connection_timeout` | No | 30 | Connection timeout in seconds |

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Discovery | :material-check-circle:{ .green } | Full table/column metadata |
| Column Statistics | :material-check-circle:{ .green } | Via system tables |
| Query Execution | :material-check-circle:{ .green } | SELECT only |
| Row Sampling | :material-check-circle:{ .green } | ORDER BY RANDOM() |
| Views | :material-check-circle:{ .green } | Including late-binding views |
| External Tables | :material-check-circle:{ .green } | Spectrum tables |
| Materialized Views | :material-check-circle:{ .green } | Included in schema |

---

## SSL Configuration

Redshift requires SSL by default. The `ssl_mode` options are:

| Mode | Description |
|------|-------------|
| `disable` | No SSL (not recommended) |
| `require` | SSL required, no cert verification |
| `verify-ca` | Verify server certificate |
| `verify-full` | Verify cert + hostname |

For production, use `verify-ca` or `verify-full`:

```python
adapter = RedshiftAdapter({
    "host": "cluster.region.redshift.amazonaws.com",
    "port": 5439,
    "database": "prod",
    "username": "dataing_reader",
    "password": "secure-password",  # pragma: allowlist secret
    "ssl_mode": "verify-full",
})
```

---

## Network Access

### VPC Peering

For clusters in a VPC:

1. Set up VPC peering between dataing and Redshift VPC
2. Update route tables in both VPCs
3. Add security group rule allowing inbound on port 5439

### Public Endpoint

For publicly accessible clusters:

1. Enable "Publicly accessible" in cluster settings
2. Ensure security group allows your IP on port 5439
3. Use the public endpoint in configuration

### Bastion Host / SSH Tunnel

```bash
# Create SSH tunnel
ssh -L 5439:cluster.region.redshift.amazonaws.com:5439 user@bastion

# Configure dataing to use localhost
export DATAING_REDSHIFT_HOST=localhost
```

---

## Query Execution

dataing uses PostgreSQL-compatible queries with Redshift extensions:

```sql
-- Query timeout enforcement
SET statement_timeout = 30000;  -- 30 seconds

-- Example investigation query
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as null_count,
    COUNT(DISTINCT user_id) as distinct_count
FROM analytics.orders
WHERE created_at >= '2024-01-01';
```

---

## Troubleshooting

### "Connection refused"

- Verify cluster is running and endpoint is correct
- Check security group allows your IP
- Ensure cluster is publicly accessible (if not using VPC peering)

### "Authentication failed"

```sql
-- Check user exists
SELECT * FROM pg_user WHERE usename = 'dataing_reader';

-- Reset password if needed
ALTER USER dataing_reader PASSWORD 'new-password';  -- pragma: allowlist secret
```

### "Permission denied for schema"

```sql
-- Grant schema access
GRANT USAGE ON SCHEMA schema_name TO dataing_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA schema_name TO dataing_reader;
```

### "Query cancelled due to timeout"

Increase the query timeout or optimize your queries:

```python
result = await adapter.execute_query(
    "SELECT ...",
    timeout_seconds=120,  # Increase timeout
)
```

---

## Learn More

<div class="grid cards" markdown>

-   :material-snowflake: **[Snowflake Integration](snowflake.md)**

    ---

    Connect to Snowflake

-   :material-database-search: **[BigQuery Integration](bigquery.md)**

    ---

    Connect to Google BigQuery

-   :material-shield: **[Security](../../security/data-privacy.md)**

    ---

    Data privacy and protection

</div>
