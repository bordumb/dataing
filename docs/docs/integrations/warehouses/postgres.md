# PostgreSQL Integration

Connect dataing to PostgreSQL for AI-powered data quality investigations.

---

## Prerequisites

- PostgreSQL 12+ server
- User with SELECT access to target tables
- Network access from dataing to PostgreSQL server

### Recommended Permissions

```sql
-- Create a read-only role for dataing
CREATE ROLE dataing_reader;

-- Grant connect to database
GRANT CONNECT ON DATABASE analytics TO dataing_reader;

-- Grant usage on schema
GRANT USAGE ON SCHEMA public TO dataing_reader;

-- Grant SELECT on all tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dataing_reader;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO dataing_reader;

-- Grant for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO dataing_reader;

-- Create user
CREATE USER dataing_user WITH PASSWORD 'secure_password';
GRANT dataing_reader TO dataing_user;
```

---

## Configuration

=== "Environment Variables"

    ```bash
    export DATAING_DATASOURCE=postgres
    export DATAING_POSTGRES_HOST=localhost
    export DATAING_POSTGRES_PORT=5432
    export DATAING_POSTGRES_USER=dataing_user
    export DATAING_POSTGRES_PASSWORD=secure_password
    export DATAING_POSTGRES_DATABASE=analytics
    export DATAING_POSTGRES_SCHEMA=public
    ```

=== "Python SDK"

    ```python
    from dataing.adapters.datasource.sql.postgres import PostgresAdapter

    adapter = PostgresAdapter(
        host="localhost",
        port=5432,
        user="dataing_user",
        password="secure_password",
        database="analytics",
        schema="public",
    )
    ```

=== "Connection String"

    ```bash
    export DATAING_POSTGRES_URL=postgresql://dataing_user:password@localhost:5432/analytics
    ```

### Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `host` | Yes | PostgreSQL server hostname |
| `port` | No | Port number (default: 5432) |
| `user` | Yes | Username for authentication |
| `password` | Yes | Password for authentication |
| `database` | Yes | Database name |
| `schema` | No | Default schema (default: public) |
| `sslmode` | No | SSL mode (disable, require, verify-ca, verify-full) |

---

## Supported Features

| Feature | Status | Notes |
|---------|--------|-------|
| Schema Discovery | :material-check-circle:{ .green } | Full table/column metadata |
| Column Statistics | :material-check-circle:{ .green } | Via pg_stats |
| Query Execution | :material-check-circle:{ .green } | SELECT only |
| Partitioned Tables | :material-check-circle:{ .green } | Native partitioning |
| Views | :material-check-circle:{ .green } | Including materialized views |
| Foreign Tables | :material-check-circle:{ .green } | Via postgres_fdw |

---

## SSL Configuration

For production deployments, enable SSL:

```bash
# Require SSL
export DATAING_POSTGRES_SSLMODE=require

# Verify server certificate
export DATAING_POSTGRES_SSLMODE=verify-ca
export DATAING_POSTGRES_SSLROOTCERT=/path/to/ca.crt
```

---

## Troubleshooting

### "Connection refused"

Check that:

- PostgreSQL is running and accepting connections
- Host and port are correct
- Firewall allows connections

```bash
# Test connection
psql -h localhost -p 5432 -U dataing_user -d analytics
```

### "Authentication failed"

Verify pg_hba.conf allows your connection method:

```
# PostgreSQL pg_hba.conf
host    analytics    dataing_user    0.0.0.0/0    md5
```

### "Permission denied"

Grant SELECT on the target tables:

```sql
GRANT SELECT ON TABLE public.orders TO dataing_reader;
```

---

## Learn More

- [Snowflake Integration](snowflake.md)
- [Architecture](../../architecture.md)
- [Security](../../security/data-privacy.md)
