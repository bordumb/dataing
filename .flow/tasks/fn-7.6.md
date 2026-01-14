# fn-7.6 Add unit tests for RBAC enforcement

## Description
Add unit tests for RBAC enforcement in investigation routes.

**File to create**: `dataing-ee/tests/unit/entrypoints/api/routes/test_investigations_rbac.py`

**Test cases**:
1. `test_get_investigation_denied_no_user_id` - API key without user_id gets 403
2. `test_get_investigation_denied_no_permission` - User without access gets 403
3. `test_get_investigation_allowed_creator` - Investigation creator gets access
4. `test_get_investigation_allowed_admin` - Admin gets access
5. `test_get_investigation_allowed_granted` - User with direct grant gets access
6. `test_list_investigations_filtered` - List only returns accessible investigations
7. `test_list_investigations_admin_sees_all` - Admin sees all investigations
8. `test_send_message_denied` - User without access cannot send message
9. `test_stream_denied` - User without access cannot open stream

**Pattern**: Mock `PermissionService` and `AppDatabase`, test route handler logic.

**Reference**: `dataing/tests/unit/core/rbac/test_permission_service.py`
## Acceptance
- [ ] All 9 test cases implemented
- [ ] Tests pass: `uv run pytest dataing-ee/tests/unit/entrypoints/api/routes/test_investigations_rbac.py -v`
- [ ] Tests use mocks appropriately (no real DB)
- [ ] Coverage for edge cases (no user_id, admin bypass)
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
