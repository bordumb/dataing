# DataDr Frontend: Lineage Integration Recommendations

## Current Frontend Structure

Based on analysis of your codebase:

```
Routes:
├── /                           → DashboardPage
├── /investigations             → InvestigationList
├── /investigations/new         → NewInvestigation
├── /investigations/:id         → InvestigationDetail
├── /datasources                → DataSourcePage
├── /settings/*                 → SettingsPage
└── /usage                      → UsagePage

Components:
├── layout/app-sidebar          → Navigation
├── features/dashboard          → Stats cards, recent investigations
├── features/investigation      → List, detail, live view, SQL explainer
├── features/datasources        → Data source management
└── features/settings           → API keys, webhooks, notifications
```

---

## Part 1: New Views & Components

### 1.1 Lineage Explorer Page (NEW ROUTE)

**Route:** `/lineage` or `/explore`

**Purpose:** Dedicated view for exploring data lineage across all datasets.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Lineage Explorer                                              [Search...] │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                                                                         ││
│  │                      INTERACTIVE LINEAGE GRAPH                         ││
│  │                                                                         ││
│  │     ┌─────────┐      ┌─────────┐      ┌─────────┐                     ││
│  │     │raw.users│─────▶│stg_users│─────▶│dim_users│                     ││
│  │     └─────────┘      └─────────┘      └────┬────┘                     ││
│  │                                            │                           ││
│  │     ┌──────────┐     ┌──────────┐     ┌────▼────┐                     ││
│  │     │raw.events│────▶│stg_events│────▶│fct_order│────▶ ...            ││
│  │     └──────────┘     └──────────┘     └─────────┘                     ││
│  │                                                                         ││
│  │  [Zoom +] [Zoom -] [Fit] [Fullscreen]              Depth: [1] [2] [3] ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ Selected: analytics.orders                                              ││
│  │                                                                         ││
│  │ Type: dbt model              Platform: Snowflake                       ││
│  │ Last Updated: 2 hours ago    Rows: 1.2M                                ││
│  │                                                                         ││
│  │ Producing Job: models/marts/orders.sql                                 ││
│  │ [View Code ↗]  [Investigate] [View Schema]                             ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Components needed:**
- `LineageGraph` - Interactive DAG visualization (use `react-flow` or `elkjs`)
- `LineageNodeCard` - Node in the graph (table/model)
- `LineageEdge` - Edge with job info on hover
- `DatasetDetailPanel` - Side panel with dataset metadata
- `LineageSearch` - Search/filter datasets
- `LineageDepthSelector` - Control upstream/downstream depth

**Value:** Users can visually explore "what feeds into this table?" before or during an investigation.

---

### 1.2 Dataset Detail Page (NEW ROUTE)

**Route:** `/datasets/:platform/:name` or `/datasources/:id/tables/:table`

**Purpose:** Deep dive into a single dataset with schema, lineage, quality history.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ← Back                                                                     │
│                                                                             │
│  analytics.orders                                           [Investigate]  │
│  Snowflake • dbt model • Last run: 2h ago                                  │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  [Schema]  [Lineage]  [Quality History]  [Jobs]                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  SCHEMA TAB:                                                               │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ Column          │ Type      │ Nullable │ Description                   ││
│  ├─────────────────┼───────────┼──────────┼───────────────────────────────┤│
│  │ order_id        │ integer   │ No (PK)  │ Unique order identifier       ││
│  │ user_id         │ integer   │ Yes      │ → dim_users.user_id           ││  ← Column lineage link!
│  │ total_amount    │ decimal   │ No       │ Order total in USD            ││
│  │ created_at      │ timestamp │ No       │ When order was placed         ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  LINEAGE TAB:                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ Upstream (2)                      │ Downstream (3)                     ││
│  │ • stg_events (dbt model)          │ • rpt_daily_orders (dbt model)    ││
│  │ • stg_users (dbt model)           │ • fct_revenue (dbt model)         ││
│  │                                    │ • Looker: Orders Dashboard        ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  QUALITY HISTORY TAB:                                                      │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ Investigation History                                                   ││
│  │ • Jan 15: NULL spike in user_id (resolved)                             ││
│  │ • Jan 10: Volume drop (CDN issue)                                      ││
│  │ • Dec 28: No issues found                                              ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Components needed:**
- `DatasetHeader` - Name, platform, badges, actions
- `SchemaTable` - Column list with types, descriptions
- `ColumnLineageLink` - Clickable link to source column
- `UpstreamDownstreamList` - Compact lineage list
- `QualityHistoryTimeline` - Past investigations for this dataset

**Value:** Single source of truth for "everything about this table."

---

### 1.3 Lineage Configuration Page (NEW ROUTE)

**Route:** `/settings/lineage`

