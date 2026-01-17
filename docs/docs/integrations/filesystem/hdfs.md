# HDFS Integration

Query Parquet, CSV, and JSON files from Hadoop Distributed File System using SQL.

---

## Overview

HDFS integration enables:

- **Hadoop ecosystem access** - Query data in your data lake
- **SQL on files** - Use familiar SQL syntax via DuckDB
- **Large-scale data** - Efficient queries on distributed files
- **Kerberos support** - Enterprise authentication

---

## Prerequisites

- Hadoop cluster with HDFS 2.x or 3.x
- Network access to NameNode
- User with read access to target directories
- Optional: Kerberos credentials

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=hdfs
    export DATAING_HDFS_NAMENODE_HOST=namenode.example.com
    export DATAING_HDFS_NAMENODE_PORT=9000
    export DATAING_HDFS_PATH=/user/data/warehouse
    export DATAING_HDFS_USERNAME=dataing
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.filesystem.hdfs import HDFSAdapter

    # Simple authentication
    adapter = HDFSAdapter({
        "namenode_host": "namenode.example.com",
        "namenode_port": 9000,
        "path": "/user/data/warehouse",
        "username": "dataing",
    })

    # Kerberos authentication
    adapter = HDFSAdapter({
        "namenode_host": "namenode.example.com",
        "namenode_port": 9000,
        "path": "/user/data/warehouse",
        "kerberos_enabled": True,
        "kerberos_principal": "dataing@REALM.COM",
        "kerberos_keytab": "/path/to/dataing.keytab",
    })
    ```

### Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `namenode_host` | Yes | - | NameNode hostname |
| `namenode_port` | Yes | 9000 | NameNode port (9000 or 8020) |
| `path` | Yes | - | Base HDFS path to query |
| `username` | No | - | HDFS username (simple auth) |
| `kerberos_enabled` | No | false | Enable Kerberos auth |
| `kerberos_principal` | No | - | Kerberos principal |
| `kerberos_keytab` | No | - | Path to keytab file |
| `file_format` | No | auto | Default file format |

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Discovery | :material-check-circle:{ .green } | Per-file inference |
| SQL Queries | :material-check-circle:{ .green } | Via DuckDB |
| File Listing | :material-check-circle:{ .green } | Recursive support |
| Parquet | :material-check-circle:{ .green } | Full support |
| CSV | :material-check-circle:{ .green } | Auto-header detection |
| JSON/JSONL | :material-check-circle:{ .green } | Line-delimited JSON |
| Kerberos | :material-check-circle:{ .green } | Enterprise auth |

---

## Querying Files

### Single File Query

```python
result = await adapter.execute_query("""
    SELECT *
    FROM read_parquet('hdfs://namenode:9000/user/data/orders.parquet')
    LIMIT 100
""")
```

### Directory Query

```python
# Query all Parquet files in directory
result = await adapter.execute_query("""
    SELECT *
    FROM read_parquet('hdfs://namenode:9000/user/data/orders/*.parquet')
    WHERE order_date >= '2024-01-01'
""")
```

### Hive-Partitioned Data

```python
# Query partitioned Hive tables
result = await adapter.execute_query("""
    SELECT *
    FROM read_parquet(
        'hdfs://namenode:9000/user/hive/warehouse/orders/year=2024/month=01/*.parquet'
    )
""")
```

---

## Authentication

### Simple Authentication

For development clusters without security:

```python
adapter = HDFSAdapter({
    "namenode_host": "namenode.example.com",
    "namenode_port": 9000,
    "path": "/user/data",
    "username": "hdfs",  # or your hadoop username
})
```

### Kerberos Authentication

For secure Hadoop clusters:

```bash
# First, obtain a Kerberos ticket
kinit dataing@REALM.COM

# Or use a keytab
kinit -kt /path/to/dataing.keytab dataing@REALM.COM
```

```python
adapter = HDFSAdapter({
    "namenode_host": "namenode.example.com",
    "namenode_port": 9000,
    "path": "/user/data",
    "kerberos_enabled": True,
    "kerberos_principal": "dataing@REALM.COM",
    "kerberos_keytab": "/path/to/dataing.keytab",
})
```

---

## NameNode Configuration

### Standard Port

Most clusters use port 9000:

```python
adapter = HDFSAdapter({
    "namenode_host": "namenode.example.com",
    "namenode_port": 9000,
    ...
})
```

### CDH/HDP Default

Some distributions use port 8020:

```python
adapter = HDFSAdapter({
    "namenode_host": "namenode.example.com",
    "namenode_port": 8020,
    ...
})
```

### HA NameNode

For clusters with NameNode HA, use the active NameNode:

```python
adapter = HDFSAdapter({
    "namenode_host": "active-namenode.example.com",
    "namenode_port": 9000,
    ...
})
```

---

## Investigation Use Cases

### Data Quality Checks

```python
result = await adapter.execute_query("""
    SELECT
        date_trunc('day', event_time) as day,
        COUNT(*) as total,
        SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as null_count
    FROM read_parquet('hdfs://namenode:9000/user/data/events/*.parquet')
    GROUP BY 1
    ORDER BY 1 DESC
    LIMIT 30
""")
```

### File Format Analysis

```python
# List all files
files = await adapter.list_files(pattern="*.parquet")

for f in files:
    print(f"{f.name}: {f.size_bytes} bytes, modified {f.last_modified}")
```

---

## Troubleshooting

### "Connection refused"

Verify NameNode is accessible:

```bash
# Test connectivity
telnet namenode.example.com 9000

# Check HDFS health
hdfs dfsadmin -report
```

### "Permission denied"

Check HDFS permissions:

```bash
# List directory permissions
hdfs dfs -ls /user/data

# Check your user
hdfs dfs -ls /user/$USER
```

### "Kerberos authentication failed"

Verify tickets:

```bash
# Check existing tickets
klist

# Renew or obtain new ticket
kinit dataing@REALM.COM
```

### "NameNode not found"

Ensure you're connecting to the correct NameNode:

```bash
# Check NameNode status
hdfs haadmin -getServiceState nn1
hdfs haadmin -getServiceState nn2
```

---

## Learn More

<div class="grid cards" markdown>

-   :material-aws: **[S3 Integration](s3.md)**

    ---

    Connect to Amazon S3

-   :material-google-cloud: **[GCS Integration](gcs.md)**

    ---

    Connect to Google Cloud Storage

-   :material-folder: **[Local Files](local.md)**

    ---

    Query local filesystem

</div>
