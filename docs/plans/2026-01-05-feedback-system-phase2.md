# Feedback System Phase 2: User Feedback Collection - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add thumbs up/down feedback buttons to the investigation detail page with tooltip-based reason selection.

**Architecture:** Backend adds POST /feedback endpoint using existing FeedbackAdapter. Frontend adds FeedbackButtons and FeedbackTooltip components to InvestigationDetail, with FeedbackContext for state management.

**Tech Stack:** FastAPI, Pydantic, React, TypeScript, TanStack Query, Radix UI Popover, shadcn/ui

---

## Task 1: Create Feedback API Schemas

**Files:**
- Create: `backend/src/dataing/entrypoints/api/routes/feedback.py`
- Test: `backend/tests/unit/entrypoints/api/routes/test_feedback.py`

**Step 1: Write the failing test**

Create `backend/tests/unit/entrypoints/api/routes/__init__.py` (empty file if not exists).

Create `backend/tests/unit/entrypoints/api/routes/test_feedback.py`:

```python
"""Tests for feedback API routes."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from dataing.entrypoints.api.routes.feedback import FeedbackCreate, FeedbackResponse


class TestFeedbackSchemas:
    """Tests for feedback Pydantic schemas."""

    def test_feedback_create_valid(self) -> None:
        """FeedbackCreate accepts valid data."""
        data = FeedbackCreate(
            target_type="hypothesis",
            target_id=uuid4(),
            investigation_id=uuid4(),
            rating=1,
            reason="Right direction",
        )
        assert data.rating == 1
        assert data.target_type == "hypothesis"

    def test_feedback_create_negative_rating(self) -> None:
        """FeedbackCreate accepts negative rating."""
        data = FeedbackCreate(
            target_type="query",
            target_id=uuid4(),
            investigation_id=uuid4(),
            rating=-1,
        )
        assert data.rating == -1

    def test_feedback_create_invalid_rating(self) -> None:
        """FeedbackCreate rejects invalid rating."""
        with pytest.raises(ValidationError):
            FeedbackCreate(
                target_type="hypothesis",
                target_id=uuid4(),
                investigation_id=uuid4(),
                rating=0,  # Invalid - must be 1 or -1
            )

    def test_feedback_create_invalid_target_type(self) -> None:
        """FeedbackCreate rejects invalid target type."""
        with pytest.raises(ValidationError):
            FeedbackCreate(
                target_type="invalid",
                target_id=uuid4(),
                investigation_id=uuid4(),
                rating=1,
            )
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/entrypoints/api/routes/test_feedback.py -v`

Expected: FAIL with "ModuleNotFoundError: No module named 'dataing.entrypoints.api.routes.feedback'"

**Step 3: Write minimal implementation**

Create `backend/src/dataing/entrypoints/api/routes/feedback.py`:

```python
"""API routes for user feedback collection."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class FeedbackCreate(BaseModel):
    """Request body for submitting feedback."""

    target_type: Literal["hypothesis", "query", "evidence", "synthesis", "investigation"]
    target_id: UUID
    investigation_id: UUID
    rating: Literal[1, -1]
    reason: str | None = None
    comment: str | None = None


class FeedbackResponse(BaseModel):
    """Response after submitting feedback."""

    id: UUID
    created_at: datetime
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/entrypoints/api/routes/test_feedback.py -v`

Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/feedback.py backend/tests/unit/entrypoints/api/routes/
git commit -m "feat(feedback): add feedback API schemas"
```

---

## Task 2: Create POST /feedback Endpoint

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/routes/feedback.py`
- Modify: `backend/src/dataing/entrypoints/api/routes/__init__.py`
- Test: `backend/tests/unit/entrypoints/api/routes/test_feedback.py`

**Step 1: Write the failing test**

Add to `backend/tests/unit/entrypoints/api/routes/test_feedback.py`:

