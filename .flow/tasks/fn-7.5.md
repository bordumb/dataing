# fn-7.5 Add RBAC to GET /investigations/{id}/stream

## Description
Add RBAC check to `GET /investigations/{investigation_id}/stream` SSE endpoint.

**File**: `dataing-ee/src/dataing_ee/entrypoints/api/routes/investigations.py`

**Approach**: Check RBAC before opening SSE stream.

```python
@router.get("/{investigation_id}/stream")
async def stream_investigation(
    investigation_id: UUID,
    auth: Annotated[ApiKeyContext, Depends(require_investigation_access)],
    service: InvestigationServiceDep,
) -> EventSourceResponse:
    return await ce_stream_investigation(investigation_id, auth, service)
```

**Reference**: CE route at `dataing/src/dataing/entrypoints/api/routes/investigations.py` (stream endpoint)
## Acceptance
- [ ] SSE stream returns 403 for users without access
- [ ] SSE stream opens for users with access
- [ ] Uses `require_investigation_access` dependency
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
