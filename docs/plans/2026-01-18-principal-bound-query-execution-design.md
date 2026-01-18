# Principal-Bound Query Execution Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure all SQL queries execute with user credentials, enforced by the database—not Dataing.

**Architecture:** Single query gateway requires a principal (user) for every query. Users store their own datasource credentials. The warehouse enforces permissions.

**Tech Stack:** Python, FastAPI, SQLAlchemy, Fernet encryption

---

## Overview

Dataing adopts the "SQL IDE" model: users enter their database credentials once, Dataing remembers them (encrypted), and all queries run as that user. The database is the source of truth for permissions.

### Key Principles

1. **Single execution gateway** - One function executes all SQL, requires a principal
2. **User credentials, not service accounts** - Each user connects with their own DB creds
3. **DB-native enforcement** - Warehouse enforces permissions, not Dataing
4. **No credentials = no queries** - Strict, no fallback
5. **Audit everything** - Every query logged with who/what/when

---

## Data Model

### New table: `user_datasource_credentials`

```sql
CREATE TABLE user_datasource_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    datasource_id UUID NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,

    -- Encrypted credential blob (JSON with username, password, role, etc.)
    credentials_encrypted BYTEA NOT NULL,

    -- Metadata (not sensitive)
    db_username VARCHAR(255),  -- For display only, not used for auth
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,

    UNIQUE(user_id, datasource_id)
);

CREATE INDEX idx_user_ds_creds_user ON user_datasource_credentials(user_id);
CREATE INDEX idx_user_ds_creds_ds ON user_datasource_credentials(datasource_id);
```

### New table: `query_audit_log`

```sql
CREATE TABLE query_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Who
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,

    -- What
    datasource_id UUID NOT NULL,
    sql_hash VARCHAR(64) NOT NULL,
    sql_text TEXT,
    tables_accessed TEXT[],

    -- When
    executed_at TIMESTAMPTZ DEFAULT NOW(),
    duration_ms INT,

    -- Result
    row_count INT,
    status VARCHAR(20),  -- success, denied, error, timeout
    error_message TEXT,

    -- Context
    investigation_id UUID,
    source VARCHAR(50)   -- 'agent', 'api', 'preview', etc.
);

CREATE INDEX idx_audit_tenant_time ON query_audit_log(tenant_id, executed_at DESC);
CREATE INDEX idx_audit_user_time ON query_audit_log(user_id, executed_at DESC);
CREATE INDEX idx_audit_datasource ON query_audit_log(datasource_id, executed_at DESC);
```

---

## Query Gateway

**File:** `dataing/src/dataing/adapters/datasource/gateway.py`

```python
@dataclass
class QueryPrincipal:
    """The identity executing a query."""
    user_id: UUID
    tenant_id: UUID
    datasource_id: UUID


class QueryGateway:
    """Single point of entry for all SQL execution.

    ALL query paths must go through this gateway:
    - Agent tool calls
    - API endpoints
    - Background jobs (must have a principal)
    """

    async def execute(
        self,
        principal: QueryPrincipal,
        sql: str,
        params: dict | None = None,
        timeout_seconds: int = 30,
    ) -> QueryResult:
        # 1. Get user's credentials for this datasource
        credentials = await self._get_user_credentials(principal)
        if not credentials:
            raise CredentialsNotConfiguredError(
                datasource_id=principal.datasource_id
            )

        # 2. Create adapter with USER's credentials
        adapter = await self._create_user_adapter(principal, credentials)

        # 3. Execute query - DB enforces permissions
        start = time.monotonic()
        try:
            result = await adapter.execute_query(sql, params, timeout_seconds)
            status = "success"
            error = None
        except Exception as e:
            result = None
            status = "error"
            error = str(e)
            raise
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            # 4. Audit log (async, don't block)
            await self._audit_log(principal, sql, result, status, error, duration_ms)

        return result
```

---

## User-Scoped Adapter Creation

```python
async def _create_user_adapter(
    self,
    principal: QueryPrincipal,
    credentials: DecryptedCredentials,
) -> SQLAdapter:
    """Create an adapter using the user's credentials."""

    # Get datasource config (host, port, database, etc.)
    ds_config = await self._get_datasource_config(principal.datasource_id)

    # Merge user credentials into connection config
    connection_config = {
        **ds_config.connection_params,
        "user": credentials.username,
        "password": credentials.password,
        "role": credentials.role,  # Snowflake
    }

    # Create fresh adapter with user's credentials
    adapter_class = ADAPTER_REGISTRY.get(ds_config.source_type)
    adapter = adapter_class(connection_config)
    await adapter.connect()

    return adapter
```

**No long-term caching** - User adapters are created per-request. Connection pooling happens at the driver level.

---

## Integration Points

Principal must be threaded through the entire stack:

```
API Request (has ApiKeyContext with user_id)
  → Start Investigation (pass user_id to workflow)
    → Temporal Workflow (stores user_id in workflow state)
      → Activity (receives user_id in input)
        → QueryGateway.execute(principal, sql)
```

### Changes Required

**Temporal activities** - Add `user_id` to all activity inputs that execute queries.

**Agent tools** - Tools receive principal from workflow context.

**API routes** - Extract `user_id` from `ApiKeyContext`, pass to gateway.

---

## Credentials Management API

**Endpoints:**

```
POST   /api/v1/datasources/{id}/credentials   - Save credentials
GET    /api/v1/datasources/{id}/credentials   - Check if configured
DELETE /api/v1/datasources/{id}/credentials   - Remove credentials
POST   /api/v1/datasources/{id}/test-connection - Test credentials work
```

**Models:**

```python
class SaveCredentialsRequest(BaseModel):
    username: str
    password: str
    role: str | None = None
    warehouse: str | None = None


class CredentialsStatusResponse(BaseModel):
    configured: bool
    db_username: str | None
    last_used_at: datetime | None
    created_at: datetime | None


class TestConnectionResponse(BaseModel):
    success: bool
    error: str | None
    tables_accessible: int | None
```

---

## Error Handling

### No credentials configured (403)

```json
{
  "error": "credentials_not_configured",
  "message": "You haven't configured credentials for 'Production Snowflake'",
  "datasource_id": "abc-123",
  "action_url": "/settings/datasources/abc-123/credentials"
}
```

### Credentials invalid (401)

```json
{
  "error": "credentials_invalid",
  "message": "Database rejected your credentials: password expired",
  "datasource_id": "abc-123",
  "action_url": "/settings/datasources/abc-123/credentials"
}
```

---

## File Structure

```
dataing/src/dataing/
├── adapters/datasource/
│   └── gateway.py              # QueryGateway, QueryPrincipal
├── core/
│   └── credentials.py          # CredentialsService (encrypt/decrypt/store)
├── entrypoints/api/routes/
│   └── credentials.py          # Credentials management API
└── models/
    └── credentials.py          # SQLAlchemy models

dataing/migrations/
└── 00XX_user_credentials.sql   # New tables
```

---

## EE Extensions (Future)

| Feature | Description |
|---------|-------------|
| External secrets manager | Store credentials in Vault/AWS Secrets Manager |
| Policy engine integration | OPA/Cedar for additional access control layer |
| Audit log retention | Configurable retention policies, export |
| Credential rotation | Automated credential rotation workflows |