```python
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.entrypoints.api.routes.feedback import router


class TestFeedbackEndpoint:
    """Tests for POST /feedback endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test FastAPI app."""
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_submit_feedback_success(self, client: TestClient) -> None:
        """POST /feedback creates feedback event."""
        tenant_id = uuid4()
        investigation_id = uuid4()
        target_id = uuid4()

        # Mock dependencies
        with patch(
            "dataing.entrypoints.api.routes.feedback.verify_api_key"
        ) as mock_auth, patch(
            "dataing.entrypoints.api.routes.feedback.get_feedback_adapter"
        ) as mock_adapter_dep:
            mock_auth.return_value = MagicMock(tenant_id=tenant_id, user_id=uuid4())

            mock_adapter = MagicMock()
            mock_adapter.emit = AsyncMock(
                return_value=MagicMock(id=uuid4(), created_at=datetime.now(UTC))
            )
            mock_adapter_dep.return_value = mock_adapter

            response = client.post(
                "/api/v1/feedback",
                json={
                    "target_type": "hypothesis",
                    "target_id": str(target_id),
                    "investigation_id": str(investigation_id),
                    "rating": 1,
                    "reason": "Right direction",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert "created_at" in data
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/entrypoints/api/routes/test_feedback.py::TestFeedbackEndpoint -v`

Expected: FAIL with "AttributeError: module has no attribute 'router'"

**Step 3: Write minimal implementation**

Update `backend/src/dataing/entrypoints/api/routes/feedback.py`:

```python
"""API routes for user feedback collection."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dataing.adapters.feedback import EventType, FeedbackAdapter
from dataing.entrypoints.api.deps import get_feedback_adapter
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

router = APIRouter(prefix="/feedback", tags=["feedback"])

AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
FeedbackAdapterDep = Annotated[FeedbackAdapter, Depends(get_feedback_adapter)]


class FeedbackCreate(BaseModel):
    """Request body for submitting feedback."""

    target_type: Literal["hypothesis", "query", "evidence", "synthesis", "investigation"]
    target_id: UUID
    investigation_id: UUID
    rating: Literal[1, -1]
    reason: str | None = None
    comment: str | None = None


class FeedbackResponse(BaseModel):
    """Response after submitting feedback."""

    id: UUID
    created_at: datetime


# Map target_type to EventType
TARGET_TYPE_TO_EVENT = {
    "hypothesis": EventType.FEEDBACK_HYPOTHESIS,
    "query": EventType.FEEDBACK_QUERY,
    "evidence": EventType.FEEDBACK_EVIDENCE,
    "synthesis": EventType.FEEDBACK_SYNTHESIS,
    "investigation": EventType.FEEDBACK_INVESTIGATION,
}


@router.post("/", status_code=201, response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackCreate,
    auth: AuthDep,
    feedback_adapter: FeedbackAdapterDep,
) -> FeedbackResponse:
    """Submit feedback on a hypothesis, query, evidence, synthesis, or investigation."""
    event_type = TARGET_TYPE_TO_EVENT[body.target_type]

    event = await feedback_adapter.emit(
        tenant_id=auth.tenant_id,
        event_type=event_type,
        event_data={
            "target_id": str(body.target_id),
            "rating": body.rating,
            "reason": body.reason,
            "comment": body.comment,
        },
        investigation_id=body.investigation_id,
        actor_id=auth.user_id if hasattr(auth, "user_id") else None,
        actor_type="user",
    )

    return FeedbackResponse(id=event.id, created_at=event.created_at)
```

**Step 4: Add dependency to deps.py**

Add to `backend/src/dataing/entrypoints/api/deps.py` (find appropriate location):

```python
from dataing.adapters.feedback import FeedbackAdapter


def get_feedback_adapter(request: Request) -> FeedbackAdapter:
    """Get FeedbackAdapter from app state."""
    return request.app.state.feedback_adapter
```

**Step 5: Register router**

Update `backend/src/dataing/entrypoints/api/routes/__init__.py`:

```python
from dataing.entrypoints.api.routes.feedback import router as feedback_router

# Add to api_router.include_router calls:
api_router.include_router(feedback_router)
```

**Step 6: Run test to verify it passes**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/entrypoints/api/routes/test_feedback.py -v`

Expected: PASS

**Step 7: Run linting**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run ruff check backend/src/dataing/entrypoints/api/routes/feedback.py --fix && uv run mypy backend/src/dataing/entrypoints/api/routes/feedback.py`

**Step 8: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/feedback.py backend/src/dataing/entrypoints/api/routes/__init__.py backend/src/dataing/entrypoints/api/deps.py
git commit -m "feat(feedback): add POST /feedback endpoint"
```

---

## Task 3: Create GET /investigations/:id/feedback Endpoint

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/routes/feedback.py`
- Test: `backend/tests/unit/entrypoints/api/routes/test_feedback.py`