**Purpose:** Configure lineage providers (dbt, Airflow, etc.)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Settings > Lineage Providers                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Connected Providers                                                       │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ [dbt logo]  dbt Cloud                                    [Connected ✓] ││
│  │             Project: analytics-prod                                     ││
│  │             Last sync: 5 minutes ago                                    ││
│  │             [Resync] [Edit] [Remove]                                   ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ [Airflow logo]  Apache Airflow                           [Connected ✓] ││
│  │                 URL: https://airflow.company.com                        ││
│  │                 Last sync: 1 hour ago                                   ││
│  │                 [Resync] [Edit] [Remove]                               ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  [+ Add Lineage Provider]                                                  │
│                                                                             │
│  Available Providers:                                                       │
│  • dbt (manifest or Cloud)                                                 │
│  • OpenLineage / Marquez                                                   │
│  • Airflow                                                                 │
│  • Dagster                                                                 │
│  • DataHub                                                                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Components needed:**
- `LineageProviderCard` - Connected provider status
- `LineageProviderForm` - Dynamic form (like DataSourceForm)
- `ProviderSyncStatus` - Last sync time, errors

---

### 1.4 New Shared Components

| Component | Purpose |
|-----------|---------|
| `LineageMiniGraph` | Small, non-interactive lineage preview (3-5 nodes) |
| `DatasetBadge` | Compact badge showing dataset type (table/model/source) |
| `PlatformIcon` | Icon for each platform (Snowflake, Postgres, dbt, etc.) |
| `CodeLink` | Link to GitHub/source code with icon |
| `JobRunStatus` | Status badge with last run time |
| `LineageDepthControls` | +/- buttons for lineage depth |

---

## Part 2: Enhance Existing Views with Lineage

### 2.1 Investigation Detail Page

**Current:** Shows investigation progress, findings, evidence, SQL queries.

**Add lineage context to make root cause analysis clearer:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Investigation: analytics.orders                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Finding                                                                   │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ Root Cause: NULL spike in user_id column                               ││
│  │ Confidence: 94%                                                         ││
│  │ Affected Rows: 892 of 5,023                                            ││
│  │                                                                         ││
│  │ ┌─────────────────────────────────────────────────────────────────────┐││
│  │ │ 📍 LINEAGE CONTEXT (NEW!)                                           │││
│  │ │                                                                      │││
│  │ │ Upstream tables checked:                                            │││
│  │ │ • stg_events ✓ No issues                                            │││
│  │ │ • stg_users  ⚠️ user_id NULL rate: 0.1% (normal)                    │││
│  │ │                                                                      │││
│  │ │ Producing job:                                                       │││
│  │ │ • models/marts/orders.sql                                           │││
│  │ │ • Last successful run: Jan 15, 10:30 AM                             │││
│  │ │ • [View Job Runs] [View Code ↗]                                     │││
│  │ │                                                                      │││
│  │ │ Downstream impact:                                                   │││
│  │ │ • 3 tables affected: rpt_daily_orders, fct_revenue, dim_customers  │││
│  │ │ • 2 dashboards may show incorrect data                              │││
│  │ └─────────────────────────────────────────────────────────────────────┘││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  Evidence                                                                   │
│  [existing evidence cards...]                                              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**New components for InvestigationDetail:**
- `LineageContextCard` - Shows upstream/downstream during investigation
- `UpstreamHealthList` - Status of upstream tables
- `DownstreamImpactList` - What breaks if this table is wrong
- `ProducingJobCard` - Job info with run history link
- `CodeLocationLink` - GitHub link to the code that builds this table

**Where to place in existing code:**

```tsx
// InvestigationDetail.tsx - Add after Finding card

{data.finding && (
  <>
    {/* Existing Finding card */}
    <Card>...</Card>

    {/* NEW: Lineage Context */}
    {data.lineage && (
      <LineageContextCard
        upstream={data.lineage.upstream}
        downstream={data.lineage.downstream}
        producingJob={data.lineage.producing_job}
        onViewLineage={() => navigate(`/lineage?focus=${data.dataset_id}`)}
      />
    )}

    {/* Existing Evidence card */}
    <Card>...</Card>
  </>
)}
```

---

### 2.2 New Investigation Page

**Current:** Select data source, table, column, describe issue.

**Enhance with lineage preview before starting investigation:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  New Investigation                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Data Source: [Snowflake Production ▼]                                     │
│                                                                             │
│  Table: [analytics.orders ▼]                                               │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ 📍 LINEAGE PREVIEW (NEW! - appears after table selection)              ││
│  │                                                                         ││
│  │   raw.events ──▶ stg_events ──┐                                        ││
│  │                               ├──▶ [analytics.orders] ──▶ 3 downstream ││
│  │   raw.users ───▶ stg_users ───┘                                        ││
│  │                                                                         ││
│  │   Produced by: dbt model (models/marts/orders.sql)                     ││
│  │   Last run: 2 hours ago (success)                                      ││
│  │   [View full lineage ↗]                                                ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  Column (optional): [user_id ▼]                                            │
│                                                                             │
│  Describe the issue:                                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ user_id has many NULL values starting yesterday                        ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  [Start Investigation]                                                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**New components for NewInvestigation:**
- `TableLineagePreview` - Mini lineage graph shown after table selection
- `ProducingJobPreview` - Quick view of what builds this table

