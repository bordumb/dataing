# Dataset Details Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add UUID-based dataset pages with schema, lineage, alerts, and investigation tabs, plus clickable dataset links throughout the app.

**Architecture:** New `datasets` table persisted on schema sync. Frontend adds Dataset List and Detail pages with tabbed interface. DatasetLink component provides hover previews and navigation.

**Tech Stack:** Python/FastAPI backend, asyncpg, React/TypeScript frontend, TanStack Query, shadcn/ui Tabs component.

---

## Task 1: Create Datasets Database Migration

**Files:**
- Create: `backend/migrations/002_datasets.sql`

**Step 1: Write the migration file**

```sql
-- Dataset registry for UUID-based dataset identification
-- Datasets are synced from data sources on schema discovery

CREATE TABLE datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    datasource_id UUID NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,
    native_path VARCHAR(500) NOT NULL,
    name VARCHAR(255) NOT NULL,
    table_type VARCHAR(50) NOT NULL DEFAULT 'table',
    schema_name VARCHAR(255),
    catalog_name VARCHAR(255),
    row_count BIGINT,
    size_bytes BIGINT,
    column_count INTEGER,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(datasource_id, native_path)
);

CREATE INDEX idx_datasets_tenant ON datasets(tenant_id);
CREATE INDEX idx_datasets_datasource ON datasets(datasource_id);
CREATE INDEX idx_datasets_native_path ON datasets(native_path);
CREATE INDEX idx_datasets_name ON datasets(name);
```

**Step 2: Verify migration syntax**

Run: `cat backend/migrations/002_datasets.sql`
Expected: SQL file displays correctly

**Step 3: Commit**

```bash
git add backend/migrations/002_datasets.sql
git commit -m "feat: add datasets table migration"
```

---

## Task 2: Add Dataset Repository Methods to AppDatabase

**Files:**
- Modify: `backend/src/dataing/adapters/db/app_db.py`

**Step 1: Add upsert_datasets method**

Add after line 239 (after `delete_data_source` method):

```python
    # Dataset operations
    async def upsert_datasets(
        self,
        tenant_id: UUID,
        datasource_id: UUID,
        datasets: list[dict[str, Any]],
    ) -> int:
        """Upsert datasets from schema discovery.

        Inserts new datasets and updates existing ones.
        Returns count of upserted datasets.
        """
        if not datasets:
            return 0

        async with self.acquire() as conn:
            count = 0
            for ds in datasets:
                await conn.execute(
                    """INSERT INTO datasets
                       (tenant_id, datasource_id, native_path, name, table_type,
                        schema_name, catalog_name, row_count, column_count, last_synced_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
                       ON CONFLICT (datasource_id, native_path)
                       DO UPDATE SET
                           name = EXCLUDED.name,
                           table_type = EXCLUDED.table_type,
                           schema_name = EXCLUDED.schema_name,
                           catalog_name = EXCLUDED.catalog_name,
                           row_count = EXCLUDED.row_count,
                           column_count = EXCLUDED.column_count,
                           last_synced_at = NOW(),
                           updated_at = NOW(),
                           is_active = true""",
                    tenant_id,
                    datasource_id,
                    ds["native_path"],
                    ds["name"],
                    ds.get("table_type", "table"),
                    ds.get("schema_name"),
                    ds.get("catalog_name"),
                    ds.get("row_count"),
                    ds.get("column_count"),
                )
                count += 1
            return count

    async def list_datasets(
        self,
        tenant_id: UUID,
        datasource_id: UUID,
        table_type: str | None = None,
        search: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List datasets for a datasource."""
        base_query = """
            SELECT id, datasource_id, native_path, name, table_type,
                   schema_name, catalog_name, row_count, column_count,
                   last_synced_at, created_at
            FROM datasets
            WHERE tenant_id = $1 AND datasource_id = $2 AND is_active = true
        """
        args: list[Any] = [tenant_id, datasource_id]
        idx = 3

        if table_type:
            base_query += f" AND table_type = ${idx}"
            args.append(table_type)
            idx += 1

        if search:
            base_query += f" AND (name ILIKE ${idx} OR native_path ILIKE ${idx})"
            args.append(f"%{search}%")
            idx += 1

        base_query += f" ORDER BY native_path LIMIT ${idx} OFFSET ${idx + 1}"
        args.extend([limit, offset])

        return await self.fetch_all(base_query, *args)

    async def get_dataset(
        self, dataset_id: UUID, tenant_id: UUID
    ) -> dict[str, Any] | None:
        """Get a dataset by ID."""
        return await self.fetch_one(
            """SELECT d.*, ds.name as datasource_name, ds.type as datasource_type
               FROM datasets d
               JOIN data_sources ds ON ds.id = d.datasource_id
               WHERE d.id = $1 AND d.tenant_id = $2 AND d.is_active = true""",
            dataset_id,
            tenant_id,
        )

    async def get_dataset_count(
        self, tenant_id: UUID, datasource_id: UUID
    ) -> int:
        """Get count of datasets for a datasource."""
        result = await self.fetch_one(
            """SELECT COUNT(*) as count FROM datasets
               WHERE tenant_id = $1 AND datasource_id = $2 AND is_active = true""",
            tenant_id,
            datasource_id,
        )
        return result["count"] if result else 0

    async def soft_delete_stale_datasets(
        self,
        tenant_id: UUID,
        datasource_id: UUID,
        active_paths: list[str],
    ) -> int:
        """Soft delete datasets no longer in the source."""
        if not active_paths:
            # Delete all if no active paths
            result = await self.execute(
                """UPDATE datasets SET is_active = false, updated_at = NOW()
                   WHERE tenant_id = $1 AND datasource_id = $2 AND is_active = true""",
                tenant_id,
                datasource_id,
            )
        else:
            result = await self.execute(
                """UPDATE datasets SET is_active = false, updated_at = NOW()
                   WHERE tenant_id = $1 AND datasource_id = $2
                     AND is_active = true AND native_path != ALL($3)""",
                tenant_id,
                datasource_id,
                active_paths,
            )
        # Extract count from result like "UPDATE 5"
        parts = result.split()
        return int(parts[1]) if len(parts) > 1 else 0

    async def list_investigations_for_dataset(
        self,
        tenant_id: UUID,
        dataset_native_path: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List investigations that reference a dataset."""
        return await self.fetch_all(
            """SELECT id, dataset_id, metric_name, status, severity,
                      created_at, completed_at
               FROM investigations
               WHERE tenant_id = $1 AND dataset_id = $2
               ORDER BY created_at DESC
               LIMIT $3""",
            tenant_id,
            dataset_native_path,
            limit,
        )
```