**Step 1: Write the failing test**

Add to `backend/tests/unit/entrypoints/api/routes/test_feedback.py`:

```python
class TestGetFeedbackEndpoint:
    """Tests for GET /investigations/:id/feedback endpoint."""

    @pytest.fixture
    def app(self) -> FastAPI:
        """Create test FastAPI app."""
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        return app

    @pytest.fixture
    def client(self, app: FastAPI) -> TestClient:
        """Create test client."""
        return TestClient(app)

    def test_get_investigation_feedback(self, client: TestClient) -> None:
        """GET /investigations/:id/feedback returns user's feedback."""
        tenant_id = uuid4()
        investigation_id = uuid4()
        user_id = uuid4()

        with patch(
            "dataing.entrypoints.api.routes.feedback.verify_api_key"
        ) as mock_auth, patch(
            "dataing.entrypoints.api.routes.feedback.get_db"
        ) as mock_db_dep:
            mock_auth.return_value = MagicMock(tenant_id=tenant_id, user_id=user_id)

            mock_db = MagicMock()
            mock_db.list_feedback_events = AsyncMock(
                return_value=[
                    {
                        "id": uuid4(),
                        "event_type": "feedback.hypothesis",
                        "event_data": {"target_id": str(uuid4()), "rating": 1},
                        "created_at": datetime.now(UTC),
                    }
                ]
            )
            mock_db_dep.return_value = mock_db

            response = client.get(f"/api/v1/investigations/{investigation_id}/feedback")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["rating"] == 1
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/entrypoints/api/routes/test_feedback.py::TestGetFeedbackEndpoint -v`

Expected: FAIL with "404 Not Found"

**Step 3: Write minimal implementation**

Add to `backend/src/dataing/entrypoints/api/routes/feedback.py`:

```python
from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_db

DbDep = Annotated[AppDatabase, Depends(get_db)]


class FeedbackItem(BaseModel):
    """A single feedback item."""

    id: UUID
    target_type: str
    target_id: UUID
    rating: int
    reason: str | None
    created_at: datetime


@router.get("/investigations/{investigation_id}", response_model=list[FeedbackItem])
async def get_investigation_feedback(
    investigation_id: UUID,
    auth: AuthDep,
    db: DbDep,
) -> list[FeedbackItem]:
    """Get current user's feedback for an investigation."""
    events = await db.list_feedback_events(
        tenant_id=auth.tenant_id,
        investigation_id=investigation_id,
        event_type=None,  # Get all feedback types
    )

    # Filter to only feedback events and current user
    user_id = auth.user_id if hasattr(auth, "user_id") else None
    feedback_events = [
        e for e in events
        if e["event_type"].startswith("feedback.")
        and (user_id is None or e.get("actor_id") == user_id)
    ]

    return [
        FeedbackItem(
            id=e["id"],
            target_type=e["event_type"].replace("feedback.", ""),
            target_id=UUID(e["event_data"]["target_id"]),
            rating=e["event_data"]["rating"],
            reason=e["event_data"].get("reason"),
            created_at=e["created_at"],
        )
        for e in feedback_events
    ]
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/entrypoints/api/routes/test_feedback.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/feedback.py backend/tests/unit/entrypoints/api/routes/test_feedback.py
git commit -m "feat(feedback): add GET /investigations/:id/feedback endpoint"
```

---

## Task 4: Add Popover UI Component

**Files:**
- Create: `frontend/src/components/ui/popover.tsx`

**Step 1: Create Popover component**

Create `frontend/src/components/ui/popover.tsx`:

```tsx
import * as React from "react"
import * as PopoverPrimitive from "@radix-ui/react-popover"

import { cn } from "@/lib/utils"

const Popover = PopoverPrimitive.Root

const PopoverTrigger = PopoverPrimitive.Trigger

const PopoverAnchor = PopoverPrimitive.Anchor

const PopoverContent = React.forwardRef<
  React.ElementRef<typeof PopoverPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, align = "center", sideOffset = 4, ...props }, ref) => (
  <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content
      ref={ref}
      align={align}
      sideOffset={sideOffset}
      className={cn(
        "z-50 w-72 rounded-md border bg-popover p-4 text-popover-foreground shadow-md outline-none data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2",
        className
      )}
      {...props}
    />
  </PopoverPrimitive.Portal>
))
PopoverContent.displayName = PopoverPrimitive.Content.displayName

export { Popover, PopoverTrigger, PopoverContent, PopoverAnchor }
```

