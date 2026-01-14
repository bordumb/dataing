# fn-7.1 Create require_investigation_access dependency

## Description
Create a reusable FastAPI dependency `require_investigation_access` that:

1. Takes `investigation_id` as a path parameter
2. Gets the current user from `AuthDep`
3. Acquires a database connection via `AppDbDep`
4. Calls `PermissionService.can_access_investigation(user_id, investigation_id)`
5. Raises `HTTPException(403)` if access denied
6. Returns the `ApiKeyContext` if access granted

**File to create**: `dataing-ee/src/dataing_ee/entrypoints/api/middleware/rbac.py`

**Pattern to follow**: See `require_scope()` in `dataing/src/dataing/entrypoints/api/middleware/auth.py:154-175`

**Handle edge cases**:
- If `auth.user_id is None`: Return 403 "User context required for RBAC"
- If investigation not found: Let PermissionService return False (will 403)
## Acceptance
- [ ] `require_investigation_access` dependency created in `dataing-ee/src/dataing_ee/entrypoints/api/middleware/rbac.py`
- [ ] Returns 403 when `user_id` is None
- [ ] Returns 403 when `PermissionService.can_access_investigation()` returns False
- [ ] Returns `ApiKeyContext` when access granted
- [ ] Properly acquires and releases database connection
- [ ] Exported from `dataing_ee.entrypoints.api.middleware` package
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
