# Audit Logging Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement comprehensive audit logging for SOC 2/GDPR compliance with decorator-based capture, PostgreSQL storage, and Admin UI.

**Architecture:** `@audited` decorator on route handlers captures actor/action/resource info and writes to `audit_logs` table via repository. Frontend displays filterable/exportable log viewer in Admin page. Kubernetes CronJob handles 2-year retention cleanup.

**Tech Stack:** FastAPI, PostgreSQL, asyncpg, Pydantic, React, TanStack Query, shadcn/ui

---

## Task 1: Database Migration

**Files:**
- Create: `backend/migrations/009_audit_logs.sql`

**Step 1: Write the migration**

```sql
-- Migration: 009_audit_logs.sql
-- Audit logging table for compliance (SOC 2, GDPR)

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- When
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Who
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    actor_id UUID,
    actor_email VARCHAR(255),
    actor_ip VARCHAR(45),
    actor_user_agent TEXT,

    -- What
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id UUID,
    resource_name VARCHAR(255),

    -- Details
    request_method VARCHAR(10),
    request_path TEXT,
    status_code INTEGER,
    changes JSONB,
    metadata JSONB,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_timestamp
    ON audit_logs(tenant_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor
    ON audit_logs(tenant_id, actor_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action
    ON audit_logs(tenant_id, action, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource
    ON audit_logs(tenant_id, resource_type, resource_id);

-- Partial index for recent logs (most common queries)
CREATE INDEX IF NOT EXISTS idx_audit_logs_recent
    ON audit_logs(tenant_id, timestamp DESC)
    WHERE timestamp > NOW() - INTERVAL '30 days';
```

**Step 2: Add migration to justfile demo recipe**

Edit `justfile` to include migration 009 in the demo recipe (after migration 008).

**Step 3: Test migration runs**

Run: `just demo` and verify table exists:
```bash
PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -c "\d audit_logs"
```

**Step 4: Commit**

```bash
git add backend/migrations/009_audit_logs.sql justfile
git commit -m "feat(audit): add audit_logs table migration"
```

---

## Task 2: Audit Types and Models

**Files:**
- Create: `backend/src/dataing/adapters/audit/__init__.py`
- Create: `backend/src/dataing/adapters/audit/types.py`
- Test: `backend/tests/unit/adapters/audit/__init__.py`
- Test: `backend/tests/unit/adapters/audit/test_types.py`

**Step 1: Create test file structure**

```python
# backend/tests/unit/adapters/audit/__init__.py
"""Audit adapter tests."""
```

**Step 2: Write failing test for AuditLogEntry**

```python
# backend/tests/unit/adapters/audit/test_types.py
"""Tests for audit types."""

from datetime import datetime, UTC
from uuid import uuid4

import pytest

from dataing.adapters.audit.types import AuditLogEntry, AuditLogCreate


class TestAuditLogEntry:
    """Tests for AuditLogEntry model."""

    def test_create_audit_log_entry(self) -> None:
        """Test creating an audit log entry."""
        entry = AuditLogEntry(
            id=uuid4(),
            timestamp=datetime.now(UTC),
            tenant_id=uuid4(),
            actor_id=uuid4(),
            actor_email="test@example.com",
            action="team.create",
            resource_type="team",
            resource_id=uuid4(),
            resource_name="Engineering",
        )
        assert entry.action == "team.create"
        assert entry.resource_type == "team"

    def test_audit_log_entry_optional_fields(self) -> None:
        """Test audit log entry with optional fields as None."""
        entry = AuditLogEntry(
            id=uuid4(),
            timestamp=datetime.now(UTC),
            tenant_id=uuid4(),
            action="auth.login",
        )
        assert entry.actor_id is None
        assert entry.resource_type is None
        assert entry.changes is None


class TestAuditLogCreate:
    """Tests for AuditLogCreate model."""

    def test_create_audit_log_create(self) -> None:
        """Test creating an audit log create request."""
        create = AuditLogCreate(
            tenant_id=uuid4(),
            actor_id=uuid4(),
            actor_email="test@example.com",
            action="datasource.create",
            resource_type="datasource",
        )
        assert create.action == "datasource.create"
```

**Step 3: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/adapters/audit/test_types.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'dataing.adapters.audit'"

**Step 4: Write minimal implementation**

```python
# backend/src/dataing/adapters/audit/__init__.py
"""Audit logging adapters."""

from dataing.adapters.audit.types import AuditLogCreate, AuditLogEntry

__all__ = [
    "AuditLogCreate",
    "AuditLogEntry",
]
```

```python
# backend/src/dataing/adapters/audit/types.py
"""Audit log types."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogCreate(BaseModel):
    """Request to create an audit log entry."""

    model_config = ConfigDict(frozen=True)

    tenant_id: UUID
    actor_id: UUID | None = None
    actor_email: str | None = None
    actor_ip: str | None = None
    actor_user_agent: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: UUID | None = None
    resource_name: str | None = None
    request_method: str | None = None
    request_path: str | None = None
    status_code: int | None = None
    changes: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class AuditLogEntry(BaseModel):
    """Audit log entry from database."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    timestamp: datetime
    tenant_id: UUID
    actor_id: UUID | None = None
    actor_email: str | None = None
    actor_ip: str | None = None
    actor_user_agent: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: UUID | None = None
    resource_name: str | None = None
    request_method: str | None = None
    request_path: str | None = None
    status_code: int | None = None
    changes: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime | None = None
```

**Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/adapters/audit/test_types.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/dataing/adapters/audit/ backend/tests/unit/adapters/audit/
git commit -m "feat(audit): add audit log types"
```

---

## Task 3: Audit Repository

**Files:**
- Create: `backend/src/dataing/adapters/audit/repository.py`
- Modify: `backend/src/dataing/adapters/audit/__init__.py`
- Test: `backend/tests/unit/adapters/audit/test_repository.py`

**Step 1: Write failing test for AuditRepository**

```python
# backend/tests/unit/adapters/audit/test_repository.py
"""Tests for audit repository."""

from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from dataing.adapters.audit.repository import AuditRepository
from dataing.adapters.audit.types import AuditLogCreate


class TestAuditRepository:
    """Tests for AuditRepository."""

    @pytest.fixture
    def mock_pool(self) -> MagicMock:
        """Create a mock database pool."""
        pool = MagicMock()
        pool.acquire = MagicMock(return_value=AsyncMock())
        return pool

    @pytest.fixture
    def repository(self, mock_pool: MagicMock) -> AuditRepository:
        """Create repository with mock pool."""
        return AuditRepository(pool=mock_pool)

    async def test_record_creates_entry(self, repository: AuditRepository) -> None:
        """Test recording an audit log entry."""
        create = AuditLogCreate(
            tenant_id=uuid4(),
            actor_id=uuid4(),
            actor_email="test@example.com",
            action="team.create",
            resource_type="team",
            resource_id=uuid4(),
            resource_name="Engineering",
        )

        # Should not raise
        await repository.record(create)

    async def test_list_returns_entries(
        self, repository: AuditRepository, mock_pool: MagicMock
    ) -> None:
        """Test listing audit log entries."""
        tenant_id = uuid4()
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.fetchval = AsyncMock(return_value=0)
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        entries, total = await repository.list(
            tenant_id=tenant_id,
            limit=50,
            offset=0,
        )

        assert entries == []
        assert total == 0

    async def test_delete_before_removes_old_entries(
        self, repository: AuditRepository, mock_pool: MagicMock
    ) -> None:
        """Test deleting entries before a cutoff date."""
        cutoff = datetime.now(UTC) - timedelta(days=730)
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 100")
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        count = await repository.delete_before(cutoff)

        assert count == 100
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/adapters/audit/test_repository.py -v`
Expected: FAIL with "cannot import name 'AuditRepository'"

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/adapters/audit/repository.py
"""Audit log repository."""

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from asyncpg import Pool

from dataing.adapters.audit.types import AuditLogCreate, AuditLogEntry

logger = structlog.get_logger()


class AuditRepository:
    """Repository for audit log operations."""

    def __init__(self, pool: Pool) -> None:
        """Initialize the repository.

        Args:
            pool: Database connection pool.
        """
        self._pool = pool

    async def record(self, entry: AuditLogCreate) -> UUID:
        """Record an audit log entry.

        Args:
            entry: Audit log entry to record.

        Returns:
            ID of the created entry.
        """
        query = """
            INSERT INTO audit_logs (
                tenant_id, actor_id, actor_email, actor_ip, actor_user_agent,
                action, resource_type, resource_id, resource_name,
                request_method, request_path, status_code, changes, metadata
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
            )
            RETURNING id
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                query,
                entry.tenant_id,
                entry.actor_id,
                entry.actor_email,
                entry.actor_ip,
                entry.actor_user_agent,
                entry.action,
                entry.resource_type,
                entry.resource_id,
                entry.resource_name,
                entry.request_method,
                entry.request_path,
                entry.status_code,
                entry.changes,
                entry.metadata,
            )
            result: UUID = row["id"]
            return result

    async def list(
        self,
        tenant_id: UUID,
        limit: int = 50,
        offset: int = 0,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        action: str | None = None,
        actor_id: UUID | None = None,
        resource_type: str | None = None,
        search: str | None = None,
    ) -> tuple[list[AuditLogEntry], int]:
        """List audit log entries with filters.

        Args:
            tenant_id: Tenant to filter by.
            limit: Maximum entries to return.
            offset: Number of entries to skip.
            start_date: Filter entries after this date.
            end_date: Filter entries before this date.
            action: Filter by action type.
            actor_id: Filter by actor.
            resource_type: Filter by resource type.
            search: Search in resource_name and action.

        Returns:
            Tuple of (entries, total_count).
        """
        conditions = ["tenant_id = $1"]
        params: list[Any] = [tenant_id]
        param_idx = 2

        if start_date:
            conditions.append(f"timestamp >= ${param_idx}")
            params.append(start_date)
            param_idx += 1

        if end_date:
            conditions.append(f"timestamp <= ${param_idx}")
            params.append(end_date)
            param_idx += 1

        if action:
            conditions.append(f"action = ${param_idx}")
            params.append(action)
            param_idx += 1

        if actor_id:
            conditions.append(f"actor_id = ${param_idx}")
            params.append(actor_id)
            param_idx += 1

        if resource_type:
            conditions.append(f"resource_type = ${param_idx}")
            params.append(resource_type)
            param_idx += 1

        if search:
            conditions.append(
                f"(resource_name ILIKE ${param_idx} OR action ILIKE ${param_idx})"
            )
            params.append(f"%{search}%")
            param_idx += 1

        where_clause = " AND ".join(conditions)

        count_query = f"SELECT COUNT(*) FROM audit_logs WHERE {where_clause}"
        list_query = f"""
            SELECT * FROM audit_logs
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])

        async with self._pool.acquire() as conn:
            total = await conn.fetchval(count_query, *params[:-2])
            rows = await conn.fetch(list_query, *params)

        entries = [
            AuditLogEntry(
                id=row["id"],
                timestamp=row["timestamp"],
                tenant_id=row["tenant_id"],
                actor_id=row["actor_id"],
                actor_email=row["actor_email"],
                actor_ip=row["actor_ip"],
                actor_user_agent=row["actor_user_agent"],
                action=row["action"],
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                resource_name=row["resource_name"],
                request_method=row["request_method"],
                request_path=row["request_path"],
                status_code=row["status_code"],
                changes=row["changes"],
                metadata=row["metadata"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

        total_count: int = total or 0
        return entries, total_count

    async def get(self, tenant_id: UUID, entry_id: UUID) -> AuditLogEntry | None:
        """Get a single audit log entry.

        Args:
            tenant_id: Tenant ID for access control.
            entry_id: Entry ID to fetch.

        Returns:
            Audit log entry or None if not found.
        """
        query = "SELECT * FROM audit_logs WHERE tenant_id = $1 AND id = $2"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, tenant_id, entry_id)

        if not row:
            return None

        return AuditLogEntry(
            id=row["id"],
            timestamp=row["timestamp"],
            tenant_id=row["tenant_id"],
            actor_id=row["actor_id"],
            actor_email=row["actor_email"],
            actor_ip=row["actor_ip"],
            actor_user_agent=row["actor_user_agent"],
            action=row["action"],
            resource_type=row["resource_type"],
            resource_id=row["resource_id"],
            resource_name=row["resource_name"],
            request_method=row["request_method"],
            request_path=row["request_path"],
            status_code=row["status_code"],
            changes=row["changes"],
            metadata=row["metadata"],
            created_at=row["created_at"],
        )

    async def delete_before(self, cutoff: datetime) -> int:
        """Delete audit logs before cutoff date.

        Args:
            cutoff: Delete entries older than this.

        Returns:
            Number of entries deleted.
        """
        query = "DELETE FROM audit_logs WHERE timestamp < $1"
        async with self._pool.acquire() as conn:
            result = await conn.execute(query, cutoff)

        # Result is like "DELETE 100"
        count_str = result.split()[-1]
        return int(count_str)
```

