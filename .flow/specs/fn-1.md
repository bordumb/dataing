# Live Usage Metrics Dashboard

## Overview

Make the usage page at `localhost:3000/usage` display live metrics from the backend instead of mock data. The backend `UsageTracker` service already exists with full implementation - this epic wires it up to the API and frontend.

## Scope

**In Scope:**
- Create backend API route `/api/v1/usage/metrics`
- Wire UsageTracker into app lifespan (deps.py)
- Update frontend to call API with React Query polling
- Add query keys and API client for usage

**Out of Scope (Future):**
- Quota enforcement (check_quota currently placeholder)
- Plan-based limits integration
- Historical usage charts
- Usage recording integration into core operations

## Current State

- ✓ `UsageTracker` service exists at `services/usage.py`
- ✓ Database schema `usage_records` exists
- ✓ Frontend `UsagePage` component exists with UI
- ✗ No API endpoint exposed
- ✗ Frontend uses mock hardcoded data
- ✗ UsageTracker not instantiated in app

## Approach

1. **Backend**: Create route, wire service, register router
2. **Frontend**: Add query keys, API client, update page to fetch

**Path Note**: The backend code lives in `dataing/` directory (not `backend/`). All backend paths use `dataing/src/dataing/...`.

**Frontend Client**: Uses manual `customInstance` with TypeScript interfaces (not generated OpenAPI client).

Follow existing patterns:
- Route pattern: `dashboard.py` for stats endpoints
- Frontend pattern: `useInvestigation` hook with polling (uses `customInstance`)
- Query keys: existing factory in `query-keys.ts`

## Quick Commands

```bash
# Smoke test - backend health
curl http://localhost:8000/health

# Test usage endpoint (after task 1)
curl -H "X-API-Key: dd_demo_12345" http://localhost:8000/api/v1/usage/metrics

# Run backend lint
cd dataing && uv run ruff check src/dataing/entrypoints/api/routes/usage.py

# Run frontend (after task 2)
cd frontend && pnpm dev
# Visit http://localhost:3000/usage
```

## Acceptance Criteria

- [ ] `GET /api/v1/usage/metrics` returns usage data for authenticated tenant
- [ ] Frontend `/usage` page displays live data from API
- [ ] Page auto-refreshes metrics every 5 seconds via polling
- [ ] Loading/error states handled gracefully
- [ ] All pre-commit checks pass

## References

- Backend service: `dataing/src/dataing/services/usage.py`
- Frontend page: `frontend/src/features/usage/usage-page.tsx`
- Route pattern: `dataing/src/dataing/entrypoints/api/routes/dashboard.py`
- Query pattern: `frontend/src/lib/api/investigations.ts`
- Query keys: `frontend/src/lib/api/query-keys.ts`
