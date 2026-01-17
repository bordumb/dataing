# Trino Integration

Connect dataing to Trino clusters for distributed SQL querying across multiple data sources.

---

## Overview

Trino (formerly PrestoSQL) enables:

- **Federated queries** - Query data across multiple catalogs (Hive, Iceberg, Delta Lake, etc.)
- **Distributed processing** - Scale investigations across large datasets
- **Lake house access** - Investigate data in object storage

---

## Prerequisites

- Trino 400+ cluster
- Network access to Trino coordinator
- User with SELECT permissions on target catalogs/schemas

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=trino
    export DATAING_TRINO_HOST=trino.example.com
    export DATAING_TRINO_PORT=8080
    export DATAING_TRINO_CATALOG=hive
    export DATAING_TRINO_SCHEMA=default
    export DATAING_TRINO_USER=dataing
    # For authenticated clusters:
    export DATAING_TRINO_PASSWORD=password
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.sql.trino import TrinoAdapter

    # Basic configuration
    adapter = TrinoAdapter({
        "host": "trino.example.com",
        "port": 8080,
        "catalog": "hive",
        "schema": "default",
        "user": "dataing",
    })

    # With authentication
    adapter = TrinoAdapter({
        "host": "trino.example.com",
        "port": 443,
        "catalog": "iceberg",
        "schema": "analytics",
        "user": "dataing",
        "password": "secure-password",  # pragma: allowlist secret
        "http_scheme": "https",
        "verify": True,
    })
    ```

### Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `host` | Yes | - | Trino coordinator hostname |
| `port` | Yes | 8080 | Coordinator port |
| `catalog` | Yes | - | Default catalog (e.g., hive, iceberg) |
| `schema` | No | default | Default schema |
| `user` | Yes | - | Trino username |
| `password` | No | - | Password (if auth enabled) |
| `http_scheme` | No | http | Protocol (http or https) |
| `verify` | No | true | Verify SSL certificates |

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Discovery | :material-check-circle:{ .green } | Via information_schema |
| Column Statistics | :material-check-circle:{ .green } | Via SQL aggregates |
| Query Execution | :material-check-circle:{ .green } | SELECT only |
| Row Sampling | :material-check-circle:{ .green } | TABLESAMPLE BERNOULLI |
| Views | :material-check-circle:{ .green } | Included in schema |
| Cross-Catalog Queries | :material-check-circle:{ .green } | Full federated support |

---

## Catalog Configuration

Trino supports multiple catalogs. Common configurations:

### Hive Metastore

```properties
# catalog/hive.properties
connector.name=hive
hive.metastore.uri=thrift://metastore:9083
hive.s3.aws-access-key=...
hive.s3.aws-secret-key=...
```

### Iceberg

```properties
# catalog/iceberg.properties
connector.name=iceberg
iceberg.catalog.type=hive_metastore
hive.metastore.uri=thrift://metastore:9083
```

### Delta Lake

```properties
# catalog/delta.properties
connector.name=delta_lake
hive.metastore.uri=thrift://metastore:9083
```

---

## Query Execution

dataing executes queries using Trino SQL:

```sql
-- Cross-catalog query
SELECT
    h.id,
    h.amount,
    i.quantity
FROM hive.sales.orders h
JOIN iceberg.inventory.stock i ON h.product_id = i.product_id;

-- Sampling with TABLESAMPLE
SELECT * FROM hive.analytics.events
TABLESAMPLE BERNOULLI(10)
LIMIT 1000;

-- Schema discovery
SELECT table_schema, table_name, table_type
FROM hive.information_schema.tables
WHERE table_schema = 'analytics';
```

---

## Authentication

### No Authentication (Development)

```python
adapter = TrinoAdapter({
    "host": "localhost",
    "port": 8080,
    "catalog": "hive",
    "user": "dev",
})
```

### Password Authentication

```python
adapter = TrinoAdapter({
    "host": "trino.example.com",
    "port": 443,
    "catalog": "hive",
    "user": "dataing",
    "password": "secure-password",  # pragma: allowlist secret
    "http_scheme": "https",
})
```

### JWT/OAuth (via Headers)

For OAuth-based authentication, configure via environment:

```bash
export TRINO_EXTRA_HEADERS='{"Authorization": "Bearer <token>"}'
```

---

## Performance Considerations

### Query Limits

Trino queries can be resource-intensive. dataing applies:

- Default row limits on sampling
- Query timeouts to prevent runaway queries
- Selective column reads where possible

### Partitioning

When investigating partitioned tables:

```sql
-- Good: Filter on partition column
SELECT * FROM hive.logs.events
WHERE dt = '2024-01-15'
LIMIT 1000;

-- Avoid: Full table scans
SELECT * FROM hive.logs.events
LIMIT 1000;
```

---

## Troubleshooting

### "Connection refused"

Verify Trino coordinator is accessible:

```bash
curl http://trino.example.com:8080/v1/info
```

### "Catalog not found"

Check available catalogs:

```sql
SHOW CATALOGS;
```

### "Schema not found"

Verify schema exists in catalog:

```sql
SHOW SCHEMAS IN hive;
```

### "Access denied"

Check user permissions in Trino's access control:

```bash
# In Trino coordinator logs
tail -f /var/log/trino/server.log | grep ACCESS_DENIED
```

### "Query timed out"

Increase timeout or optimize query:

```python
result = await adapter.execute_query(
    "SELECT ...",
    timeout_seconds=300,  # 5 minutes
)
```

---

## Learn More

<div class="grid cards" markdown>

-   :material-duck: **[DuckDB Integration](duckdb.md)**

    ---

    Local analytical queries

-   :material-snowflake: **[Snowflake Integration](snowflake.md)**

    ---

    Cloud data warehouse

-   :material-hexagon-outline: **[Architecture](../../architecture/overview.md)**

    ---

    System overview and design

</div>
