# fn-7.7 Add integration tests for RBAC

## Description
Add integration tests for RBAC enforcement.

**File to create**: `dataing-ee/tests/integration/test_investigation_rbac.py`

**Test cases**:
1. Create two users in same org with different permissions
2. Create investigation as user A
3. Verify user A can access investigation
4. Verify user B cannot access investigation (403)
5. Grant user B access via permission_grants table
6. Verify user B can now access investigation
7. Verify list endpoint only shows accessible investigations

**Prerequisites**: Requires test database with RBAC tables seeded.

**Reference**: `dataing-ee/tests/integration/` for existing patterns
## Acceptance
- [ ] Integration tests created
- [ ] Tests pass: `uv run pytest dataing-ee/tests/integration/test_investigation_rbac.py -v`
- [ ] Tests verify end-to-end RBAC behavior
- [ ] Tests clean up after themselves
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