**Step 2: Install Radix Popover dependency**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system/frontend && pnpm add @radix-ui/react-popover`

**Step 3: Commit**

```bash
git add frontend/src/components/ui/popover.tsx frontend/package.json frontend/pnpm-lock.yaml
git commit -m "feat(ui): add Popover component"
```

---

## Task 5: Create Feedback API Client

**Files:**
- Create: `frontend/src/lib/api/feedback.ts`

**Step 1: Create feedback API client**

Create `frontend/src/lib/api/feedback.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { queryKeys } from './query-keys'

export type TargetType = 'hypothesis' | 'query' | 'evidence' | 'synthesis' | 'investigation'

export interface FeedbackCreate {
  target_type: TargetType
  target_id: string
  investigation_id: string
  rating: 1 | -1
  reason?: string
  comment?: string
}

export interface FeedbackResponse {
  id: string
  created_at: string
}

export interface FeedbackItem {
  id: string
  target_type: string
  target_id: string
  rating: number
  reason: string | null
  created_at: string
}

async function submitFeedback(data: FeedbackCreate): Promise<FeedbackResponse> {
  const response = await fetch('/api/v1/feedback/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    throw new Error('Failed to submit feedback')
  }
  return response.json()
}

async function getInvestigationFeedback(investigationId: string): Promise<FeedbackItem[]> {
  const response = await fetch(`/api/v1/feedback/investigations/${investigationId}`)
  if (!response.ok) {
    throw new Error('Failed to get feedback')
  }
  return response.json()
}

export function useInvestigationFeedback(investigationId: string) {
  return useQuery({
    queryKey: ['feedback', investigationId],
    queryFn: () => getInvestigationFeedback(investigationId),
    enabled: !!investigationId,
  })
}

export function useSubmitFeedback(investigationId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: submitFeedback,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['feedback', investigationId] })
    },
  })
}
```

**Step 2: Commit**

```bash
git add frontend/src/lib/api/feedback.ts
git commit -m "feat(feedback): add feedback API client"
```

---

## Task 6: Create FeedbackContext

**Files:**
- Create: `frontend/src/features/investigation/context/FeedbackContext.tsx`

**Step 1: Create FeedbackContext**

Create directory and file:

```bash
mkdir -p frontend/src/features/investigation/context
```

Create `frontend/src/features/investigation/context/FeedbackContext.tsx`:

```typescript
import { createContext, useContext, useMemo, ReactNode } from 'react'
import { useInvestigationFeedback, useSubmitFeedback, FeedbackCreate, TargetType } from '@/lib/api/feedback'

interface FeedbackState {
  ratings: Record<string, { rating: 1 | -1; reason?: string }>
  isLoading: boolean
  submitFeedback: (params: Omit<FeedbackCreate, 'investigation_id'>) => Promise<void>
  getRating: (targetType: TargetType, targetId: string) => { rating: 1 | -1; reason?: string } | null
}

const FeedbackContext = createContext<FeedbackState | null>(null)

interface FeedbackProviderProps {
  investigationId: string
  children: ReactNode
}

export function FeedbackProvider({ investigationId, children }: FeedbackProviderProps) {
  const { data: feedbackItems, isLoading } = useInvestigationFeedback(investigationId)
  const submitMutation = useSubmitFeedback(investigationId)

  const ratings = useMemo(() => {
    if (!feedbackItems) return {}
    return feedbackItems.reduce((acc, item) => {
      const key = `${item.target_type}:${item.target_id}`
      acc[key] = { rating: item.rating as 1 | -1, reason: item.reason ?? undefined }
      return acc
    }, {} as Record<string, { rating: 1 | -1; reason?: string }>)
  }, [feedbackItems])

  const submitFeedback = async (params: Omit<FeedbackCreate, 'investigation_id'>) => {
    await submitMutation.mutateAsync({
      ...params,
      investigation_id: investigationId,
    })
  }

  const getRating = (targetType: TargetType, targetId: string) => {
    const key = `${targetType}:${targetId}`
    return ratings[key] ?? null
  }

  return (
    <FeedbackContext.Provider value={{ ratings, isLoading, submitFeedback, getRating }}>
      {children}
    </FeedbackContext.Provider>
  )
}

