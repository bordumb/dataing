# RBAC Enforcement for Investigation Routes (EE)

## Overview

Wire up RBAC enforcement in dataing-ee by calling `PermissionService.can_access_investigation()` in investigation route handlers. The PermissionService already exists and implements flexible union-based access control (user role, creator, direct grant, tag-based, datasource-based, team-based).

## Scope

**In scope:**
- Add RBAC checks to `GET /investigations/{id}` - single investigation access
- Add RBAC filtering to `GET /investigations` - list only accessible investigations
- Add RBAC checks to `POST /investigations/{id}/messages` - verify access before messaging
- Add RBAC checks to `GET /investigations/{id}/stream` - verify access before SSE stream
- Create reusable dependency for RBAC checks
- Unit and integration tests

**Out of scope:**
- Modifying PermissionService logic (already complete)
- UI changes for permissions
- New permission grant endpoints (already exist)

## Approach

### Strategy: EE Route Wrappers

Since investigation routes are in CE (`dataing/src/dataing/entrypoints/api/routes/investigations.py`), we'll create EE wrapper routes that:
1. Import CE route functions
2. Add RBAC checks before calling CE logic
3. Register EE routes to override CE routes

### Implementation Pattern

```python
# dataing-ee/src/dataing_ee/entrypoints/api/routes/investigations.py

from dataing.entrypoints.api.routes.investigations import get_investigation as ce_get_investigation

async def get_investigation(
    investigation_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
    service: InvestigationServiceDep,
) -> InvestigationStateResponse:
    # RBAC check
    if auth.user_id is None:
        raise HTTPException(status_code=403, detail="User context required for RBAC")

    async with app_db.acquire() as conn:
        permission_svc = PermissionService(conn)
        if not await permission_svc.can_access_investigation(auth.user_id, investigation_id):
            raise HTTPException(status_code=403, detail="Access denied")

    # Delegate to CE implementation
    return await ce_get_investigation(investigation_id, auth, service)
```

### API Key Handling

- API keys without `user_id`: Return 403 "User context required for RBAC"
- Admin-scope API keys: Still require `user_id` for audit trail
- This matches existing CE behavior in `get_investigation` (lines 288-292)

### List Endpoint Filtering

Use `PermissionService.get_accessible_investigation_ids()`:
- Returns `None` for admin/owner (can see all)
- Returns `list[UUID]` for others → filter with `WHERE id IN (...)`

## Quick Commands

```bash
# Run unit tests for RBAC
uv run pytest dataing-ee/tests/unit/entrypoints/api/routes/test_investigations_rbac.py -v

# Run integration tests
uv run pytest dataing-ee/tests/integration/test_investigation_rbac.py -v

# Start EE backend to manually test
just dev-backend
```

## Acceptance Criteria

- [ ] `GET /investigations/{id}` returns 403 for users without access
- [ ] `GET /investigations/{id}` returns 200 for users with access (creator, granted, team, admin)
- [ ] `GET /investigations` only returns investigations user can access
- [ ] `POST /investigations/{id}/messages` returns 403 for users without access
- [ ] `GET /investigations/{id}/stream` returns 403 for users without access
- [ ] API keys without `user_id` receive 403 with clear message
- [ ] Admin/owner users can access all investigations in their org
- [ ] Unit tests cover all RBAC scenarios
- [ ] Integration tests verify end-to-end RBAC

## References

- **PermissionService**: `dataing/src/dataing/core/rbac/permission_service.py:29-201`
- **CE Investigation Routes**: `dataing/src/dataing/entrypoints/api/routes/investigations.py`
- **Auth Middleware**: `dataing/src/dataing/entrypoints/api/middleware/auth.py`
- **EE Route Pattern**: `dataing-ee/src/dataing_ee/entrypoints/api/routes/settings.py`
- **RBAC Design Doc**: `docs/plans/2026-01-06-rbac-scim-design.md`

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Performance impact on list endpoint | Use SQL subquery instead of Python filtering for large datasets |
| Breaking existing API key integrations | Clear error message explaining user_id requirement |
| Missing RBAC tables in CE deployments | PermissionService already handles missing tables gracefully |
