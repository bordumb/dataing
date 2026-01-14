# fn-7.3 Add RBAC filtering to GET /investigations

## Description
Add RBAC filtering to `GET /investigations` list endpoint.

**Approach**: Override CE list endpoint to filter by accessible investigations.

```python
@router.get("/", response_model=list[InvestigationListItem])
async def list_investigations(
    auth: AuthDep,
    app_db: AppDbDep,
    service: InvestigationServiceDep,
    # ... existing params
) -> list[InvestigationListItem]:
    if auth.user_id is None:
        raise HTTPException(status_code=403, detail="User context required")

    async with app_db.acquire() as conn:
        permission_svc = PermissionService(conn)
        accessible_ids = await permission_svc.get_accessible_investigation_ids(
            auth.user_id, auth.tenant_id
        )

    # accessible_ids is None if admin/owner (can see all)
    # Otherwise filter query by these IDs
    return await service.list_investigations(
        tenant_id=auth.tenant_id,
        accessible_ids=accessible_ids,
        # ... other filters
    )
```

**Reference**: CE route at `dataing/src/dataing/entrypoints/api/routes/investigations.py:144-186`

**Note**: May need to modify `InvestigationService.list_investigations()` to accept `accessible_ids` filter.
## Acceptance
- [ ] EE list endpoint filters by accessible investigations
- [ ] Admin/owner users see all investigations
- [ ] Regular users only see investigations they have access to
- [ ] Returns 403 when `user_id` is None
- [ ] Performance: Uses SQL filtering, not Python filtering
## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
