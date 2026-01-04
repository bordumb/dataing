# Dataing v2 Gap Analysis & Implementation Prompt

## Executive Summary

The current codebase implements a **solid MVP** with clean architecture. However, it's missing significant functionality for startup and enterprise customers. This document analyzes what exists, what's missing, and provides detailed implementation guidance.

---

## Current State Assessment

  ⎿  ☒ Set up backend database models and migrations
     ☒ Implement authentication system (API keys, middleware)
     ☒ Add multi-tenant support and services layer
     ☒ Create notification adapters (webhook, Slack, email)
     ☒ Add audit logging middleware
     ☐ Implement data source management routes
     ☐ Add human-in-the-loop approval routes
     ☒ Implement usage tracking service
     ☐ Set up frontend shadcn/ui components
     ☐ Create sidebar and layout components
     ☐ Build data table components
     ☐ Implement auth context and login page
     ☐ Create dashboard page
     ☐ Build data source management UI
     ☐ Create settings page with tabs
     ☐ Add HITL context review component
     ☐ Update App.tsx with new routes and layout

### ✅ Frontend: What's Working Well

| Component | Status | Quality |
|-----------|--------|---------|
| shadcn/ui components | ✅ Partial | Good - Badge, Button, Card, Input |
| Investigation list | ✅ Complete | Basic |
| Investigation detail | ✅ Complete | Basic |
| New investigation form | ✅ Complete | Basic |
| Live event viewer | ✅ Complete | Good |
| SQL syntax highlighter | ✅ Complete | Good |
| Orval/TanStack Query setup | ✅ Complete | Good |

### ❌ Frontend: What's Missing

| Component | Priority | Effort | Notes |
|-----------|----------|--------|-------|
| Authentication UI | HIGH | Medium | No login/logout |
| Dashboard/home page | HIGH | Low | Just shows list |
| Data source config UI | MEDIUM | High | No connection management |
| Settings page | MEDIUM | Medium | No configuration UI |
| User management | MEDIUM | High | No users at all |
| HITL approval UI | MEDIUM | High | ContextReview.tsx mentioned but not implemented |
| Dark mode toggle | LOW | Low | CSS vars ready, no toggle |
| Schema browser | LOW | Medium | Would help users |
| Lineage visualizer | LOW | High | Nice to have |
| Mobile responsiveness | LOW | Low | Partial |

---

## Implementation Prompt for LLM

You are implementing features for Dataing v2, an autonomous data quality investigation system. The codebase follows hexagonal architecture with Python/FastAPI backend and React/TypeScript frontend.

### Context

**Tech Stack:**
- Backend: Python 3.11+, FastAPI, Pydantic, asyncpg, sqlglot, anthropic SDK
- Frontend: React 18, TypeScript, Vite, TanStack Query, shadcn/ui, Tailwind
- Database: PostgreSQL (for app state, separate from data warehouse)
- Auth: To be implemented

**Architecture Principles:**
- Core domain has zero external dependencies
- All state changes through events (event sourcing)
- FAIL FAST on missing schema context
- Safety is non-negotiable (sqlglot validation, circuit breakers)

---

## BACKEND FILE TREE - Files to Edit/Add

```
backend/src/dataing/
├── adapters/
│   ├── db/
│   │   ├── app_db.py                    # [ADD] Application database (not warehouse)
│   │   └── ...
│   └── notifications/                    # [ADD] New directory
│       ├── __init__.py                   # [ADD]
│       ├── webhook.py                    # [ADD] Webhook delivery
│       ├── slack.py                      # [ADD] Slack notifications
│       └── email.py                      # [ADD] Email via SMTP/SES
│
├── core/
│   ├── domain_types.py                   # [EDIT] Add User, Tenant, DataSource, ApiKey
│   └── ...
│
├── entrypoints/
│   └── api/
│       ├── app.py                        # [EDIT] Add middleware
│       ├── routes.py                     # [EDIT] Split into multiple files
│       ├── deps.py                       # [EDIT] Add auth dependencies
│       ├── middleware/                   # [ADD] New directory
│       │   ├── __init__.py               # [ADD]
│       │   ├── auth.py                   # [ADD] API key validation
│       │   ├── rate_limit.py             # [ADD] Rate limiting
│       │   └── audit.py                  # [ADD] Audit logging
│       └── routes/                       # [ADD] Split routes
│           ├── __init__.py               # [ADD]
│           ├── investigations.py         # [ADD] Move from routes.py
│           ├── datasources.py            # [ADD] CRUD for data sources
│           ├── users.py                  # [ADD] User management
│           └── settings.py               # [ADD] Tenant settings
│
├── services/                             # [ADD] New directory
│   ├── __init__.py                       # [ADD]
│   ├── auth.py                           # [ADD] Authentication service
│   ├── tenant.py                         # [ADD] Multi-tenancy
│   ├── usage.py                          # [ADD] Usage/cost tracking
│   └── notification.py                   # [ADD] Notification orchestration
│
└── models/                               # [ADD] New directory - SQLAlchemy models
    ├── __init__.py                       # [ADD]
    ├── base.py                           # [ADD] Base model with tenant_id
    ├── user.py                           # [ADD]
    ├── api_key.py                        # [ADD]
    ├── data_source.py                    # [ADD]
    ├── investigation.py                  # [ADD]
    └── audit_log.py                      # [ADD]
```

