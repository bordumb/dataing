# Audit Logging Design

**Goal:** Comprehensive audit logging for SOC 2, GDPR compliance, enterprise sales, and internal security.

**Date:** 2026-01-06

---

## Decisions

| Decision | Choice |
|----------|--------|
| Compliance targets | SOC 2, GDPR, enterprise sales, internal security |
| What to log | Writes + Auth only (skip read-only GETs) |
| Storage | Same PostgreSQL database, `audit_logs` table |
| Retention | 2 years |
| Cleanup | Kubernetes CronJob |
| Frontend | Full UI in Admin page (search, filter, export CSV) |
| Implementation | `@audited` decorator on route handlers |

---

## Data Model

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- When
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Who
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    actor_id UUID,                    -- user who performed action (null for system)
    actor_email VARCHAR(255),         -- denormalized for easy querying
    actor_ip VARCHAR(45),             -- IPv4 or IPv6
    actor_user_agent TEXT,

    -- What
    action VARCHAR(100) NOT NULL,     -- e.g., "team.create", "user.login"
    resource_type VARCHAR(50),        -- e.g., "team", "datasource"
    resource_id UUID,                 -- ID of affected resource
    resource_name VARCHAR(255),       -- denormalized for readability

    -- Details
    request_method VARCHAR(10),       -- POST, PUT, DELETE
    request_path TEXT,
    status_code INTEGER,
    changes JSONB,                    -- {"field": {"old": x, "new": y}}
    metadata JSONB,                   -- additional context

    -- Indexing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX idx_audit_logs_tenant_timestamp ON audit_logs(tenant_id, timestamp DESC);
CREATE INDEX idx_audit_logs_actor ON audit_logs(tenant_id, actor_id, timestamp DESC);
CREATE INDEX idx_audit_logs_action ON audit_logs(tenant_id, action, timestamp DESC);
CREATE INDEX idx_audit_logs_resource ON audit_logs(tenant_id, resource_type, resource_id);
```

---

## Actions to Audit

### Authentication
- `auth.login` - User login success
- `auth.login_failed` - Failed login attempt
- `auth.logout` - User logout
- `auth.sso_login` - SSO login
- `auth.password_reset_request` - Password reset requested
- `auth.password_reset_complete` - Password reset completed

### Teams & Users
- `team.create`, `team.update`, `team.delete`
- `team.member_add`, `team.member_remove`
- `user.invite`, `user.deactivate`

### RBAC
- `permission.grant`, `permission.revoke`
- `tag.create`, `tag.update`, `tag.delete`

### SSO & SCIM
- `sso.config_update`, `sso.domain_claim`, `sso.domain_verify`
- `scim.token_create`, `scim.token_revoke`
- `scim.user_provision`, `scim.user_deprovision`
- `scim.group_sync`

### Data Sources
- `datasource.create`, `datasource.update`, `datasource.delete`
- `datasource.test_connection`

### Investigations
- `investigation.create`, `investigation.delete`
- `investigation.approve` (human-in-the-loop)

### Settings
- `settings.update`
- `webhook.create`, `webhook.update`, `webhook.delete`
- `apikey.create`, `apikey.revoke`

---

## Backend Implementation

### Decorator Pattern

```python
# backend/src/dataing/adapters/audit/decorator.py
def audited(action: str, resource_type: str | None = None):
    """Decorator to audit route handlers."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = _extract_request(kwargs)
            result = await func(*args, **kwargs)
            await _record_audit(
                action=action,
                resource_type=resource_type,
                resource_id=_extract_resource_id(result, kwargs),
                request=request,
                status_code=200,
            )
            return result
        return wrapper
    return decorator
```

### Usage

```python
@router.post("/teams")
@audited(action="team.create", resource_type="team")
async def create_team(body: TeamCreate, ...) -> TeamResponse:
    team = await teams_repo.create(body)
    return team
```

---

## API Endpoints

```
GET  /api/v1/audit-logs          - List with filters (paginated)
GET  /api/v1/audit-logs/{id}     - Get single entry details
GET  /api/v1/audit-logs/export   - Export filtered results as CSV
```

Query parameters for list/export:
- `start_date`, `end_date` - Date range filter
- `action` - Filter by action (e.g., "team.create")
- `actor_id` - Filter by user
- `resource_type` - Filter by resource type
- `search` - Free-text search
- `page`, `limit` - Pagination

---

## Frontend UI

Location: Admin page > "Audit Log" tab (Admin/Owner only)

Features:
- Date range picker (default: last 7 days)
- Filter by action category
- Filter by user
- Free-text search
- Expandable rows for full details
- Export to CSV button
- Pagination (50 per page)

```
┌─────────────────────────────────────────────────────────────────┐
│ Filters:                                                        │
│ [Date Range ▼] [Action ▼] [User ▼] [Search...    ] [Export CSV] │
├─────────────────────────────────────────────────────────────────┤
│ Timestamp          User              Action          Resource   │
│ ─────────────────────────────────────────────────────────────── │
│ 2026-01-06 14:23   alice@acme.com    team.create     "Backend"  │
│ 2026-01-06 14:20   bob@acme.com      datasource.del  "Legacy"   │
│ ...                                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Retention Cleanup

Kubernetes CronJob runs daily to delete logs older than 2 years:

```yaml
# k8s/cronjobs/audit-cleanup.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: audit-log-cleanup
spec:
  schedule: "0 3 * * *"  # 3 AM daily
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: cleanup
            image: dataing-backend:latest
            command: ["python", "-m", "dataing.jobs.audit_cleanup"]
          restartPolicy: OnFailure
```

---

## Files to Create

| File | Purpose |
|------|---------|
| `backend/migrations/009_audit_logs.sql` | Database table + indexes |
| `backend/src/dataing/adapters/audit/__init__.py` | Module exports |
| `backend/src/dataing/adapters/audit/repository.py` | CRUD operations |
| `backend/src/dataing/adapters/audit/decorator.py` | `@audited` decorator |
| `backend/src/dataing/adapters/audit/types.py` | Pydantic models |
| `backend/src/dataing/entrypoints/api/routes/audit.py` | API routes |
| `backend/src/dataing/jobs/audit_cleanup.py` | Cleanup job script |
| `frontend/src/features/settings/audit/index.ts` | Exports |
| `frontend/src/features/settings/audit/audit-log-settings.tsx` | Main component |
| `frontend/src/features/settings/audit/audit-log-table.tsx` | Table component |
| `frontend/src/features/settings/audit/audit-log-filters.tsx` | Filters component |
| `frontend/src/features/settings/audit/audit-log-export.tsx` | CSV export |
| `frontend/src/lib/api/generated/audit/` | Generated API client |
| `k8s/cronjobs/audit-cleanup.yaml` | Kubernetes CronJob |
| `backend/tests/unit/adapters/audit/` | Unit tests |
