# Amazon DynamoDB Integration

Connect dataing to Amazon DynamoDB for NoSQL data quality investigations.

---

## Overview

DynamoDB integration enables:

- **Schema inference** - Discover attribute structure from item samples
- **Table scanning** - Efficiently scan tables for anomalies
- **PartiQL queries** - Use SQL-like syntax for investigations
- **Key-value access** - Direct item lookups by primary key

---

## Prerequisites

- AWS account with DynamoDB access
- IAM user or role with read permissions
- Network access to DynamoDB (or local DynamoDB)

### Recommended IAM Policy

Create a read-only policy:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:Scan",
                "dynamodb:Query",
                "dynamodb:GetItem",
                "dynamodb:DescribeTable",
                "dynamodb:ListTables"
            ],
            "Resource": "arn:aws:dynamodb:*:*:table/*"
        }
    ]
}
```

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=dynamodb
    export DATAING_DYNAMODB_REGION=us-east-1
    export DATAING_DYNAMODB_ACCESS_KEY_ID=AKIA...
    export DATAING_DYNAMODB_SECRET_ACCESS_KEY=...
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.document.dynamodb import DynamoDBAdapter

    adapter = DynamoDBAdapter({
        "region": "us-east-1",
        "access_key_id": "AKIA...",
        "secret_access_key": "...",  # pragma: allowlist secret
    })

    # For local DynamoDB
    adapter = DynamoDBAdapter({
        "region": "local",
        "access_key_id": "dummy",
        "secret_access_key": "dummy",  # pragma: allowlist secret
        "endpoint_url": "http://localhost:8000",
    })
    ```

### Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `region` | Yes | - | AWS region (e.g., us-east-1) |
| `access_key_id` | Yes | - | AWS Access Key ID |
| `secret_access_key` | Yes | - | AWS Secret Access Key |
| `endpoint_url` | No | - | Custom endpoint (for local DynamoDB) |

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Inference | :material-check-circle:{ .green } | From item samples |
| Table Scan | :material-check-circle:{ .green } | With filter expressions |
| Query | :material-check-circle:{ .green } | On key attributes |
| Random Sampling | :material-check-circle:{ .green } | Via scan with limit |
| Item Count | :material-check-circle:{ .green } | Via table description |
| Global Indexes | :material-check-circle:{ .green } | GSI/LSI support |

---

## DynamoDB Type Mapping

| DynamoDB Type | dataing Type |
|---------------|--------------|
| S (String) | string |
| N (Number) | decimal |
| B (Binary) | binary |
| SS/NS/BS (Sets) | array |
| M (Map) | map |
| L (List) | array |
| BOOL | boolean |
| NULL | unknown |

---

## Schema Inference

DynamoDB is schemaless beyond keys. dataing infers structure from samples:

```python
# Infer schema from 100 item samples
schema = await adapter.infer_schema("orders", sample_size=100)

# Result
{
    "table": "orders",
    "key_schema": [
        {"name": "pk", "type": "HASH"},
        {"name": "sk", "type": "RANGE"}
    ],
    "attributes": {
        "pk": "string",
        "sk": "string",
        "order_id": "string",
        "amount": "decimal",
        "items": "array",
        "metadata": "map"
    }
}
```

---

## Querying Tables

### Table Scan

```python
# Scan with filter expression
result = await adapter.scan_table(
    table="orders",
    filter_expression="order_status = :status",
    expression_values={":status": {"S": "completed"}},
    limit=1000,
)
```

### Key-based Query

```python
# Query by partition key
result = await adapter.query(
    table="orders",
    key_condition="pk = :pk AND begins_with(sk, :prefix)",
    expression_values={
        ":pk": {"S": "USER#123"},
        ":prefix": {"S": "ORDER#"},
    },
)
```

### Sampling

```python
# Get random sample for investigation
result = await adapter.sample(
    table="orders",
    n=500,
)
```

---

## Investigation Use Cases

### Detecting Sparse Attributes

```python
# Find items missing expected attributes
result = await adapter.scan_table(
    table="users",
    filter_expression="attribute_not_exists(email)",
    limit=100,
)
```

### Finding Type Mismatches

```python
# Items where amount is not a number
result = await adapter.scan_table(
    table="orders",
    filter_expression="attribute_type(amount, :type)",
    expression_values={":type": {"S": "S"}},  # String instead of Number
    limit=100,
)
```

### Hot Partition Detection

Analyze partition key distribution:

```python
# Group by partition key prefix
result = await adapter.scan_table(
    table="orders",
    projection_expression="pk",
    limit=10000,
)

# Analyze distribution
from collections import Counter
prefixes = Counter(item["pk"].split("#")[0] for item in result.rows)
print(prefixes.most_common(10))
```

---

## Local Development

Use DynamoDB Local for testing:

```bash
# Run DynamoDB Local
docker run -p 8000:8000 amazon/dynamodb-local

# Configure dataing
adapter = DynamoDBAdapter({
    "region": "local",
    "access_key_id": "dummy",
    "secret_access_key": "dummy",  # pragma: allowlist secret
    "endpoint_url": "http://localhost:8000",
})
```

---

## Troubleshooting

### "Access denied"

Verify IAM permissions:

```bash
# Test with AWS CLI
aws dynamodb list-tables --region us-east-1
aws dynamodb describe-table --table-name your_table --region us-east-1
```

### "Table not found"

Check table exists in the correct region:

```bash
aws dynamodb list-tables --region us-east-1
```

### "Throughput exceeded"

DynamoDB has capacity limits. Reduce scan rate:

```python
# Add delay between operations
result = await adapter.scan_table(
    table="orders",
    limit=100,  # Smaller batches
)
```

### "Signature mismatch"

Check credentials are correct and not expired:

```bash
# Verify credentials
aws sts get-caller-identity
```

---

## Learn More

<div class="grid cards" markdown>

-   :material-database: **[MongoDB Integration](mongodb.md)**

    ---

    Connect to MongoDB

-   :material-database: **[Cassandra Integration](cassandra.md)**

    ---

    Connect to Apache Cassandra

-   :material-shield: **[Security](../../security/data-privacy.md)**

    ---

    Data privacy and protection

</div>
