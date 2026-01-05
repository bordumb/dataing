# Phase 3: Comments System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a threaded comment system for dataset schema fields and a Knowledge tab for dataset-level discussion.

**Architecture:** Two comment tables (schema_comments, knowledge_comments) with unified voting. Slide-out panel UI for schema comments, full-width tab for knowledge. Adjacency list for threading.

**Tech Stack:** FastAPI, asyncpg, PostgreSQL, React, TanStack Query, Radix UI, Tailwind CSS

---

## Part 1: Rename Feedback → Investigation Feedback

### Task 1.1: Rename Backend Migration File

**Files:**
- Rename: `backend/migrations/003_feedback_events.sql` → `backend/migrations/003_investigation_feedback_events.sql`

**Step 1: Rename the file**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/phase3-comments
git mv backend/migrations/003_feedback_events.sql backend/migrations/003_investigation_feedback_events.sql
```

**Step 2: Update table name in migration**

Edit `backend/migrations/003_investigation_feedback_events.sql`:
- Change `CREATE TABLE feedback_events` → `CREATE TABLE investigation_feedback_events`
- Update index names accordingly

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor: rename feedback_events table to investigation_feedback_events"
```

---

### Task 1.2: Rename Backend Adapter Directory

**Files:**
- Rename: `backend/src/dataing/adapters/feedback/` → `backend/src/dataing/adapters/investigation_feedback/`

**Step 1: Rename directory**

```bash
git mv backend/src/dataing/adapters/feedback backend/src/dataing/adapters/investigation_feedback
```

**Step 2: Update adapter __init__.py exports**

Edit `backend/src/dataing/adapters/investigation_feedback/__init__.py` - update any references.

**Step 3: Update adapters/__init__.py**

Edit `backend/src/dataing/adapters/__init__.py` - change import from `feedback` to `investigation_feedback`.

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: rename feedback adapter to investigation_feedback"
```

---

### Task 1.3: Rename Backend Route File

**Files:**
- Rename: `backend/src/dataing/entrypoints/api/routes/feedback.py` → `backend/src/dataing/entrypoints/api/routes/investigation_feedback.py`
- Modify: `backend/src/dataing/entrypoints/api/routes/__init__.py`

**Step 1: Rename file**

```bash
git mv backend/src/dataing/entrypoints/api/routes/feedback.py backend/src/dataing/entrypoints/api/routes/investigation_feedback.py
```

**Step 2: Update route prefix**

Edit `backend/src/dataing/entrypoints/api/routes/investigation_feedback.py`:
```python
router = APIRouter(prefix="/investigation-feedback", tags=["investigation-feedback"])
```

**Step 3: Update routes __init__.py**

Edit `backend/src/dataing/entrypoints/api/routes/__init__.py`:
- Change `from .feedback import router as feedback_router` → `from .investigation_feedback import router as investigation_feedback_router`
- Update the router registration

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: rename feedback routes to investigation-feedback"
```

---

### Task 1.4: Update All Backend Imports

**Files:**
- Modify: All files importing from `dataing.adapters.feedback` or `dataing.entrypoints.api.routes.feedback`

**Step 1: Find and update imports**

```bash
grep -r "from dataing.adapters.feedback" backend/src --include="*.py"
grep -r "from dataing.entrypoints.api.routes.feedback" backend/src --include="*.py"
```

Update each file to use `investigation_feedback` instead of `feedback`.

**Step 2: Update FeedbackAdapter class name**

In `backend/src/dataing/adapters/investigation_feedback/adapter.py`:
- Rename `FeedbackAdapter` → `InvestigationFeedbackAdapter`
- Rename `FeedbackEmitter` protocol → `InvestigationFeedbackEmitter`

**Step 3: Update all references to these classes**

**Step 4: Run tests**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/phase3-comments
PYTHONPATH=backend/src uv run pytest backend/tests/unit -v --tb=short
```

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: update all backend imports for investigation_feedback rename"
```

---

### Task 1.5: Rename Backend Test Files

