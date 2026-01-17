# MySQL Integration

Connect dataing to MySQL databases for AI-powered data quality investigations.

---

## Prerequisites

- MySQL 5.7+ or MariaDB 10.2+
- User with SELECT permissions on target databases
- Network access to MySQL server

### Recommended Permissions

Create a read-only user for dataing:

```sql
-- Create user
CREATE USER 'dataing_reader'@'%' IDENTIFIED BY 'secure-password';

-- Grant read access
GRANT SELECT ON your_database.* TO 'dataing_reader'@'%';

-- For schema discovery
GRANT SELECT ON information_schema.* TO 'dataing_reader'@'%';

FLUSH PRIVILEGES;
```

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=mysql
    export DATAING_MYSQL_HOST=localhost
    export DATAING_MYSQL_PORT=3306
    export DATAING_MYSQL_DATABASE=your_database
    export DATAING_MYSQL_USERNAME=dataing_reader
    export DATAING_MYSQL_PASSWORD=secure-password
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.sql.mysql import MySQLAdapter

    adapter = MySQLAdapter({
        "host": "localhost",
        "port": 3306,
        "database": "your_database",
        "username": "dataing_reader",
        "password": "secure-password",  # pragma: allowlist secret
        "ssl": True,  # Optional
        "connection_timeout": 30,  # Optional
    })
    ```

### Configuration Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `host` | Yes | - | MySQL server hostname |
| `port` | Yes | 3306 | MySQL server port |
| `database` | Yes | - | Database name to connect to |
| `username` | Yes | - | MySQL username |
| `password` | Yes | - | MySQL password |
| `ssl` | No | false | Enable SSL/TLS connection |
| `connection_timeout` | No | 30 | Connection timeout in seconds |

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Discovery | :material-check-circle:{ .green } | Full table/column metadata |
| Column Statistics | :material-check-circle:{ .green } | Via INFORMATION_SCHEMA |
| Query Execution | :material-check-circle:{ .green } | SELECT only |
| Row Sampling | :material-check-circle:{ .green } | ORDER BY RAND() |
| Views | :material-check-circle:{ .green } | Included in schema |
| Stored Procedures | :material-close-circle:{ .red } | Not supported |

---

## SSL/TLS Configuration

For production deployments, enable SSL:

```python
adapter = MySQLAdapter({
    "host": "mysql.example.com",
    "port": 3306,
    "database": "production",
    "username": "dataing_reader",
    "password": "secure-password",  # pragma: allowlist secret
    "ssl": True,
})
```

For custom CA certificates, configure via environment:

```bash
export MYSQL_SSL_CA=/path/to/ca-cert.pem
```

---

## Query Execution

dataing executes read-only queries with timeouts:

```sql
-- Query timeout is enforced via
SET max_execution_time = 30000;  -- 30 seconds

-- Example investigation query
SELECT
    COUNT(*) as total,
    COUNT(user_id) as non_null,
    COUNT(DISTINCT user_id) as distinct_count
FROM orders
WHERE created_at >= '2024-01-01';
```

---

## Troubleshooting

### "Access denied for user"

Verify credentials and permissions:

```sql
-- Check user grants
SHOW GRANTS FOR 'dataing_reader'@'%';

-- Test connection
mysql -h hostname -u dataing_reader -p
```

### "Unknown database"

Check that the database exists:

```sql
SHOW DATABASES;
```

### "Connection timed out"

- Verify network connectivity to MySQL server
- Check firewall rules allow port 3306
- Increase `connection_timeout` if needed

### "SSL connection error"

For SSL issues:

```bash
# Test SSL connection
mysql -h hostname -u user -p --ssl-mode=REQUIRED

# Check server SSL support
SHOW VARIABLES LIKE '%ssl%';
```

---

## Learn More

<div class="grid cards" markdown>

-   :material-database: **[PostgreSQL Integration](postgres.md)**

    ---

    Connect to PostgreSQL databases

-   :material-database-search: **[BigQuery Integration](bigquery.md)**

    ---

    Connect to Google BigQuery

-   :material-shield: **[Security](../../security/data-privacy.md)**

    ---

    Data privacy and protection

</div>
