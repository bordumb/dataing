# Enterprise Notification Center

## Overview

Replace the mock notifications page with a real-time notification center.

## Scope

**In Scope (v1):**
- Org/tenant mapping resolution (prerequisite)
- Database schema: `notifications` + `notification_reads` tables
- Backend REST API + SSE endpoint
- Frontend NotificationProvider, sidebar badge, interactive cards
- Unit tests

**v1 Events:** `investigation_completed`, `investigation_failed`

**Deferred:** `approval_required`, retention purge

## Prerequisite: Org/Tenant Mapping

**Current state:** JWT auth uses `org_id` (organizations table), but investigations use `tenant_id` (tenants table). No mapping exists.

**Solution for this epic:** Add mapping to JwtContext:

```python
# dataing/src/dataing/entrypoints/api/middleware/jwt_auth.py
@dataclass
class JwtContext:
    user_id: UUID
    org_id: UUID
    tenant_id: UUID  # NEW: resolved from org
    role: str

async def decode_token(token: str) -> JwtContext:
    # existing decode...
    # NEW: Look up tenant_id from organizations.tenant_id or use org_id as tenant_id
    # (For now, many orgs ARE 1:1 with tenants via the migration)
    tenant_id = await db.fetchval("SELECT tenant_id FROM organizations WHERE id = $1", org_id)
    if not tenant_id:
        tenant_id = org_id  # Fallback: use org_id as tenant_id
    return JwtContext(user_id=..., org_id=..., tenant_id=tenant_id, role=...)
```

**Or simpler:** Organizations table already has data migrated from tenants. For v1, treat `org_id` as `tenant_id` (they share the same UUID namespace from migration).

## Data Model (014_notifications.sql)

```sql
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    resource_kind VARCHAR(50),
    resource_id UUID,
    severity VARCHAR(20) DEFAULT 'info',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE notification_reads (
    notification_id UUID NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    read_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (notification_id, user_id)
);

CREATE INDEX idx_notifications_tenant_cursor ON notifications(tenant_id, created_at DESC, id DESC);
CREATE INDEX idx_notification_reads_user ON notification_reads(user_id, notification_id);
```

## Auth

**JWT required.** Create SSE-specific dependency that shares validation with existing `verify_jwt`:

```python
# dataing/src/dataing/entrypoints/api/middleware/jwt_auth.py
async def verify_jwt_or_query(
    authorization: str | None = Header(None),
    token: str | None = Query(None),
) -> JwtContext:
    """Accept JWT from header OR query param (for SSE only)."""
    jwt_token = None
    if authorization and authorization.startswith("Bearer "):
        jwt_token = authorization[7:]
    elif token:
        jwt_token = token
    if not jwt_token:
        raise HTTPException(401, "JWT required")
    # Reuse existing decode_token logic
    return await decode_token(jwt_token)
```

## Notification Repository

`InAppNotificationRepository` in `dataing/src/dataing/adapters/db/notification_repository.py`:

- `create(tenant_id, type, title, body, resource_kind, resource_id, severity)`
- `list_for_user(tenant_id, user_id, cursor, limit, unread_only)`
- `mark_read(tenant_id, notification_id, user_id)` - SELECT then INSERT pattern
- `mark_all_read(tenant_id, user_id)` - Batched with ordered cursor
- `get_unread_count(tenant_id, user_id)`
- `get_new_since(tenant_id, cursor)`

## Notification Creation

**Emit from orchestrator signal handlers** (where status is known):

```python
# dataing/src/dataing/core/investigation/orchestrator/signal_handlers.py

# In handle_complete (for main branch completion):
if branch.branch_type == BranchType.MAIN:
    # Get investigation details
    investigation = await repository.get_investigation(snapshot.investigation_id)
    alert = investigation.alert  # dict with dataset_id, metric_name, etc.
    await notification_repo.create(
        tenant_id=investigation.tenant_id,
        type="investigation_completed",
        title=f"Investigation completed: {alert.get('dataset_id', 'Unknown')}",
        resource_kind="investigation",
        resource_id=investigation.id,
        severity="success",
    )

# In handle_fail:
if branch.branch_type == BranchType.MAIN:
    investigation = await repository.get_investigation(snapshot.investigation_id)
    await notification_repo.create(
        tenant_id=investigation.tenant_id,
        type="investigation_failed",
        title=f"Investigation failed: {error_message[:50]}",
        resource_kind="investigation",
        resource_id=investigation.id,
        severity="error",
    )
```

**Wiring:** Pass `notification_repo` through `InvestigationOrchestrator` constructor to handlers.

## API Endpoints

| Endpoint | Auth | Response |
|----------|------|----------|
| `GET /notifications` | JWT | Cursor-paginated list |
| `PUT /notifications/{id}/read` | JWT | 204 or 404 |
| `POST /notifications/read-all` | JWT | `{"count": N}` |
| `GET /notifications/unread-count` | JWT | `{"count": N}` |
| `GET /notifications/stream?token=` | JWT (query) | SSE |

## SSE Contract

```
GET /api/v1/notifications/stream?token=<jwt>&after=<cursor>

retry: 3000
event: heartbeat
event: notification (id: cursor, data: {..., cursor: "..."})
```

## Frontend

- NotificationProvider under JwtAuthProvider
- Use `auth.tenant_id` (or `org_id` if treating as same)
- Query keys: `notifications.*`
- Optimistic updates, toast rate limiting

## Test Plan

- Repository: create, list, mark_read, mark_all_read, unread_count
- API: JWT required, pagination, 404 cross-tenant
- SSE: heartbeat, resume

## Acceptance Criteria

- [ ] Org/tenant mapping works (JWT provides tenant_id)
- [ ] JWT required (401 for API key)
- [ ] Investigation completion/failure creates notification
- [ ] Sidebar badge updates real-time
- [ ] Tests pass

## Quick Commands

```bash
cd dataing && uv run pytest tests/unit/adapters/db/test_notification_repository.py -v
open http://localhost:5173/notifications
```