**Files:**
- Rename: `backend/tests/unit/adapters/feedback/` → `backend/tests/unit/adapters/investigation_feedback/`
- Rename: `backend/tests/unit/entrypoints/api/routes/test_feedback.py` → `backend/tests/unit/entrypoints/api/routes/test_investigation_feedback.py`
- Rename: `backend/tests/integration/adapters/feedback/` → `backend/tests/integration/adapters/investigation_feedback/`

**Step 1: Rename directories and files**

```bash
git mv backend/tests/unit/adapters/feedback backend/tests/unit/adapters/investigation_feedback
git mv backend/tests/unit/entrypoints/api/routes/test_feedback.py backend/tests/unit/entrypoints/api/routes/test_investigation_feedback.py
git mv backend/tests/integration/adapters/feedback backend/tests/integration/adapters/investigation_feedback
```

**Step 2: Update imports in test files**

Update all test files to import from new locations.

**Step 3: Run tests**

```bash
PYTHONPATH=backend/src uv run pytest backend/tests/unit -v --tb=short
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor: rename feedback test files to investigation_feedback"
```

---

### Task 1.6: Rename Frontend Files

**Files:**
- Rename: `frontend/src/lib/api/feedback.ts` → `frontend/src/lib/api/investigation-feedback.ts`
- Rename: `frontend/src/features/investigation/context/FeedbackContext.tsx` → `frontend/src/features/investigation/context/InvestigationFeedbackContext.tsx`
- Rename: `frontend/src/features/investigation/components/FeedbackButtons.tsx` → `frontend/src/features/investigation/components/InvestigationFeedbackButtons.tsx`

**Step 1: Rename files**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/phase3-comments/frontend
git mv src/lib/api/feedback.ts src/lib/api/investigation-feedback.ts
git mv src/features/investigation/context/FeedbackContext.tsx src/features/investigation/context/InvestigationFeedbackContext.tsx
git mv src/features/investigation/components/FeedbackButtons.tsx src/features/investigation/components/InvestigationFeedbackButtons.tsx
```

**Step 2: Update API endpoint URLs**

Edit `frontend/src/lib/api/investigation-feedback.ts`:
- Change `/api/v1/feedback/` → `/api/v1/investigation-feedback/`

**Step 3: Update exports and imports**

- Update `frontend/src/lib/api/query-keys.ts` - rename `feedback` key
- Update all imports in `InvestigationDetail.tsx` and other files

**Step 4: Verify build**

```bash
pnpm build
```

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename frontend feedback to investigation-feedback"
```

---

### Task 1.7: Regenerate OpenAPI Client

**Files:**
- Modify: `backend/openapi.json`
- Regenerate: `frontend/src/lib/api/generated/`

**Step 1: Export OpenAPI schema**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/phase3-comments/backend
uv run python scripts/export_openapi.py
```

**Step 2: Regenerate client**

```bash
cd ../frontend
pnpm orval
```

**Step 3: Verify frontend builds**

```bash
pnpm build
```

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: regenerate OpenAPI client after investigation-feedback rename"
```

---

## Part 2: Create Comment Tables

### Task 2.1: Create Schema Comments Migration

**Files:**
- Create: `backend/migrations/004_schema_comments.sql`

**Step 1: Write migration**

Create `backend/migrations/004_schema_comments.sql`:

```sql
-- Schema field comments (threaded)
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

CREATE INDEX idx_schema_comments_dataset ON schema_comments(tenant_id, dataset_id, field_name);
CREATE INDEX idx_schema_comments_parent ON schema_comments(parent_id);
```

**Step 2: Commit**

```bash
git add backend/migrations/004_schema_comments.sql
git commit -m "feat: add schema_comments table migration"
```

---

### Task 2.2: Create Knowledge Comments Migration

**Files:**
- Create: `backend/migrations/005_knowledge_comments.sql`

**Step 1: Write migration**

Create `backend/migrations/005_knowledge_comments.sql`:

```sql
-- Knowledge tab comments (dataset-level discussion)
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

CREATE INDEX idx_knowledge_comments_dataset ON knowledge_comments(tenant_id, dataset_id);
CREATE INDEX idx_knowledge_comments_parent ON knowledge_comments(parent_id);
```