---

## Backend Implementation Details

### 3. Data Source Management (MEDIUM Priority)

**File: `backend/src/dataing/models/data_source.py`**

```python
"""Data source configuration model."""
from sqlalchemy import Column, String, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from cryptography.fernet import Fernet
import enum

class DataSourceType(str, enum.Enum):
    POSTGRES = "postgres"
    TRINO = "trino"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    REDSHIFT = "redshift"

class DataSource(BaseModel):
    """Configured data source for investigations."""
    __tablename__ = "data_sources"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(Enum(DataSourceType), nullable=False)

    # Connection details (encrypted)
    connection_config_encrypted = Column(String, nullable=False)  # Fernet encrypted JSON

    # Metadata
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    last_health_check_at = Column(DateTime(timezone=True))
    last_health_check_status = Column(String)  # "healthy" | "unhealthy"

    def get_connection_config(self, encryption_key: bytes) -> dict:
        """Decrypt and return connection config."""
        f = Fernet(encryption_key)
        return json.loads(f.decrypt(self.connection_config_encrypted.encode()))
```

**File: `backend/src/dataing/entrypoints/api/routes/datasources.py`**

```python
"""Data source management routes."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/datasources", tags=["datasources"])

class CreateDataSourceRequest(BaseModel):
    name: str
    type: str  # postgres, trino, snowflake, etc.
    connection_config: dict  # host, port, database, credentials

class DataSourceResponse(BaseModel):
    id: str
    name: str
    type: str
    is_default: bool
    is_active: bool
    last_health_check_at: str | None
    last_health_check_status: str | None

@router.post("/", response_model=DataSourceResponse)
async def create_datasource(
    request: CreateDataSourceRequest,
    auth: ApiKeyContext = Depends(verify_api_key),
    db: Database = Depends(get_db),
):
    """Create a new data source connection."""
    # Encrypt connection config
    encrypted = encrypt_config(request.connection_config)

    # Test connection first
    adapter = create_adapter(request.type, request.connection_config)
    try:
        await adapter.connect()
        schema = await adapter.get_schema()
        await adapter.close()
    except Exception as e:
        raise HTTPException(400, f"Connection test failed: {e}")

    # Save to database
    datasource = await db.execute(
        """INSERT INTO data_sources (tenant_id, name, type, connection_config_encrypted)
           VALUES ($1, $2, $3, $4) RETURNING *""",
        auth.tenant_id, request.name, request.type, encrypted
    )

    return DataSourceResponse(**datasource)

@router.post("/{datasource_id}/test")
async def test_datasource(datasource_id: str, ...):
    """Test data source connectivity."""
    ...

@router.get("/{datasource_id}/schema")
async def get_schema(datasource_id: str, ...):
    """Get schema from data source."""
    ...
```

### 5. Human-in-the-Loop (MEDIUM Priority)

**File: `backend/src/dataing/core/domain_types.py`** (additions)

```python
class ApprovalRequest(BaseModel):
    """Request for human approval before proceeding."""
    model_config = ConfigDict(frozen=True)

    investigation_id: str
    request_type: str  # "context_review" | "query_approval"
    context: dict  # What needs approval
    requested_at: datetime
    requested_by: str  # System or user

class ApprovalDecision(BaseModel):
    """Human decision on approval request."""
    model_config = ConfigDict(frozen=True)

    request_id: str
    decision: str  # "approved" | "rejected" | "modified"
    decided_by: str
    decided_at: datetime
    comment: str | None = None
    modifications: dict | None = None  # For "modified" decisions
```