**Step 2: Run linting to verify syntax**

Run: `cd backend && uv run ruff check src/dataing/adapters/db/app_db.py`
Expected: No errors (or only pre-existing warnings)

**Step 3: Commit**

```bash
git add backend/src/dataing/adapters/db/app_db.py
git commit -m "feat: add dataset repository methods to AppDatabase"
```

---

## Task 3: Add Dataset API Endpoints

**Files:**
- Create: `backend/src/dataing/entrypoints/api/routes/datasets.py`
- Modify: `backend/src/dataing/entrypoints/api/routes/__init__.py`

**Step 1: Create datasets routes file**

```python
"""Dataset API routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from dataing.adapters.db.app_db import AppDatabase
from dataing.entrypoints.api.deps import get_app_db
from dataing.entrypoints.api.middleware.auth import (
    ApiKeyContext,
    verify_api_key,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])

AppDbDep = Annotated[AppDatabase, Depends(get_app_db)]
AuthDep = Annotated[ApiKeyContext, Depends(verify_api_key)]


class DatasetResponse(BaseModel):
    """Response for a dataset."""

    id: str
    datasource_id: str
    datasource_name: str | None = None
    datasource_type: str | None = None
    native_path: str
    name: str
    table_type: str
    schema_name: str | None = None
    catalog_name: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    last_synced_at: str | None = None
    created_at: str


class DatasetListResponse(BaseModel):
    """Response for listing datasets."""

    datasets: list[DatasetResponse]
    total: int


class DatasetDetailResponse(DatasetResponse):
    """Detailed dataset response with columns."""

    columns: list[dict[str, Any]] = Field(default_factory=list)


class InvestigationSummary(BaseModel):
    """Summary of an investigation for dataset detail."""

    id: str
    dataset_id: str
    metric_name: str
    status: str
    severity: str | None = None
    created_at: str
    completed_at: str | None = None


class DatasetInvestigationsResponse(BaseModel):
    """Response for dataset investigations."""

    investigations: list[InvestigationSummary]
    total: int


def _format_dataset(ds: dict[str, Any]) -> DatasetResponse:
    """Format dataset record for response."""
    return DatasetResponse(
        id=str(ds["id"]),
        datasource_id=str(ds["datasource_id"]),
        datasource_name=ds.get("datasource_name"),
        datasource_type=ds.get("datasource_type"),
        native_path=ds["native_path"],
        name=ds["name"],
        table_type=ds["table_type"],
        schema_name=ds.get("schema_name"),
        catalog_name=ds.get("catalog_name"),
        row_count=ds.get("row_count"),
        column_count=ds.get("column_count"),
        last_synced_at=ds["last_synced_at"].isoformat() if ds.get("last_synced_at") else None,
        created_at=ds["created_at"].isoformat(),
    )


@router.get("/{dataset_id}", response_model=DatasetDetailResponse)
async def get_dataset(
    dataset_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> DatasetDetailResponse:
    """Get a dataset by ID with column information."""
    ds = await app_db.get_dataset(dataset_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    base = _format_dataset(ds)
    return DatasetDetailResponse(
        **base.model_dump(),
        columns=[],  # Columns fetched separately via schema endpoint
    )


@router.get("/{dataset_id}/investigations", response_model=DatasetInvestigationsResponse)
async def get_dataset_investigations(
    dataset_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
    limit: int = 50,
) -> DatasetInvestigationsResponse:
    """Get investigations for a dataset."""
    ds = await app_db.get_dataset(dataset_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")

    investigations = await app_db.list_investigations_for_dataset(
        auth.tenant_id,
        ds["native_path"],
        limit=limit,
    )

    summaries = [
        InvestigationSummary(
            id=str(inv["id"]),
            dataset_id=inv["dataset_id"],
            metric_name=inv["metric_name"],
            status=inv["status"],
            severity=inv.get("severity"),
            created_at=inv["created_at"].isoformat(),
            completed_at=inv["completed_at"].isoformat() if inv.get("completed_at") else None,
        )
        for inv in investigations
    ]

    return DatasetInvestigationsResponse(
        investigations=summaries,
        total=len(summaries),
    )
```