**Step 2: Commit**

```bash
git add backend/migrations/005_knowledge_comments.sql
git commit -m "feat: add knowledge_comments table migration"
```

---

### Task 2.3: Create Comment Votes Migration

**Files:**
- Create: `backend/migrations/006_comment_votes.sql`

**Step 1: Write migration**

Create `backend/migrations/006_comment_votes.sql`:

```sql
-- Unified comment votes table
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

CREATE INDEX idx_comment_votes_lookup ON comment_votes(comment_type, comment_id);
```

**Step 2: Commit**

```bash
git add backend/migrations/006_comment_votes.sql
git commit -m "feat: add comment_votes table migration"
```

---

### Task 2.4: Update justfile Demo Command

**Files:**
- Modify: `justfile`

**Step 1: Add new migrations to demo command**

Edit `justfile` - in the demo recipe, add the new migrations after the existing ones:

```bash
PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f backend/migrations/004_schema_comments.sql 2>/dev/null || true
PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f backend/migrations/005_knowledge_comments.sql 2>/dev/null || true
PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f backend/migrations/006_comment_votes.sql 2>/dev/null || true
```

**Step 2: Commit**

```bash
git add justfile
git commit -m "chore: add comment migrations to just demo"
```

---

## Part 3: Backend Schema Comments API

### Task 3.1: Create Schema Comments Adapter - Types

**Files:**
- Create: `backend/src/dataing/adapters/comments/__init__.py`
- Create: `backend/src/dataing/adapters/comments/types.py`

**Step 1: Create directory and __init__.py**

```bash
mkdir -p backend/src/dataing/adapters/comments
```

**Step 2: Write types.py**

Create `backend/src/dataing/adapters/comments/types.py`:

```python
"""Type definitions for comments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class SchemaComment:
    """A comment on a schema field."""

    id: UUID
    tenant_id: UUID
    dataset_id: UUID
    field_name: str
    parent_id: UUID | None
    content: str
    author_id: UUID | None
    author_name: str | None
    upvotes: int
    downvotes: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class KnowledgeComment:
    """A comment on dataset knowledge tab."""

    id: UUID
    tenant_id: UUID
    dataset_id: UUID
    parent_id: UUID | None
    content: str
    author_id: UUID | None
    author_name: str | None
    upvotes: int
    downvotes: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class CommentVote:
    """A vote on a comment."""

    id: UUID
    tenant_id: UUID
    comment_type: str
    comment_id: UUID
    user_id: UUID
    vote: int
    created_at: datetime
```

**Step 3: Write __init__.py**

Create `backend/src/dataing/adapters/comments/__init__.py`:

```python
"""Comments adapters."""

from dataing.adapters.comments.types import (
    CommentVote,
    KnowledgeComment,
    SchemaComment,
)

__all__ = ["SchemaComment", "KnowledgeComment", "CommentVote"]
```

**Step 4: Commit**

```bash
git add backend/src/dataing/adapters/comments/
git commit -m "feat: add comment type definitions"
```

---

### Task 3.2: Add Schema Comments Repository Methods to AppDatabase

**Files:**
- Modify: `backend/src/dataing/adapters/db/app_db.py`
- Create: `backend/tests/unit/adapters/db/test_app_db_schema_comments.py`

**Step 1: Write failing test**

Create `backend/tests/unit/adapters/db/test_app_db_schema_comments.py`:

```python
"""Tests for schema comments database methods."""

from __future__ import annotations

from uuid import uuid4

import pytest

from dataing.adapters.db.app_db import AppDatabase


class TestSchemaComments:
    """Tests for schema comment CRUD operations."""

    @pytest.fixture
    def db(self) -> AppDatabase:
        """Create AppDatabase instance."""
        return AppDatabase(pool=None)  # type: ignore[arg-type]

    def test_create_schema_comment_returns_comment(self, db: AppDatabase) -> None:
        """Test that create_schema_comment returns the created comment."""
        # This test will fail until we implement the method
        assert hasattr(db, "create_schema_comment")
```