**File: `backend/src/dataing/entrypoints/api/routes/approvals.py`**

```python
"""Human-in-the-loop approval routes."""
router = APIRouter(prefix="/approvals", tags=["approvals"])

@router.get("/pending")
async def list_pending_approvals(auth: ApiKeyContext = Depends(verify_api_key)):
    """List all pending approval requests for this tenant."""
    ...

@router.get("/{investigation_id}")
async def get_approval_request(investigation_id: str, ...):
    """Get approval request details including context to review."""
    ...

@router.post("/{investigation_id}/approve")
async def approve_investigation(
    investigation_id: str,
    comment: str | None = None,
    auth: ApiKeyContext = Depends(verify_api_key),
):
    """Approve investigation to proceed."""
    # Record decision
    # Resume investigation (trigger background task)
    ...

@router.post("/{investigation_id}/reject")
async def reject_investigation(
    investigation_id: str,
    reason: str,
    auth: ApiKeyContext = Depends(verify_api_key),
):
    """Reject investigation."""
    ...
```

---

## FRONTEND FILE TREE - Files to Edit/Add

```
frontend/src/
├── components/
│   ├── ui/
│   │   ├── ...                           # [EXISTING]
│   │   ├── Dialog.tsx                    # [ADD] Modal dialogs
│   │   ├── Select.tsx                    # [ADD] Dropdown select
│   │   ├── Table.tsx                     # [ADD] Data tables
│   │   ├── Tabs.tsx                      # [ADD] Tab navigation
│   │   ├── Toast.tsx                     # [ADD] Toast notifications
│   │   ├── Skeleton.tsx                  # [ADD] Loading skeletons
│   │   └── Avatar.tsx                    # [ADD] User avatars
│   │
│   ├── Layout.tsx                        # [EDIT] Add sidebar, user menu
│   └── Sidebar.tsx                       # [ADD] Navigation sidebar
│
├── features/
│   ├── auth/                             # [ADD] New directory
│   │   ├── LoginPage.tsx                 # [ADD]
│   │   ├── ApiKeyManager.tsx             # [ADD]
│   │   └── AuthProvider.tsx              # [ADD] Context provider
│   │
│   ├── dashboard/                        # [ADD] New directory
│   │   ├── DashboardPage.tsx             # [ADD] Overview/metrics
│   │   └── StatsCards.tsx                # [ADD] Summary cards
│   │
│   ├── datasources/                      # [ADD] New directory
│   │   ├── DataSourceList.tsx            # [ADD]
│   │   ├── DataSourceForm.tsx            # [ADD] Create/edit form
│   │   └── SchemaExplorer.tsx            # [ADD] Browse tables/columns
│   │
│   ├── investigation/
│   │   ├── ...                           # [EXISTING]
│   │   ├── ContextReview.tsx             # [ADD] HITL approval UI
│   │   └── InvestigationFilters.tsx      # [ADD] Filter/search
│   │
│   ├── settings/                         # [ADD] New directory
│   │   ├── SettingsPage.tsx              # [ADD]
│   │   ├── WebhookSettings.tsx           # [ADD]
│   │   ├── NotificationSettings.tsx      # [ADD]
│   │   └── TeamSettings.tsx              # [ADD] User management
│   │
│   └── usage/                            # [ADD] New directory
│       ├── UsagePage.tsx                 # [ADD]
│       └── UsageChart.tsx                # [ADD] Usage over time
│
├── lib/
│   ├── api/
│   │   ├── client.ts                     # [EDIT] Add auth header
│   │   ├── investigations.ts             # [EXISTING]
│   │   ├── datasources.ts                # [ADD]
│   │   ├── auth.ts                       # [ADD]
│   │   └── settings.ts                   # [ADD]
│   │
│   └── auth/                             # [ADD] New directory
│       ├── context.tsx                   # [ADD] Auth context
│       └── storage.ts                    # [ADD] Token storage
│
└── App.tsx                               # [EDIT] Add routes, auth guard
```

Note: current status is this, where ☒ is complete, and ☐ is work we need to do

☒ Set up backend database models and migrations
☒ Implement authentication system (API keys, middleware)
☒ Add multi-tenant support and services layer
☒ Create notification adapters (webhook, Slack, email)
☒ Add audit logging middleware
☐ Implement data source management routes
☐ Add human-in-the-loop approval routes
☒ Implement usage tracking service
