# MongoDB Integration

Connect dataing to MongoDB for document-oriented data quality investigations.

---

## Overview

MongoDB integration enables:

- **Schema inference** - Automatically discover document structure from samples
- **Collection scanning** - Efficiently scan documents for anomalies
- **Aggregation pipelines** - Run complex analytical queries
- **Flexible schemas** - Handle schemaless data with mixed types

---

## Prerequisites

- MongoDB 4.0+ (or MongoDB Atlas)
- User with read access to target databases
- Network access to MongoDB instance

### Recommended Permissions

Create a read-only user:

```javascript
use admin
db.createUser({
  user: "dataing_reader",
  pwd: "secure-password",  // pragma: allowlist secret
  roles: [
    { role: "read", db: "your_database" }
  ]
})
```

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=mongodb
    export DATAING_MONGODB_CONNECTION_STRING="mongodb+srv://user:pass@cluster.mongodb.net"  # pragma: allowlist secret
    export DATAING_MONGODB_DATABASE=your_database
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.document.mongodb import MongoDBAdapter

    adapter = MongoDBAdapter({
        "connection_string": "mongodb+srv://user:pass@cluster.mongodb.net",  # pragma: allowlist secret
        "database": "your_database",
    })
    ```

### Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `connection_string` | Yes | Full MongoDB connection URI |
| `database` | Yes | Database name to connect to |

### Connection String Formats

```bash
# MongoDB Atlas
mongodb+srv://user:password@cluster.mongodb.net/database  # pragma: allowlist secret

# Self-hosted replica set
mongodb://user:password@host1:27017,host2:27017/database?replicaSet=rs0  # pragma: allowlist secret

# Single node
mongodb://user:password@localhost:27017/database  # pragma: allowlist secret
```

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Inference | :material-check-circle:{ .green } | Sample-based inference |
| Collection Scan | :material-check-circle:{ .green } | With filter support |
| Random Sampling | :material-check-circle:{ .green } | $sample aggregation |
| Aggregation Pipelines | :material-check-circle:{ .green } | Full pipeline support |
| Document Count | :material-check-circle:{ .green } | Accurate counts |
| SQL Queries | :material-close-circle:{ .red } | Use MQL instead |

---

## Schema Inference

MongoDB is schemaless, so dataing infers schema from document samples:

```python
# Infer schema from 100 document samples
schema = await adapter.infer_schema("orders", sample_size=100)

# Result
{
    "collection": "orders",
    "fields": {
        "_id": "string",
        "user_id": "string",
        "amount": "float",
        "items": "array",
        "metadata": "object",
        "status": "mixed"  # Multiple types detected
    }
}
```

Mixed types indicate data quality issues worth investigating.

---

## Querying Documents

### Scanning Collections

```python
# Scan with filter
result = await adapter.scan_collection(
    collection="orders",
    filter={"status": "completed"},
    limit=1000,
)
```

### Random Sampling

```python
# Get random sample for investigation
result = await adapter.sample(
    collection="orders",
    n=500,
)
```

### Aggregation Pipelines

```python
# Run aggregation pipeline
result = await adapter.aggregate(
    collection="orders",
    pipeline=[
        {"$match": {"created_at": {"$gte": "2024-01-01"}}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "total_amount": {"$sum": "$amount"}
        }},
        {"$sort": {"count": -1}}
    ]
)
```

---

## Investigation Use Cases

### Detecting Missing Fields

```python
# Find documents missing required fields
result = await adapter.aggregate(
    collection="users",
    pipeline=[
        {"$match": {"email": {"$exists": False}}},
        {"$count": "missing_email"}
    ]
)
```

### Finding Type Anomalies

```python
# Find documents where amount is not a number
result = await adapter.aggregate(
    collection="orders",
    pipeline=[
        {"$match": {
            "amount": {"$not": {"$type": "number"}}
        }},
        {"$limit": 100}
    ]
)
```

### Orphan Reference Detection

```python
# Find orders referencing non-existent users
result = await adapter.aggregate(
    collection="orders",
    pipeline=[
        {"$lookup": {
            "from": "users",
            "localField": "user_id",
            "foreignField": "_id",
            "as": "user"
        }},
        {"$match": {"user": {"$size": 0}}},
        {"$count": "orphaned_orders"}
    ]
)
```

---

## Troubleshooting

### "Authentication failed"

Verify connection string and credentials:

```bash
# Test with mongosh
mongosh "mongodb+srv://cluster.mongodb.net" --username user
```

### "Connection timed out"

Check network access:
- Verify IP whitelist on MongoDB Atlas
- Check firewall rules for self-hosted
- Ensure DNS resolution works

### "Collection not found"

List available collections:

```python
collections = await adapter._db.list_collection_names()
print(collections)
```

### "Type inference issues"

Increase sample size for better accuracy:

```python
schema = await adapter.infer_schema(
    "orders",
    sample_size=500,  # Larger sample
)
```

---

## Learn More

<div class="grid cards" markdown>

-   :material-aws: **[DynamoDB Integration](dynamodb.md)**

    ---

    Connect to Amazon DynamoDB

-   :material-database: **[Cassandra Integration](cassandra.md)**

    ---

    Connect to Apache Cassandra

-   :material-shield: **[Security](../../security/data-privacy.md)**

    ---

    Data privacy and protection

</div>
