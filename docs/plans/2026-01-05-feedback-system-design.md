# Feedback System Design

## Overview

A comprehensive feedback system that captures investigation traces, user ratings, and tribal knowledge to enable semantic search and future ML training.

## Goals

1. **Full trace capture** - record hypotheses, queries, evidence, synthesis, and rejected paths
2. **Granular feedback** - users can rate hypotheses, queries, evidence, and synthesis separately
3. **Tribal knowledge** - aggregate insights per dataset (activity, quirks, top findings, ownership)
4. **Hybrid search** - PostgreSQL full-text + vector search for semantic discovery
5. **ML training pipeline** - prepare data for fine-tuning hypothesis generation, query optimization, and synthesis

## Core Schema

### Event Log: `feedback_events`

Append-only event stream for all investigation activity and user feedback.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Event ID |
| tenant_id | UUID | For filtering/isolation |
| investigation_id | UUID | Links to investigation |
| dataset_id | UUID | Nullable, for dataset-level aggregation |
| event_type | VARCHAR | e.g., `hypothesis.generated`, `query.executed`, `feedback.submitted` |
| event_data | JSONB | Flexible payload per event type |
| actor_id | UUID | User or system that caused event |
| actor_type | VARCHAR | `user` or `system` |
| created_at | TIMESTAMPTZ | Immutable timestamp |

**Event types:**
- `investigation.started`, `investigation.completed`
- `hypothesis.generated`, `hypothesis.accepted`, `hypothesis.rejected`
- `query.planned`, `query.executed`, `query.succeeded`, `query.failed`
- `evidence.collected`, `evidence.evaluated`
- `synthesis.generated`
- `feedback.hypothesis`, `feedback.query`, `feedback.synthesis`, `feedback.investigation`
- `comment.added`

### Dataset Knowledge Aggregation

Materialized aggregations for fast queries.

**Table: `dataset_knowledge`**

| Column | Type | Description |
|--------|------|-------------|
| dataset_id | UUID | Primary key |
| tenant_id | UUID | For filtering |
| investigation_count | INT | Total investigations touching this dataset |
| positive_feedback_count | INT | Thumbs up across all feedback |
| negative_feedback_count | INT | Thumbs down |
| last_investigation_at | TIMESTAMPTZ | Most recent activity |
| common_issues | JSONB | Top recurring issue patterns |
| known_quirks | JSONB | User-submitted notes ("this table has a 2-day lag") |
| owners | JSONB | People frequently involved with this dataset |
| updated_at | TIMESTAMPTZ | Last aggregation refresh |

**Table: `dataset_findings`**

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Finding ID |
| dataset_id | UUID | FK |
| investigation_id | UUID | Source investigation |
| finding_type | VARCHAR | `root_cause`, `observation`, `recommendation` |
| summary | TEXT | Human-readable finding |
| confidence | FLOAT | 0-1 confidence score |
| feedback_score | FLOAT | Aggregated user feedback |
| created_at | TIMESTAMPTZ | When discovered |

### Hybrid Search

**Vector search table: `search_embeddings`**

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| tenant_id | UUID | For filtering |
| source_type | VARCHAR | `finding`, `hypothesis`, `query`, `comment` |
| source_id | UUID | FK to source record |
| dataset_id | UUID | For dataset-scoped search |
| content | TEXT | Original text that was embedded |
| embedding | vector(1536) | OpenAI or similar embedding |
| created_at | TIMESTAMPTZ | For recency ranking |

Uses pgvector extension. Search flow:
1. User query → generate embedding
2. Run both: PostgreSQL full-text AND vector similarity search
3. Merge results, boost by recency and feedback score
4. Filter by tenant (and future: sub-tenant permissions)

## Feedback Collection

Users can rate hypotheses, queries, evidence, and the final synthesis.

**Feedback event structure:**

```json
{
  "event_type": "feedback.hypothesis",
  "event_data": {
    "target_id": "uuid-of-hypothesis",
    "rating": 1,
    "comment": "This was the right direction",
    "context": {
      "investigation_id": "...",
      "dataset_id": "...",
      "hypothesis_text": "NULL values from mobile app bug"
    }
  }
}
```

**Feedback types:**

| Type | Target | Question to user |
|------|--------|------------------|
| `feedback.hypothesis` | Hypothesis | "Was this hypothesis worth investigating?" |
| `feedback.query` | SQL query | "Did this query provide useful evidence?" |
| `feedback.evidence` | Evidence step | "Was this evidence relevant to the root cause?" |
| `feedback.synthesis` | Final synthesis | "Did this root cause analysis solve the problem?" |
| `feedback.investigation` | Overall | "Was this investigation helpful?" |

## Dataset Knowledge UI

Each dataset gets a "Knowledge" tab showing activity, insights, and searchable history.