**Step 2: Run test to verify failure**

```bash
PYTHONPATH=backend/src uv run pytest backend/tests/unit/adapters/db/test_app_db_schema_comments.py -v
```

Expected: FAIL with AttributeError

**Step 3: Implement create_schema_comment method**

Add to `backend/src/dataing/adapters/db/app_db.py`:

```python
async def create_schema_comment(
    self,
    tenant_id: UUID,
    dataset_id: UUID,
    field_name: str,
    content: str,
    parent_id: UUID | None = None,
    author_id: UUID | None = None,
    author_name: str | None = None,
) -> dict[str, Any]:
    """Create a schema comment.

    Args:
        tenant_id: The tenant ID.
        dataset_id: The dataset ID.
        field_name: The schema field name.
        content: The comment content (markdown).
        parent_id: Parent comment ID for replies.
        author_id: The author's user ID.
        author_name: The author's display name.

    Returns:
        The created comment as a dict.
    """
    query = """
        INSERT INTO schema_comments (tenant_id, dataset_id, field_name, parent_id, content, author_id, author_name)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id, tenant_id, dataset_id, field_name, parent_id, content, author_id, author_name, upvotes, downvotes, created_at, updated_at
    """
    row = await self._pool.fetchrow(
        query, tenant_id, dataset_id, field_name, parent_id, content, author_id, author_name
    )
    return dict(row)
```

**Step 4: Add list, get, update, delete methods**

Continue adding these methods to `app_db.py`:

```python
async def list_schema_comments(
    self,
    tenant_id: UUID,
    dataset_id: UUID,
    field_name: str | None = None,
) -> list[dict[str, Any]]:
    """List schema comments for a dataset.

    Args:
        tenant_id: The tenant ID.
        dataset_id: The dataset ID.
        field_name: Optional filter by field name.

    Returns:
        List of comments ordered by votes then recency.
    """
    if field_name:
        query = """
            SELECT id, tenant_id, dataset_id, field_name, parent_id, content, author_id, author_name, upvotes, downvotes, created_at, updated_at
            FROM schema_comments
            WHERE tenant_id = $1 AND dataset_id = $2 AND field_name = $3
            ORDER BY (upvotes - downvotes) DESC, created_at DESC
        """
        rows = await self._pool.fetch(query, tenant_id, dataset_id, field_name)
    else:
        query = """
            SELECT id, tenant_id, dataset_id, field_name, parent_id, content, author_id, author_name, upvotes, downvotes, created_at, updated_at
            FROM schema_comments
            WHERE tenant_id = $1 AND dataset_id = $2
            ORDER BY field_name, (upvotes - downvotes) DESC, created_at DESC
        """
        rows = await self._pool.fetch(query, tenant_id, dataset_id)
    return [dict(row) for row in rows]


async def get_schema_comment(
    self,
    tenant_id: UUID,
    comment_id: UUID,
) -> dict[str, Any] | None:
    """Get a single schema comment.

    Args:
        tenant_id: The tenant ID.
        comment_id: The comment ID.

    Returns:
        The comment or None if not found.
    """
    query = """
        SELECT id, tenant_id, dataset_id, field_name, parent_id, content, author_id, author_name, upvotes, downvotes, created_at, updated_at
        FROM schema_comments
        WHERE tenant_id = $1 AND id = $2
    """
    row = await self._pool.fetchrow(query, tenant_id, comment_id)
    return dict(row) if row else None


async def update_schema_comment(
    self,
    tenant_id: UUID,
    comment_id: UUID,
    content: str,
) -> dict[str, Any] | None:
    """Update a schema comment's content.

    Args:
        tenant_id: The tenant ID.
        comment_id: The comment ID.
        content: The new content.

    Returns:
        The updated comment or None if not found.
    """
    query = """
        UPDATE schema_comments
        SET content = $3, updated_at = now()
        WHERE tenant_id = $1 AND id = $2
        RETURNING id, tenant_id, dataset_id, field_name, parent_id, content, author_id, author_name, upvotes, downvotes, created_at, updated_at
    """
    row = await self._pool.fetchrow(query, tenant_id, comment_id, content)
    return dict(row) if row else None


async def delete_schema_comment(
    self,
    tenant_id: UUID,
    comment_id: UUID,
) -> bool:
    """Delete a schema comment.

    Args:
        tenant_id: The tenant ID.
        comment_id: The comment ID.

    Returns:
        True if deleted, False if not found.
    """
    query = """
        DELETE FROM schema_comments
        WHERE tenant_id = $1 AND id = $2
    """
    result = await self._pool.execute(query, tenant_id, comment_id)
    return result == "DELETE 1"
```