export function useFeedback() {
  const context = useContext(FeedbackContext)
  if (!context) {
    throw new Error('useFeedback must be used within FeedbackProvider')
  }
  return context
}
```

**Step 2: Commit**

```bash
git add frontend/src/features/investigation/context/
git commit -m "feat(feedback): add FeedbackContext for state management"
```

---

## Task 7: Create FeedbackButtons Component

**Files:**
- Create: `frontend/src/features/investigation/components/FeedbackButtons.tsx`

**Step 1: Create FeedbackButtons component**

Create `frontend/src/features/investigation/components/FeedbackButtons.tsx`:

```tsx
import { useState } from 'react'
import { ThumbsUp, ThumbsDown } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Input } from '@/components/ui/Input'
import { useFeedback } from '../context/FeedbackContext'
import { TargetType } from '@/lib/api/feedback'
import { cn } from '@/lib/utils'

const REASON_OPTIONS: Record<TargetType, { positive: string[]; negative: string[] }> = {
  hypothesis: {
    positive: ['Right direction', 'Key insight'],
    negative: ['Dead end', 'Already known'],
  },
  query: {
    positive: ['Useful data', 'Confirmed suspicion'],
    negative: ['Wrong table', 'Inconclusive'],
  },
  evidence: {
    positive: ['Key proof', 'Clear signal'],
    negative: ['Noise', 'Misleading'],
  },
  synthesis: {
    positive: ['Solved it', 'Actionable'],
    negative: ['Partial answer', 'Missed root cause'],
  },
  investigation: {
    positive: ['Saved time', 'Found the issue'],
    negative: ['No value', 'Wrong conclusion'],
  },
}

interface FeedbackButtonsProps {
  targetType: TargetType
  targetId: string
}

export function FeedbackButtons({ targetType, targetId }: FeedbackButtonsProps) {
  const { getRating, submitFeedback } = useFeedback()
  const [openPopover, setOpenPopover] = useState<'up' | 'down' | null>(null)
  const [comment, setComment] = useState('')

  const currentRating = getRating(targetType, targetId)
  const reasons = REASON_OPTIONS[targetType]

  const handleRatingClick = (rating: 1 | -1) => {
    setOpenPopover(rating === 1 ? 'up' : 'down')
  }

  const handleReasonClick = async (reason: string) => {
    const rating = openPopover === 'up' ? 1 : -1
    await submitFeedback({
      target_type: targetType,
      target_id: targetId,
      rating,
      reason,
      comment: comment || undefined,
    })
    setOpenPopover(null)
    setComment('')
  }

  return (
    <div className="flex items-center gap-1">
      <Popover open={openPopover === 'up'} onOpenChange={(open) => !open && setOpenPopover(null)}>
        <PopoverTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              'h-7 w-7 p-0',
              currentRating?.rating === 1 && 'text-green-600 bg-green-50'
            )}
            onClick={() => handleRatingClick(1)}
          >
            <ThumbsUp className="h-4 w-4" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-56 p-3" align="start">
          <p className="text-sm font-medium mb-2">Why?</p>
          <div className="flex flex-wrap gap-2 mb-2">
            {reasons.positive.map((reason) => (
              <Button
                key={reason}
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => handleReasonClick(reason)}
              >
                {reason}
              </Button>
            ))}
          </div>
          <Input
            placeholder="Add comment..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className="text-xs h-7"
          />
        </PopoverContent>
      </Popover>

      <Popover open={openPopover === 'down'} onOpenChange={(open) => !open && setOpenPopover(null)}>
        <PopoverTrigger asChild>
          <Button
            variant="ghost"
            size="sm"
            className={cn(
              'h-7 w-7 p-0',
              currentRating?.rating === -1 && 'text-red-600 bg-red-50'
            )}
            onClick={() => handleRatingClick(-1)}
          >
            <ThumbsDown className="h-4 w-4" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-56 p-3" align="start">
          <p className="text-sm font-medium mb-2">Why?</p>
          <div className="flex flex-wrap gap-2 mb-2">
            {reasons.negative.map((reason) => (
              <Button
                key={reason}
                variant="outline"
                size="sm"
                className="text-xs"
                onClick={() => handleReasonClick(reason)}
              >
                {reason}
              </Button>
            ))}
          </div>
          <Input
            placeholder="Add comment..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className="text-xs h-7"
          />
        </PopoverContent>
      </Popover>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/features/investigation/components/FeedbackButtons.tsx
