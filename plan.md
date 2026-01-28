# Dataing: Killer Features Roadmap

**Document Version:** 1.0
**Date:** January 2026
**Scope:** 6 Priority Features (3 Notebook, 3 CLI)

---

## Overview

This document contains implementation-ready epics and tasks for Dataing's six highest-priority features. Each task is written for an engineer to pick up and execute without further clarification.

**Notebook Features:**
1. Ghost State Hydrator
2. Fix-It Button
3. Trace-to-Test Codify

**CLI Features:**
1. `dataing blame`
2. `dataing sniff`
3. `dataing mock`

---

# Part 1: Notebook Features

---

## Epic N1: Ghost State Hydrator

**Goal:** Enable engineers to pull a remote production investigation state into their local Jupyter notebook, fully hydrated with DataFrames, schema snapshots, and lineage context.

**User Value:** "It works on my machine" becomes "I can reproduce the exact production state on my machine." The notebook becomes a forensic time machine.

**Competitor Gap:** Nobody does this. Monte Carlo investigations live in their UI. GX has no investigation concept. Soda has no state capture.

**Technical Approach:**
- Bond agent serializes investigation state (DataFrames, schema, context) to cloud storage during workflow execution
- JupyterLab widget fetches and deserializes state into notebook kernel
- User gets populated variables matching the production failure moment

---

### Task N1.1: Design State Snapshot Schema

**Description:**
Define the schema for a serializable investigation snapshot that captures everything needed to reproduce a production debugging session locally.

**Why:**
Without a well-defined schema, serialization will be brittle and deserialization will fail across Python versions or environments.

**Acceptance Criteria:**
- [ ] Schema defined as Pydantic model `InvestigationSnapshot`
- [ ] Includes: investigation_id, timestamp, alert context, hypothesis list, evidence list with query results
- [ ] Includes: schema snapshot (table/column definitions at investigation time)
- [ ] Includes: lineage subgraph (upstream/downstream 2 hops)
- [ ] Includes: sample DataFrames (max 10K rows each, configurable)
- [ ] Includes: environment metadata (Python version, package versions, datasource type)
- [ ] Schema versioned (version field) for forward compatibility
- [ ] Estimated serialized size calculation method

**Key Design Notes:**
- Use `orjson` for JSON serialization (faster than stdlib)
- DataFrames serialized as Parquet bytes (preserves dtypes)
- Large objects (>10MB) stored as references, not inline
- Schema evolution: new fields optional with defaults

**Data Model:**
```python
class InvestigationSnapshot(BaseModel):
    version: str = "1.0"
    investigation_id: UUID
    captured_at: datetime
    alert: AnomalyAlert
    hypotheses: list[Hypothesis]
    evidence: list[Evidence]
    synthesis: Synthesis | None
    schema_snapshot: SchemaResponse
    lineage_snapshot: LineageGraph | None
    sample_data: dict[str, bytes]  # table_name -> parquet bytes
    environment: EnvironmentMetadata
```

**Dependencies:** None

**Risks + Mitigations:**
- Risk: Parquet incompatibility across pyarrow versions → Pin pyarrow version, test matrix
- Risk: Snapshot too large → Enforce size limits, compress, store samples as references

**Effort:** M

**OSS vs Enterprise:** OSS (schema), Enterprise (cloud storage integration)

---

### Task N1.2: Implement Snapshot Capture in Temporal Workflow

**Description:**
Modify the investigation Temporal workflow to capture and persist snapshots at key checkpoints.

**Why:**
Snapshots must be captured during live investigation while state is hot. Retrospective capture is impossible—the data may have changed.

**Acceptance Criteria:**
- [ ] Snapshot captured at: investigation start, after each hypothesis tested, on completion/failure
- [ ] Snapshots stored to configurable backend (local file, S3, GCS)
- [ ] Storage path: `{tenant_id}/snapshots/{investigation_id}/{checkpoint_name}.snapshot`
- [ ] Capture is async and non-blocking (investigation continues if capture fails)
- [ ] Capture failure logged but doesn't fail investigation
- [ ] Snapshot TTL configurable (default: 7 days)
- [ ] Cleanup job removes expired snapshots

**Key Design Notes:**
- Use Temporal activity for async upload (retryable)
- Snapshot capture should take <2s for typical investigation
- Consider streaming upload for large snapshots
- Storage abstraction: `SnapshotStore` protocol with S3/GCS/Local implementations

**API Changes:**
- Add `snapshot_config` to investigation request (enable/disable, storage backend)
- Add `GET /api/v1/investigations/{id}/snapshots` to list available snapshots

**Dependencies:** Task N1.1 (schema)

**Risks + Mitigations:**
- Risk: S3 upload latency delays investigation → Fire-and-forget with activity
- Risk: Storage costs → Aggressive TTL, compression, tenant quotas

**Effort:** L

**OSS vs Enterprise:** Enterprise (cloud storage), OSS (local file only)

---

### Task N1.3: Build Snapshot Download API

**Description:**
Create API endpoint to download investigation snapshots for local hydration.

**Why:**
The JupyterLab widget needs a way to fetch snapshots. This endpoint handles auth, access control, and streaming large snapshots.

**Acceptance Criteria:**
- [ ] `GET /api/v1/investigations/{id}/snapshots/{checkpoint}` returns snapshot
- [ ] Supports streaming response for large snapshots (>10MB)
- [ ] Supports `Accept-Encoding: gzip` for compressed transfer
- [ ] Auth required (API key or JWT)
- [ ] Tenant isolation enforced (can't access other tenant's snapshots)
- [ ] 404 if snapshot expired or doesn't exist
- [ ] Response includes `Content-Length` and `X-Snapshot-Version` headers