**Step 5: Run tests**

```bash
PYTHONPATH=backend/src uv run pytest backend/tests/unit/adapters/db/test_app_db_schema_comments.py -v
```

**Step 6: Commit**

```bash
git add -A
git commit -m "feat: add schema comments repository methods"
```

---

### Task 3.3: Create Schema Comments API Routes

**Files:**
- Create: `backend/src/dataing/entrypoints/api/routes/schema_comments.py`
- Modify: `backend/src/dataing/entrypoints/api/routes/__init__.py`

**Step 1: Write routes**

Create `backend/src/dataing/entrypoints/api/routes/schema_comments.py`:

```python
"""API routes for schema comments."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

router = APIRouter(prefix="/datasets/{dataset_id}/schema-comments", tags=["schema-comments"])

AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
DbDep = Annotated[AppDatabase, Depends(get_app_db)]


class SchemaCommentCreate(BaseModel):
    """Request body for creating a schema comment."""

    field_name: str
    content: str
    parent_id: UUID | None = None


class SchemaCommentUpdate(BaseModel):
    """Request body for updating a schema comment."""

    content: str


class SchemaCommentResponse(BaseModel):
    """Response for a schema comment."""

    id: UUID
    dataset_id: UUID
    field_name: str
    parent_id: UUID | None
    content: str
    author_id: UUID | None
    author_name: str | None
    upvotes: int
    downvotes: int
    created_at: datetime
    updated_at: datetime


@router.get("/", response_model=list[SchemaCommentResponse])
async def list_schema_comments(
    dataset_id: UUID,
    auth: AuthDep,
    db: DbDep,
    field_name: str | None = None,
) -> list[SchemaCommentResponse]:
    """List schema comments for a dataset."""
    comments = await db.list_schema_comments(
        tenant_id=auth.tenant_id,
        dataset_id=dataset_id,
        field_name=field_name,
    )
    return [SchemaCommentResponse(**c) for c in comments]


@router.post("/", status_code=201, response_model=SchemaCommentResponse)
async def create_schema_comment(
    dataset_id: UUID,
    body: SchemaCommentCreate,
    auth: AuthDep,
    db: DbDep,
) -> SchemaCommentResponse:
    """Create a schema comment."""
    comment = await db.create_schema_comment(
        tenant_id=auth.tenant_id,
        dataset_id=dataset_id,
        field_name=body.field_name,
        content=body.content,
        parent_id=body.parent_id,
        author_id=auth.user_id if hasattr(auth, "user_id") else None,
        author_name=auth.user_name if hasattr(auth, "user_name") else None,
    )
    return SchemaCommentResponse(**comment)


@router.patch("/{comment_id}", response_model=SchemaCommentResponse)
async def update_schema_comment(
    dataset_id: UUID,
    comment_id: UUID,
    body: SchemaCommentUpdate,
    auth: AuthDep,
    db: DbDep,
) -> SchemaCommentResponse:
    """Update a schema comment."""
    comment = await db.update_schema_comment(
        tenant_id=auth.tenant_id,
        comment_id=comment_id,
        content=body.content,
    )
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    return SchemaCommentResponse(**comment)


@router.delete("/{comment_id}", status_code=204)
async def delete_schema_comment(
    dataset_id: UUID,
    comment_id: UUID,
    auth: AuthDep,
    db: DbDep,
) -> None:
    """Delete a schema comment."""
    deleted = await db.delete_schema_comment(
        tenant_id=auth.tenant_id,
        comment_id=comment_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Comment not found")
```