**Step 2: Register router in routes __init__.py**

Add import and include in `backend/src/dataing/entrypoints/api/routes/__init__.py`:

```python
from .datasets import router as datasets_router
```

And add to the router includes list.

**Step 3: Run linting**

Run: `cd backend && uv run ruff check src/dataing/entrypoints/api/routes/datasets.py`
Expected: No errors

**Step 4: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/datasets.py
git add backend/src/dataing/entrypoints/api/routes/__init__.py
git commit -m "feat: add dataset API endpoints"
```

---

## Task 4: Add Sync Endpoint and Dataset Registration Logic

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/routes/datasources.py`

**Step 1: Add sync endpoint**

Add after the `get_column_stats` endpoint (around line 727):

```python
class SyncResponse(BaseModel):
    """Response for schema sync."""

    datasets_synced: int
    datasets_removed: int
    message: str


@router.post("/{datasource_id}/sync", response_model=SyncResponse)
async def sync_datasource_schema(
    datasource_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
) -> SyncResponse:
    """Sync schema and register/update datasets.

    Discovers all tables from the data source and upserts them
    into the datasets table. Soft-deletes datasets that no longer exist.
    """
    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    registry = get_registry()

    try:
        source_type = SourceType(ds["type"])
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source type: {ds['type']}",
        ) from None

    # Decrypt config
    encryption_key = get_encryption_key()
    try:
        config = _decrypt_config(ds["connection_config_encrypted"], encryption_key)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to decrypt configuration: {str(e)}",
        ) from e

    # Get schema
    try:
        adapter = registry.create(source_type, config)
        async with adapter:
            schema = await adapter.get_schema(SchemaFilter(max_tables=10000))

        # Build dataset records from schema
        dataset_records: list[dict[str, Any]] = []
        for catalog in schema.catalogs:
            for schema_obj in catalog.schemas:
                for table in schema_obj.tables:
                    dataset_records.append({
                        "native_path": table.native_path,
                        "name": table.name,
                        "table_type": table.table_type,
                        "schema_name": schema_obj.name,
                        "catalog_name": catalog.name,
                        "row_count": table.row_count,
                        "column_count": len(table.columns),
                    })

        # Upsert datasets
        synced_count = await app_db.upsert_datasets(
            auth.tenant_id,
            datasource_id,
            dataset_records,
        )

        # Soft-delete removed datasets
        active_paths = [d["native_path"] for d in dataset_records]
        removed_count = await app_db.soft_delete_stale_datasets(
            auth.tenant_id,
            datasource_id,
            active_paths,
        )

        return SyncResponse(
            datasets_synced=synced_count,
            datasets_removed=removed_count,
            message=f"Synced {synced_count} datasets, removed {removed_count}",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Schema sync failed: {str(e)}",
        ) from e


@router.get("/{datasource_id}/datasets", response_model=DatasetListResponse)
async def list_datasource_datasets(
    datasource_id: UUID,
    auth: AuthDep,
    app_db: AppDbDep,
    table_type: str | None = None,
    search: str | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> DatasetListResponse:
    """List datasets for a datasource."""
    # Import here to avoid circular imports
    from dataing.entrypoints.api.routes.datasets import DatasetListResponse, _format_dataset

    ds = await app_db.get_data_source(datasource_id, auth.tenant_id)

    if not ds:
        raise HTTPException(status_code=404, detail="Data source not found")

    datasets = await app_db.list_datasets(
        auth.tenant_id,
        datasource_id,
        table_type=table_type,
        search=search,
        limit=limit,
        offset=offset,
    )

    total = await app_db.get_dataset_count(auth.tenant_id, datasource_id)

    return DatasetListResponse(
        datasets=[_format_dataset(d) for d in datasets],
        total=total,
    )
```

