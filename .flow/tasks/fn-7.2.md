# fn-7.2 Add RBAC to GET /investigations/{id}

## Description
Add RBAC check to `GET /investigations/{investigation_id}` endpoint.

**File to create**: `dataing-ee/src/dataing_ee/entrypoints/api/routes/investigations.py`

**Approach**: Create EE route that wraps CE implementation:
1. Import CE `get_investigation` function
2. Use `require_investigation_access` dependency
3. Call CE implementation after RBAC passes

```python
from dataing.entrypoints.api.routes.investigations import get_investigation as ce_get_investigation

@router.get("/{investigation_id}", response_model=InvestigationStateResponse)
async def get_investigation(
    investigation_id: UUID,
    auth: Annotated[ApiKeyContext, Depends(require_investigation_access)],
    service: InvestigationServiceDep,
) -> InvestigationStateResponse:
    return await ce_get_investigation(investigation_id, auth, service)
```

**Reference**: CE route at `dataing/src/dataing/entrypoints/api/routes/investigations.py:266-356`
## Acceptance
- [ ] EE route file created at `dataing-ee/src/dataing_ee/entrypoints/api/routes/investigations.py`
- [ ] Route returns 403 for users without access
- [ ] Route returns investigation data for users with access
- [ ] Route registered in EE app to override CE route
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