**Step 4: Update __init__.py**

```python
# backend/src/dataing/adapters/audit/__init__.py
"""Audit logging adapters."""

from dataing.adapters.audit.repository import AuditRepository
from dataing.adapters.audit.types import AuditLogCreate, AuditLogEntry

__all__ = [
    "AuditLogCreate",
    "AuditLogEntry",
    "AuditRepository",
]
```

**Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/adapters/audit/test_repository.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/dataing/adapters/audit/ backend/tests/unit/adapters/audit/
git commit -m "feat(audit): add audit repository"
```

---

## Task 4: Audit Decorator

**Files:**
- Create: `backend/src/dataing/adapters/audit/decorator.py`
- Modify: `backend/src/dataing/adapters/audit/__init__.py`
- Test: `backend/tests/unit/adapters/audit/test_decorator.py`

**Step 1: Write failing test for decorator**

```python
# backend/tests/unit/adapters/audit/test_decorator.py
"""Tests for audit decorator."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import Request
from starlette.datastructures import Headers

from dataing.adapters.audit.decorator import audited, get_client_ip


class TestGetClientIp:
    """Tests for get_client_ip helper."""

    def test_extracts_from_x_forwarded_for(self) -> None:
        """Test extracting IP from X-Forwarded-For header."""
        request = MagicMock(spec=Request)
        request.headers = Headers({"x-forwarded-for": "1.2.3.4, 5.6.7.8"})
        request.client = MagicMock(host="127.0.0.1")

        ip = get_client_ip(request)

        assert ip == "1.2.3.4"

    def test_falls_back_to_client_host(self) -> None:
        """Test falling back to request.client.host."""
        request = MagicMock(spec=Request)
        request.headers = Headers({})
        request.client = MagicMock(host="192.168.1.1")

        ip = get_client_ip(request)

        assert ip == "192.168.1.1"


class TestAuditedDecorator:
    """Tests for @audited decorator."""

    async def test_decorator_records_audit_log(self) -> None:
        """Test that decorator records audit log after success."""
        mock_repo = AsyncMock()
        mock_request = MagicMock(spec=Request)
        mock_request.headers = Headers({"user-agent": "TestAgent"})
        mock_request.client = MagicMock(host="127.0.0.1")
        mock_request.method = "POST"
        mock_request.url = MagicMock(path="/api/v1/teams")
        mock_request.state = MagicMock()
        mock_request.state.tenant_id = uuid4()
        mock_request.state.user_id = uuid4()
        mock_request.state.user_email = "test@example.com"
        mock_request.app = MagicMock()
        mock_request.app.state = MagicMock()
        mock_request.app.state.audit_repo = mock_repo

        @audited(action="team.create", resource_type="team")
        async def create_team(request: Request) -> dict:
            return {"id": str(uuid4()), "name": "Engineering"}

        result = await create_team(request=mock_request)

        assert result["name"] == "Engineering"
        mock_repo.record.assert_called_once()

    async def test_decorator_extracts_resource_id_from_result(self) -> None:
        """Test that decorator extracts resource_id from result."""
        mock_repo = AsyncMock()
        resource_id = uuid4()
        mock_request = MagicMock(spec=Request)
        mock_request.headers = Headers({})
        mock_request.client = MagicMock(host="127.0.0.1")
        mock_request.method = "POST"
        mock_request.url = MagicMock(path="/api/v1/teams")
        mock_request.state = MagicMock()
        mock_request.state.tenant_id = uuid4()
        mock_request.state.user_id = uuid4()
        mock_request.state.user_email = "test@example.com"
        mock_request.app = MagicMock()
        mock_request.app.state = MagicMock()
        mock_request.app.state.audit_repo = mock_repo

        @audited(action="team.create", resource_type="team")
        async def create_team(request: Request) -> dict:
            return {"id": str(resource_id), "name": "Engineering"}

        await create_team(request=mock_request)

        call_args = mock_repo.record.call_args[0][0]
        assert call_args.resource_id == resource_id
        assert call_args.resource_name == "Engineering"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/adapters/audit/test_decorator.py -v`
Expected: FAIL with "cannot import name 'audited'"

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/adapters/audit/decorator.py
"""Audit logging decorator for route handlers."""

from functools import wraps
from typing import Any, Callable, ParamSpec, TypeVar
from uuid import UUID

import structlog
from fastapi import Request

from dataing.adapters.audit.types import AuditLogCreate

logger = structlog.get_logger()

P = ParamSpec("P")
R = TypeVar("R")


def get_client_ip(request: Request) -> str | None:
    """Extract client IP from request.

    Args:
        request: FastAPI request object.

    Returns:
        Client IP address or None.
    """
    # Check X-Forwarded-For header first (for proxied requests)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take the first IP in the chain
        return forwarded_for.split(",")[0].strip()

    # Fall back to direct client
    if request.client:
        return request.client.host

    return None


def _extract_resource_info(
    result: Any, kwargs: dict[str, Any]
) -> tuple[UUID | None, str | None]:
    """Extract resource ID and name from result or kwargs.

    Args:
        result: Return value from handler.
        kwargs: Keyword arguments passed to handler.

    Returns:
        Tuple of (resource_id, resource_name).
    """
    resource_id: UUID | None = None
    resource_name: str | None = None

    # Try to extract from result
    if isinstance(result, dict):
        if "id" in result:
            try:
                resource_id = UUID(str(result["id"]))
            except (ValueError, TypeError):
                pass
        resource_name = result.get("name")
    elif hasattr(result, "id"):
        try:
            resource_id = UUID(str(result.id))
        except (ValueError, TypeError):
            pass
        if hasattr(result, "name"):
            resource_name = result.name

    # Try to extract from path params if not in result
    if resource_id is None:
        for key in ("team_id", "tag_id", "datasource_id", "investigation_id", "id"):
            if key in kwargs:
                try:
                    resource_id = UUID(str(kwargs[key]))
                    break
                except (ValueError, TypeError):
                    pass

    return resource_id, resource_name


def audited(
    action: str,
    resource_type: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to audit route handlers.

    Args:
        action: Action identifier (e.g., "team.create").
        resource_type: Type of resource (e.g., "team").

    Returns:
        Decorated function that records audit logs.
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # Extract request from kwargs
            request: Request | None = kwargs.get("request")
            if request is None:
                # Try positional args
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            # Execute the handler
            result = await func(*args, **kwargs)

            # Record audit log if we have a request
            if request is not None:
                try:
                    await _record_audit(
                        request=request,
                        action=action,
                        resource_type=resource_type,
                        result=result,
                        kwargs=dict(kwargs),
                    )
                except Exception as e:
                    # Log but don't fail the request
                    logger.error(f"Failed to record audit log: {e}")

            return result

        return wrapper  # type: ignore[return-value]

    return decorator


async def _record_audit(
    request: Request,
    action: str,
    resource_type: str | None,
    result: Any,
    kwargs: dict[str, Any],
) -> None:
    """Record an audit log entry.

    Args:
        request: FastAPI request object.
        action: Action identifier.
        resource_type: Type of resource.
        result: Handler result.
        kwargs: Handler kwargs.
    """
    # Get audit repo from app state
    audit_repo = getattr(request.app.state, "audit_repo", None)
    if audit_repo is None:
        logger.warning("Audit repository not configured, skipping audit log")
        return

    # Extract actor info from request state (set by auth middleware)
    tenant_id = getattr(request.state, "tenant_id", None)
    actor_id = getattr(request.state, "user_id", None)
    actor_email = getattr(request.state, "user_email", None)

    if tenant_id is None:
        logger.warning("No tenant_id in request state, skipping audit log")
        return

    # Extract resource info
    resource_id, resource_name = _extract_resource_info(result, kwargs)

    entry = AuditLogCreate(
        tenant_id=tenant_id,
        actor_id=actor_id,
        actor_email=actor_email,
        actor_ip=get_client_ip(request),
        actor_user_agent=request.headers.get("user-agent"),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        resource_name=resource_name,
        request_method=request.method,
        request_path=str(request.url.path),
        status_code=200,
    )

    await audit_repo.record(entry)
    logger.debug(f"Recorded audit log: {action}", resource_id=str(resource_id))
```

**Step 4: Update __init__.py**

```python
# backend/src/dataing/adapters/audit/__init__.py
"""Audit logging adapters."""

from dataing.adapters.audit.decorator import audited, get_client_ip
from dataing.adapters.audit.repository import AuditRepository
from dataing.adapters.audit.types import AuditLogCreate, AuditLogEntry

__all__ = [
    "AuditLogCreate",
    "AuditLogEntry",
    "AuditRepository",
    "audited",
    "get_client_ip",
]
```

**Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/adapters/audit/test_decorator.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/dataing/adapters/audit/ backend/tests/unit/adapters/audit/
git commit -m "feat(audit): add @audited decorator"
```

---

## Task 5: Audit API Routes

**Files:**
- Create: `backend/src/dataing/entrypoints/api/routes/audit.py`
- Modify: `backend/src/dataing/entrypoints/api/routes/__init__.py`
- Test: `backend/tests/unit/entrypoints/api/routes/test_audit.py`

**Step 1: Write failing test for audit routes**

```python
# backend/tests/unit/entrypoints/api/routes/test_audit.py
"""Tests for audit log routes."""

from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dataing.entrypoints.api.routes.audit import router
from dataing.adapters.audit.types import AuditLogEntry


@pytest.fixture
def mock_audit_repo() -> AsyncMock:
    """Create mock audit repository."""
    return AsyncMock()


@pytest.fixture
def app(mock_audit_repo: AsyncMock) -> FastAPI:
    """Create test app with audit routes."""
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.state.audit_repo = mock_audit_repo
    app.state.db_pool = MagicMock()

    @app.middleware("http")
    async def add_state(request, call_next):
        request.state.tenant_id = uuid4()
        request.state.user_id = uuid4()
        request.state.user_email = "admin@example.com"
        return await call_next(request)

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestListAuditLogs:
    """Tests for list audit logs endpoint."""

    def test_returns_empty_list(
        self, client: TestClient, mock_audit_repo: AsyncMock
    ) -> None:
        """Test listing returns empty list when no logs."""
        mock_audit_repo.list.return_value = ([], 0)

        response = client.get("/api/v1/audit-logs")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_returns_paginated_results(
        self, client: TestClient, mock_audit_repo: AsyncMock
    ) -> None:
        """Test pagination parameters."""
        entry = AuditLogEntry(
            id=uuid4(),
            timestamp=datetime.now(UTC),
            tenant_id=uuid4(),
            action="team.create",
            resource_type="team",
        )
        mock_audit_repo.list.return_value = ([entry], 1)

        response = client.get("/api/v1/audit-logs?page=1&limit=10")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/unit/entrypoints/api/routes/test_audit.py -v`
Expected: FAIL with "cannot import name 'router' from 'dataing.entrypoints.api.routes.audit'"

**Step 3: Write minimal implementation**

```python
# backend/src/dataing/entrypoints/api/routes/audit.py
"""Audit log API routes."""

from datetime import datetime
from io import StringIO
from typing import Annotated, Any
from uuid import UUID
import csv

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from dataing.adapters.audit import AuditRepository, AuditLogEntry

router = APIRouter(prefix="/audit-logs", tags=["audit"])


class AuditLogResponse(BaseModel):
    """Response for a single audit log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    timestamp: datetime
    actor_id: UUID | None
    actor_email: str | None
    actor_ip: str | None
    action: str
    resource_type: str | None
    resource_id: UUID | None
    resource_name: str | None
    request_method: str | None
    request_path: str | None
    status_code: int | None
    changes: dict[str, Any] | None
    metadata: dict[str, Any] | None