**Step 2: Add SyncResponse import and DatasetListResponse**

At the top of datasources.py, add the import for the DatasetListResponse model (or define it locally to avoid circular imports).

**Step 3: Run linting**

Run: `cd backend && uv run ruff check src/dataing/entrypoints/api/routes/datasources.py`
Expected: No errors

**Step 4: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/datasources.py
git commit -m "feat: add schema sync endpoint with dataset registration"
```

---

## Task 5: Add Auto-Sync on Datasource Creation

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/routes/datasources.py`

**Step 1: Add auto-sync after datasource creation**

In the `create_datasource` endpoint, after line 333 (after returning DataSourceResponse), add the sync call. Modify the function to trigger sync:

```python
    # After saving to database and before returning
    # Auto-sync schema to register datasets
    try:
        async with adapter:
            schema = await adapter.get_schema(SchemaFilter(max_tables=10000))

        dataset_records: list[dict[str, Any]] = []
        for catalog in schema.catalogs:
            for schema_obj in catalog.schemas:
                for table in schema_obj.tables:
                    dataset_records.append({
                        "native_path": table.native_path,
                        "name": table.name,
                        "table_type": table.table_type,
                        "schema_name": schema_obj.name,
                        "catalog_name": catalog.name,
                        "row_count": table.row_count,
                        "column_count": len(table.columns),
                    })

        await app_db.upsert_datasets(
            auth.tenant_id,
            UUID(str(db_result["id"])),
            dataset_records,
        )
    except Exception as e:
        # Log but don't fail - datasource was created successfully
        logger.warning("auto_sync_failed", datasource_id=db_result["id"], error=str(e))
```

**Step 2: Commit**

```bash
git add backend/src/dataing/entrypoints/api/routes/datasources.py
git commit -m "feat: auto-sync datasets on datasource creation"
```

---

## Task 6: Regenerate OpenAPI and Frontend Types

**Files:**
- Modify: `backend/openapi.json`
- Frontend generated files

**Step 1: Export OpenAPI schema**

Run: `cd backend && uv run python scripts/export_openapi.py`
Expected: "OpenAPI schema exported to backend/openapi.json"

**Step 2: Generate frontend types**

Run: `cd frontend && pnpm run orval`
Expected: "Your OpenAPI spec has been converted"

**Step 3: Commit**

```bash
git add backend/openapi.json
git add frontend/src/lib/api/generated/
git commit -m "chore: regenerate OpenAPI spec and frontend types"
```

---

## Task 7: Add Frontend Dataset API Hooks

**Files:**
- Create: `frontend/src/lib/api/datasets.ts`
- Modify: `frontend/src/lib/api/query-keys.ts`

**Step 1: Add dataset query keys**

Add to `query-keys.ts`:

```typescript
  datasets: {
    all: (datasourceId: string) => [`/api/v1/datasources/${datasourceId}/datasets`] as const,
    detail: (id: string) => [`/api/v1/datasets/${id}`] as const,
    investigations: (id: string) => [`/api/v1/datasets/${id}/investigations`] as const,
  },
```

**Step 2: Create datasets.ts API file**

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { queryKeys } from './query-keys'
import { apiClient } from './client'

export interface Dataset {
  id: string
  datasource_id: string
  datasource_name?: string
  datasource_type?: string
  native_path: string
  name: string
  table_type: string
  schema_name?: string
  catalog_name?: string
  row_count?: number
  column_count?: number
  last_synced_at?: string
  created_at: string
}

export interface DatasetListResponse {
  datasets: Dataset[]
  total: number
}

export interface DatasetDetail extends Dataset {
  columns: Array<{
    name: string
    data_type: string
    nullable: boolean
    is_primary_key: boolean
  }>
}

export interface InvestigationSummary {
  id: string
  dataset_id: string
  metric_name: string
  status: string
  severity?: string
  created_at: string
  completed_at?: string
}

export interface SyncResponse {
  datasets_synced: number
  datasets_removed: number
  message: string
}

export function useDatasets(datasourceId: string | null) {
  return useQuery({
    queryKey: datasourceId ? queryKeys.datasets.all(datasourceId) : ['disabled'],
    queryFn: async (): Promise<DatasetListResponse> => {
      if (!datasourceId) throw new Error('No datasource ID')
      return apiClient.get(`/api/v1/datasources/${datasourceId}/datasets`)
    },
    enabled: !!datasourceId,
  })
}