**Key Design Notes:**
- Use `StreamingResponse` for large payloads
- Pre-signed URLs for S3/GCS (don't proxy through API server)
- Cache snapshot metadata in Redis for fast lookup

**API Response:**
```
HTTP 200
Content-Type: application/octet-stream
Content-Length: 15728640
X-Snapshot-Version: 1.0
X-Snapshot-Checkpoint: on_complete

<binary snapshot data>
```

**Dependencies:** Task N1.2 (capture)

**Risks + Mitigations:**
- Risk: Large snapshot download times out → Use pre-signed URLs, resume support
- Risk: Auth token in URL for pre-signed → Short TTL (5 min), single use

**Effort:** M

**OSS vs Enterprise:** Enterprise

---

### Task N1.4: Implement Snapshot Deserializer in SDK

**Description:**
Add Python SDK function to deserialize a snapshot into live Python objects.

**Why:**
Raw snapshot bytes are useless. The SDK must reconstitute DataFrames, Pydantic models, and namespace-injectable objects.

**Acceptance Criteria:**
- [ ] `dataing_sdk.load_snapshot(snapshot_bytes) -> HydratedState`
- [ ] `HydratedState` contains: `.alert`, `.hypotheses`, `.evidence`, `.synthesis`
- [ ] `HydratedState.dataframes` dict of table_name → pandas DataFrame
- [ ] `HydratedState.schema` is navigable (`.schema.tables['orders'].columns`)
- [ ] `HydratedState.lineage` is queryable (`.lineage.upstream('orders')`)
- [ ] Version mismatch handled gracefully (warning, not error)
- [ ] Missing optional fields handled (lineage may be None)

**Key Design Notes:**
- Use `pydantic.model_validate` for typed deserialization
- Parquet bytes → DataFrame via `pd.read_parquet(io.BytesIO(data))`
- Consider lazy loading for large DataFrames (don't deserialize until accessed)

**SDK Interface:**
```python
from dataing_sdk import load_snapshot

state = load_snapshot(snapshot_bytes)
print(state.synthesis.root_cause)
df = state.dataframes['analytics.orders']
```

**Dependencies:** Task N1.1 (schema)

**Risks + Mitigations:**
- Risk: Pandas version mismatch corrupts DataFrame → Store dtype metadata, validate on load
- Risk: Memory exhaustion with large DataFrames → Lazy loading, warn on >100MB

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task N1.5: Build JupyterLab "Hydrate" Command

**Description:**
Add UI button and magic command to fetch and inject snapshot state into notebook kernel.

**Why:**
This is the user-facing feature. Everything else is plumbing. The user clicks "Hydrate" and their notebook populates with production state.

**Acceptance Criteria:**
- [ ] Sidebar widget shows list of recent investigations with snapshots
- [ ] "Hydrate" button next to each investigation
- [ ] Click triggers: fetch snapshot, deserialize, inject into kernel namespace
- [ ] Kernel receives variables: `alert`, `hypotheses`, `evidence`, `synthesis`, `dataframes`
- [ ] Success toast: "Hydrated investigation inv_abc123 - 5 DataFrames loaded"
- [ ] Magic command alternative: `%dataing hydrate inv_abc123`
- [ ] Handles kernel not running (prompt to start kernel)
- [ ] Handles existing variables (prompt to overwrite or namespace)

**Key Design Notes:**
- Use `IPython.get_ipython().push()` to inject variables
- Widget fetches via SDK client (uses stored auth)
- Show progress bar during download
- Consider namespacing: `dataing.alert` instead of `alert` to avoid collisions

**Widget Flow:**
```
[Sidebar: Recent Investigations]
├─ inv_abc123 (2h ago) - orders null spike [Hydrate]
├─ inv_def456 (1d ago) - revenue drop [Hydrate]
└─ inv_ghi789 (3d ago) - schema change [Expired]

User clicks [Hydrate] on inv_abc123
→ Progress: "Downloading snapshot... 45%"
→ Progress: "Deserializing... 80%"
→ Progress: "Injecting into kernel... 100%"
→ Toast: "✓ Hydrated! Variables: alert, hypotheses, evidence, synthesis, df_orders, df_customers"
```

**Dependencies:** Task N1.3 (API), Task N1.4 (deserializer), existing JupyterLab widget

**Risks + Mitigations:**
- Risk: Kernel busy during injection → Queue injection, show warning
- Risk: Variable collision → Use `dataing_` prefix or namespace dict

**Effort:** L

**OSS vs Enterprise:** Enterprise (requires snapshot storage)

---

### Task N1.6: Add Snapshot Diff Comparison

**Description:**
Allow comparing two snapshots to see what changed between investigation checkpoints.

**Why:**
Debugging sometimes requires understanding "what changed between hypothesis 1 and hypothesis 3?" Diff comparison enables this.

**Acceptance Criteria:**
- [ ] `%dataing diff inv_abc123:start inv_abc123:on_complete`
- [ ] Shows: new evidence added, hypothesis status changes, data changes
- [ ] DataFrame diff: added/removed rows, changed values (sample)
- [ ] Schema diff: added/removed columns, type changes
- [ ] Output as rich HTML table in notebook cell
- [ ] Exportable as markdown

**Key Design Notes:**
- Use `deepdiff` for structural comparison
- DataFrame diff via `pd.compare()` or custom sampling
- Limit diff output to 100 changes (expandable)

**Dependencies:** Task N1.5

**Risks + Mitigations:**
- Risk: Diff of large DataFrames is slow → Sample-based diff, not full comparison

**Effort:** M

**OSS vs Enterprise:** Enterprise

---

## Epic N2: Fix-It Button

**Goal:** After investigation identifies root cause, agent proposes a specific code/SQL fix that the user can apply with one click.

**User Value:** Closes the loop from "here's the problem" to "here's the fix." No more copy-pasting SQL from ChatGPT. The agent that investigated also remediates.

**Competitor Gap:** Every observability tool stops at diagnosis. None propose fixes. This makes Dataing an agent, not a dashboard.

**Technical Approach:**
- Agent generates fix proposal during synthesis phase
- Fix proposals are typed (SQL DDL, SQL DML, dbt patch, Python patch)
- Widget renders fix with "Apply" button
- Apply executes in transaction with rollback on failure

---

### Task N2.1: Define Fix Proposal Schema

**Description:**
Design the data model for fix proposals that the agent can generate.

**Why:**
Fixes must be typed and validated. Random SQL strings are dangerous. The schema constrains what fixes are possible and how they're applied.

**Acceptance Criteria:**
- [ ] `FixProposal` Pydantic model with: fix_type, description, code, confidence, risks
- [ ] Supported fix_types: `sql_ddl`, `sql_dml`, `dbt_patch`, `python_patch`, `manual_instruction`
- [ ] Each fix_type has validation rules (e.g., sql_ddl must be ALTER/CREATE/DROP)
- [ ] `risks` field lists potential negative effects
- [ ] `rollback` field contains undo statement if applicable
- [ ] `requires_confirmation` boolean (always True for DDL)
- [ ] `estimated_impact` describes affected rows/tables

**Data Model:**
```python
class FixProposal(BaseModel):
    fix_type: Literal["sql_ddl", "sql_dml", "dbt_patch", "python_patch", "manual_instruction"]
    description: str  # Human-readable explanation
    code: str  # The actual fix code
    confidence: float  # 0-1, how sure is the agent
    risks: list[str]  # Potential negative effects
    rollback: str | None  # Undo statement
    requires_confirmation: bool = True
    estimated_impact: str  # "Affects ~1000 rows in orders table"
    target_asset: str  # Table/model being fixed
```

**Key Design Notes:**
- `manual_instruction` is escape hatch for fixes that can't be automated
- Never auto-apply DDL (schema changes require human review)
- DML fixes should be wrapped in transactions by default

**Dependencies:** None

**Risks + Mitigations:**
- Risk: Agent generates dangerous SQL → Strict validation, require confirmation
- Risk: Fix type too limited → Include `manual_instruction` for edge cases

**Effort:** S

**OSS vs Enterprise:** OSS

---

### Task N2.2: Add Fix Generation to Synthesis Agent

**Description:**
Extend the synthesis LLM prompt to generate fix proposals when root cause is identified with high confidence.

**Why:**
The agent already knows the root cause. Generating a fix is a natural extension of its reasoning.

**Acceptance Criteria:**
- [ ] Synthesis prompt extended with fix generation instruction
- [ ] Fix only generated when confidence > 0.7
- [ ] Fix matches the root cause category (schema issue → DDL fix, data issue → DML fix)
- [ ] Prompt includes schema context for valid SQL generation
- [ ] Prompt includes examples of good vs bad fixes
- [ ] Fix validated against FixProposal schema before returning
- [ ] If validation fails, falls back to `manual_instruction`

**Prompt Addition:**
```
If confidence > 0.7, propose a fix:
- For schema issues: propose ALTER TABLE statement
- For data issues: propose UPDATE/DELETE with WHERE clause matching bad data
- For transformation issues: propose dbt model patch (SQL diff)
- Always include rollback statement
- Always explain risks
- If unsure, use manual_instruction type with clear steps
```

**Key Design Notes:**
- Use structured output (tool call) for fix proposal, not free text
- Include schema in prompt so LLM generates valid column names
- Temperature 0 for fix generation (deterministic)

**API Changes:**
- Add `fix_proposal: FixProposal | None` to `SynthesisResponse`

**Dependencies:** Task N2.1 (schema), existing synthesis agent

**Risks + Mitigations:**
- Risk: LLM generates invalid SQL → Validation + syntax check before returning
- Risk: Fix doesn't actually fix the problem → Include confidence, require user review

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task N2.3: Implement SQL Fix Validator

**Description:**
Validate that generated SQL fixes are syntactically correct and safe to execute.

**Why:**
LLMs hallucinate. We must validate fixes before showing them to users, let alone executing them.

**Acceptance Criteria:**
- [ ] Syntax validation via sqlglot parse (dialect-aware)
- [ ] Safety validation: no DROP TABLE, no TRUNCATE, no DELETE without WHERE
- [ ] Scope validation: fix only touches tables in investigation context
- [ ] Sanity check: estimated affected rows < 100K (configurable)
- [ ] For DML: dry-run with EXPLAIN to estimate impact
- [ ] Validation errors returned with specific failure reason
- [ ] Validation adds `is_validated: bool` and `validation_errors: list[str]` to proposal

**Key Design Notes:**
- Use sqlglot for parsing (supports Snowflake, BigQuery, Postgres dialects)
- Blacklist dangerous patterns: `DROP`, `TRUNCATE`, `DELETE FROM table` (no WHERE)
- Whitelist safe DDL: `ALTER TABLE ADD COLUMN`, `ALTER TABLE ADD CONSTRAINT`

**Validation Flow:**
```
Input: "DELETE FROM orders WHERE order_date < '2020-01-01'"
1. Parse with sqlglot → Valid syntax ✓
2. Check for blacklist → DELETE has WHERE clause ✓
3. Check scope → 'orders' is in investigation context ✓
4. Dry-run EXPLAIN → Estimated 5000 rows affected ✓
5. Output: is_validated=True
```

**Dependencies:** Task N2.1

**Risks + Mitigations:**
- Risk: sqlglot doesn't support all dialects → Graceful degradation, skip validation with warning
- Risk: EXPLAIN not available (permissions) → Make dry-run optional

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task N2.4: Build Fix Preview Widget

**Description:**
Render fix proposals in the JupyterLab widget with syntax highlighting, risk warnings, and action buttons.

**Why:**
Users need to review fixes before applying. A clear, well-designed preview builds trust and reduces errors.

**Acceptance Criteria:**
- [ ] Fix proposal rendered as expandable card in investigation results
- [ ] Code block with syntax highlighting (SQL, Python)
- [ ] Confidence score displayed with color coding (green >0.8, yellow 0.7-0.8)
- [ ] Risks displayed as warning callouts
- [ ] Rollback statement displayed (collapsed by default)
- [ ] "Preview Impact" button runs dry-run and shows affected rows
- [ ] "Apply Fix" button (disabled until user checks confirmation box)
- [ ] "Copy to Clipboard" button for manual execution

**Widget Mockup:**
```
┌─────────────────────────────────────────────────────────────┐
│ 💡 Proposed Fix (confidence: 0.85)                          │
├─────────────────────────────────────────────────────────────┤
│ Add NOT NULL constraint to handle upstream schema change    │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ ALTER TABLE analytics.orders                            │ │
│ │ ALTER COLUMN customer_id SET NOT NULL;                  │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ⚠️ Risks:                                                   │
│ • Will fail if existing NULL values present                 │
│ • Requires UPDATE to fix existing NULLs first              │
│                                                             │
│ 📊 Estimated Impact: 0 rows (DDL only)                     │
│                                                             │
│ [Preview Impact] [Copy] [☑ I understand the risks] [Apply] │
└─────────────────────────────────────────────────────────────┘
```

**Dependencies:** Task N2.2 (generation), existing widget

**Risks + Mitigations:**
- Risk: User clicks Apply without reading → Require checkbox confirmation
- Risk: Widget too cluttered → Collapsible sections, progressive disclosure

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task N2.5: Implement Fix Execution Engine

**Description:**
Execute approved fixes against the datasource with transaction safety and rollback capability.

**Why:**
The "Apply" button must actually work. This is the scariest part—executing user-approved SQL against production.

**Acceptance Criteria:**
- [ ] Execution wrapped in transaction (BEGIN...COMMIT/ROLLBACK)
- [ ] Pre-execution validation re-run (state may have changed)
- [ ] Execution timeout configurable (default: 30s)
- [ ] On failure: automatic rollback, error displayed in widget
- [ ] On success: confirmation with affected row count
- [ ] Execution logged to audit trail (who, when, what, result)
- [ ] Rollback button appears after successful apply (for 5 minutes)
- [ ] Execution blocked if datasource is read-only

**Execution Flow:**
```
User clicks [Apply]
1. Re-validate fix (datasource state may have changed)
2. BEGIN TRANSACTION
3. Execute fix SQL
4. If error: ROLLBACK, show error
5. If success: COMMIT, show "✓ Applied: 1523 rows updated"
6. Log to audit: {user, timestamp, fix_sql, result}
7. Enable [Rollback] button for 5 minutes
```

**Key Design Notes:**
- Use same datasource connection as investigation (already authed)
- DDL may not support transactions (Snowflake) → Warn user, require extra confirmation
- Consider "Apply to Staging First" option for enterprise

**API Changes:**
- Add `POST /api/v1/investigations/{id}/apply-fix` endpoint
- Add `POST /api/v1/investigations/{id}/rollback-fix` endpoint

**Dependencies:** Task N2.3 (validator), Task N2.4 (widget), datasource adapters

**Risks + Mitigations:**
- Risk: Fix breaks production → Transaction wrapping, require confirmation, audit log
- Risk: Long-running fix times out → Configurable timeout, async execution option

**Effort:** L

**OSS vs Enterprise:** Enterprise (production writes are scary, need audit)

---

### Task N2.6: Add Fix Proposal Feedback Loop

**Description:**
Collect user feedback on fix proposals to improve future generation.

**Why:**
Fix generation will be imperfect initially. User feedback ("this fix was wrong", "this fix worked") improves the agent over time.

**Acceptance Criteria:**
- [ ] After applying fix, prompt for feedback: "Did this fix work?" [Yes] [No] [Partially]
- [ ] If No/Partially: prompt for what went wrong (free text)
- [ ] Feedback stored with fix proposal and investigation
- [ ] Feedback exportable for fine-tuning analysis
- [ ] Dashboard shows fix success rate over time
- [ ] Low success rate triggers alert to review prompts

**Key Design Notes:**
- Don't require feedback (optional, non-blocking)
- Prompt 24h after fix applied (give time to verify)
- Aggregate feedback by fix_type, root_cause_category

**Dependencies:** Task N2.5

**Risks + Mitigations:**
- Risk: Users don't provide feedback → Make it one-click, offer incentive (usage credits?)

**Effort:** S

**OSS vs Enterprise:** Enterprise (analytics)

---

## Epic N3: Trace-to-Test Codify

**Goal:** Generate a regression test from a solved investigation that can be added to CI/CD to prevent recurrence.

**User Value:** Every bug fixed becomes a permanent test. Institutional knowledge compounds. The platform gets stickier and the data gets safer over time.

**Competitor Gap:** GX has tests but you write them manually. Soda has checks but no auto-generation. Nobody turns investigations into tests.

**Technical Approach:**
- Investigation synthesis includes test-relevant assertions
- "Codify" action generates test in user's preferred format (GX, dbt, Soda, SQL)
- Test is scoped to the specific failure mode discovered
- User can customize and export to their test framework

---

### Task N3.1: Design Test Template Schema

**Description:**
Define the abstract representation of a data quality test that can be rendered to multiple formats.

**Why:**
Users have different test frameworks (GX, dbt tests, Soda, raw SQL). We need an intermediate representation that renders to all of them.

**Acceptance Criteria:**
- [ ] `DataQualityTest` model captures: assertion, scope, threshold, description
- [ ] Assertion types: not_null, unique, accepted_values, in_range, row_count_change, custom_sql
- [ ] Scope: table, column, or custom SQL expression
- [ ] Threshold: exact value, percentage, or range
- [ ] Model is framework-agnostic (no GX/dbt-specific fields)
- [ ] Includes `source_investigation_id` for traceability
- [ ] Includes `failure_description` from original incident

**Data Model:**
```python
class DataQualityTest(BaseModel):
    test_id: str
    name: str  # Human-readable name
    description: str  # What this test catches
    assertion_type: AssertionType
    table: str
    column: str | None  # None for table-level tests
    parameters: dict[str, Any]  # Threshold, accepted values, etc.
    sql_expression: str | None  # For custom_sql type
    severity: Literal["warn", "fail"]
    source_investigation_id: UUID
    failure_description: str  # Original incident summary

class AssertionType(str, Enum):
    NOT_NULL = "not_null"
    UNIQUE = "unique"
    ACCEPTED_VALUES = "accepted_values"
    IN_RANGE = "in_range"
    ROW_COUNT_CHANGE = "row_count_change"
    FRESHNESS = "freshness"
    CUSTOM_SQL = "custom_sql"
```

**Dependencies:** None

**Risks + Mitigations:**
- Risk: Test types too limited → Include custom_sql as escape hatch

**Effort:** S

**OSS vs Enterprise:** OSS

---

### Task N3.2: Build Test Extraction from Synthesis

**Description:**
Extract testable assertions from investigation synthesis automatically.

**Why:**
The investigation already identified what went wrong. That knowledge should translate directly into a test assertion.

**Acceptance Criteria:**
- [ ] Given a `SynthesisResponse`, extract relevant `DataQualityTest` objects
- [ ] Root cause "null values introduced" → `NOT_NULL` test on column
- [ ] Root cause "unexpected values" → `ACCEPTED_VALUES` or `IN_RANGE` test
- [ ] Root cause "row count dropped" → `ROW_COUNT_CHANGE` test
- [ ] Root cause "stale data" → `FRESHNESS` test
- [ ] Complex root causes → `CUSTOM_SQL` test with explanation query
- [ ] Multiple tests possible per synthesis (return list)
- [ ] Confidence threshold: only generate test if synthesis confidence > 0.6

**Extraction Logic:**
```python
def extract_tests(synthesis: SynthesisResponse) -> list[DataQualityTest]:
    tests = []

    # Map root cause categories to test types
    if "null" in synthesis.root_cause.lower():
        tests.append(DataQualityTest(
            assertion_type=AssertionType.NOT_NULL,
            column=synthesis.affected_column,
            ...
        ))

    if "unexpected value" in synthesis.root_cause.lower():
        # Extract expected values from evidence
        tests.append(DataQualityTest(
            assertion_type=AssertionType.ACCEPTED_VALUES,
            parameters={"values": extract_accepted_values(synthesis.evidence)},
            ...
        ))

    return tests
```

**Key Design Notes:**
- Use rule-based extraction initially (not LLM)
- LLM can be added later for complex cases
- Err on side of generating tests (false positives are better than missing tests)

**Dependencies:** Task N3.1 (schema), existing synthesis

**Risks + Mitigations:**
- Risk: Extraction misses root cause type → Add custom_sql fallback, log for review

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task N3.3: Implement Test Renderers (GX, dbt, Soda, SQL)

**Description:**
Render abstract `DataQualityTest` to concrete test code for each supported framework.

**Why:**
Users won't change frameworks for us. We must output tests in their existing format.

**Acceptance Criteria:**
- [ ] `GXRenderer` outputs Great Expectations expectation suite JSON
- [ ] `DbtRenderer` outputs dbt schema.yml test definition
- [ ] `SodaRenderer` outputs SodaCL check YAML
- [ ] `SQLRenderer` outputs raw SQL assertion query (returns 0 rows if pass)
- [ ] Each renderer handles all assertion types
- [ ] Each renderer includes comments with investigation context
- [ ] Renderer selection via `--format` flag

**Renderer Outputs:**

**GX (Great Expectations):**
```json
{
  "expectation_type": "expect_column_values_to_not_be_null",
  "kwargs": {
    "column": "customer_id"
  },
  "meta": {
    "generated_by": "dataing",
    "investigation_id": "inv_abc123",
    "notes": "Null spike detected on 2026-01-27"
  }
}
```

**dbt:**
```yaml
# Generated by Dataing from investigation inv_abc123
# Null spike detected on 2026-01-27
models:
  - name: orders
    columns:
      - name: customer_id
        tests:
          - not_null:
              severity: error
```

**Soda:**
```yaml
# Generated by Dataing from investigation inv_abc123
checks for orders:
  - missing_count(customer_id) = 0:
      name: customer_id not null (from inv_abc123)
```

**SQL:**
```sql
-- Generated by Dataing from investigation inv_abc123
-- Null spike detected on 2026-01-27
-- This query should return 0 rows if data is healthy
SELECT COUNT(*) as null_count
FROM analytics.orders
WHERE customer_id IS NULL;
-- EXPECTED: 0
```

**Key Design Notes:**
- Use Jinja2 templates for each renderer
- Include comments with provenance (investigation_id, date, description)
- GX renderer should output both JSON and Python code options

**Dependencies:** Task N3.1 (schema)

**Risks + Mitigations:**
- Risk: Framework version changes break output → Pin to stable versions, test against latest

**Effort:** L

**OSS vs Enterprise:** OSS

---

### Task N3.4: Build "Codify" Widget Button

**Description:**
Add "Codify Test" button to investigation results that generates and displays the test code.

**Why:**
The user journey: investigate → see root cause → click "Codify" → copy test to project.

**Acceptance Criteria:**
- [ ] "Codify Test" button appears on completed investigations with high confidence
- [ ] Click opens modal with format selector (GX, dbt, Soda, SQL)
- [ ] Selected format renders test code with syntax highlighting
- [ ] "Copy to Clipboard" button for easy export
- [ ] "Download" button saves as file (expectations.json, schema.yml, etc.)
- [ ] "Add to Project" button (if project integration configured)
- [ ] Show all extracted tests if multiple

**Widget Mockup:**
```
┌─────────────────────────────────────────────────────────────┐
│ 🧪 Codify as Regression Test                               │
├─────────────────────────────────────────────────────────────┤
│ Format: [dbt ▼]  [GX]  [Soda]  [SQL]                       │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ # Generated by Dataing from investigation inv_abc123    │ │
│ │ models:                                                 │ │
│ │   - name: orders                                        │ │
│ │     columns:                                            │ │
│ │       - name: customer_id                               │ │
│ │         tests:                                          │ │
│ │           - not_null                                    │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ [Copy to Clipboard]  [Download schema.yml]  [Add to dbt]   │
└─────────────────────────────────────────────────────────────┘
```

**Dependencies:** Task N3.2 (extraction), Task N3.3 (renderers), existing widget

**Risks + Mitigations:**
- Risk: User doesn't know which format → Auto-detect from project files if possible

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task N3.5: Add CLI Test Generation Command

**Description:**
Expose test generation via CLI for automation and CI/CD integration.

**Why:**
Not everyone uses notebooks. CLI enables scripted workflows: investigate → codify → commit.

**Acceptance Criteria:**
- [ ] `dataing codify <investigation_id> --format=dbt` outputs test to stdout
- [ ] `--output=path/to/file` writes to file
- [ ] `--format` supports: gx, dbt, soda, sql
- [ ] `--append` adds to existing file (dbt schema.yml) instead of overwriting
- [ ] `--all-investigations` codifies all completed investigations (batch)
- [ ] Exit code 0 if tests generated, 1 if no testable assertions found

**CLI Usage:**
```bash
# Generate dbt test and append to existing schema.yml
$ dataing codify inv_abc123 --format=dbt --append --output=models/schema.yml
✓ Added 1 test to models/schema.yml

# Generate GX expectation suite
$ dataing codify inv_abc123 --format=gx --output=expectations/orders_suite.json
✓ Wrote expectation suite to expectations/orders_suite.json

# Pipe SQL test to stdout
$ dataing codify inv_abc123 --format=sql
-- Generated by Dataing...
SELECT COUNT(*) as null_count...
```

**Dependencies:** Task N3.3 (renderers)

**Risks + Mitigations:**
- Risk: Append corrupts existing file → Parse existing, merge, validate before write

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task N3.6: Track Test Adoption and Effectiveness

**Description:**
Track which generated tests are adopted and whether they catch future issues.

**Why:**
This proves ROI: "Dataing-generated tests have caught 47 issues that would have reached production."

**Acceptance Criteria:**
- [ ] When test generated, log to analytics (test_id, format, investigation_id)
- [ ] Optional: if user runs tests with Dataing integration, track pass/fail
- [ ] Dashboard: "Tests generated", "Tests adopted" (detected in project), "Issues caught"
- [ ] Alert when generated test catches a failure (celebration moment!)
- [ ] Metric: "Test effectiveness rate" (failures caught / tests generated)

**Key Design Notes:**
- "Tests adopted" requires project integration or user confirmation
- "Issues caught" requires test run integration (GX, dbt test results)
- Start with manual confirmation, add automation later

**Dependencies:** Task N3.5

**Risks + Mitigations:**
- Risk: Can't track adoption without integration → Manual confirmation button as fallback

**Effort:** M

**OSS vs Enterprise:** Enterprise (analytics)

---

# Part 2: CLI Features

---

## Epic C1: `dataing blame`

**Goal:** Provide "git blame for data"—show the history of changes affecting a table/column, linking to PRs, authors, and correlated anomalies.

**User Value:** When paged at 3am, run one command to see what changed, who changed it, and when. Instant context for debugging.

**Competitor Gap:** Nobody connects data state to code history in a single CLI command. This is the purest expression of "causal debugging."

---

### Task C1.1: Design Blame Output Schema

**Description:**
Define the data model for blame output that connects code changes to data impact.

**Why:**
Blame output must be structured for both human reading and machine parsing (JSON output for scripting).

**Acceptance Criteria:**
- [ ] `BlameResult` model with: target (table/column), timeline of changes
- [ ] Each `BlameEntry` has: timestamp, change_type, description, commit, pr, author, anomaly_correlation
- [ ] Change types: schema_change, transformation_change, config_change, data_load
- [ ] PR reference includes: number, title, URL
- [ ] Author includes: name, email, handle
- [ ] Anomaly correlation: list of anomalies within ±24h of change
- [ ] Supports both table-level and column-level blame

**Data Model:**
```python
class BlameEntry(BaseModel):
    timestamp: datetime
    change_type: ChangeType
    description: str  # Human-readable summary
    commit_sha: str | None
    commit_message: str | None
    pr_number: int | None
    pr_title: str | None
    pr_url: str | None
    author_name: str | None
    author_email: str | None
    author_handle: str | None  # @username
    correlated_anomalies: list[AnomalyReference]
    file_path: str | None  # Path to changed file
    diff_summary: str | None  # "+15 -3 in models/orders.sql"

class BlameResult(BaseModel):
    target: str  # "analytics.orders" or "analytics.orders.customer_id"
    target_type: Literal["table", "column"]
    entries: list[BlameEntry]
    time_range: tuple[datetime, datetime]
    total_changes: int
```

**Dependencies:** None

**Risks + Mitigations:**
- Risk: Git data not available → Graceful degradation, show data-only changes

**Effort:** S

**OSS vs Enterprise:** OSS

---

### Task C1.2: Implement Change Detection from Git History

**Description:**
Scan git history to find commits that affected a specific table or column.

**Why:**
Git history is the source of truth for code changes. We need to filter it to changes relevant to a specific data asset.

**Acceptance Criteria:**
- [ ] Given table name, find all commits touching files that define/transform that table
- [ ] Uses dataset-to-repo mapping to know which files to scan
- [ ] For dbt: scan model SQL file + any refs to the model
- [ ] For general SQL: scan files containing table name in CREATE, ALTER, INSERT, UPDATE
- [ ] Column-level: additionally filter to commits mentioning column name
- [ ] Time range filter (default: last 90 days)
- [ ] Limit filter (default: 20 most recent)
- [ ] Returns structured commit data, not raw git output

**Implementation Approach:**
```python
def get_blame_commits(table: str, column: str | None, repo_path: str) -> list[CommitInfo]:
    # 1. Get files related to table from dataset-repo-mapping
    related_files = get_related_files(table)

    # 2. Get commits touching those files
    commits = git_log(paths=related_files, since="90 days ago")

    # 3. If column specified, filter to commits with column name in diff
    if column:
        commits = [c for c in commits if column in get_diff(c)]

    # 4. Enrich with PR info (GitHub API)
    commits = enrich_with_pr_info(commits)

    return commits
```

**Key Design Notes:**
- Use dulwich or GitPython for git operations
- Cache PR info (GitHub API rate limits)
- Consider pre-built index for large repos

**Dependencies:** Task C1.1, existing git integration (Task 1.1.1 from main roadmap)

**Risks + Mitigations:**
- Risk: Table name appears in many files (false positives) → Use AST parsing for precision
- Risk: Column name is common word → Require column to appear in relevant context (ALTER, SELECT, etc.)

**Effort:** L

**OSS vs Enterprise:** OSS (local git), Enterprise (GitHub API for PR info)

---

### Task C1.3: Correlate Changes with Anomaly History

**Description:**
For each code change, find anomalies that occurred shortly after.

**Why:**
The killer insight is "this commit caused this anomaly." Correlation is the first step to causation.

**Acceptance Criteria:**
- [ ] For each commit, query anomaly history within ±24h window
- [ ] Match anomalies by table (and column if column-level blame)
- [ ] Correlation strength: anomaly within 1h = "strong", 1-6h = "medium", 6-24h = "weak"
- [ ] Multiple anomalies can correlate with single commit
- [ ] Single anomaly can correlate with multiple commits (show all)
- [ ] Correlation displayed in blame output with strength indicator

**Correlation Logic:**
```python
def correlate_anomalies(commit: CommitInfo, table: str) -> list[AnomalyCorrelation]:
    # Get anomalies for this table within ±24h of commit
    anomalies = get_anomalies(
        table=table,
        after=commit.timestamp - timedelta(hours=24),
        before=commit.timestamp + timedelta(hours=24)
    )

    correlations = []
    for anomaly in anomalies:
        delta = abs(anomaly.detected_at - commit.timestamp)
        strength = "strong" if delta < timedelta(hours=1) else \
                   "medium" if delta < timedelta(hours=6) else "weak"
        correlations.append(AnomalyCorrelation(anomaly=anomaly, strength=strength))

    return correlations
```

**Dependencies:** Task C1.2, anomaly history storage

**Risks + Mitigations:**
- Risk: No anomaly history available → Show changes only, note "no anomaly data"

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task C1.4: Build CLI Command and Output Formatting

**Description:**
Implement the `dataing blame` CLI command with rich terminal output.

**Why:**
This is the user-facing feature. Output must be scannable, informative, and shareable.

**Acceptance Criteria:**
- [ ] `dataing blame <table>` shows table-level blame
- [ ] `dataing blame <table>.<column>` shows column-level blame
- [ ] `--since=<date>` filters to changes after date
- [ ] `--limit=N` limits to N most recent changes
- [ ] `--json` outputs structured JSON
- [ ] Default output: rich table with colors and emoji
- [ ] Anomaly correlations highlighted (🔴 for strong, 🟡 for medium)
- [ ] PR links are clickable in supported terminals

**CLI Output:**
```
$ dataing blame analytics.orders.customer_id

📜 Blame: analytics.orders.customer_id
   Last 90 days • 4 changes found

┌────────────┬─────────────────────────────────────┬─────────────┬──────────────────────┐
│ Date       │ Change                              │ Author      │ Anomaly Correlation  │
├────────────┼─────────────────────────────────────┼─────────────┼──────────────────────┤
│ 2026-01-27 │ Column made nullable                │ @jane.doe   │ 🔴 null_rate spike   │
│            │ PR #456: Add customer_id from API   │             │    (2h after)        │
├────────────┼─────────────────────────────────────┼─────────────┼──────────────────────┤
│ 2026-01-15 │ Added COALESCE wrapper              │ @bob.smith  │ None                 │
│            │ PR #412: Handle null customer_id    │             │                      │
├────────────┼─────────────────────────────────────┼─────────────┼──────────────────────┤
│ 2025-12-01 │ Column created                      │ @jane.doe   │ None                 │
│            │ PR #389: Initial orders model       │             │                      │
└────────────┴─────────────────────────────────────┴─────────────┴──────────────────────┘

💡 Most likely cause of recent issues: PR #456 by @jane.doe (2026-01-27)
```

**Key Design Notes:**
- Use Rich for table formatting
- Truncate long descriptions with ellipsis
- Support piping (no colors if not TTY)

**Dependencies:** Task C1.2, Task C1.3

**Risks + Mitigations:**
- Risk: Output too wide for terminal → Responsive layout, collapse columns on narrow terminals

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task C1.5: Add Deep-Dive Mode

**Description:**
Allow drilling into a specific change to see full diff, related files, and investigation link.

**Why:**
The blame table is a summary. Sometimes you need the full story.

**Acceptance Criteria:**
- [ ] `dataing blame <table> --expand=<commit_sha>` shows detailed view
- [ ] Detail includes: full commit message, complete diff, all files changed
- [ ] If anomaly correlated: link to investigation (if exists)
- [ ] "Investigate this change" suggestion if no investigation exists
- [ ] Interactive mode: up/down to select change, Enter to expand

**Expanded View:**
```
$ dataing blame analytics.orders --expand=abc123f

📜 Commit abc123f by Jane Doe <jane@acme.com>
   2026-01-27 14:32:05 UTC

   Add customer_id from new API source

   This PR adds customer_id to the orders model by joining
   with the new raw_customers table from the API integration.

   PR #456: https://github.com/acme/dbt-models/pull/456

📁 Files Changed:
   models/staging/stg_orders.sql (+15, -3)
   models/marts/orders.sql (+2, -0)

📝 Diff (stg_orders.sql):
   @@ -12,7 +12,19 @@
    SELECT
        order_id,
   -    NULL as customer_id,  -- TODO: add when available
   +    raw_customers.customer_id,
        order_date,
   ...

🔴 Correlated Anomaly:
   null_rate spike on customer_id (2026-01-27 16:45)
   Investigation: inv_abc123 [View]
```

**Dependencies:** Task C1.4

**Risks + Mitigations:**
- Risk: Large diffs flood terminal → Paginate, or truncate with "see full diff" link

**Effort:** M

**OSS vs Enterprise:** OSS

---

## Epic C2: `dataing sniff`

**Goal:** Pre-merge impact analysis—before merging a dbt/SQL change, predict what downstream data will break.

**User Value:** Shift-left data quality. Catch problems before they reach production. CI/CD integration makes Dataing un-churnable.

**Competitor Gap:** Datafold does "data diff" but not anomaly prediction. Monte Carlo's "Circuit Breaker" is post-merge. Nobody predicts anomalies pre-merge.

---

### Task C2.1: Design Impact Prediction Model

**Description:**
Define what "impact" means and how we predict it from code changes.

**Why:**
Impact prediction requires understanding the relationship between code changes and data outcomes. We need a clear model.

**Acceptance Criteria:**
- [ ] `ImpactPrediction` model with: affected_tables, predicted_anomalies, confidence, risks
- [ ] Affected tables derived from lineage (downstream of changed model)
- [ ] Predicted anomalies based on change type (schema change → potential null/type issues)
- [ ] Confidence based on: change magnitude, historical patterns, test coverage
- [ ] Risks categorized: schema_break, data_quality, performance, freshness

**Data Model:**
```python
class ImpactPrediction(BaseModel):
    changed_files: list[str]
    changed_models: list[str]  # dbt model names
    affected_downstream: list[AffectedTable]
    predicted_anomalies: list[PredictedAnomaly]
    overall_risk: Literal["low", "medium", "high", "critical"]
    confidence: float
    recommendations: list[str]

class AffectedTable(BaseModel):
    table: str
    distance: int  # Hops from changed model
    impact_type: Literal["schema", "data", "freshness"]

class PredictedAnomaly(BaseModel):
    table: str
    column: str | None
    anomaly_type: str  # null_rate, row_count, etc.
    likelihood: float
    reasoning: str
```

**Dependencies:** None

**Risks + Mitigations:**
- Risk: Predictions inaccurate → Calibrate with historical data, show confidence

**Effort:** S

**OSS vs Enterprise:** OSS

---

### Task C2.2: Implement Change Parser (dbt/SQL)

**Description:**
Parse code changes to understand what's being modified (tables, columns, transformations).

**Why:**
To predict impact, we must understand the change. A column rename is different from a join change.

**Acceptance Criteria:**
- [ ] Parse dbt model files to extract: refs, sources, columns selected, transformations
- [ ] Detect change types: schema change (new column, type change), logic change (WHERE, JOIN), config change
- [ ] Parse git diff to identify exact changes (not just "file changed")
- [ ] Support SQL files (non-dbt) with basic parsing
- [ ] Output structured `ChangeAnalysis` with: change_type, affected_columns, added/removed/modified

**Change Types to Detect:**
```python
class ChangeType(Enum):
    COLUMN_ADDED = "column_added"
    COLUMN_REMOVED = "column_removed"
    COLUMN_RENAMED = "column_renamed"
    COLUMN_TYPE_CHANGED = "column_type_changed"
    JOIN_ADDED = "join_added"
    JOIN_REMOVED = "join_removed"
    JOIN_TYPE_CHANGED = "join_type_changed"  # INNER → LEFT
    FILTER_ADDED = "filter_added"
    FILTER_REMOVED = "filter_removed"
    FILTER_MODIFIED = "filter_modified"
    AGGREGATION_CHANGED = "aggregation_changed"
    SOURCE_CHANGED = "source_changed"
```

**Key Design Notes:**
- Use sqlglot for SQL parsing
- For dbt, parse both SQL and YAML (schema.yml for column definitions)
- Git diff provides before/after, parse both and compare

**Dependencies:** Task C2.1

**Risks + Mitigations:**
- Risk: sqlglot doesn't parse all SQL dialects → Graceful degradation, treat as "unknown change"

**Effort:** L

**OSS vs Enterprise:** OSS

---

### Task C2.3: Build Downstream Impact Analyzer

**Description:**
Given changed models, trace lineage to find all downstream tables that could be affected.

**Why:**
A change to `stg_orders` affects `orders`, `revenue`, `customer_orders`, etc. We need the full blast radius.

**Acceptance Criteria:**
- [ ] Use lineage graph to find all downstream tables
- [ ] Depth configurable (default: 3 hops)
- [ ] For each downstream table, determine impact type (schema propagation, data change, etc.)
- [ ] Weight by distance (immediate children higher risk than grandchildren)
- [ ] Include column-level impact where lineage supports it
- [ ] Output: list of `AffectedTable` with distance and impact type

**Impact Flow:**
```
Changed: stg_orders (added nullable customer_id)
         ↓
  orders (inherits nullable customer_id) [distance: 1, impact: schema]
         ↓
  revenue (joins with orders.customer_id) [distance: 2, impact: data]
  customer_orders (filters on customer_id) [distance: 2, impact: data]
```

**Dependencies:** Task C2.2, existing lineage API

**Risks + Mitigations:**
- Risk: Lineage incomplete → Warn user, suggest manual review

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task C2.4: Implement Anomaly Predictor

**Description:**
Predict which anomalies are likely to occur based on change type and historical patterns.

**Why:**
The goal isn't just "this table is affected" but "this specific anomaly is likely."

**Acceptance Criteria:**
- [ ] Map change types to likely anomalies:
  - `COLUMN_ADDED nullable` → `null_rate` increase likely
  - `JOIN_TYPE_CHANGED inner→left` → `null_rate` increase likely
  - `FILTER_REMOVED` → `row_count` increase likely
  - `COLUMN_REMOVED` → downstream `schema_break` certain
- [ ] Check historical patterns: "Last time X changed, Y anomaly occurred"
- [ ] Assign likelihood score (0-1) based on change type + history
- [ ] Generate human-readable reasoning

**Prediction Logic:**
```python
def predict_anomalies(change: ChangeAnalysis, affected: list[AffectedTable]) -> list[PredictedAnomaly]:
    predictions = []

    # Rule-based predictions
    if change.type == ChangeType.JOIN_TYPE_CHANGED and "LEFT" in change.new_value:
        predictions.append(PredictedAnomaly(
            table=affected[0].table,
            column=change.join_column,
            anomaly_type="null_rate",
            likelihood=0.8,
            reasoning="LEFT JOIN can introduce NULLs for non-matching rows"
        ))

    # Historical pattern matching
    similar_changes = get_similar_historical_changes(change)
    for hist in similar_changes:
        if hist.caused_anomaly:
            predictions.append(PredictedAnomaly(
                anomaly_type=hist.anomaly_type,
                likelihood=0.6,
                reasoning=f"Similar change on {hist.date} caused {hist.anomaly_type}"
            ))

    return predictions
```

**Dependencies:** Task C2.2, Task C2.3, anomaly history

**Risks + Mitigations:**
- Risk: Predictions wrong (false positives/negatives) → Show confidence, track accuracy over time

**Effort:** L

**OSS vs Enterprise:** OSS

---

### Task C2.5: Build CLI Command with CI/CD Output

**Description:**
Implement `dataing sniff` with outputs suitable for CI/CD integration.

**Why:**
CI/CD integration is the strategic goal. Output must support GitHub Actions, GitLab CI, etc.

**Acceptance Criteria:**
- [ ] `dataing sniff` (in git repo) analyzes uncommitted changes
- [ ] `dataing sniff --ref=HEAD~1..HEAD` analyzes specific commit range
- [ ] `dataing sniff --pr=123` fetches PR diff from GitHub and analyzes
- [ ] Output includes: risk level, affected tables, predicted anomalies, recommendations
- [ ] `--exit-code` mode: exit 0 if low risk, exit 1 if high/critical
- [ ] `--format=github` outputs GitHub Actions annotation format
- [ ] `--format=gitlab` outputs GitLab CI report format
- [ ] `--format=json` outputs structured JSON for custom integration

**CLI Output (Human):**
```
$ dataing sniff

🔍 Analyzing changes in PR #456...

📁 Changed Models:
   • stg_orders.sql (+15, -3)

🎯 Downstream Impact (5 tables):
   ├─ orders (direct) - SCHEMA CHANGE
   ├─ revenue (2 hops) - DATA CHANGE
   ├─ customer_orders (2 hops) - DATA CHANGE
   ├─ daily_revenue (3 hops) - DATA CHANGE
   └─ customer_ltv (3 hops) - DATA CHANGE

⚠️ Predicted Anomalies:
   ┌────────────────┬───────────────┬────────────┬────────────────────────────────┐
   │ Table          │ Anomaly       │ Likelihood │ Reasoning                      │
   ├────────────────┼───────────────┼────────────┼────────────────────────────────┤
   │ orders         │ null_rate     │ 80%        │ New nullable column added      │
   │ revenue        │ revenue_drop  │ 40%        │ JOIN may exclude some orders   │
   └────────────────┴───────────────┴────────────┴────────────────────────────────┘

📊 Overall Risk: MEDIUM (confidence: 0.75)

💡 Recommendations:
   1. Add NOT NULL constraint or COALESCE for customer_id
   2. Add test for null_rate on orders.customer_id
   3. Monitor revenue for 24h after deploy

Exit code: 1 (medium+ risk detected)
```

**GitHub Actions Format:**
```
::warning file=models/staging/stg_orders.sql,line=15::Nullable column may cause null_rate increase in orders
::warning file=models/staging/stg_orders.sql::Downstream impact: 5 tables affected
```

**Dependencies:** Task C2.4

**Risks + Mitigations:**
- Risk: CI run too slow → Cache lineage, parallelize parsing

**Effort:** L

**OSS vs Enterprise:** OSS

---

### Task C2.6: Create GitHub Action Wrapper

**Description:**
Publish a GitHub Action that wraps `dataing sniff` for easy CI integration.

**Why:**
Lower the barrier to CI/CD adoption. `uses: dataing/sniff-action@v1` is easier than custom scripting.

**Acceptance Criteria:**
- [ ] GitHub Action published to marketplace
- [ ] Inputs: dataing API key, risk threshold, output format
- [ ] Outputs: risk level, affected tables count, predictions JSON
- [ ] Posts PR comment with impact summary
- [ ] Sets check status (pass/fail based on risk threshold)
- [ ] Example workflow in documentation

**Action Usage:**
```yaml
name: Data Impact Check
on: pull_request

jobs:
  sniff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: dataing/sniff-action@v1
        with:
          api-key: ${{ secrets.DATAING_API_KEY }}
          risk-threshold: medium  # fail on medium+
          comment: true  # post PR comment
```

**Dependencies:** Task C2.5

**Risks + Mitigations:**
- Risk: Action maintenance burden → Keep thin, most logic in CLI

**Effort:** M

**OSS vs Enterprise:** OSS

---

## Epic C3: `dataing mock`

**Goal:** Spin up a local data environment that mirrors production schema with realistic sample data for development and testing.

**User Value:** Dev/prod parity without copying production data. Engineers can develop locally with confidence.

**Competitor Gap:** Existing tools (dbt seed, Datafold) provide static fixtures. We provide production-like data with anomaly patterns included.

---

### Task C3.1: Design Mock Environment Specification

**Description:**
Define what a "mock environment" contains and how it's configured.

**Why:**
Users need control over what's mocked: which tables, how much data, what patterns to include.

**Acceptance Criteria:**
- [ ] `MockSpec` model with: tables to include, row counts, sampling strategy, output format
- [ ] Sampling strategies: random, stratified (by key columns), recent (last N days), anomaly-biased
- [ ] Output formats: DuckDB file, SQLite file, Parquet files, PostgreSQL (docker)
- [ ] Include schema (DDL) and sample data
- [ ] Option to include recent anomaly patterns (data that caused issues)
- [ ] Configurable via CLI flags or `dataing-mock.yml` file

**Data Model:**
```python
class MockSpec(BaseModel):
    tables: list[TableMockSpec]
    output_format: Literal["duckdb", "sqlite", "parquet", "postgres"]
    output_path: str
    include_anomaly_patterns: bool = True
    random_seed: int | None = None  # For reproducibility

class TableMockSpec(BaseModel):
    table: str
    row_count: int = 1000
    sampling_strategy: SamplingStrategy = "stratified"
    stratify_columns: list[str] | None = None
    include_edge_cases: bool = True
    date_range: tuple[date, date] | None = None
```

**Dependencies:** None

**Risks + Mitigations:**
- Risk: Spec too complex → Sensible defaults, simple CLI for common case

**Effort:** S

**OSS vs Enterprise:** OSS

---

### Task C3.2: Implement Schema Cloner

**Description:**
Clone table schemas from production datasource to local environment.

**Why:**
Mock data must match production schema exactly—same column names, types, constraints.

**Acceptance Criteria:**
- [ ] Fetch schema from production datasource via existing adapter
- [ ] Convert to target format (DuckDB DDL, SQLite DDL, etc.)
- [ ] Handle type mapping between databases (Snowflake VARIANT → JSON, etc.)
- [ ] Preserve constraints where possible (NOT NULL, PRIMARY KEY)
- [ ] Handle views (clone as tables with schema)
- [ ] Output DDL script or execute directly

**Schema Conversion Example:**
```
Snowflake: CREATE TABLE orders (
    order_id NUMBER(38,0),
    customer_id VARCHAR(100),
    order_date TIMESTAMP_NTZ,
    amount NUMBER(18,2),
    metadata VARIANT
)

→ DuckDB: CREATE TABLE orders (
    order_id BIGINT,
    customer_id VARCHAR(100),
    order_date TIMESTAMP,
    amount DECIMAL(18,2),
    metadata JSON
)
```

**Key Design Notes:**
- Use sqlglot for dialect translation
- Maintain type mapping table for each source → target pair
- Foreign keys optional (may not exist in prod)

**Dependencies:** Task C3.1, existing datasource adapters

**Risks + Mitigations:**
- Risk: Type mapping lossy → Document limitations, allow manual overrides

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task C3.3: Build Stratified Sampler

**Description:**
Sample production data while preserving distribution of key columns.

**Why:**
Random sampling may miss important segments. Stratified sampling ensures representative data.

**Acceptance Criteria:**
- [ ] Given table and stratify columns, sample preserving distribution
- [ ] Example: 1000 rows from orders, stratified by customer_segment → same % in each segment
- [ ] Auto-detect stratify columns if not specified (categorical columns with <100 values)
- [ ] Handle skewed distributions (ensure minimum representation of rare values)
- [ ] Handle date columns (sample recent + some historical)
- [ ] Include edge cases: NULLs, min/max values, boundary conditions

**Sampling Algorithm:**
```python
def stratified_sample(table: str, columns: list[str], n: int) -> pd.DataFrame:
    # 1. Get value distribution for each stratify column
    distributions = get_distributions(table, columns)

    # 2. Calculate samples per stratum
    strata = calculate_strata(distributions, n)

    # 3. Sample from each stratum
    samples = []
    for stratum, count in strata.items():
        samples.append(sample_stratum(table, stratum, count))

    # 4. Add edge cases (NULLs, extremes)
    samples.append(sample_edge_cases(table, n // 10))

    return pd.concat(samples)
```

**Key Design Notes:**
- Use SQL for sampling (don't load full table into memory)
- For large tables, use approximate sampling (TABLESAMPLE)
- Respect user's date_range if specified

**Dependencies:** Task C3.2

**Risks + Mitigations:**
- Risk: Slow on large tables → Use TABLESAMPLE, limit stratify columns

**Effort:** L

**OSS vs Enterprise:** OSS

---

### Task C3.4: Add Anomaly Pattern Injection

**Description:**
Include data patterns from recent anomalies so developers can test failure handling.

**Why:**
Mocked data should include the problems that actually occur. This lets developers debug and test against realistic failure modes.

**Acceptance Criteria:**
- [ ] For each table, fetch recent anomalies from history
- [ ] Sample rows that triggered anomalies (NULL values, out-of-range, etc.)
- [ ] Inject anomaly-causing rows into mock data (flagged as anomalies)
- [ ] Document which rows are anomaly patterns in metadata
- [ ] Option to disable (some users want clean data)

**Anomaly Injection:**
```
Recent anomaly: null_rate spike in orders.customer_id on 2026-01-27

Injection:
- Sample 50 rows where customer_id IS NULL (from that date)
- Add to mock data
- Flag in metadata: "anomaly_pattern: null_rate, source_date: 2026-01-27"
```

**Key Design Notes:**
- Don't inject too many anomalies (10% max of mock data)
- Anomaly patterns help test: monitoring, data validation, error handling

**Dependencies:** Task C3.3, anomaly history

**Risks + Mitigations:**
- Risk: PII in anomaly rows → Apply same anonymization as general sampling

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task C3.5: Implement Output Writers

**Description:**
Write mock data to various output formats (DuckDB, SQLite, Parquet, etc.).

**Why:**
Different developers prefer different local environments. We support the common ones.

**Acceptance Criteria:**
- [ ] DuckDB writer: single .duckdb file, tables created with sampled data
- [ ] SQLite writer: single .sqlite file, same structure
- [ ] Parquet writer: directory with one .parquet per table
- [ ] PostgreSQL writer: Docker Compose + SQL script to populate
- [ ] All writers include metadata table with mock generation info
- [ ] All writers are atomic (temp file → rename)

**Output Structure:**
```
# DuckDB
mock_env.duckdb
├── orders (1000 rows)
├── customers (500 rows)
├── _dataing_metadata (generation info)

# Parquet
mock_env/
├── orders.parquet
├── customers.parquet
├── _metadata.json

# PostgreSQL
mock_env/
├── docker-compose.yml
├── init.sql
└── README.md
```

**Dependencies:** Task C3.4

**Risks + Mitigations:**
- Risk: Large output files → Compression option, warn on >1GB

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task C3.6: Build CLI Command

**Description:**
Implement `dataing mock` with intuitive defaults and powerful overrides.

**Why:**
The command should work out of the box for common cases but allow customization.

**Acceptance Criteria:**
- [ ] `dataing mock <table>` mocks single table with defaults
- [ ] `dataing mock --all` mocks all tables in default datasource
- [ ] `dataing mock --config=dataing-mock.yml` uses config file
- [ ] `--rows=N` sets default row count
- [ ] `--format=duckdb|sqlite|parquet|postgres` selects output
- [ ] `--output=<path>` sets output location
- [ ] `--no-anomalies` disables anomaly pattern injection
- [ ] Progress bar shows sampling progress
- [ ] Summary shows tables mocked, total rows, output location

**CLI Usage:**
```
$ dataing mock orders customers --rows=5000 --format=duckdb --output=local_dev.duckdb

🎭 Dataing Mock Environment Generator

📋 Tables to mock:
   • orders (5000 rows, stratified by: order_date, customer_segment)
   • customers (5000 rows, stratified by: country, customer_type)

⚙️ Options:
   • Format: DuckDB
   • Anomaly patterns: included
   • Output: local_dev.duckdb

[Cloning schemas...] ████████████████████ 100%
[Sampling orders...] ████████████████████ 100%
[Sampling customers...] ████████████████████ 100%
[Injecting anomaly patterns...] ████████████████████ 100%
[Writing DuckDB file...] ████████████████████ 100%

✓ Mock environment created: local_dev.duckdb
  • 2 tables
  • 10,000 total rows
  • 127 anomaly pattern rows included

💡 Usage:
   import duckdb
   conn = duckdb.connect('local_dev.duckdb')
   df = conn.execute('SELECT * FROM orders').df()
```

**Dependencies:** Task C3.5

**Risks + Mitigations:**
- Risk: User mocks huge table by accident → Warn if estimated >100K rows

**Effort:** M

**OSS vs Enterprise:** OSS

---

### Task C3.7: Add Config File Support

**Description:**
Support `dataing-mock.yml` configuration file for complex mock environments.

**Why:**
Repeatable mock generation for team sharing. Commit config to repo.

**Acceptance Criteria:**
- [ ] `dataing-mock.yml` in repo root auto-detected
- [ ] Config specifies tables, row counts, sampling strategies
- [ ] Config supports table relationships (mock customers before orders)
- [ ] Config versioned and shareable via git
- [ ] `dataing mock init` generates template config
- [ ] Config validated on load with helpful errors

**Config Format:**
```yaml
# dataing-mock.yml
version: 1
output:
  format: duckdb
  path: local_dev.duckdb

tables:
  - name: customers
    rows: 1000
    stratify_by: [country, customer_type]

  - name: orders
    rows: 5000
    stratify_by: [order_date, customer_segment]
    date_range: [2025-01-01, 2026-01-31]
    include_anomalies: true

  - name: order_items
    rows: 15000
    # Auto-sample to match orders foreign keys

settings:
  include_anomaly_patterns: true
  random_seed: 42  # Reproducibility
```

**Dependencies:** Task C3.6

**Risks + Mitigations:**
- Risk: Config format changes break existing configs → Version field, migration support

**Effort:** M

**OSS vs Enterprise:** OSS

---

# Summary: Implementation Sequence

## Phase 1: Quick Wins (Weeks 1-4)

| Task | Feature | Effort | Impact |
|------|---------|--------|--------|
| C1.1-C1.4 | `dataing blame` MVP | L | High (viral) |
| C3.1-C3.2 | `dataing mock` schema cloning | M | Medium |
| N2.1-N2.2 | Fix-It proposal generation | M | High (differentiation) |

## Phase 2: Core Functionality (Weeks 5-8)

| Task | Feature | Effort | Impact |
|------|---------|--------|--------|
| C3.3-C3.6 | `dataing mock` full implementation | L | High (DX) |
| C2.1-C2.5 | `dataing sniff` impact analysis | L | High (CI/CD lock-in) |
| N2.3-N2.5 | Fix-It validation + execution | L | High (differentiation) |

## Phase 3: Advanced Features (Weeks 9-12)

| Task | Feature | Effort | Impact |
|------|---------|--------|--------|
| N1.1-N1.5 | Ghost State Hydrator | L | High (unique) |
| N3.1-N3.5 | Trace-to-Test Codify | L | High (moat) |
| C2.6 | GitHub Action for sniff | M | Medium (adoption) |

## Phase 4: Polish & Analytics (Weeks 13-16)

| Task | Feature | Effort | Impact |
|------|---------|--------|--------|
| C1.5 | blame deep-dive mode | M | Medium |
| N1.6 | Snapshot diff comparison | M | Medium |
| N2.6, N3.6 | Feedback loops + tracking | M | Medium (long-term) |
| C3.7 | Mock config file support | M | Medium |

---

*Total estimated effort: ~16 weeks for solo founder. Prioritize blame → mock → sniff for CLI virality, then Fix-It → Codify for notebook differentiation. Ghost Hydrator is high-effort/high-reward—schedule for when you have momentum.*
