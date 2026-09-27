# Apache Cassandra Integration

!!! warning "Not available yet"
    Cassandra is not yet offered as a data source in dataing. This page describes the
    planned integration.

Connect dataing to Apache Cassandra for distributed NoSQL data quality investigations.

---

## Overview

Cassandra integration enables:

- **Schema discovery** - Read table definitions from system tables
- **CQL queries** - Execute read-only CQL for investigations
- **Partition-aware scanning** - Efficient scans respecting partition structure
- **Wide-column support** - Handle dynamic columns and collections

---

## Prerequisites

- Apache Cassandra 3.11+ or DataStax Enterprise
- User with SELECT permissions
- Network access to Cassandra nodes

### Recommended Permissions

Create a read-only role:

```cql
CREATE ROLE dataing_reader WITH PASSWORD = 'secure-password' AND LOGIN = true;  -- pragma: allowlist secret

GRANT SELECT ON KEYSPACE your_keyspace TO dataing_reader;
```

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=cassandra
    export DATAING_CASSANDRA_HOSTS=node1.example.com,node2.example.com
    export DATAING_CASSANDRA_PORT=9042
    export DATAING_CASSANDRA_KEYSPACE=your_keyspace
    export DATAING_CASSANDRA_USERNAME=dataing_reader
    export DATAING_CASSANDRA_PASSWORD=secure-password
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.document.cassandra import CassandraAdapter

    adapter = CassandraAdapter({
        "hosts": "node1.example.com,node2.example.com",
        "port": 9042,
        "keyspace": "your_keyspace",
        "username": "dataing_reader",
        "password": "secure-password",  # pragma: allowlist secret
    })
    ```

### Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `hosts` | Yes | - | Comma-separated contact points |
| `port` | Yes | 9042 | Cassandra native port |
| `keyspace` | Yes | - | Default keyspace |
| `username` | Yes | - | Authentication username |
| `password` | Yes | - | Authentication password |
| `connection_timeout` | No | 30 | Timeout in seconds |
| `request_timeout` | No | 30 | Query timeout in seconds |

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Discovery | :material-check-circle:{ .green } | From system tables |
| CQL Execution | :material-check-circle:{ .green } | SELECT only |
| Token-range Scans | :material-check-circle:{ .green } | Partition-aware |
| Column Statistics | :material-check-circle:{ .green } | Via CQL aggregates |
| Materialized Views | :material-check-circle:{ .green } | Included in schema |
| UDTs | :material-check-circle:{ .green } | User-defined types |

---

## Cassandra Type Mapping

| Cassandra Type | dataing Type |
|----------------|--------------|
| ascii, text, varchar | string |
| bigint, int, smallint, tinyint, varint | integer |
| boolean | boolean |
| blob | binary |
| date | date |
| time | time |
| timestamp | timestamp |
| decimal, double, float | float |
| uuid, timeuuid | string |
| list, set | array |
| map | map |
| tuple, frozen | struct |

---

## Query Execution

### Basic CQL Queries

```python
# Execute CQL query
result = await adapter.execute_query(
    "SELECT * FROM orders WHERE user_id = ? LIMIT 100",
    params=["user_123"],
)
```

### Partition-Aware Scanning

```python
# Scan by partition key (efficient)
result = await adapter.execute_query(
    "SELECT * FROM orders WHERE user_id = ?",
    params=["user_123"],
)

# Full table scan (use with caution)
result = await adapter.execute_query(
    "SELECT * FROM orders LIMIT 1000",
)
```

### Aggregations

```python
# Count records (partition-aware)
result = await adapter.execute_query(
    "SELECT COUNT(*) FROM orders WHERE user_id = ?",
    params=["user_123"],
)
```

---

## Schema Discovery

dataing discovers schema from Cassandra system tables:

```python
schema = await adapter.get_schema()

# Result includes tables with:
# - Partition keys
# - Clustering columns
# - Regular columns
# - Static columns
# - Collection types
```

---

## Investigation Use Cases

### Detecting TTL Anomalies

```python
# Find records with specific TTL
result = await adapter.execute_query("""
    SELECT user_id, order_id, TTL(status) as ttl_remaining
    FROM orders
    WHERE user_id = ?
""", params=["user_123"])
```

### Finding Tombstones

```python
# Query with tracing to detect tombstones
result = await adapter.execute_query(
    "SELECT * FROM orders WHERE user_id = ? LIMIT 100",
    params=["user_123"],
    # Enable tracing in adapter
)
```

### Collection Size Analysis

```python
# Analyze collection sizes
result = await adapter.execute_query("""
    SELECT user_id, SIZE(tags) as tag_count
    FROM users
    WHERE user_id = ?
""", params=["user_123"])
```

---

## Performance Considerations

### Avoid Full Table Scans

```python
# Bad: Full table scan
result = await adapter.execute_query(
    "SELECT * FROM large_table",  # Avoid!
)

# Good: Partition-key filter
result = await adapter.execute_query(
    "SELECT * FROM large_table WHERE partition_key = ?",
    params=["value"],
)
```

### Use ALLOW FILTERING Carefully

```python
# Avoid when possible
result = await adapter.execute_query(
    "SELECT * FROM orders WHERE amount > 100 ALLOW FILTERING",
    # Full scan - use only for small tables
)
```

### Limit Result Sets

```python
# Always use LIMIT for investigation queries
result = await adapter.execute_query(
    "SELECT * FROM orders WHERE user_id = ? LIMIT 1000",
    params=["user_123"],
)
```

---

## Troubleshooting

### "Connection refused"

Verify Cassandra is running and accessible:

```bash
# Test with cqlsh
cqlsh node1.example.com 9042 -u dataing_reader -p password
```

### "Keyspace does not exist"

Check keyspace exists:

```cql
DESCRIBE KEYSPACES;
```

### "Unauthorized"

Verify permissions:

```cql
LIST ALL PERMISSIONS OF dataing_reader;
```

### "Read timed out"

Increase timeout or optimize query:

```python
adapter = CassandraAdapter({
    ...
    "request_timeout": 120,  # Increase timeout
})
```

### "Tombstone threshold exceeded"

Query smaller partitions or contact DBA to clean up tombstones:

```cql
-- Check tombstone warnings in logs
-- Consider running repairs or adjusting gc_grace_seconds
```

---

## Learn More

<div class="grid cards" markdown>

-   :material-database: **[MongoDB Integration](mongodb.md)**

    ---

    Connect to MongoDB

-   :material-aws: **[DynamoDB Integration](dynamodb.md)**

    ---

    Connect to Amazon DynamoDB

-   :material-shield: **[Security](../../security/data-privacy.md)**

    ---

    Data privacy and protection

</div>