```
┌─────────────────────────────────────────────────────────────┐
│ Dataset: public.orders                                       │
│ ┌─────────┬─────────┬───────────┬──────────────┐            │
│ │ Schema  │ Lineage │ Knowledge │ Investigations│            │
│ └─────────┴─────────┴───────────┴──────────────┘            │
│                                                              │
│ ┌──────────────────────────────────────────────────────────┐│
│ │ 🔍 Search this dataset's history...                      ││
│ └──────────────────────────────────────────────────────────┘│
│                                                              │
│ ┌─ Known Quirks ────────────────────────────────────────────┐│
│ │ • "ETL has 2-day lag on weekends" - @sarah, 3 weeks ago   ││
│ │ • "price column was string until 2024-06" - @mike         ││
│ │ + Add note                                                 ││
│ └───────────────────────────────────────────────────────────┘│
│                                                              │
│ ┌─ Top Findings (by feedback score) ────────────────────────┐│
│ │ 👍 12  NULL spike caused by mobile app v2.3 bug           ││
│ │ 👍 8   Duplicate orders from retry logic                  ││
│ │ 👍 5   Missing EU data during CDN migration               ││
│ └───────────────────────────────────────────────────────────┘│
│                                                              │
│ ┌─ Recent Activity ─────────────────────────────────────────┐│
│ │ Today     Investigation completed - schema drift detected ││
│ │ 2 days    @alex commented: "Check with payments team"     ││
│ │ 1 week    Investigation completed - volume drop explained ││
│ └───────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

## ML Training Pipeline

**Training data extraction:**

| Training Target | Input | Label | Source Events |
|-----------------|-------|-------|---------------|
| Hypothesis generation | Alert + context | Hypothesis text | `hypothesis.generated` + `feedback.hypothesis` |
| Hypothesis ranking | Multiple hypotheses | Which was correct | `hypothesis.accepted` vs `hypothesis.rejected` + feedback |
| Query generation | Hypothesis + schema | SQL query | `query.planned` + `feedback.query` |
| Synthesis quality | Evidence list | Root cause text | `synthesis.generated` + `feedback.synthesis` |

**Table: `ml_training_examples`**

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Example ID |
| task_type | VARCHAR | `hypothesis_gen`, `hypothesis_rank`, `query_gen`, `synthesis` |
| input_data | JSONB | Model input (alert, context, schema, etc.) |
| output_data | JSONB | Expected output (hypothesis, query, synthesis) |
| feedback_score | FLOAT | Aggregated quality signal |
| dataset_type | VARCHAR | Table category (e.g., `events`, `transactions`, `users`) |
| issue_type | VARCHAR | Anomaly type (e.g., `null_spike`, `volume_drop`) |
| created_at | TIMESTAMPTZ | When example was generated |

Export format: JSONL files for fine-tuning, filtered by minimum feedback score threshold.

Privacy: Training data stays within tenant unless explicitly opted-in for cross-tenant learning.

## Implementation Architecture

**New adapter: `FeedbackAdapter`**

```
backend/src/dataing/adapters/feedback/
├── __init__.py
├── event_emitter.py      # Write events to feedback_events
├── aggregator.py         # Background aggregation logic
├── search.py             # Hybrid search implementation
└── ml_export.py          # Training data extraction
```

**Background jobs:**

| Job | Frequency | Purpose |
|-----|-----------|---------|
| `aggregate_dataset_knowledge` | Every 5 min | Update `dataset_knowledge` from new events |
| `generate_embeddings` | Every 5 min | Embed new findings/hypotheses for vector search |
| `rebuild_training_examples` | Daily | Refresh `ml_training_examples` table |
| `export_training_data` | On-demand | Generate JSONL for fine-tuning |

**API endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/datasets/:id/knowledge` | Aggregated tribal knowledge |
| GET | `/search` | Tenant-wide semantic search |
| POST | `/feedback` | Submit feedback event |
| GET | `/datasets/:id/activity` | Recent activity feed |

## Implementation Phases

### Phase 1: Event Foundation
- Create `feedback_events` table and migration
- Implement `FeedbackAdapter.emit()` in `backend/src/dataing/adapters/feedback/`
- Wire orchestrator to emit events during investigations
- No UI changes yet - just start collecting data

### Phase 2: User Feedback Collection
- Add `POST /feedback` endpoint
- Add thumbs up/down buttons to investigation detail UI (hypotheses, queries, synthesis)
- Add post-investigation rating modal
- Events flow into `feedback_events`

### Phase 3: Dataset Knowledge Aggregation
- Create `dataset_knowledge` and `dataset_findings` tables
- Implement aggregation background job
- Add "Knowledge" tab to dataset detail page
- Show known quirks, top findings, recent activity

### Phase 4: Hybrid Search
- Add pgvector extension, create `search_embeddings` table
- Implement embedding generation job (OpenAI or local model)
- Add `GET /search` endpoint with hybrid ranking
- Add global search bar to frontend header

### Phase 5: ML Training Pipeline
- Create `ml_training_examples` table
- Implement training data extraction logic
- Add export endpoint/CLI command for JSONL generation
- Document fine-tuning workflow

## Future Considerations (Out of Scope)

- Cross-tenant learning with anonymization
- Sub-tenant filtering for enterprise (e.g., Goldman divisions)
- Real-time search index updates (vs batch)
- A/B testing framework for model improvements