class AuditLogListResponse(BaseModel):
    """Paginated list of audit logs."""

    items: list[AuditLogResponse]
    total: int
    page: int
    pages: int
    limit: int


def get_audit_repo(request: Request) -> AuditRepository:
    """Get audit repository from app state."""
    return AuditRepository(pool=request.app.state.db_pool)


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    action: str | None = None,
    actor_id: UUID | None = None,
    resource_type: str | None = None,
    search: str | None = None,
    audit_repo: AuditRepository = Depends(get_audit_repo),
) -> AuditLogListResponse:
    """List audit logs with filtering and pagination."""
    tenant_id = request.state.tenant_id
    offset = (page - 1) * limit

    entries, total = await audit_repo.list(
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
        start_date=start_date,
        end_date=end_date,
        action=action,
        actor_id=actor_id,
        resource_type=resource_type,
        search=search,
    )

    pages = (total + limit - 1) // limit if total > 0 else 1

    return AuditLogListResponse(
        items=[AuditLogResponse.model_validate(e) for e in entries],
        total=total,
        page=page,
        pages=pages,
        limit=limit,
    )


@router.get("/export")
async def export_audit_logs(
    request: Request,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    action: str | None = None,
    actor_id: UUID | None = None,
    resource_type: str | None = None,
    search: str | None = None,
    audit_repo: AuditRepository = Depends(get_audit_repo),
) -> StreamingResponse:
    """Export audit logs as CSV."""
    tenant_id = request.state.tenant_id

    # Fetch all matching entries (up to 10000)
    entries, _ = await audit_repo.list(
        tenant_id=tenant_id,
        limit=10000,
        offset=0,
        start_date=start_date,
        end_date=end_date,
        action=action,
        actor_id=actor_id,
        resource_type=resource_type,
        search=search,
    )

    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Timestamp",
        "Actor Email",
        "Actor IP",
        "Action",
        "Resource Type",
        "Resource Name",
        "Request Method",
        "Request Path",
        "Status Code",
    ])

    for entry in entries:
        writer.writerow([
            entry.timestamp.isoformat(),
            entry.actor_email or "",
            entry.actor_ip or "",
            entry.action,
            entry.resource_type or "",
            entry.resource_name or "",
            entry.request_method or "",
            entry.request_path or "",
            entry.status_code or "",
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=audit-logs-{datetime.now().strftime('%Y%m%d')}.csv"
        },
    )