**Value:** User sees context before investigation starts. Might realize "oh, the upstream table is the problem" and investigate that instead.

---

### 2.3 Data Sources Page

**Current:** List of connected data sources with table counts.

**Enhance with lineage provider status:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Data Sources                                              [+ Add Source]  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ [Snowflake]  Production Warehouse                        [Connected ✓] ││
│  │              snowflake://company.snowflakecomputing.com                 ││
│  │              156 tables • Last synced: 5 min ago                        ││
│  │                                                                         ││
│  │              Lineage: dbt Cloud ✓  Airflow ✓              ← NEW!       ││
│  │              [View Tables] [Explore Lineage]              ← NEW!       ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ [Postgres]   App Database                                [Connected ✓] ││
│  │              postgres://app-db.internal:5432                            ││
│  │              42 tables • Last synced: 1 hour ago                        ││
│  │                                                                         ││
│  │              Lineage: Not configured                      ← NEW!       ││
│  │              [View Tables] [Configure Lineage]            ← NEW!       ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**New components for DataSourcePage:**
- `LineageStatusBadge` - Shows which lineage providers are connected
- `ExploreLineageButton` - Links to `/lineage?source=<id>`

---

### 2.4 Dashboard Page

**Current:** Stats cards (active investigations, completed today, etc.) + recent investigations.

**Add lineage health summary:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Dashboard                                          [+ New Investigation]  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [Existing stats cards: Active, Completed, Data Sources, Pending]          │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │ Lineage Health (NEW!)                                                   ││
│  ├─────────────────────────────────────────────────────────────────────────┤│
│  │                                                                         ││
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 ││
│  │  │ 156          │  │ 12           │  │ 3            │                 ││
│  │  │ Datasets     │  │ Failed Jobs  │  │ Stale Tables │                 ││
│  │  │ tracked      │  │ (last 24h)   │  │ (>24h old)   │                 ││
│  │  └──────────────┘  └──────────────┘  └──────────────┘                 ││
│  │                                                                         ││
│  │  Recent Job Failures:                                                   ││
│  │  • orders_daily (dbt) - Failed 2h ago - [View]                         ││
│  │  • events_sync (Airflow) - Failed 6h ago - [View]                      ││
│  │                                                                         ││
│  │  [View All Lineage →]                                                   ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  [Existing Recent Investigations card]                                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**New components for DashboardPage:**
- `LineageHealthCard` - Summary stats from lineage providers
- `FailedJobsList` - Recent job failures that might indicate data issues
- `StaleTablesAlert` - Tables that haven't been updated

**Value:** Proactive alerting. User sees "12 failed jobs" and investigates before dashboards break.

---

### 2.5 Sidebar Navigation

**Current navigation items:**
- Dashboard
- Investigations
- Data Sources
- Usage
- Settings
- Notifications

**Add lineage entry:**

```tsx
const mainNavItems = [
  { title: 'Dashboard', url: '/', icon: LayoutDashboard },
  { title: 'Investigations', url: '/investigations', icon: Search },
  { title: 'Data Sources', url: '/datasources', icon: Database },
  { title: 'Lineage', url: '/lineage', icon: GitBranch },  // ← NEW
  { title: 'Usage', url: '/usage', icon: BarChart3 },
]
```

---

## Part 3: Component Architecture

### 3.1 New Feature Directory

```
frontend/src/features/lineage/
├── lineage-explorer-page.tsx       # Main lineage exploration view
├── dataset-detail-page.tsx         # Single dataset deep dive
├── components/
│   ├── lineage-graph.tsx           # Interactive DAG visualization
│   ├── lineage-node.tsx            # Single node in graph
│   ├── lineage-edge.tsx            # Edge with job info
│   ├── lineage-mini-graph.tsx      # Compact preview version
│   ├── lineage-search.tsx          # Dataset search
│   ├── lineage-depth-controls.tsx  # Depth selector
│   ├── dataset-detail-panel.tsx    # Side panel with metadata
│   ├── upstream-downstream-list.tsx # Compact list view
│   ├── column-lineage-table.tsx    # Column-level lineage
│   ├── job-run-history.tsx         # Job execution history
│   ├── code-location-link.tsx      # GitHub link component
│   └── lineage-context-card.tsx    # For investigation detail
├── hooks/
│   ├── use-lineage-graph.ts        # Fetch and manage graph state
│   ├── use-dataset.ts              # Fetch single dataset
│   └── use-job-runs.ts             # Fetch job run history
└── types.ts                        # Lineage-specific types

frontend/src/features/settings/
├── lineage-settings.tsx            # NEW: Lineage provider config
└── ...existing files
```