**Step 2: Register router**

Edit `backend/src/dataing/entrypoints/api/routes/__init__.py` to import and include the new router.

**Step 3: Run linting**

```bash
cd /Users/bordumb/workspace/repositories/dataing/.worktrees/phase3-comments/backend
uv run ruff check src/dataing/ --fix
uv run mypy src/dataing/
```

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: add schema comments API routes"
```

---

### Task 3.4: Add Knowledge Comments Repository and Routes

**Files:**
- Modify: `backend/src/dataing/adapters/db/app_db.py`
- Create: `backend/src/dataing/entrypoints/api/routes/knowledge_comments.py`

**Step 1: Add repository methods**

Add to `app_db.py` - same pattern as schema comments but without `field_name`:

- `create_knowledge_comment()`
- `list_knowledge_comments()`
- `get_knowledge_comment()`
- `update_knowledge_comment()`
- `delete_knowledge_comment()`

**Step 2: Create routes file**

Create `backend/src/dataing/entrypoints/api/routes/knowledge_comments.py` - same pattern as schema comments.

**Step 3: Register router**

**Step 4: Run linting and tests**

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add knowledge comments API"
```

---

### Task 3.5: Add Comment Voting API

**Files:**
- Modify: `backend/src/dataing/adapters/db/app_db.py`
- Create: `backend/src/dataing/entrypoints/api/routes/comment_votes.py`

**Step 1: Add vote repository methods**

Add to `app_db.py`:

```python
async def upsert_comment_vote(
    self,
    tenant_id: UUID,
    comment_type: str,
    comment_id: UUID,
    user_id: UUID,
    vote: int,
) -> None:
    """Create or update a comment vote.

    Args:
        tenant_id: The tenant ID.
        comment_type: 'schema' or 'knowledge'.
        comment_id: The comment ID.
        user_id: The user ID.
        vote: 1 for upvote, -1 for downvote.
    """
    # Upsert vote
    vote_query = """
        INSERT INTO comment_votes (tenant_id, comment_type, comment_id, user_id, vote)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (comment_type, comment_id, user_id)
        DO UPDATE SET vote = $5
    """
    await self._pool.execute(vote_query, tenant_id, comment_type, comment_id, user_id, vote)

    # Update vote counts on comment
    await self._update_comment_vote_counts(comment_type, comment_id)


async def delete_comment_vote(
    self,
    tenant_id: UUID,
    comment_type: str,
    comment_id: UUID,
    user_id: UUID,
) -> bool:
    """Delete a comment vote.

    Returns:
        True if deleted, False if not found.
    """
    query = """
        DELETE FROM comment_votes
        WHERE tenant_id = $1 AND comment_type = $2 AND comment_id = $3 AND user_id = $4
    """
    result = await self._pool.execute(query, tenant_id, comment_type, comment_id, user_id)
    if result == "DELETE 1":
        await self._update_comment_vote_counts(comment_type, comment_id)
        return True
    return False


async def _update_comment_vote_counts(self, comment_type: str, comment_id: UUID) -> None:
    """Recalculate vote counts for a comment."""
    table = "schema_comments" if comment_type == "schema" else "knowledge_comments"
    query = f"""
        UPDATE {table}
        SET upvotes = (SELECT COUNT(*) FROM comment_votes WHERE comment_type = $1 AND comment_id = $2 AND vote = 1),
            downvotes = (SELECT COUNT(*) FROM comment_votes WHERE comment_type = $1 AND comment_id = $2 AND vote = -1)
        WHERE id = $2
    """
    await self._pool.execute(query, comment_type, comment_id)
```

**Step 2: Create votes routes**

Create `backend/src/dataing/entrypoints/api/routes/comment_votes.py`:

```python
"""API routes for comment voting."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import ApiKeyContext, verify_api_key

router = APIRouter(prefix="/comments", tags=["comment-votes"])

AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]
DbDep = Annotated[AppDatabase, Depends(get_app_db)]


class VoteCreate(BaseModel):
    """Request body for voting."""

    vote: Literal[1, -1]


@router.post("/{comment_type}/{comment_id}/vote", status_code=204)
async def vote_on_comment(
    comment_type: Literal["schema", "knowledge"],
    comment_id: UUID,
    body: VoteCreate,
    auth: AuthDep,
    db: DbDep,
) -> None:
    """Vote on a comment."""
    user_id = auth.user_id if hasattr(auth, "user_id") else auth.tenant_id
    await db.upsert_comment_vote(
        tenant_id=auth.tenant_id,
        comment_type=comment_type,
        comment_id=comment_id,
        user_id=user_id,
        vote=body.vote,
    )


@router.delete("/{comment_type}/{comment_id}/vote", status_code=204)
async def remove_vote(
    comment_type: Literal["schema", "knowledge"],
    comment_id: UUID,
    auth: AuthDep,
    db: DbDep,
) -> None:
    """Remove vote from a comment."""
    user_id = auth.user_id if hasattr(auth, "user_id") else auth.tenant_id
    await db.delete_comment_vote(
        tenant_id=auth.tenant_id,
        comment_type=comment_type,
        comment_id=comment_id,
        user_id=user_id,
    )
```

**Step 3: Register router and run linting**

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: add comment voting API"
```

---

## Part 4: Frontend Comment Components

### Task 4.1: Create Comment API Client

**Files:**
- Create: `frontend/src/lib/api/schema-comments.ts`
- Create: `frontend/src/lib/api/knowledge-comments.ts`
- Create: `frontend/src/lib/api/comment-votes.ts`

**Step 1: Write schema-comments.ts**

```typescript
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import customInstance from './client'
import { queryKeys } from './query-keys'

export interface SchemaComment {
  id: string
  dataset_id: string
  field_name: string
  parent_id: string | null
  content: string
  author_id: string | null
  author_name: string | null
  upvotes: number
  downvotes: number
  created_at: string
  updated_at: string
}

export interface SchemaCommentCreate {
  field_name: string
  content: string
  parent_id?: string
}

async function listSchemaComments(datasetId: string, fieldName?: string): Promise<SchemaComment[]> {
  const params = fieldName ? `?field_name=${encodeURIComponent(fieldName)}` : ''
  return customInstance<SchemaComment[]>({
    url: `/api/v1/datasets/${datasetId}/schema-comments/${params}`,
    method: 'GET',
  })
}

async function createSchemaComment(datasetId: string, data: SchemaCommentCreate): Promise<SchemaComment> {
  return customInstance<SchemaComment>({
    url: `/api/v1/datasets/${datasetId}/schema-comments/`,
    method: 'POST',
    data,
  })
}

export function useSchemaComments(datasetId: string, fieldName?: string) {
  return useQuery({
    queryKey: queryKeys.schemaComments.list(datasetId, fieldName),
    queryFn: () => listSchemaComments(datasetId, fieldName),
    enabled: !!datasetId,
  })
}

export function useCreateSchemaComment(datasetId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: SchemaCommentCreate) => createSchemaComment(datasetId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.schemaComments.all(datasetId) })
    },
  })
}
```

**Step 2: Add query keys**

Update `frontend/src/lib/api/query-keys.ts`:

```typescript
export const queryKeys = {
  // ... existing keys
  schemaComments: {
    all: (datasetId: string) => ['schema-comments', datasetId] as const,
    list: (datasetId: string, fieldName?: string) => ['schema-comments', datasetId, fieldName] as const,
  },
  knowledgeComments: {
    all: (datasetId: string) => ['knowledge-comments', datasetId] as const,
    list: (datasetId: string) => ['knowledge-comments', datasetId, 'list'] as const,
  },
}
```

**Step 3: Create knowledge-comments.ts and comment-votes.ts similarly**

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: add comment API clients"
```

---

### Task 4.2: Create Comment UI Components

