# Phase 3: Dataset Comments & Knowledge Tab

## Overview

Add a threaded comment system for datasets with two surfaces:
1. **Schema Tab** - Comments anchored to specific schema fields (slide-out panel)
2. **Knowledge Tab** - General dataset-level discussion

## Scope

### In Scope
- Rename existing `feedback` → `investigation_feedback`
- Schema field comments with threading
- Knowledge tab with threaded discussion
- Thumbs up/down voting on comments
- Markdown support with links
- Basic @mentions (text only, no autocomplete/notifications)

### Out of Scope (Deferred)
- Top Findings aggregation
- @mention autocomplete and notifications
- Comment editing history
- Real-time updates (polling is fine)

## Data Model

### Rename Existing

| Before | After |
|--------|-------|
| `feedback_events` table | `investigation_feedback_events` |
| `FeedbackAdapter` | `InvestigationFeedbackAdapter` |
| `/api/v1/feedback/` | `/api/v1/investigation-feedback/` |
| `feedback.ts` | `investigation-feedback.ts` |

### New Tables

```sql
-- Schema field comments
CREATE TABLE schema_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    field_name VARCHAR(255) NOT NULL,
    parent_id UUID REFERENCES schema_comments(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    author_id UUID,
    author_name VARCHAR(255),
    upvotes INT DEFAULT 0,
    downvotes INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Knowledge tab comments
CREATE TABLE knowledge_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES knowledge_comments(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    author_id UUID,
    author_name VARCHAR(255),
    upvotes INT DEFAULT 0,
    downvotes INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Unified votes table
CREATE TABLE comment_votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    comment_type VARCHAR(50) NOT NULL,  -- 'schema' or 'knowledge'
    comment_id UUID NOT NULL,
    user_id UUID NOT NULL,
    vote INT NOT NULL CHECK (vote IN (1, -1)),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(comment_type, comment_id, user_id)
);

-- Indexes
CREATE INDEX idx_schema_comments_dataset ON schema_comments(tenant_id, dataset_id, field_name);
CREATE INDEX idx_knowledge_comments_dataset ON knowledge_comments(tenant_id, dataset_id);
CREATE INDEX idx_comment_votes_lookup ON comment_votes(comment_type, comment_id);
```

### Threading Model (Adjacency List)

```
parent_id = NULL     → Thread root (new conversation)
parent_id = <uuid>   → Reply to that comment
```

Example for field `user_id`:

| id | field_name | parent_id | content | author |
|----|------------|-----------|---------|--------|
| A | user_id | NULL | "iOS 18.2 has nulls" | Bob |
| B | user_id | A | "Fixed in v2.4" | Alice |
| C | user_id | A | "Still seeing it" | Carol |
| D | user_id | NULL | "Unrelated topic" | Timothy |
| E | user_id | D | "Reply to Timothy" | Bob |

Results in:
```
Thread 1 (A): "iOS 18.2 has nulls" - Bob
  └── Reply (B): "Fixed in v2.4" - Alice
  └── Reply (C): "Still seeing it" - Carol

Thread 2 (D): "Unrelated topic" - Timothy
  └── Reply (E): "Reply to Timothy" - Bob
```

## API Endpoints

### Renamed Investigation Feedback

- `POST /api/v1/investigation-feedback/` – Submit feedback
- `GET /api/v1/investigation-feedback/investigations/{id}` – Get feedback for investigation

### Schema Comments

- `GET /api/v1/datasets/{id}/schema-comments` – All comments grouped by field
- `GET /api/v1/datasets/{id}/schema-comments/{field_name}` – Comments for specific field
- `POST /api/v1/datasets/{id}/schema-comments` – Create comment/reply
- `PATCH /api/v1/datasets/{id}/schema-comments/{comment_id}` – Edit comment
- `DELETE /api/v1/datasets/{id}/schema-comments/{comment_id}` – Delete comment

### Knowledge Comments

- `GET /api/v1/datasets/{id}/knowledge-comments` – All discussion threads
- `POST /api/v1/datasets/{id}/knowledge-comments` – Create comment/reply
- `PATCH /api/v1/datasets/{id}/knowledge-comments/{comment_id}` – Edit
- `DELETE /api/v1/datasets/{id}/knowledge-comments/{comment_id}` – Delete

### Comment Voting

- `POST /api/v1/comments/{comment_type}/{comment_id}/vote` – Vote (`{ "vote": 1 }` or `{ "vote": -1 }`)
- `DELETE /api/v1/comments/{comment_type}/{comment_id}/vote` – Remove vote

## Frontend UI

### Schema Tab Changes

1. **Comment indicator** – Chat bubble icon at far-right of each field row
   - Filled if comments exist
   - Outline if none

2. **Hover behavior** – "Leave comment" tooltip on row hover

3. **Click behavior** – Opens slide-out panel from right

### Slide-out Panel

```
┌─────────────────────────────────────────┐
│ Comments: user_id              [×]      │
├─────────────────────────────────────────┤
│ ┌─────────────────────────────────────┐ │
│ │ + New thread                        │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ▼ Thread: "iOS 18.2 nulls" (3) 👍5 👎1  │
│   Bob · 2 days ago                      │
│   This field has nulls for iOS 18.2... │
│   [Reply]                               │
│     └─ Alice · 1 day ago                │
│        Fixed in v2.4                    │
│        👍2 [Reply]                      │
│     └─ Carol · 3 hours ago              │
│        Still seeing it on prod          │
│        [Reply]                          │
│                                         │
│ ▼ Thread: "Column rename planned" 👍0   │
│   Timothy · 1 week ago                  │
│   FYI we're renaming this to...         │
│   [Reply]                               │
└─────────────────────────────────────────┘
```

### Knowledge Tab

Same thread/comment UI but displayed full-width in the tab content area (not slide-out).

### Ranking

1. If votes exist: sort by (upvotes - downvotes) descending
2. If no votes: sort by created_at descending (newest first)

## File Structure

### Backend

```
backend/src/dataing/
├── adapters/
│   ├── feedback/                         # Rename to investigation_feedback/
│   └── comments/                         # NEW
│       ├── __init__.py
│       ├── schema_comments.py
│       └── knowledge_comments.py
├── entrypoints/api/routes/
│   ├── feedback.py                       # Rename to investigation_feedback.py
│   ├── schema_comments.py                # NEW
│   ├── knowledge_comments.py             # NEW
│   └── comment_votes.py                  # NEW

backend/migrations/
├── 003_feedback_events.sql               # Rename to 003_investigation_feedback_events.sql
├── 004_schema_comments.sql               # NEW
├── 005_knowledge_comments.sql            # NEW
└── 006_comment_votes.sql                 # NEW
```

### Frontend

```
frontend/src/
├── lib/api/
│   ├── feedback.ts                       # Rename to investigation-feedback.ts
│   ├── schema-comments.ts                # NEW
│   ├── knowledge-comments.ts             # NEW
│   └── comment-votes.ts                  # NEW
├── features/
│   ├── investigation/
│   │   └── context/
│   │       └── FeedbackContext.tsx       # Rename to InvestigationFeedbackContext.tsx
│   └── datasets/
│       ├── dataset-detail-page.tsx       # Add Knowledge tab
│       └── components/                   # NEW
│           ├── schema-comment-indicator.tsx
│           ├── comment-slide-panel.tsx
│           ├── comment-thread.tsx
│           ├── comment-item.tsx
│           ├── comment-editor.tsx
│           └── knowledge-tab.tsx
```

## Migration Order

1. Rename existing feedback system → investigation_feedback
2. Create `schema_comments` table
3. Create `knowledge_comments` table
4. Create `comment_votes` table
