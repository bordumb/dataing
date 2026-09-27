# Google Cloud Storage Integration

Query Parquet, CSV, and JSON files directly from GCS using SQL.

---

## Overview

GCS integration enables:

- **Direct file queries** - Query files in-place without ETL
- **Schema inference** - Automatically detect file schemas
- **SQL on files** - Use familiar SQL syntax via DuckDB
- **GCP integration** - Works with Google Cloud ecosystem

---

## Prerequisites

- Google Cloud project with GCS enabled
- Service account with read access
- HMAC key for that service account
- Files in supported formats (Parquet, CSV, JSON)

### Service Account Setup

dataing reads GCS through DuckDB, which authenticates with an
[HMAC key](https://cloud.google.com/storage/docs/authentication/managing-hmackeys).
Create a service account with minimal permissions and an HMAC key for it:

```bash
# Create service account
gcloud iam service-accounts create dataing-reader \
  --display-name="dataing Data Reader"

# Grant Storage Object Viewer role
gsutil iam ch \
  serviceAccount:dataing-reader@PROJECT_ID.iam.gserviceaccount.com:objectViewer \
  gs://your-bucket

# Create an HMAC key (prints the access ID and secret; the secret is shown once)
gcloud storage hmac create dataing-reader@PROJECT_ID.iam.gserviceaccount.com
```

You can also create the key in the console under
**Cloud Storage > Settings > Interoperability**.

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=gcs
    export DATAING_GCS_BUCKET=my-data-bucket
    export DATAING_GCS_PREFIX=data/warehouse/
    export DATAING_GCS_HMAC_ACCESS_ID=GOOG1E...
    export DATAING_GCS_HMAC_SECRET=...
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.filesystem.gcs import GCSAdapter

    adapter = GCSAdapter({
        "bucket": "my-data-bucket",
        "prefix": "data/warehouse/",
        "hmac_access_id": "GOOG1E...",
        "hmac_secret": "...",
        "file_format": "auto",
    })
    ```

### Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `bucket` | Yes | - | GCS bucket name |
| `prefix` | No | - | Path prefix to limit scope |
| `hmac_access_id` | Yes | - | Access ID of the service account's HMAC key |
| `hmac_secret` | Yes | - | Secret of that HMAC key |
| `file_format` | No | auto | Default format for files |

The key is stored as a DuckDB secret scoped to `gs://<bucket>/<prefix>/`, so it is
only sent with requests for the source's own objects.

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Discovery | :material-check-circle:{ .green } | Per-file inference |
| SQL Queries | :material-check-circle:{ .green } | Via DuckDB |
| File Listing | :material-check-circle:{ .green } | With pattern matching |
| Parquet | :material-check-circle:{ .green } | Full support |
| CSV | :material-check-circle:{ .green } | Auto-header detection |
| JSON/JSONL | :material-check-circle:{ .green } | Line-delimited JSON |

---

## Querying Files

### Single File Query

```python
# Query a specific Parquet file
result = await adapter.execute_query("""
    SELECT *
    FROM read_parquet('gs://my-bucket/data/orders.parquet')
    LIMIT 100
""")
```

### Pattern-Based Query

```python
# Query all Parquet files in a directory
result = await adapter.execute_query("""
    SELECT *
    FROM read_parquet('gs://my-bucket/data/orders/*.parquet')
    WHERE order_date >= '2024-01-01'
""")
```

### Hive-Partitioned Data

```python
# Query partitioned data
result = await adapter.execute_query("""
    SELECT *
    FROM read_parquet('gs://my-bucket/data/orders/year=2024/month=01/*.parquet')
""")
```

---

## File Formats

### Parquet (Recommended)

```python
# Parquet with predicate pushdown
result = await adapter.execute_query("""
    SELECT order_id, amount
    FROM read_parquet('gs://bucket/orders.parquet')
    WHERE amount > 100
""")
```

### CSV

```python
# CSV with auto-detection
result = await adapter.execute_query("""
    SELECT *
    FROM read_csv_auto('gs://bucket/data.csv')
    LIMIT 100
""")
```

### JSON/JSONL

```python
# Line-delimited JSON
result = await adapter.execute_query("""
    SELECT *
    FROM read_json_auto('gs://bucket/events.jsonl')
    LIMIT 100
""")
```

---

## Schema Discovery

```python
# List files in bucket
files = await adapter.list_files(pattern="*.parquet")

# Infer schema for a file
table = await adapter.infer_schema("gs://bucket/orders.parquet")

# Get full schema (all files as tables)
schema = await adapter.get_schema()
```

---

## Investigation Use Cases

### Data Quality Checks

```python
result = await adapter.execute_query("""
    SELECT
        date_trunc('day', created_at) as day,
        COUNT(*) as total,
        SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as null_count
    FROM read_parquet('gs://bucket/events/*.parquet')
    GROUP BY 1
    ORDER BY 1
""")
```

### Cross-File Analysis

```python
# Join data across files
result = await adapter.execute_query("""
    SELECT o.*, p.name as product_name
    FROM read_parquet('gs://bucket/orders/*.parquet') o
    JOIN read_parquet('gs://bucket/products.parquet') p
        ON o.product_id = p.id
""")
```

---

## Troubleshooting

### "Permission denied"

Verify service account permissions:

```bash
# Test with gsutil
gsutil ls gs://your-bucket/
gsutil cat gs://your-bucket/test.parquet | head
```

### "Bucket not found"

Check bucket exists and is accessible:

```bash
gsutil ls -b gs://your-bucket
```

### "Invalid credentials"

Check that the HMAC key exists and is active:

```bash
gcloud storage hmac describe GOOG1E...
```

### "File format error"

Ensure file format is correct:

```python
# Explicit format selection
result = await adapter.read_file(
    "gs://bucket/data.parquet",
    file_format="parquet",
)
```

---

## Learn More

<div class="grid cards" markdown>

-   :material-aws: **[S3 Integration](s3.md)**

    ---

    Connect to Amazon S3

-   :material-harddisk: **[HDFS Integration](hdfs.md)**

    ---

    Connect to Hadoop HDFS

-   :material-folder: **[Local Files](local.md)**

    ---

    Query local filesystem

</div>
