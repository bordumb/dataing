# Dataset Details Page Design

## Overview

Add dedicated dataset pages with UUID-based identification, enabling users to view dataset metadata, schema, lineage, and investigation history. Dataset names become clickable links throughout the application with hover previews.

## Navigation Flow

```
Home
  └── Datasources (table with "See Datasets" button per row)
        └── Dataset List (table of datasets within datasource)
              └── Dataset Detail (tabs: Schema, Lineage, Alerts, Investigations)
```

## Data Model

### New Database Table: `datasets`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| tenant_id | UUID | Multi-tenancy |
| datasource_id | UUID | FK to datasources |
| native_path | VARCHAR | e.g., `public.orders` |
| name | VARCHAR | Table name (last segment) |
| table_type | VARCHAR | table, view, external |
| schema_name | VARCHAR | e.g., `public` |
| catalog_name | VARCHAR | e.g., `default` |
| row_count | BIGINT | Nullable, from stats |
| size_bytes | BIGINT | Nullable |
| last_synced_at | TIMESTAMP | When schema was synced |
| created_at | TIMESTAMP | First discovery |

### Dataset Registration

Datasets are registered automatically when a datasource schema is synced:
- On datasource creation, schema sync runs automatically
- Manual sync via "Sync Schema" button
- Upsert by `(datasource_id, native_path)` - existing datasets updated, new ones created
- Datasets no longer in source are soft-deleted

## API Endpoints

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/datasources/:id/datasets` | List datasets for a datasource |
| GET | `/datasets/:id` | Get dataset detail (metadata + columns) |
| GET | `/datasets/:id/stats` | Get column-level statistics |
| GET | `/datasets/:id/investigations` | List investigations for this dataset |
| POST | `/datasources/:id/sync` | Trigger schema sync (registers/updates datasets) |

## Frontend Routes

| Path | Component | Description |
|------|-----------|-------------|
| `/datasources` | DataSourcePage | Existing - add "See Datasets" button |
| `/datasources/:datasourceId/datasets` | DatasetListPage | List datasets in a datasource |
| `/datasets/:datasetId` | DatasetDetailPage | Dataset detail with tabs |

## Page Designs

### Dataset List Page

```
┌─────────────────────────────────────────────────────────┐
│ Breadcrumb: Datasources > Prod Warehouse                │
│                                                         │
│ Datasets in Prod Warehouse              [Sync Schema]   │
│ 47 datasets • Last synced 2h ago                        │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ Filter datasets...                       [Type ▼]   │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌──────────────────┬────────┬──────────┬─────────────┐ │
│ │ Name             │ Type   │ Rows     │ Last Synced │ │
│ ├──────────────────┼────────┼──────────┼─────────────┤ │
│ │ public.orders    │ table  │ 1.2M     │ 2h ago      │ │
│ │ public.users     │ table  │ 50K      │ 2h ago      │ │
│ │ analytics.daily  │ view   │ —        │ 2h ago      │ │
│ └──────────────────┴────────┴──────────┴─────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**Features:**
- Search/filter by name
- Filter by type (table/view/all)
- Sortable columns
- Uses existing DataTable component

### Dataset Detail Page

```
┌─────────────────────────────────────────────────────────┐
│ Breadcrumb: Datasources > Prod Warehouse > orders       │
│                                                         │
│ [Dataset Name: public.orders]          [Sync] [Actions] │
│ PostgreSQL • Table • 1.2M rows • Last synced 2h ago     │
│                                                         │
│ ┌─────────┬─────────┬─────────┬───────────────┐        │
│ │ Schema  │ Lineage │ Alerts  │ Investigations │        │
│ └─────────┴─────────┴─────────┴───────────────┘        │
│                                                         │
│ [Tab Content Area]                                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Tab Contents:**

| Tab | Content |
|-----|---------|
| Schema | Column table: name, type, nullable, PK, null rate, distinct count, min/max |
| Lineage | Reuse existing LineagePanel component |
| Alerts | Empty state placeholder: "No alert rules configured. Coming soon." |
| Investigations | List of investigations referencing this dataset |

## DatasetLink Component

A reusable component for clickable dataset names with hover preview.

```tsx
<DatasetLink datasetId="uuid" name="public.orders" />
```

**Hover Preview Tooltip:**

```
┌────────────────────────────┐
│ public.orders              │
│ PostgreSQL • Table         │
│ ─────────────────────────  │
│ Rows: 1,234,567            │
│ Columns: 12                │
│ Last synced: 2h ago        │
│                            │
│ Click to view details →    │
└────────────────────────────┘
```

**Behavior:**
- 300ms hover delay before showing tooltip
- Click navigates to `/datasets/:datasetId`
- Styled as link (underline on hover, primary color)

**Usage locations:**
- NewInvestigation.tsx - Dataset selector items
- InvestigationDetail.tsx - Dataset name in header
- DatasetListPage - Dataset names in table
- Dashboard - Dataset references in activity

## Implementation Phases

### Phase 1: Backend
1. Create `datasets` database table and migration
2. Add dataset repository methods to AppDatabase
3. Implement sync logic in datasources routes
4. Add new API endpoints for datasets

### Phase 2: Frontend - List Page
1. Add "See Datasets" button to datasource table
2. Create DatasetListPage component
3. Add route to App.tsx
4. Create datasets API hooks

### Phase 3: Frontend - Detail Page
1. Create DatasetDetailPage with tab structure
2. Implement Schema tab with statistics
3. Integrate existing LineagePanel for Lineage tab
4. Add Alerts placeholder tab
5. Implement Investigations tab

### Phase 4: DatasetLink Component
1. Create DatasetLink component with hover preview
2. Create tooltip/popover for preview
3. Replace dataset references across the app

## Future Enhancements (Out of Scope)

- Alert rule configuration (Alerts tab)
- Dataset favorites/bookmarks
- Dataset-level permissions
- Cross-datasource dataset comparison
- Sample data preview tab