git commit -m "feat(feedback): add FeedbackButtons component with popover"
```

---

## Task 8: Update InvestigationDetail Page

**Files:**
- Modify: `frontend/src/features/investigation/InvestigationDetail.tsx`

**Step 1: Update InvestigationDetail to use feedback components**

Modify `frontend/src/features/investigation/InvestigationDetail.tsx`:

```tsx
import { useParams, Link } from 'react-router-dom'
import { useInvestigation } from '@/lib/api/investigations'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { formatPercentage } from '@/lib/utils'
import { ArrowLeft, RefreshCw, ChevronDown, ChevronRight } from 'lucide-react'
import { InvestigationLiveView } from './InvestigationLiveView'
import { SqlExplainer } from './SqlExplainer'
import { FeedbackProvider } from './context/FeedbackContext'
import { FeedbackButtons } from './components/FeedbackButtons'
import { useState } from 'react'

function getStatusVariant(status: string) {
  switch (status) {
    case 'completed':
      return 'success'
    case 'failed':
      return 'destructive'
    default:
      return 'warning'
  }
}

export function InvestigationDetail() {
  const { id } = useParams<{ id: string }>()
  const { data, isLoading, error } = useInvestigation(id!)
  const [expandedHypotheses, setExpandedHypotheses] = useState<Set<string>>(new Set())

  const toggleHypothesis = (hypothesisId: string) => {
    setExpandedHypotheses((prev) => {
      const next = new Set(prev)
      if (next.has(hypothesisId)) {
        next.delete(hypothesisId)
      } else {
        next.add(hypothesisId)
      }
      return next
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error || !data) {
    return (
      <Card>
        <CardContent className="py-12 text-center">
          <p className="text-destructive">
            Failed to load investigation: {error?.message || 'Not found'}
          </p>
          <Link to="/">
            <Button className="mt-4">Back to list</Button>
          </Link>
        </CardContent>
      </Card>
    )
  }

  // Sort evidence by confidence descending
  const sortedEvidence = [...(data.finding?.evidence || [])].sort(
    (a, b) => b.confidence - a.confidence
  )

  // Expand highest confidence hypothesis by default
  if (sortedEvidence.length > 0 && expandedHypotheses.size === 0) {
    setExpandedHypotheses(new Set([sortedEvidence[0].hypothesis_id]))
  }

  return (
    <FeedbackProvider investigationId={id!}>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <Link to="/">
              <Button variant="ghost" size="icon">
                <ArrowLeft className="h-4 w-4" />
              </Button>
            </Link>
            <h1 className="text-3xl font-bold">Investigation Details</h1>
            <Badge variant={getStatusVariant(data.status)}>{data.status}</Badge>
          </div>
          {data.status === 'completed' && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground">Rate this investigation:</span>
              <FeedbackButtons targetType="investigation" targetId={id!} />
            </div>
          )}
        </div>

        {/* Live Event View */}
        <Card>
          <CardHeader>
            <CardTitle>Investigation Progress</CardTitle>
          </CardHeader>
          <CardContent>
            <InvestigationLiveView events={data.events} status={data.status} />
          </CardContent>
        </Card>

        {/* Synthesis (at top) */}
        {data.finding && (
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Synthesis</CardTitle>
                <FeedbackButtons targetType="synthesis" targetId={id!} />
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <h4 className="font-semibold">Root Cause</h4>
                <p className="text-muted-foreground">
                  {data.finding.root_cause || 'Not determined'}
                </p>
              </div>

              <div>
                <h4 className="font-semibold">Confidence</h4>
                <p className="text-muted-foreground">
                  {formatPercentage(data.finding.confidence)}
                </p>
              </div>

              {data.finding.recommendations.length > 0 && (
                <div>
                  <h4 className="font-semibold">Recommendations</h4>
                  <ul className="list-disc list-inside text-muted-foreground">
                    {data.finding.recommendations.map((rec, i) => (
                      <li key={i}>{rec}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div>
                <h4 className="font-semibold">Duration</h4>
                <p className="text-muted-foreground">
                  {data.finding.duration_seconds.toFixed(1)}s
                </p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Evidence (accordion sorted by confidence) */}
        {sortedEvidence.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle>Evidence</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {sortedEvidence.map((ev) => {
                const isExpanded = expandedHypotheses.has(ev.hypothesis_id)
                return (
                  <div key={ev.hypothesis_id} className="border rounded-lg">
                    <button
                      className="w-full flex items-center justify-between p-4 hover:bg-muted/50"
                      onClick={() => toggleHypothesis(ev.hypothesis_id)}
                    >
                      <div className="flex items-center gap-3">
                        {isExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                        <span className="font-medium">
                          Hypothesis: {ev.hypothesis_id.slice(0, 8)}
                        </span>
                        <Badge variant="secondary">
                          {formatPercentage(ev.confidence)}
                        </Badge>
                      </div>
                      <div onClick={(e) => e.stopPropagation()}>
                        <FeedbackButtons
                          targetType="hypothesis"
                          targetId={ev.hypothesis_id}
                        />
                      </div>
                    </button>
                    {isExpanded && (
                      <div className="px-4 pb-4 space-y-4">
                        <div className="pl-7">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium">Query</span>
                            <FeedbackButtons
                              targetType="query"
                              targetId={`${ev.hypothesis_id}-query`}
                            />
                          </div>
                          <SqlExplainer sql={ev.query} />
                        </div>
                        <div className="pl-7">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-sm font-medium">Evidence</span>
                            <FeedbackButtons
                              targetType="evidence"
                              targetId={`${ev.hypothesis_id}-evidence`}
                            />
                          </div>
                          <p className="text-sm text-muted-foreground">
                            {ev.interpretation}
                          </p>
                          <p className="text-xs text-muted-foreground mt-1">
                            {ev.row_count} rows returned
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                )
              })}
            </CardContent>
          </Card>
        )}
      </div>
    </FeedbackProvider>
  )
}
```

**Step 2: Run frontend linting**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system/frontend && pnpm lint --fix`

**Step 3: Commit**

```bash
git add frontend/src/features/investigation/InvestigationDetail.tsx
git commit -m "feat(feedback): integrate feedback buttons into InvestigationDetail"
```

---

## Task 9: Run All Tests and Final Verification

**Step 1: Run backend tests**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run pytest backend/tests/unit/entrypoints/api/routes/test_feedback.py backend/tests/unit/adapters/feedback/ -v`

Expected: All tests pass

**Step 2: Run backend linting**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system && uv run ruff check backend/src/dataing/entrypoints/api/routes/feedback.py --fix && uv run mypy backend/src/dataing/entrypoints/api/routes/feedback.py`

**Step 3: Run frontend type check**

Run: `cd /Users/bordumb/workspace/repositories/dataing/.worktrees/feedback-system/frontend && pnpm typecheck`

**Step 4: Final commit**

```bash
git add -A
git commit -m "chore(feedback): phase 2 complete - user feedback collection ready"
```

---

## Summary

Phase 2 adds user feedback collection:

| Component | File | Purpose |
|-----------|------|---------|
| API Schemas | `backend/.../routes/feedback.py` | FeedbackCreate, FeedbackResponse |
| POST Endpoint | `backend/.../routes/feedback.py` | Submit feedback |
| GET Endpoint | `backend/.../routes/feedback.py` | Retrieve user's feedback |
| Popover UI | `frontend/.../ui/popover.tsx` | Radix popover component |
| API Client | `frontend/.../api/feedback.ts` | React Query hooks |
| Context | `frontend/.../context/FeedbackContext.tsx` | Feedback state management |
| Buttons | `frontend/.../components/FeedbackButtons.tsx` | 👍👎 with tooltip |
| Detail Page | `frontend/.../InvestigationDetail.tsx` | Integrated feedback UI |

Next: Phase 3 - Dataset Knowledge Aggregation