@router.get("/{entry_id}", response_model=AuditLogResponse)
async def get_audit_log(
    request: Request,
    entry_id: UUID,
    audit_repo: AuditRepository = Depends(get_audit_repo),
) -> AuditLogResponse:
    """Get a single audit log entry."""
    tenant_id = request.state.tenant_id

    entry = await audit_repo.get(tenant_id=tenant_id, entry_id=entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Audit log entry not found")

    return AuditLogResponse.model_validate(entry)
```

**Step 4: Update routes/__init__.py to include audit router**

Add to `backend/src/dataing/entrypoints/api/routes/__init__.py`:

```python
from dataing.entrypoints.api.routes.audit import router as audit_router

# In the router setup section:
api_router.include_router(audit_router)
```

**Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/unit/entrypoints/api/routes/test_audit.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/audit.py
git add backend/src/dataing/entrypoints/api/routes/__init__.py
git add backend/tests/unit/entrypoints/api/routes/test_audit.py
git commit -m "feat(audit): add audit log API routes"
```

---

## Task 6: Wire Up Audit Repository in deps.py

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/deps.py`

**Step 1: Import AuditRepository**

Add import at top of deps.py:
```python
from dataing.adapters.audit import AuditRepository
```

**Step 2: Create audit_repo in lifespan**

In the `lifespan` function, after creating the db_pool, add:
```python
# Create audit repository
audit_repo = AuditRepository(pool=db_pool)
app.state.audit_repo = audit_repo
```

**Step 3: Test by running the app**

Run: `cd backend && uv run fastapi dev src/dataing/entrypoints/api/app.py`
Verify: No import errors, app starts successfully.

**Step 4: Commit**

```bash
git add backend/src/dataing/entrypoints/api/deps.py
git commit -m "feat(audit): wire up audit repository in app lifespan"
```

---

## Task 7: Add @audited to Teams Routes

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/routes/teams.py`

**Step 1: Import audited decorator**

```python
from dataing.adapters.audit import audited
```

**Step 2: Add @audited to create_team**

```python
@router.post("", response_model=TeamResponse, status_code=201)
@audited(action="team.create", resource_type="team")
async def create_team(...):
```

**Step 3: Add @audited to update_team**

```python
@router.put("/{team_id}", response_model=TeamResponse)
@audited(action="team.update", resource_type="team")
async def update_team(...):
```

**Step 4: Add @audited to delete_team**

```python
@router.delete("/{team_id}", status_code=204)
@audited(action="team.delete", resource_type="team")
async def delete_team(...):
```

**Step 5: Add @audited to add/remove member**

```python
@router.post("/{team_id}/members", status_code=201)
@audited(action="team.member_add", resource_type="team")
async def add_team_member(...):

@router.delete("/{team_id}/members/{user_id}", status_code=204)
@audited(action="team.member_remove", resource_type="team")
async def remove_team_member(...):
```

**Step 6: Run tests**

Run: `cd backend && uv run pytest tests/unit -q`
Expected: All tests pass

**Step 7: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/teams.py
git commit -m "feat(audit): add @audited decorator to teams routes"
```

---

## Task 8: Add @audited to Remaining Routes

**Files to modify:**
- `backend/src/dataing/entrypoints/api/routes/tags.py` - tag.create, tag.update, tag.delete
- `backend/src/dataing/entrypoints/api/routes/permissions.py` - permission.grant, permission.revoke
- `backend/src/dataing/entrypoints/api/routes/datasources.py` - datasource.create, datasource.update, datasource.delete
- `backend/src/dataing/entrypoints/api/routes/investigations.py` - investigation.create, investigation.delete
- `backend/src/dataing/entrypoints/api/routes/sso.py` - sso.config_update
- `backend/src/dataing/entrypoints/api/routes/scim.py` - scim.user_provision, scim.group_sync
- `backend/src/dataing/entrypoints/api/routes/auth.py` - auth.login, auth.logout
- `backend/src/dataing/entrypoints/api/routes/settings.py` - settings.update

Follow the same pattern as Task 7 for each file:
1. Import `from dataing.adapters.audit import audited`
2. Add `@audited(action="...", resource_type="...")` to write operations
3. Run tests
4. Commit

**Step: Commit all remaining routes**

```bash
git add backend/src/dataing/entrypoints/api/routes/
git commit -m "feat(audit): add @audited decorator to all write routes"
```

---

## Task 9: Kubernetes CronJob for Cleanup

**Files:**
- Create: `k8s/cronjobs/audit-cleanup.yaml`
- Create: `backend/src/dataing/jobs/__init__.py`
- Create: `backend/src/dataing/jobs/audit_cleanup.py`

**Step 1: Create jobs module**

```python
# backend/src/dataing/jobs/__init__.py
"""Background jobs."""
```

**Step 2: Create cleanup job script**

```python
# backend/src/dataing/jobs/audit_cleanup.py
"""Audit log cleanup job.

Run via: python -m dataing.jobs.audit_cleanup
"""

import asyncio
import os
from datetime import datetime, timedelta, UTC

import asyncpg
import structlog

from dataing.adapters.audit import AuditRepository

logger = structlog.get_logger()

RETENTION_DAYS = int(os.getenv("AUDIT_RETENTION_DAYS", "730"))  # 2 years


async def main() -> None:
    """Run audit log cleanup."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL not set")
        return

    logger.info(f"Connecting to database...")
    pool = await asyncpg.create_pool(database_url)

    try:
        repo = AuditRepository(pool=pool)
        cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)

        logger.info(f"Deleting audit logs older than {cutoff.isoformat()}")
        count = await repo.delete_before(cutoff)

        logger.info(f"Deleted {count} audit log entries")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 3: Create Kubernetes CronJob manifest**

```yaml
# k8s/cronjobs/audit-cleanup.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: audit-log-cleanup
  labels:
    app: dataing
    component: audit-cleanup
spec:
  # Run at 3 AM UTC daily
  schedule: "0 3 * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 3
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
          - name: cleanup
            image: dataing-backend:latest
            imagePullPolicy: IfNotPresent
            command:
              - python
              - -m
              - dataing.jobs.audit_cleanup
            env:
              - name: DATABASE_URL
                valueFrom:
                  secretKeyRef:
                    name: dataing-secrets
                    key: database-url
              - name: AUDIT_RETENTION_DAYS
                value: "730"
            resources:
              requests:
                memory: "128Mi"
                cpu: "100m"
              limits:
                memory: "256Mi"
                cpu: "200m"
```

**Step 4: Test cleanup job locally**

<!-- pragma: allowlist secret -->

Run: `cd backend && DATABASE_URL=postgresql://dataing:dataing@localhost:5432/dataing_demo <!-- pragma: allowlist secret --> uv run python -m dataing.jobs.audit_cleanup`

**Step 5: Commit**

```bash
mkdir -p k8s/cronjobs
git add k8s/cronjobs/audit-cleanup.yaml
git add backend/src/dataing/jobs/
git commit -m "feat(audit): add Kubernetes CronJob for retention cleanup"
```

---

## Task 10: Frontend - Audit Log Settings Component

**Files:**
- Create: `frontend/src/features/settings/audit/index.ts`
- Create: `frontend/src/features/settings/audit/audit-log-settings.tsx`

**Step 1: Create index.ts**

```typescript
// frontend/src/features/settings/audit/index.ts
export { AuditLogSettings } from './audit-log-settings'
```

**Step 2: Create main component**

```typescript
// frontend/src/features/settings/audit/audit-log-settings.tsx
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format } from 'date-fns'
import { Download, Search, ChevronDown, ChevronRight } from 'lucide-react'

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/Badge'
import { DatePickerWithRange } from '@/components/ui/date-range-picker'
import { useApiClient } from '@/lib/api/client'

const ACTION_CATEGORIES = [
  { value: 'all', label: 'All Actions' },
  { value: 'auth', label: 'Authentication' },
  { value: 'team', label: 'Teams' },
  { value: 'tag', label: 'Tags' },
  { value: 'permission', label: 'Permissions' },
  { value: 'datasource', label: 'Data Sources' },
  { value: 'investigation', label: 'Investigations' },
  { value: 'sso', label: 'SSO' },
  { value: 'scim', label: 'SCIM' },
]

interface AuditLogEntry {
  id: string
  timestamp: string
  actor_email: string | null
  actor_ip: string | null
  action: string
  resource_type: string | null
  resource_name: string | null
  request_method: string | null
  request_path: string | null
  status_code: number | null
  changes: Record<string, unknown> | null
  metadata: Record<string, unknown> | null
}

interface AuditLogListResponse {
  items: AuditLogEntry[]
  total: number
  page: number
  pages: number
  limit: number
}

export function AuditLogSettings() {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [actionCategory, setActionCategory] = useState('all')
  const [expandedRow, setExpandedRow] = useState<string | null>(null)
  const [dateRange, setDateRange] = useState<{ from: Date; to: Date } | null>(null)

  const api = useApiClient()

  const { data, isLoading } = useQuery<AuditLogListResponse>({
    queryKey: ['audit-logs', page, search, actionCategory, dateRange],
    queryFn: async () => {
      const params = new URLSearchParams({
        page: page.toString(),
        limit: '50',
      })
      if (search) params.set('search', search)
      if (actionCategory !== 'all') params.set('action', actionCategory)
      if (dateRange?.from) params.set('start_date', dateRange.from.toISOString())
      if (dateRange?.to) params.set('end_date', dateRange.to.toISOString())

      const response = await api.get(`/api/v1/audit-logs?${params}`)
      return response.data
    },
  })

  const handleExport = async () => {
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    if (actionCategory !== 'all') params.set('action', actionCategory)
    if (dateRange?.from) params.set('start_date', dateRange.from.toISOString())
    if (dateRange?.to) params.set('end_date', dateRange.to.toISOString())

    const response = await api.get(`/api/v1/audit-logs/export?${params}`, {
      responseType: 'blob',
    })

    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', `audit-logs-${format(new Date(), 'yyyy-MM-dd')}.csv`)
    document.body.appendChild(link)
    link.click()
    link.remove()
  }

  const getActionBadgeVariant = (action: string) => {
    if (action.startsWith('auth.')) return 'secondary'
    if (action.includes('delete') || action.includes('revoke')) return 'destructive'
    if (action.includes('create') || action.includes('grant')) return 'default'
    return 'outline'
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Audit Log</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Filters */}
        <div className="flex flex-wrap gap-4">
          <div className="flex-1 min-w-[200px]">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
          </div>
          <Select value={actionCategory} onValueChange={setActionCategory}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Action type" />
            </SelectTrigger>
            <SelectContent>
              {ACTION_CATEGORIES.map((cat) => (
                <SelectItem key={cat.value} value={cat.value}>
                  {cat.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <DatePickerWithRange
            value={dateRange}
            onChange={setDateRange}
          />
          <Button variant="outline" onClick={handleExport}>
            <Download className="h-4 w-4 mr-2" />
            Export CSV
          </Button>
        </div>

        {/* Table */}
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[30px]"></TableHead>
                <TableHead>Timestamp</TableHead>
                <TableHead>User</TableHead>
                <TableHead>Action</TableHead>
                <TableHead>Resource</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8">
                    Loading...
                  </TableCell>
                </TableRow>
              ) : data?.items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                    No audit logs found
                  </TableCell>
                </TableRow>
              ) : (
                data?.items.map((entry) => (
                  <>
                    <TableRow
                      key={entry.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => setExpandedRow(expandedRow === entry.id ? null : entry.id)}
                    >
                      <TableCell>
                        {expandedRow === entry.id ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-sm">
                        {format(new Date(entry.timestamp), 'MMM d, HH:mm:ss')}
                      </TableCell>
                      <TableCell>{entry.actor_email || 'System'}</TableCell>
                      <TableCell>
                        <Badge variant={getActionBadgeVariant(entry.action)}>
                          {entry.action}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {entry.resource_name || entry.resource_type || '-'}
                      </TableCell>
                    </TableRow>
                    {expandedRow === entry.id && (
                      <TableRow>
                        <TableCell colSpan={5} className="bg-muted/30">
                          <div className="p-4 space-y-2 text-sm">
                            <div><strong>IP:</strong> {entry.actor_ip || 'Unknown'}</div>
                            <div><strong>Path:</strong> {entry.request_method} {entry.request_path}</div>
                            <div><strong>Status:</strong> {entry.status_code}</div>
                            {entry.changes && (
                              <div>
                                <strong>Changes:</strong>
                                <pre className="mt-1 p-2 bg-muted rounded text-xs overflow-auto">
                                  {JSON.stringify(entry.changes, null, 2)}
                                </pre>
                              </div>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        {/* Pagination */}
        {data && data.pages > 1 && (
          <div className="flex items-center justify-between">
            <div className="text-sm text-muted-foreground">
              Showing {(page - 1) * data.limit + 1} to {Math.min(page * data.limit, data.total)} of {data.total}
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page === data.pages}
                onClick={() => setPage(page + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
```

**Step 3: Commit**

```bash
git add frontend/src/features/settings/audit/
git commit -m "feat(audit): add audit log settings component"
```

---

## Task 11: Add Audit Tab to Admin Page

**Files:**
- Modify: `frontend/src/features/admin/admin-page.tsx`

**Step 1: Import AuditLogSettings**

```typescript
import { AuditLogSettings } from '@/features/settings/audit'
```

**Step 2: Add Audit Log tab**

Add to TabsList:
```tsx
<TabsTrigger value="audit">Audit Log</TabsTrigger>
```

Add TabsContent:
```tsx
<TabsContent value="audit">
  <AuditLogSettings />
</TabsContent>
```

**Step 3: Build and verify**

Run: `cd frontend && pnpm build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add frontend/src/features/admin/admin-page.tsx
git commit -m "feat(audit): add audit log tab to admin page"
```

---

## Task 12: Generate OpenAPI Client

**Files:**
- Regenerate: `frontend/src/lib/api/generated/`

**Step 1: Generate client**

Run: `just generate-client`

**Step 2: Verify audit endpoints in generated client**

Check that `frontend/src/lib/api/generated/audit/` exists with proper types.

**Step 3: Commit**

```bash
git add frontend/src/lib/api/
git commit -m "chore: regenerate OpenAPI client with audit endpoints"
```

---

## Task 13: Final Integration Test

**Step 1: Run full demo**

Run: `just demo`

**Step 2: Test audit logging**

1. Login to frontend at http://localhost:3000
2. Create a team
3. Go to Admin > Audit Log tab
4. Verify the team.create action appears

**Step 3: Test CSV export**

1. Click "Export CSV" button
2. Verify CSV downloads with correct data

**Step 4: Run all tests**

Run: `just test`
Expected: All tests pass

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat(audit): complete audit logging implementation"
```

---

## Summary

| Task | Description |
|------|-------------|
| 1 | Database migration |
| 2 | Audit types and models |
| 3 | Audit repository |
| 4 | @audited decorator |
| 5 | Audit API routes |
| 6 | Wire up in deps.py |
| 7 | Add @audited to teams routes |
| 8 | Add @audited to all remaining routes |
| 9 | Kubernetes CronJob for cleanup |
| 10 | Frontend audit log component |
| 11 | Add audit tab to Admin page |
| 12 | Generate OpenAPI client |
| 13 | Final integration test |
