# fn-7.4 Add RBAC to POST /investigations/{id}/messages

## Description
Add RBAC check to `POST /investigations/{investigation_id}/messages` endpoint.

**File**: `dataing-ee/src/dataing_ee/entrypoints/api/routes/investigations.py`

**Approach**: Use same pattern as GET single - wrap CE implementation with RBAC check.

```python
@router.post("/{investigation_id}/messages", response_model=InvestigationMessageResponse)
async def send_message(
    investigation_id: UUID,
    body: InvestigationMessageRequest,
    auth: Annotated[ApiKeyContext, Depends(require_investigation_access)],
    service: InvestigationServiceDep,
) -> InvestigationMessageResponse:
    return await ce_send_message(investigation_id, body, auth, service)
```

**Reference**: CE route at `dataing/src/dataing/entrypoints/api/routes/investigations.py:359-398`
## Acceptance
- [ ] POST /messages returns 403 for users without access
- [ ] POST /messages succeeds for users with access
- [ ] Uses `require_investigation_access` dependency
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