**Files:**
- Create: `frontend/src/features/datasets/components/comment-item.tsx`
- Create: `frontend/src/features/datasets/components/comment-thread.tsx`
- Create: `frontend/src/features/datasets/components/comment-editor.tsx`
- Create: `frontend/src/features/datasets/components/comment-slide-panel.tsx`

**Step 1: Create comment-item.tsx**

Basic comment display with voting buttons, reply button, markdown rendering.

**Step 2: Create comment-thread.tsx**

Renders a root comment and its nested replies recursively.

**Step 3: Create comment-editor.tsx**

Markdown textarea with submit button.

**Step 4: Create comment-slide-panel.tsx**

Slide-out panel that shows threads for a field, uses Radix Dialog or custom slide animation.

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add comment UI components"
```

---

### Task 4.3: Add Comment Indicator to Schema Tab

**Files:**
- Create: `frontend/src/features/datasets/components/schema-comment-indicator.tsx`
- Modify: `frontend/src/features/datasets/dataset-detail-page.tsx`

**Step 1: Create indicator component**

Small chat bubble icon that shows if comments exist for a field.

**Step 2: Integrate into schema table**

Add indicator to far-right of each row in the schema table.

**Step 3: Wire up slide panel**

Clicking indicator opens the comment slide panel for that field.

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: add comment indicator to schema tab"
```

---

### Task 4.4: Create Knowledge Tab

**Files:**
- Create: `frontend/src/features/datasets/components/knowledge-tab.tsx`
- Modify: `frontend/src/features/datasets/dataset-detail-page.tsx`

**Step 1: Create knowledge-tab.tsx**

Full-width discussion area reusing comment-thread and comment-editor components.

**Step 2: Add tab to dataset detail page**

Add "Knowledge" tab with Brain icon to the tabs list.

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: add Knowledge tab to dataset detail page"
```

---

## Part 5: Testing & Polish

### Task 5.1: Add Backend Integration Tests

**Files:**
- Create: `backend/tests/integration/adapters/comments/test_schema_comments.py`
- Create: `backend/tests/integration/adapters/comments/test_knowledge_comments.py`

**Step 1: Write integration tests**

Test full CRUD flow with real database.

**Step 2: Run tests**

```bash
PYTHONPATH=backend/src uv run pytest backend/tests/integration -v
```

**Step 3: Commit**

```bash
git add -A
git commit -m "test: add comment integration tests"
```

---

### Task 5.2: Run Full Test Suite and Fix Issues

**Step 1: Run backend tests**

```bash
PYTHONPATH=backend/src uv run pytest backend/tests -v
```

**Step 2: Run frontend build**

```bash
cd frontend && pnpm build
```

**Step 3: Run linting**

```bash
cd backend && uv run ruff check src/dataing/ && uv run mypy src/dataing/
cd ../frontend && pnpm lint
```

**Step 4: Fix any issues**

**Step 5: Commit fixes**

```bash
git add -A
git commit -m "fix: resolve test and lint issues"
```

---

### Task 5.3: Manual Testing

**Step 1: Start demo**

```bash
just demo
```

**Step 2: Test schema comments**

- Navigate to a dataset detail page
- Hover over a schema field row
- Click the comment indicator
- Create a new thread
- Reply to the thread
- Vote on comments
- Verify persistence after page reload

**Step 3: Test knowledge tab**

- Click Knowledge tab
- Create a discussion thread
- Reply and vote
- Verify persistence

**Step 4: Document any bugs found**

---

### Task 5.4: Final Commit and Push

**Step 1: Review all changes**

```bash
git log --oneline feature/feedback-system..HEAD
git diff --stat feature/feedback-system..HEAD
```

**Step 2: Push branch**

```bash
git push -u origin feature/phase3-comments
```

---

## Summary

| Part | Tasks | Description |
|------|-------|-------------|
| 1 | 1.1-1.7 | Rename feedback → investigation_feedback |
| 2 | 2.1-2.4 | Create comment database tables |
| 3 | 3.1-3.5 | Backend API for schema/knowledge comments + voting |
| 4 | 4.1-4.4 | Frontend comment components and UI |
| 5 | 5.1-5.4 | Testing and polish |


Total: ~23 tasks