export function useDataset(datasetId: string | null) {
  return useQuery({
    queryKey: datasetId ? queryKeys.datasets.detail(datasetId) : ['disabled'],
    queryFn: async (): Promise<DatasetDetail> => {
      if (!datasetId) throw new Error('No dataset ID')
      return apiClient.get(`/api/v1/datasets/${datasetId}`)
    },
    enabled: !!datasetId,
  })
}

export function useDatasetInvestigations(datasetId: string | null) {
  return useQuery({
    queryKey: datasetId ? queryKeys.datasets.investigations(datasetId) : ['disabled'],
    queryFn: async (): Promise<{ investigations: InvestigationSummary[]; total: number }> => {
      if (!datasetId) throw new Error('No dataset ID')
      return apiClient.get(`/api/v1/datasets/${datasetId}/investigations`)
    },
    enabled: !!datasetId,
  })
}

export function useSyncDatasource() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (datasourceId: string): Promise<SyncResponse> => {
      return apiClient.post(`/api/v1/datasources/${datasourceId}/sync`, {})
    },
    onSuccess: (_, datasourceId) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.datasets.all(datasourceId),
      })
    },
  })
}
```

**Step 3: Commit**

```bash
git add frontend/src/lib/api/datasets.ts
git add frontend/src/lib/api/query-keys.ts
git commit -m "feat: add dataset API hooks"
```

---

## Task 8: Add "See Datasets" Button to Datasource Table

**Files:**
- Modify: `frontend/src/features/datasources/datasource-columns.tsx`

**Step 1: Add Datasets button column**

Add after the `created_at` column, before `actions`:

```tsx
  {
    id: 'datasets',
    header: 'Datasets',
    cell: ({ row }) => {
      const datasource = row.original
      return (
        <Link to={`/datasources/${datasource.id}/datasets`}>
          <Button variant="outline" size="sm">
            See Datasets
          </Button>
        </Link>
      )
    },
  },
```

Add import at top:

```tsx
import { Link } from 'react-router-dom'
```

**Step 2: Commit**

```bash
git add frontend/src/features/datasources/datasource-columns.tsx
git commit -m "feat: add See Datasets button to datasource table"
```

---

## Task 9: Create Dataset List Page

**Files:**
- Create: `frontend/src/features/datasets/dataset-list-page.tsx`
- Create: `frontend/src/features/datasets/dataset-columns.tsx`

**Step 1: Create dataset-columns.tsx**

```tsx
import { ColumnDef } from '@tanstack/react-table'
import { Link } from 'react-router-dom'

import { Badge } from '@/components/ui/Badge'
import { DataTableColumnHeader } from '@/components/data-table/data-table-column-header'
import { formatRelativeTime, formatNumber } from '@/lib/utils'
import { Dataset } from '@/lib/api/datasets'

function getTypeVariant(type: string) {
  switch (type) {
    case 'view':
      return 'secondary'
    case 'external':
      return 'outline'
    default:
      return 'default'
  }
}

export const datasetColumns: ColumnDef<Dataset>[] = [
  {
    accessorKey: 'native_path',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Name" />,
    cell: ({ row }) => (
      <Link
        to={`/datasets/${row.original.id}`}
        className="font-medium text-primary hover:underline"
      >
        {row.original.native_path}
      </Link>
    ),
  },
  {
    accessorKey: 'table_type',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Type" />,
    cell: ({ row }) => (
      <Badge variant={getTypeVariant(row.getValue('table_type'))}>
        {row.getValue('table_type')}
      </Badge>
    ),
  },
  {
    accessorKey: 'row_count',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Rows" />,
    cell: ({ row }) => {
      const count = row.getValue('row_count') as number | null
      return count !== null ? (
        <span className="text-muted-foreground">{formatNumber(count)}</span>
      ) : (
        <span className="text-muted-foreground">—</span>
      )
    },
  },
  {
    accessorKey: 'column_count',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Columns" />,
    cell: ({ row }) => {
      const count = row.getValue('column_count') as number | null
      return count !== null ? (
        <span className="text-muted-foreground">{count}</span>
      ) : (
        <span className="text-muted-foreground">—</span>
      )
    },
  },
  {
    accessorKey: 'last_synced_at',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Last Synced" />,
    cell: ({ row }) => {
      const synced = row.getValue('last_synced_at') as string | null
      return synced ? (
        <span className="text-muted-foreground">{formatRelativeTime(synced)}</span>
      ) : (
        <span className="text-muted-foreground">Never</span>
      )
    },
  },
]
```

**Step 2: Create dataset-list-page.tsx**

```tsx
import { useParams, Link } from 'react-router-dom'
import { RefreshCw, Database, ArrowLeft, AlertCircle } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { PageHeader } from '@/components/shared/page-header'
import { DataTable } from '@/components/data-table/data-table'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { EmptyState } from '@/components/shared/empty-state'
import { useDatasets, useSyncDatasource } from '@/lib/api/datasets'
import { useDataSource } from '@/lib/api/datasources'
import { datasetColumns } from './dataset-columns'
import { formatRelativeTime } from '@/lib/utils'
import { toast } from 'sonner'

export function DatasetListPage() {
  const { datasourceId } = useParams<{ datasourceId: string }>()
  const { data: datasource, isLoading: isLoadingDatasource } = useDataSource(datasourceId || '')
  const { data, isLoading, error, refetch } = useDatasets(datasourceId || null)
  const syncMutation = useSyncDatasource()

  const handleSync = async () => {
    if (!datasourceId) return
    try {
      const result = await syncMutation.mutateAsync(datasourceId)
      toast.success(result.message)
      refetch()
    } catch (err) {
      toast.error('Failed to sync schema')
    }
  }

  if (isLoading || isLoadingDatasource) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4 max-w-lg">
          <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0" />
          <div>
            <p className="font-medium text-destructive">Failed to load datasets</p>
            <p className="text-sm text-muted-foreground mt-1">
              {error.message || 'Please try again.'}
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={() => refetch()}>
          <RefreshCw className="mr-2 h-4 w-4" />
          Retry
        </Button>
      </div>
    )
  }

  const datasets = data?.datasets || []
  const lastSynced = datasets[0]?.last_synced_at

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/datasources">
          <Button variant="ghost" size="sm" className="gap-1">
            <ArrowLeft className="h-4 w-4" />
            Datasources
          </Button>
        </Link>
      </div>

      <PageHeader
        title={`Datasets in ${datasource?.name || 'Data Source'}`}
        description={
          <span>
            {data?.total || 0} datasets
            {lastSynced && ` • Last synced ${formatRelativeTime(lastSynced)}`}
          </span>
        }
        action={
          <Button onClick={handleSync} disabled={syncMutation.isPending}>
            <RefreshCw className={`mr-2 h-4 w-4 ${syncMutation.isPending ? 'animate-spin' : ''}`} />
            {syncMutation.isPending ? 'Syncing...' : 'Sync Schema'}
          </Button>
        }
      />

      {datasets.length === 0 ? (
        <EmptyState
          icon={Database}
          title="No datasets"
          description="Sync the schema to discover datasets in this data source."
          action={
            <Button onClick={handleSync} disabled={syncMutation.isPending}>
              <RefreshCw className="mr-2 h-4 w-4" />
              Sync Schema
            </Button>
          }
        />
      ) : (
        <DataTable
          columns={datasetColumns}
          data={datasets}
          searchKey="native_path"
          searchPlaceholder="Filter datasets..."
        />
      )}
    </div>
  )
}
```

**Step 3: Commit**

```bash
git add frontend/src/features/datasets/
git commit -m "feat: add dataset list page"
```

---

## Task 10: Create Dataset Detail Page

**Files:**
- Create: `frontend/src/features/datasets/dataset-detail-page.tsx`

**Step 1: Create the page with tabs**

```tsx
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, RefreshCw, AlertCircle, Table2, GitBranch, Bell, Search } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { LoadingSpinner } from '@/components/shared/loading-spinner'
import { useDataset, useDatasetInvestigations } from '@/lib/api/datasets'
import { useDataSourceSchema } from '@/lib/api/datasources'
import { LineagePanel } from '@/features/investigation/components'
import { formatNumber, formatRelativeTime } from '@/lib/utils'