### 3.2 Shared Components to Add

```
frontend/src/components/shared/
├── platform-icon.tsx               # Icons for Snowflake, Postgres, dbt, etc.
├── dataset-badge.tsx               # Type badge (table/model/source)
├── job-status-badge.tsx            # Success/failed/running
├── code-link.tsx                   # GitHub/GitLab link with icon
└── ...existing files
```

### 3.3 API Hooks to Add

```typescript
// frontend/src/lib/api/lineage.ts

// Fetch lineage graph for a dataset
export function useLineageGraph(
  platform: string,
  dataset: string,
  options?: { upstreamDepth?: number; downstreamDepth?: number }
) { ... }

// Fetch single dataset metadata
export function useDataset(platform: string, dataset: string) { ... }

// Fetch upstream datasets
export function useUpstream(platform: string, dataset: string, depth?: number) { ... }

// Fetch downstream datasets
export function useDownstream(platform: string, dataset: string, depth?: number) { ... }

// Fetch producing job
export function useProducingJob(platform: string, dataset: string) { ... }

// Fetch job run history
export function useJobRuns(jobId: string, limit?: number) { ... }

// Search datasets
export function useDatasetSearch(query: string) { ... }

// List lineage providers
export function useLineageProviders() { ... }

// Test lineage provider connection
export function useTestLineageProvider() { ... }
```

---

## Part 4: Priority Recommendations

### Phase 1: High-Impact, Low-Effort (Week 1)

| Task | Effort | Value |
|------|--------|-------|
| Add `LineageContextCard` to InvestigationDetail | 1 day | Shows immediate value of lineage |
| Add `TableLineagePreview` to NewInvestigation | 1 day | Helps users pick right table |
| Add lineage nav item to sidebar | 30 min | Discoverability |
| Create placeholder `/lineage` page | 2 hours | Route exists even if minimal |

### Phase 2: Core Lineage Views (Weeks 2-3)

| Task | Effort | Value |
|------|--------|-------|
| Build `LineageExplorerPage` with graph | 3-4 days | Main lineage feature |
| Build `DatasetDetailPage` | 2 days | Deep dive on single table |
| Add lineage status to DataSourcePage | 1 day | Shows lineage coverage |

### Phase 3: Settings & Polish (Week 4)

| Task | Effort | Value |
|------|--------|-------|
| Build `LineageSettingsPage` | 2 days | Configure providers |
| Add `LineageHealthCard` to Dashboard | 1 day | Proactive alerting |
| Add column lineage to schema views | 2 days | Fine-grained lineage |

---

## Part 5: Library Recommendations

### For Lineage Graph Visualization

**Option A: React Flow (Recommended)**
- Pros: Most flexible, great docs, good performance
- Cons: Learning curve
- Use for: Main lineage explorer

```bash
pnpm add reactflow
```

**Option B: Dagre + D3**
- Pros: Pure layout algorithm, works with any renderer
- Cons: More DIY work
- Use for: If you need custom rendering

**Option C: Elkjs**
- Pros: Best automatic layout for DAGs
- Cons: Heavier, more complex
- Use for: Very large graphs

### For Mini Graphs

Consider a simpler approach for `LineageMiniGraph`:
- Static SVG generation
- Or very simple CSS-based node layout
- Doesn't need full interactivity

---

## Summary

### New Routes
1. `/lineage` - Lineage Explorer
2. `/datasets/:platform/:name` - Dataset Detail
3. `/settings/lineage` - Lineage Provider Config

### Enhanced Existing Views
1. **InvestigationDetail** - Add LineageContextCard (upstream, downstream, job info)
2. **NewInvestigation** - Add TableLineagePreview after table selection
3. **DataSourcePage** - Add lineage status badges, "Explore Lineage" button
4. **Dashboard** - Add LineageHealthCard (failed jobs, stale tables)
5. **Sidebar** - Add Lineage nav item

### Key New Components
- `LineageGraph` - Interactive DAG visualization
- `LineageMiniGraph` - Compact preview
- `LineageContextCard` - For investigation detail
- `DatasetDetailPanel` - Side panel with metadata
- `UpstreamDownstreamList` - Compact list view
- `JobRunHistory` - Job execution timeline
- `CodeLocationLink` - GitHub link component

### Implementation Order
1. First: Add lineage context to existing investigation flow
2. Then: Build dedicated lineage explorer
3. Finally: Settings and dashboard integration
