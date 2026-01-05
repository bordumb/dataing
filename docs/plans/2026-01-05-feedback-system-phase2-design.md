# Feedback System Phase 2: User Feedback Collection

## Overview

Add user feedback collection to the investigation detail UI. Users can rate hypotheses, queries, evidence, synthesis, and the overall investigation with thumbs up/down plus quick-select reasons.

## API Design

### Endpoint: `POST /api/v1/feedback`

```
Request body:
{
  "target_type": "hypothesis" | "query" | "evidence" | "synthesis" | "investigation",
  "target_id": "uuid",
  "investigation_id": "uuid",
  "rating": 1 | -1,
  "reason": "string (quick-select option)",
  "comment": "string (optional free text)"
}

Response: 201 Created
{
  "id": "uuid",
  "created_at": "timestamp"
}
```

### Quick-select reason options by target:

| Target | Positive (+1) | Negative (-1) |
|--------|---------------|---------------|
| hypothesis | "Right direction", "Key insight" | "Dead end", "Already known" |
| query | "Useful data", "Confirmed suspicion" | "Wrong table", "Inconclusive" |
| evidence | "Key proof", "Clear signal" | "Noise", "Misleading" |
| synthesis | "Solved it", "Actionable" | "Partial answer", "Missed root cause" |
| investigation | "Saved time", "Found the issue" | "No value", "Wrong conclusion" |

### Read endpoint: `GET /api/v1/investigations/:id/feedback`

Returns list of current user's feedback for that investigation.

## Frontend Layout

```
┌─────────────────────────────────────────────────────────────┐
│ Investigation: NULL Spike in public.orders                  │
│ Status: Completed    Confidence: 0.87    [Rate Investigation]│
├─────────────────────────────────────────────────────────────┤
│ Synthesis                                            👍 👎  │
│ Root cause: Mobile app v2.3 introduced a bug that...        │
│ Recommendation: Roll back to v2.2 or hotfix the...          │
├─────────────────────────────────────────────────────────────┤
│ Evidence                                                     │
│                                                              │
│ ▼ Hypothesis: Mobile app v2.3 NULL bug (conf: 0.92)  👍 👎  │
│   ┌─────────────────────────────────────────────────────────┐
│   │ Query: SELECT date, COUNT(*) FROM orders...      👍 👎  │
│   │ Evidence: 94% of NULLs from app_version='2.3'    👍 👎  │
│   └─────────────────────────────────────────────────────────┘
│                                                              │
│ ▶ Hypothesis: ETL pipeline failure (conf: 0.34)      👍 👎  │
│                                                              │
│ ▶ Hypothesis: Schema migration issue (conf: 0.21)    👍 👎  │
└─────────────────────────────────────────────────────────────┘
```

Key layout decisions:
- Synthesis at top (main answer, most important)
- Hypotheses sorted by confidence descending
- Highest-confidence hypothesis expanded by default, others collapsed
- "Rate Investigation" button in header (user-triggered, not automatic)

## Feedback Tooltip Interaction

```
                                    ┌─────────────────────────┐
                                    │ Why?                    │
  👍  👎  ←── user clicks 👍 ──────▶│ ┌───────────┐ ┌───────┐ │
                                    │ │ Right     │ │ Key   │ │
                                    │ │ direction │ │insight│ │
                                    │ └───────────┘ └───────┘ │
                                    │ ┌─────────────────────┐ │
                                    │ │ Add comment...      │ │
                                    │ └─────────────────────┘ │
                                    └─────────────────────────┘
```

Interaction flow:
1. User clicks 👍 or 👎 → Tooltip pops up from that button's corner
2. Shows "Why?" + 2 quick-select chips (target-specific based on +1 or -1)
3. Small "Add comment..." input below (expands on focus)
4. Clicking a chip submits immediately → tooltip closes → button shows filled state
5. Clicking outside dismisses tooltip without submitting (rating still counts, reason optional)
6. If user already rated, clicking again shows tooltip to change rating

Implementation: Use Radix UI Popover (shadcn/ui) anchored to the clicked button.

## Backend Implementation

### Route: `POST /api/v1/feedback`

```python
# backend/src/dataing/entrypoints/api/routes/feedback.py

@router.post("/feedback", status_code=201)
async def submit_feedback(
    body: FeedbackCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AppDatabase = Depends(get_db),
    feedback_adapter: FeedbackAdapter = Depends(get_feedback_adapter),
):
    # Validate target exists and belongs to investigation
    # Emit event via FeedbackAdapter (built in Phase 1)
    # Return created event ID
```

### Request/Response schemas:

```python
class FeedbackCreate(BaseModel):
    target_type: Literal["hypothesis", "query", "evidence", "synthesis", "investigation"]
    target_id: UUID
    investigation_id: UUID
    rating: Literal[1, -1]
    reason: str | None = None
    comment: str | None = None

class FeedbackResponse(BaseModel):
    id: UUID
    created_at: datetime
```

Reuses `FeedbackAdapter.emit()` and `AppDatabase.list_feedback_events()` from Phase 1.

## Frontend Implementation

### API client (generated via orval):

```typescript
// POST /api/v1/feedback
submitFeedback(body: FeedbackCreate): Promise<FeedbackResponse>

// GET /api/v1/investigations/:id/feedback
getInvestigationFeedback(investigationId: string): Promise<FeedbackEvent[]>
```

### React state:

```typescript
// FeedbackContext.tsx - scoped to investigation detail page
type FeedbackState = {
  // Map of "targetType:targetId" → user's feedback
  ratings: Record<string, { rating: 1 | -1; reason?: string }>
  submitFeedback: (params: FeedbackCreate) => Promise<void>
}
```

### Component data flow:

1. `InvestigationDetail` page mounts → calls `getInvestigationFeedback(id)`
2. Populates `FeedbackContext` with existing ratings
3. `FeedbackButtons` reads from context to show filled/unfilled state
4. On submit → calls `submitFeedback()` → updates context → shows filled state
5. Optimistic update: button fills immediately, reverts if API fails

### Files to create/modify:

| File | Purpose |
|------|---------|
| `frontend/src/lib/api/feedback.ts` | API client hooks |
| `frontend/src/features/investigations/context/FeedbackContext.tsx` | State management |
| `frontend/src/features/investigations/components/FeedbackButtons.tsx` | 👍👎 component |
| `frontend/src/features/investigations/components/FeedbackTooltip.tsx` | Popover with reasons |

## Testing Strategy

### Backend tests:

| Test | Purpose |
|------|---------|
| `test_submit_feedback_success` | Valid feedback creates event |
| `test_submit_feedback_invalid_target` | Returns 404 for non-existent target |
| `test_submit_feedback_wrong_investigation` | Returns 400 if target doesn't belong to investigation |
| `test_get_investigation_feedback` | Returns only current user's feedback |
| `test_feedback_updates_on_resubmit` | Second rating replaces first |

### Frontend tests:

| Test | Purpose |
|------|---------|
| `FeedbackButtons` renders unfilled initially | No rating state |
| `FeedbackButtons` shows filled after submit | Optimistic update |
| `FeedbackTooltip` shows correct options for thumbs up | Target-specific reasons |
| `FeedbackTooltip` shows correct options for thumbs down | Different reasons |
| `FeedbackTooltip` submits on chip click | Auto-close behavior |

### Integration test:

End-to-end: Load investigation → click 👍 on hypothesis → select reason → verify event in database → reload page → verify button still filled.