export function DatasetDetailPage() {
  const { datasetId } = useParams<{ datasetId: string }>()
  const { data: dataset, isLoading, error } = useDataset(datasetId || null)
  const { data: investigations } = useDatasetInvestigations(datasetId || null)
  const { data: schemaData } = useDataSourceSchema(dataset?.datasource_id || null)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner size="lg" />
      </div>
    )
  }

  if (error || !dataset) {
    return (
      <div className="flex flex-col items-center justify-center py-12 space-y-4">
        <div className="flex items-center gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4 max-w-lg">
          <AlertCircle className="h-5 w-5 text-destructive flex-shrink-0" />
          <div>
            <p className="font-medium text-destructive">Dataset not found</p>
            <p className="text-sm text-muted-foreground mt-1">
              The dataset may have been deleted or you don't have access.
            </p>
          </div>
        </div>
        <Link to="/datasources">
          <Button variant="outline">Back to Datasources</Button>
        </Link>
      </div>
    )
  }

  // Find columns for this dataset from schema
  const columns = schemaData?.catalogs
    ?.flatMap((c: any) => c.schemas)
    ?.flatMap((s: any) => s.tables)
    ?.find((t: any) => t.native_path === dataset.native_path)?.columns || []

  return (
    <div className="space-y-6">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link to="/datasources" className="hover:text-foreground">
          Datasources
        </Link>
        <span>/</span>
        <Link
          to={`/datasources/${dataset.datasource_id}/datasets`}
          className="hover:text-foreground"
        >
          {dataset.datasource_name}
        </Link>
        <span>/</span>
        <span className="text-foreground">{dataset.name}</span>
      </div>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold">{dataset.native_path}</h1>
          <div className="flex items-center gap-3 mt-2 text-sm text-muted-foreground">
            <Badge variant="outline">{dataset.datasource_type}</Badge>
            <Badge variant="secondary">{dataset.table_type}</Badge>
            {dataset.row_count !== null && (
              <span>{formatNumber(dataset.row_count)} rows</span>
            )}
            {dataset.last_synced_at && (
              <span>Last synced {formatRelativeTime(dataset.last_synced_at)}</span>
            )}
          </div>
        </div>
        <Button variant="outline" size="sm">
          <RefreshCw className="mr-2 h-4 w-4" />
          Sync
        </Button>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="schema" className="w-full">
        <TabsList>
          <TabsTrigger value="schema" className="gap-2">
            <Table2 className="h-4 w-4" />
            Schema
          </TabsTrigger>
          <TabsTrigger value="lineage" className="gap-2">
            <GitBranch className="h-4 w-4" />
            Lineage
          </TabsTrigger>
          <TabsTrigger value="alerts" className="gap-2">
            <Bell className="h-4 w-4" />
            Alerts
          </TabsTrigger>
          <TabsTrigger value="investigations" className="gap-2">
            <Search className="h-4 w-4" />
            Investigations
          </TabsTrigger>
        </TabsList>

        <TabsContent value="schema" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>Columns ({columns.length})</CardTitle>
            </CardHeader>
            <CardContent>
              {columns.length === 0 ? (
                <p className="text-muted-foreground">
                  No column information available. Try syncing the schema.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-2 px-3 font-medium">Name</th>
                        <th className="text-left py-2 px-3 font-medium">Type</th>
                        <th className="text-left py-2 px-3 font-medium">Nullable</th>
                        <th className="text-left py-2 px-3 font-medium">Key</th>
                      </tr>
                    </thead>
                    <tbody>
                      {columns.map((col: any) => (
                        <tr key={col.name} className="border-b last:border-0">
                          <td className="py-2 px-3 font-mono">{col.name}</td>
                          <td className="py-2 px-3">
                            <Badge variant="outline">{col.data_type}</Badge>
                          </td>
                          <td className="py-2 px-3 text-muted-foreground">
                            {col.nullable ? 'Yes' : 'No'}
                          </td>
                          <td className="py-2 px-3">
                            {col.is_primary_key && <Badge>PK</Badge>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="lineage" className="mt-4">
          <LineagePanel tableName={dataset.native_path} isLoading={false} />
        </TabsContent>

        <TabsContent value="alerts" className="mt-4">
          <Card>
            <CardContent className="py-12 text-center">
              <Bell className="h-12 w-12 mx-auto text-muted-foreground/50" />
              <h3 className="mt-4 font-medium">No alert rules configured</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Alert rules are coming soon. You'll be able to set up automatic
                monitoring for this dataset.
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="investigations" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>
                Investigations ({investigations?.total || 0})
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!investigations?.investigations?.length ? (
                <p className="text-muted-foreground">
                  No investigations have been run on this dataset yet.
                </p>
              ) : (
                <div className="space-y-3">
                  {investigations.investigations.map((inv) => (
                    <Link
                      key={inv.id}
                      to={`/investigations/${inv.id}`}
                      className="block p-3 rounded-lg border hover:bg-muted/50 transition-colors"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="font-medium">{inv.metric_name}</span>
                          <span className="text-muted-foreground ml-2">
                            {formatRelativeTime(inv.created_at)}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          {inv.severity && (
                            <Badge variant="outline">{inv.severity}</Badge>
                          )}
                          <Badge
                            variant={
                              inv.status === 'completed'
                                ? 'default'
                                : inv.status === 'failed'
                                ? 'destructive'
                                : 'secondary'
                            }
                          >
                            {inv.status}
                          </Badge>
                        </div>
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/features/datasets/dataset-detail-page.tsx
git commit -m "feat: add dataset detail page with tabs"
```

---

## Task 11: Add Routes to App.tsx

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Import new pages**

Add imports:

```tsx
import { DatasetListPage } from '@/features/datasets/dataset-list-page'
import { DatasetDetailPage } from '@/features/datasets/dataset-detail-page'
```

**Step 2: Add routes**

Add after the datasources route:

```tsx
<Route
  path="datasources/:datasourceId/datasets"
  element={
    <FeatureErrorBoundary feature="datasets">
      <DatasetListPage />
    </FeatureErrorBoundary>
  }
/>
<Route
  path="datasets/:datasetId"
  element={
    <FeatureErrorBoundary feature="dataset details">
      <DatasetDetailPage />
    </FeatureErrorBoundary>
  }
/>
```

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add dataset routes"
```

---

## Task 12: Add formatNumber and formatRelativeTime Utils

**Files:**
- Modify: `frontend/src/lib/utils.ts`

**Step 1: Add utility functions**

```typescript
export function formatNumber(num: number): string {
  if (num >= 1_000_000_000) {
    return `${(num / 1_000_000_000).toFixed(1)}B`
  }
  if (num >= 1_000_000) {
    return `${(num / 1_000_000).toFixed(1)}M`
  }
  if (num >= 1_000) {
    return `${(num / 1_000).toFixed(1)}K`
  }
  return num.toString()
}

export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`

  return date.toLocaleDateString()
}
```

**Step 2: Commit**

```bash
git add frontend/src/lib/utils.ts
git commit -m "feat: add formatNumber and formatRelativeTime utilities"
```

---

## Task 13: Create DatasetLink Component

**Files:**
- Create: `frontend/src/components/shared/dataset-link.tsx`

**Step 1: Create the component**

```tsx
import * as React from 'react'
import { Link } from 'react-router-dom'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { Badge } from '@/components/ui/Badge'
import { useDataset } from '@/lib/api/datasets'
import { formatNumber, formatRelativeTime } from '@/lib/utils'
import { Loader2 } from 'lucide-react'

interface DatasetLinkProps {
  datasetId: string
  name: string
  className?: string
}

export function DatasetLink({ datasetId, name, className }: DatasetLinkProps) {
  const [showTooltip, setShowTooltip] = React.useState(false)
  const { data: dataset, isLoading } = useDataset(showTooltip ? datasetId : null)

  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip open={showTooltip} onOpenChange={setShowTooltip}>
        <TooltipTrigger asChild>
          <Link
            to={`/datasets/${datasetId}`}
            className={`text-primary hover:underline font-medium ${className || ''}`}
          >
            {name}
          </Link>
        </TooltipTrigger>
        <TooltipContent side="top" align="start" className="w-64 p-3">
          {isLoading ? (
            <div className="flex items-center justify-center py-2">
              <Loader2 className="h-4 w-4 animate-spin" />
            </div>
          ) : dataset ? (
            <div className="space-y-2">
              <div className="font-medium">{dataset.native_path}</div>
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-xs">
                  {dataset.datasource_type}
                </Badge>
                <Badge variant="secondary" className="text-xs">
                  {dataset.table_type}
                </Badge>
              </div>
              <div className="border-t pt-2 mt-2 text-xs text-muted-foreground space-y-1">
                {dataset.row_count !== null && (
                  <div>Rows: {formatNumber(dataset.row_count)}</div>
                )}
                {dataset.column_count !== null && (
                  <div>Columns: {dataset.column_count}</div>
                )}
                {dataset.last_synced_at && (
                  <div>Last synced: {formatRelativeTime(dataset.last_synced_at)}</div>
                )}
              </div>
              <div className="text-xs text-primary pt-1">
                Click to view details →
              </div>
            </div>
          ) : (
            <div className="text-sm text-muted-foreground">
              Dataset not found
            </div>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/shared/dataset-link.tsx
git commit -m "feat: add DatasetLink component with hover preview"
```

---

## Task 14: Run Linting and Build Verification

**Files:** None (verification only)

**Step 1: Run backend linting**

Run: `cd backend && uv run ruff check src/ --fix`
Expected: No errors or auto-fixed

**Step 2: Run frontend linting**

Run: `cd frontend && pnpm run lint`
Expected: No errors

**Step 3: Run frontend build**

Run: `cd frontend && pnpm run build`
Expected: Build succeeds

**Step 4: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: fix lint issues" --allow-empty
```

---

## Task 15: Final Verification and Cleanup

**Step 1: Review all changes**

Run: `git log --oneline -15`
Expected: See all commits from this implementation

**Step 2: Push branch**

Run: `git push -u origin dev-datasetDetails`

**Step 3: Use finishing-a-development-branch skill**

REQUIRED SUB-SKILL: Use superpowers:finishing-a-development-branch to complete the work.

---

## Summary

This implementation plan creates:
- Database migration for `datasets` table
- Repository methods for dataset CRUD operations
- API endpoints for datasets and sync
- Frontend dataset list and detail pages
- DatasetLink component with hover previews
- Integration with existing datasource pages

Total: 15 tasks with bite-sized steps for TDD workflow.
