# fn-1.1 Create backend usage API route

## Description
Create the backend API route for usage metrics.

**Path Note**: Backend code is in `dataing/` directory (not `backend/`). This is the correct path.

**Typing Note**: The app uses untyped `app.state.xxx` pattern (no Protocol needed). Just add `app.state.usage_tracker` directly.

## Files to Create/Modify

1. **Create** `dataing/src/dataing/entrypoints/api/routes/usage.py`
   - Follow pattern from `dashboard.py`
   - Use `APIRouter(prefix="/usage", tags=["usage"])` for router prefix
   - Define `AuthDep` locally: `AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]`
   - Define `UsageMetricsResponse` Pydantic model (maps from `UsageSummary` dataclass)
   - `GET /metrics` endpoint (becomes `/api/v1/usage/metrics` with router prefix)
   - Returns `UsageMetricsResponse` with llm_tokens, llm_cost, query_executions, investigations, total_cost

2. **Modify** `dataing/src/dataing/entrypoints/api/deps.py`
   - Import `UsageTracker` from services/usage.py
   - Instantiate `UsageTracker(db=app_db)` in lifespan (~line 108)
   - Add `app.state.usage_tracker = usage_tracker`
   - Add `get_usage_tracker()` dependency function
   - Add `UsageTrackerDep` type alias: `UsageTrackerDep = Annotated[UsageTracker, Depends(get_usage_tracker)]`

3. **Modify** `dataing/src/dataing/entrypoints/api/routes/__init__.py`
   - Import and register `usage_router`

## Key Patterns to Follow

```python
# Router with prefix (in usage.py)
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

router = APIRouter(prefix="/usage", tags=["usage"])

# Auth dependency (defined locally in usage.py, following dashboard.py pattern)
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]

# Response model (define in usage.py, maps from UsageSummary dataclass)
class UsageMetricsResponse(BaseModel):
    """Usage metrics response."""
    llm_tokens: int
    llm_cost: float
    query_executions: int
    investigations: int
    total_cost: float

# Route pattern (from dashboard.py)
@router.get("/metrics", response_model=UsageMetricsResponse)
async def get_usage_metrics(
    auth: AuthDep,
    usage_tracker: UsageTrackerDep,
) -> UsageMetricsResponse:
    """Get current usage metrics for tenant."""
    summary = await usage_tracker.get_monthly_usage(auth.tenant_id)
    return UsageMetricsResponse(
        llm_tokens=summary.llm_tokens,
        llm_cost=summary.llm_cost,
        query_executions=summary.query_executions,
        investigations=summary.investigations,
        total_cost=summary.total_cost,
    )

# Dependency function and type alias (in deps.py)
def get_usage_tracker(request: Request) -> UsageTracker:
    """Get UsageTracker from app state."""
    return request.app.state.usage_tracker

UsageTrackerDep = Annotated[UsageTracker, Depends(get_usage_tracker)]
```

## References

- `dataing/src/dataing/services/usage.py` - UsageTracker service
- `dataing/src/dataing/entrypoints/api/routes/dashboard.py` - Route pattern
- `dataing/src/dataing/entrypoints/api/deps.py` - Dependency injection
## Acceptance
- [ ] `usage.py` route file created with `GET /metrics` endpoint
- [ ] `UsageTracker` instantiated in `deps.py` lifespan
- [ ] Route registered in `routes/__init__.py`
- [ ] `curl -H "X-API-Key: dd_demo_12345" http://localhost:8000/api/v1/usage/metrics` returns JSON
- [ ] Ruff and mypy pass: `cd dataing && uv run ruff check && uv run mypy`
## Done summary
Created usage.py route with GET /metrics endpoint. UsageTracker wired into deps.py. Route registered.
## Evidence
- Commits:
- Tests:
- PRs:
