# Feature Gating Phase 1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enforce plan-based access control for Enterprise features and usage limits, with frontend upgrade modal.

**Architecture:** Backend decorators gate API routes, returning structured 403 responses. Frontend global interceptor catches these errors and shows upgrade modal. Entitlements context already exists in frontend.

**Tech Stack:** FastAPI decorators, React context, radix-ui Dialog

---

## Task 1: Fix Entitlements Middleware Tests

**Files:**
- Modify: `backend/tests/unit/entrypoints/api/middleware/test_entitlements.py`

**Step 1: Update test helper to use correct ApiKeyContext fields**

```python
def create_mock_auth(tenant_id: str = "00000000-0000-0000-0000-000000000123") -> ApiKeyContext:
    """Create a mock auth context."""
    return ApiKeyContext(
        key_id=UUID("00000000-0000-0000-0000-000000000001"),
        tenant_id=UUID(tenant_id),
        tenant_slug="test-org",
        tenant_name="Test Organization",
        user_id=UUID("00000000-0000-0000-0000-000000000002"),
        scopes=["admin"],
    )
```

**Step 2: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/unit/entrypoints/api/middleware/test_entitlements.py -v`
Expected: 6 passed

**Step 3: Commit**

```bash
git add backend/tests/unit/entrypoints/api/middleware/test_entitlements.py
git commit -m "fix: update entitlements tests for ApiKeyContext fields"
```

---

## Task 2: Add contact_sales Field to 403 Responses

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/middleware/entitlements.py:52-60`
- Modify: `backend/src/dataing/entrypoints/api/middleware/entitlements.py:107-117`

**Step 1: Update require_feature to include contact_sales: true**

Find in `entitlements.py` lines 52-60:
```python
raise HTTPException(
    status_code=403,
    detail={
        "error": "feature_not_available",
        "feature": feature.value,
        "message": f"The '{feature.value}' feature requires an Enterprise plan.",
        "upgrade_url": "/settings/billing",
    },
)
```

Replace with:
```python
raise HTTPException(
    status_code=403,
    detail={
        "error": "feature_not_available",
        "feature": feature.value,
        "message": f"The '{feature.value}' feature requires an Enterprise plan.",
        "upgrade_url": "/settings/billing",
        "contact_sales": True,
    },
)
```

**Step 2: Update require_under_limit to include contact_sales: false**

Find in `entitlements.py` lines 107-117:
```python
raise HTTPException(
    status_code=403,
    detail={
        "error": "limit_exceeded",
        "feature": feature.value,
        "limit": limit,
        "usage": usage,
        "message": f"You've reached your limit of {limit} for {feature.value}.",
        "upgrade_url": "/settings/billing",
    },
)
```

Replace with:
```python
raise HTTPException(
    status_code=403,
    detail={
        "error": "limit_exceeded",
        "feature": feature.value,
        "limit": limit,
        "usage": usage,
        "message": f"You've reached your limit of {limit} for {feature.value}.",
        "upgrade_url": "/settings/billing",
        "contact_sales": False,
    },
)
```

**Step 3: Run tests to verify they still pass**

Run: `cd backend && uv run pytest tests/unit/entrypoints/api/middleware/test_entitlements.py -v`
Expected: 6 passed

**Step 4: Commit**

```bash
git add backend/src/dataing/entrypoints/api/middleware/entitlements.py
git commit -m "feat: add contact_sales field to 403 responses"
```

---

## Task 3: Gate Investigation Creation

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/routes/investigations.py:77-86`

**Step 1: Add import for require_under_limit and Feature**

Add to imports at top of file:
```python
from dataing.core.entitlements.features import Feature
from dataing.entrypoints.api.middleware.entitlements import require_under_limit
```

**Step 2: Add decorator to create_investigation**

Find lines 77-86:
```python
@router.post("/", response_model=InvestigationResponse)
@audited(action="investigation.create", resource_type="investigation")
async def create_investigation(
    http_request: Request,
    request: CreateInvestigationRequest,
    background_tasks: BackgroundTasks,
    auth: AuthDep,
    orchestrator: OrchestratorDep,
    investigations: InvestigationsDep,
) -> InvestigationResponse:
```

Replace with:
```python
@router.post("/", response_model=InvestigationResponse)
@audited(action="investigation.create", resource_type="investigation")
@require_under_limit(Feature.MAX_INVESTIGATIONS_PER_MONTH)
async def create_investigation(
    request: Request,
    body: CreateInvestigationRequest,
    background_tasks: BackgroundTasks,
    auth: AuthDep,
    orchestrator: OrchestratorDep,
    investigations: InvestigationsDep,
) -> InvestigationResponse:
```

Note: Renamed `http_request` to `request` and `request` to `body` to match decorator expectations.

**Step 3: Update all references from `request` to `body` in function body**

Replace `request.` with `body.` throughout the function (dataset_id, metric_name, etc.)

**Step 4: Run linter**

Run: `cd backend && uv run ruff check src/dataing/entrypoints/api/routes/investigations.py --fix`
Expected: No errors

**Step 5: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/investigations.py
git commit -m "feat: gate investigation creation with MAX_INVESTIGATIONS_PER_MONTH"
```

---

## Task 4: Gate Datasource Creation

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/routes/datasources.py:301-307`

**Step 1: Add imports**

Add to imports at top of file:
```python
from fastapi import Request
from dataing.core.entitlements.features import Feature
from dataing.entrypoints.api.middleware.entitlements import require_under_limit
```

**Step 2: Add decorator and request parameter**

Find lines 301-307:
```python
@router.post("/", response_model=DataSourceResponse, status_code=201)
@audited(action="datasource.create", resource_type="datasource")
async def create_datasource(
    request: CreateDataSourceRequest,
    auth: WriteScopeDep,
    app_db: AppDbDep,
) -> DataSourceResponse:
```

Replace with:
```python
@router.post("/", response_model=DataSourceResponse, status_code=201)
@audited(action="datasource.create", resource_type="datasource")
@require_under_limit(Feature.MAX_DATASOURCES)
async def create_datasource(
    request: Request,
    body: CreateDataSourceRequest,
    auth: WriteScopeDep,
    app_db: AppDbDep,
) -> DataSourceResponse:
```

**Step 3: Update all references from `request` to `body` in function body**

Replace `request.name`, `request.type`, `request.config`, `request.is_default` with `body.` versions.

**Step 4: Run linter**

Run: `cd backend && uv run ruff check src/dataing/entrypoints/api/routes/datasources.py --fix`
Expected: No errors

**Step 5: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/datasources.py
git commit -m "feat: gate datasource creation with MAX_DATASOURCES"
```

---

## Task 5: Gate Team Member Addition (Seats)

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/routes/teams.py:218-226`

**Step 1: Add imports**

Add to imports at top of file:
```python
from dataing.core.entitlements.features import Feature
from dataing.entrypoints.api.middleware.entitlements import require_under_limit
```

**Step 2: Add decorator to add_team_member**

Find lines 218-226:
```python
@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
@audited(action="team.member_add", resource_type="team")
async def add_team_member(
    request: Request,
    team_id: UUID,
    body: TeamMemberAdd,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> dict[str, str]:
```

Replace with:
```python
@router.post("/{team_id}/members", status_code=status.HTTP_201_CREATED)
@audited(action="team.member_add", resource_type="team")
@require_under_limit(Feature.MAX_SEATS)
async def add_team_member(
    request: Request,
    team_id: UUID,
    body: TeamMemberAdd,
    auth: AdminScopeDep,
    app_db: AppDbDep,
) -> dict[str, str]:
```

**Step 3: Run linter**

Run: `cd backend && uv run ruff check src/dataing/entrypoints/api/routes/teams.py --fix`
Expected: No errors

**Step 4: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/teams.py
git commit -m "feat: gate team member addition with MAX_SEATS"
```

---

## Task 6: Create UpgradeRequiredModal Component

**Files:**
- Create: `frontend/src/components/shared/upgrade-required-modal.tsx`

**Step 1: Create the component**

```tsx
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/Button'
import { Progress } from '@/components/ui/progress'

export interface UpgradeError {
  error: 'feature_not_available' | 'limit_exceeded'
  feature: string
  message: string
  upgrade_url: string
  contact_sales: boolean
  limit?: number
  usage?: number
}

interface UpgradeRequiredModalProps {
  error: UpgradeError | null
  onClose: () => void
}

export function UpgradeRequiredModal({ error, onClose }: UpgradeRequiredModalProps) {
  if (!error) return null

  const isLimitError = error.error === 'limit_exceeded'
  const usagePercent = error.limit && error.usage ? (error.usage / error.limit) * 100 : 0

  return (
    <Dialog open={!!error} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {isLimitError ? 'Limit Reached' : 'Upgrade Required'}
          </DialogTitle>
          <DialogDescription>{error.message}</DialogDescription>
        </DialogHeader>

        {isLimitError && error.limit && error.usage !== undefined && (
          <div className="py-4">
            <div className="flex justify-between text-sm mb-2">
              <span>Current usage</span>
              <span>{error.usage} / {error.limit}</span>
            </div>
            <Progress value={usagePercent} className="h-2" />
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          {error.contact_sales ? (
            <Button asChild>
              <a href="mailto:sales@dataing.io?subject=Enterprise%20Upgrade">
                Contact Sales
              </a>
            </Button>
          ) : (
            <Button asChild>
              <a href={error.upgrade_url}>Upgrade Plan</a>
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

**Step 2: Run linter**

Run: `cd frontend && pnpm lint`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/shared/upgrade-required-modal.tsx
git commit -m "feat: add UpgradeRequiredModal component"
```

---

## Task 7: Add Global 403 Interceptor

**Files:**
- Modify: `frontend/src/lib/api/client.ts`
- Modify: `frontend/src/App.tsx` (or root layout)

**Step 1: Create upgrade error state manager**

Create `frontend/src/lib/api/upgrade-error.ts`:

```typescript
import { UpgradeError } from '@/components/shared/upgrade-required-modal'

type UpgradeErrorListener = (error: UpgradeError | null) => void

let currentError: UpgradeError | null = null
const listeners: Set<UpgradeErrorListener> = new Set()

export function setUpgradeError(error: UpgradeError | null) {
  currentError = error
  listeners.forEach((listener) => listener(error))
}

export function subscribeToUpgradeError(listener: UpgradeErrorListener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getUpgradeError() {
  return currentError
}
```

**Step 2: Update client.ts to detect upgrade errors**

Find in `client.ts` lines 51-57:
```typescript
if (!response.ok) {
  const errorData = await response.json().catch(() => ({}))
  throw new Error(errorData.detail || `HTTP error ${response.status}`)
}
```

Replace with:
```typescript
if (!response.ok) {
  const errorData = await response.json().catch(() => ({}))

  // Check for upgrade-required errors
  if (response.status === 403 && errorData.detail?.error) {
    const detail = errorData.detail
    if (detail.error === 'feature_not_available' || detail.error === 'limit_exceeded') {
      // Import dynamically to avoid circular deps
      const { setUpgradeError } = await import('./upgrade-error')
      setUpgradeError(detail)
      throw new Error(detail.message)
    }
  }

  throw new Error(errorData.detail?.message || errorData.detail || `HTTP error ${response.status}`)
}
```

**Step 3: Add modal to App.tsx or root layout**

Add to the main App component or layout:

```tsx
import { useState, useEffect } from 'react'
import { UpgradeRequiredModal, UpgradeError } from '@/components/shared/upgrade-required-modal'
import { subscribeToUpgradeError, setUpgradeError } from '@/lib/api/upgrade-error'

// Inside component:
const [upgradeError, setUpgradeErrorState] = useState<UpgradeError | null>(null)

useEffect(() => {
  return subscribeToUpgradeError(setUpgradeErrorState)
}, [])

// In JSX:
<UpgradeRequiredModal
  error={upgradeError}
  onClose={() => setUpgradeError(null)}
/>
```

**Step 4: Run linter**

Run: `cd frontend && pnpm lint`
Expected: No errors

**Step 5: Commit**

```bash
git add frontend/src/lib/api/client.ts frontend/src/lib/api/upgrade-error.ts frontend/src/components/shared/upgrade-required-modal.tsx
git commit -m "feat: add global 403 interceptor for upgrade prompts"
```

---

## Task 8: Manual Testing

**Step 1: Start demo environment**

Run: `just demo`
Expected: Backend on :8000, frontend on :3000

**Step 2: Set org to FREE plan**

```sql
UPDATE organizations SET plan = 'free' WHERE slug = 'demo';
```

**Step 3: Test investigation limit**

Navigate to frontend, try to create investigation.
Expected: Modal appears with "You've reached your limit" and "Upgrade Plan" button.

**Step 4: Test audit logs (Enterprise feature)**

Navigate to Settings > Audit Logs tab.
Try to view logs.
Expected: Modal appears with "Contact Sales" button.

**Step 5: Set org to ENTERPRISE plan**

```sql
UPDATE organizations SET plan = 'enterprise' WHERE slug = 'demo';
```

**Step 6: Verify Enterprise has access**

Repeat steps 3-4.
Expected: Both features work without modal.

**Step 7: Commit test documentation (optional)**

```bash
git commit --allow-empty -m "test: verify feature gating works for free/enterprise plans"
```

---

## Summary

| Task | Files | Purpose |
|------|-------|---------|
| 1 | test_entitlements.py | Fix broken tests |
| 2 | entitlements.py | Add contact_sales field |
| 3 | investigations.py | Gate with MAX_INVESTIGATIONS |
| 4 | datasources.py | Gate with MAX_DATASOURCES |
| 5 | teams.py | Gate with MAX_SEATS |
| 6 | upgrade-required-modal.tsx | Create modal component |
| 7 | client.ts, upgrade-error.ts | Global 403 interceptor |
| 8 | Manual | Verify end-to-end |
