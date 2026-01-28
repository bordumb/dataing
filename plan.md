# Dataing Strategic Roadmap
## CTO/VP Product Execution Plan — F500 Enterprise Focus

**Document Version:** 1.0
**Date:** January 2026
**Author:** CTO/VP Product

---

## 1. Positioning Statement

> **Dataing is the autonomous data debugging agent that understands why your data broke—not just that it broke.**

While Monte Carlo watches for anomalies and Great Expectations validates schemas, Dataing is the first platform that autonomously investigates root causes by connecting code changes, pipeline mutations, and data drift into causal explanations. We don't generate alerts; we generate answers.

**One-liner for developers:**
*"It's like having a senior data engineer who never sleeps, already knows your lineage, and writes the post-mortem before you finish your coffee."*

---

## 2. Competitive Gap Analysis

### 2.1 Comparison Table

| Capability | Dataing | Monte Carlo | Great Expectations | Soda |
|------------|---------|-------------|-------------------|------|
| **Autonomous Investigation** | ✅ Full (hypothesis→evidence→synthesis) | ⚠️ Partial (agents recommend, don't execute) | ❌ None | ❌ None |
| **Root Cause Analysis** | ✅ Causal chain with confidence scores | ⚠️ ML correlation + lineage hints | ❌ None (validation only) | ❌ None |
| **Native Lineage** | ✅ Column-level, OpenLineage | ✅ Column-level, SQL parsing | ❌ None (integration only) | ❌ None |
| **CLI-First Experience** | ✅ Full investigation from terminal | ⚠️ Limited (mostly UI) | ⚠️ Basic (init/run) | ✅ Good (soda scan) |
| **Notebook Integration** | ✅ IPython magics, streaming | ❌ None native | ⚠️ SDK only | ⚠️ SDK only |
| **Open Source Core** | ✅ Investigation engine, CLI, SDK | ❌ Minimal (examples) | ✅ Full validation engine | ✅ Soda Core |
| **Self-Host Option** | ✅ Full (Temporal + API) | ❌ SaaS only | ✅ OSS engine | ⚠️ Core only |
| **Evidence Chain/Audit** | ✅ Hash-linked, reproducible | ⚠️ Logs only | ❌ No audit trail | ❌ No audit trail |
| **Pricing Transparency** | ✅ Clear tiers, no surprises | ❌ Opaque credits | ❌ Sales required | ⚠️ Partially visible |
| **AI Check Generation** | 🔜 Planned | ✅ ML monitors | ✅ ExpectAI (Cloud) | ✅ SodaGPT |
| **Alert Fatigue Solution** | ✅ Investigations reduce noise | ⚠️ Grouping helps | ❌ Basic alerts | ⚠️ Anomaly detection |

### 2.2 Wedge + Moat Narrative

**The Wedge: CLI + Notebook for Autonomous Debugging**

Every competitor has a UI-first approach. Monte Carlo's value prop requires navigating dashboards. GX requires Python boilerplate and YAML configs. Soda needs SodaCL syntax learning.

Our wedge is radical simplicity for the 90% use case:

```bash
dataing run start analytics.orders --goal "Why did nulls spike 40% yesterday?"
```

That's it. The agent investigates, builds evidence, links to code changes, and outputs an explanation. No dashboard required.

**The Moat: Causal Investigation Engine**

1. **Hypothesis generation** that learns from your domain
2. **Evidence chains** that are hash-linked and reproducible
3. **Lineage integration** that traces symptoms to root causes
4. **Feedback loop** that improves with every investigation

Monte Carlo's agents recommend; ours explain. GX validates; we diagnose. Soda tests; we investigate.

---

## 3. Open-Core Packaging Plan

### 3.1 What is OSS vs Enterprise

| Component | License | Rationale |
|-----------|---------|-----------|
| **Investigation Engine** | MIT | Core value prop must be open to build trust and adoption |
| **CLI (dataing-cli)** | MIT | Distribution channel—needs to be frictionless |
| **Python SDK (dataing-sdk)** | MIT | Developer adoption requires open SDK |
| **Notebook Extension** | MIT | Community adoption, competitive with GX |
| **Agent Prompts** | MIT | Transparency builds trust in AI systems |
| **Temporal Workers** | MIT | Self-host requires these |
| **API Server (core routes)** | MIT | Enables self-host deployments |
| --- | --- | --- |
| **SSO/SAML/OIDC** | Enterprise | Standard enterprise gate |
| **RBAC + Audit Logs** | Enterprise | Compliance requirement at F500 |
| **Multi-Workspace** | Enterprise | Team isolation, common upsell |
| **Priority Queues** | Enterprise | SLA guarantees for paid customers |
| **Advanced Connectors** (Oracle, SAP, Teradata) | Enterprise | Low volume, high ACV customers |
| **Scheduled Investigations** | Enterprise | Automation at scale |
| **Custom Agent Training** | Enterprise | Per-customer model tuning |
| **SLA + Support** | Enterprise | Standard commercial offering |

### 3.2 Boundary Rationale

**Distribution:** CLI, SDK, and investigation engine must be MIT. An engineer should be able to `pip install dataing-cli && dataing run start` in under 5 minutes with no sign-up. This is how we beat GX's friction and Soda's Cloud-gate.

**Monetization:** Enterprise features follow the "team scale" principle. Individual developers get full power for free. When organizations need coordination (SSO, RBAC, multi-workspace), they pay.

**Security:** Audit logs and compliance features are enterprise-gated because they require infrastructure investment and are table-stakes for procurement.

---

## 4. Roadmap

### Phase 0: Foundation (Weeks 0–6)
*Goal: Ship the CLI + Notebook golden path that demonstrates autonomous investigation*

### Phase 1: Distribution (Weeks 6–12)
*Goal: OSS release, PyPI distribution, community building*

### Phase 2: Enterprise (Months 3–6)
*Goal: Land first F500 design partners with enterprise features*

---

## Phase 0: Foundation (Weeks 0–6)

### Epic 0.1: CLI Investigation Golden Path
**Goal:** A developer can run a complete autonomous investigation from the terminal with streaming output.
**User Value:** Debug data issues without leaving the terminal or opening a browser.
**Competitor Weakness:** Monte Carlo requires UI navigation; GX has no investigation; Soda has no root cause analysis.

---

#### Task 0.1.1: CLI `run start` with Streaming Timeline

**Title:** Implement streaming investigation output in CLI

**Description:**
The `dataing run start` command should stream investigation progress to stdout with a rich timeline display. Each hypothesis, query, and evidence item should render progressively. The final synthesis should display with confidence scores and causal chain.

**Why:** This is the demo moment. A developer types one command and watches an AI investigate their data issue in real-time. This is our primary differentiation.

**Acceptance Criteria:**
- [ ] `dataing run start <dataset> --goal "<question>"` initiates investigation
- [ ] SSE events render progressively with timestamps
- [ ] Hypothesis generation shows numbered hypotheses with categories
- [ ] Query execution shows SQL with syntax highlighting
- [ ] Evidence shows support/refute with confidence
- [ ] Final synthesis shows root cause, confidence, and recommendations
- [ ] `--json` flag outputs machine-parseable NDJSON
- [ ] `--no-stream` flag waits and outputs final result only
- [ ] Exit code 0 on completed investigation, non-zero on failure

**Key Design Notes:**
- Use Rich library for terminal rendering (already in codebase)
- SSE parsing uses existing `display.py` infrastructure
- Timeline should show elapsed time per step
- Color coding: hypothesis=blue, query=yellow, evidence=green/red, synthesis=cyan

**Key APIs:**
- `POST /api/v1/investigations` (exists)
- `GET /api/v1/investigations/{id}/stream` (exists)
- No new endpoints needed

**Dependencies:**
- Existing CLI infrastructure (dataing-cli)
- Existing SSE streaming (investigations router)

**Risks + Mitigations:**
- Risk: Long investigations timeout → Mitigation: Show heartbeat indicator
- Risk: Terminal width issues → Mitigation: Responsive layout with word wrap

**Effort:** M (3-5 days)

**Designation:** OSS

---

#### Task 0.1.2: CLI `run export` for Investigation Bundles

**Title:** Export investigation as reproducible markdown bundle

**Description:**
After an investigation completes, `dataing run export <run_id>` should generate a self-contained markdown report with all evidence, queries, and findings. This bundle should be suitable for sharing in PRs, Slack, or incident post-mortems.

**Why:** Investigations are only valuable if they can be shared. A markdown export enables integration with existing workflows (GitHub issues, Confluence, Notion).

**Acceptance Criteria:**
- [ ] `dataing run export <run_id>` generates markdown to stdout
- [ ] `--output <file>` writes to file
- [ ] `--format json` outputs structured JSON
- [ ] Report includes: summary, hypotheses tested, queries run, evidence collected, root cause, recommendations
- [ ] All SQL queries are included as fenced code blocks
- [ ] Evidence links to specific rows/samples
- [ ] Metadata includes: investigation ID, dataset, goal, duration, confidence
- [ ] Hash of evidence chain included for audit

**Key Design Notes:**
- Template-based generation using existing `markdown.py` utilities
- Include lineage visualization as ASCII art for terminal compatibility
- JSON format should match Investigation API response schema

**Key APIs:**
- `GET /api/v1/investigations/{id}` (exists)
- No new endpoints

**Dependencies:**
- Task 0.1.1 (need completed investigations to export)

**Risks + Mitigations:**
- Risk: Large investigations produce huge reports → Mitigation: Truncate samples, link to full data

**Effort:** S (2-3 days)

**Designation:** OSS

---

#### Task 0.1.3: CLI `ask` Interactive Mode

**Title:** Implement conversational investigation interface

**Description:**
`dataing ask` enters an interactive REPL where users can have a conversation with an ongoing investigation. They can ask follow-up questions, request deeper analysis on specific hypotheses, or pivot the investigation direction.

**Why:** Autonomous is great, but data engineers often have context the agent lacks. Interactive mode lets them steer without breaking flow.

**Acceptance Criteria:**
- [ ] `dataing ask` with no args enters interactive mode on current context
- [ ] `dataing ask "<question>"` on attached context sends one-shot question
- [ ] Interactive mode shows prompt with current context indicator
- [ ] Follow-up questions sent via `POST /api/v1/investigations/{id}/messages`
- [ ] Agent responses stream to terminal
- [ ] `/lineage` command shows current lineage graph
- [ ] `/hypotheses` shows hypotheses and their status
- [ ] `/evidence` shows collected evidence
- [ ] `/export` runs export without leaving interactive mode
- [ ] Ctrl+C gracefully exits with state preserved
- [ ] History persisted in `~/.dataing/history`

**Key Design Notes:**
- Use `prompt_toolkit` for readline-style editing
- Context indicator shows: dataset, goal, hypothesis count, evidence count
- Tab completion for commands and dataset names

**Key APIs:**
- `POST /api/v1/investigations/{id}/messages` (exists)
- `GET /api/v1/investigations/{id}` for state refresh

**Dependencies:**
- Task 0.1.1 (streaming infrastructure)
- Existing message signal handling in Temporal workflow

**Risks + Mitigations:**
- Risk: User sends conflicting instructions → Mitigation: Agent explains conflicts, asks for clarification
- Risk: Long-running investigations lose context → Mitigation: Periodic state summaries

**Effort:** M (4-5 days)

**Designation:** OSS

---

#### Task 0.1.4: CLI Context Management (`attach`, `detach`)

**Title:** Implement dataset context attachment for CLI sessions

**Description:**
The CLI should maintain a "current context" (attached dataset) that persists across commands within a session. This enables workflows like: attach to orders table → ask questions → see lineage → export results.

**Why:** Without context, every command requires repeating dataset identifiers. Context management makes the CLI feel like a proper development environment.

**Acceptance Criteria:**
- [ ] `dataing ds attach <dataset_id>` sets current context
- [ ] `dataing ds attach <urn>` resolves URN to dataset
- [ ] `dataing ds attach --sql "SELECT..." --datasource <id>` attaches from SQL
- [ ] `dataing ds detach` clears context
- [ ] `dataing ds current` shows current context with details
- [ ] Context persists in `~/.dataing/context.json`
- [ ] All investigation commands use current context if no explicit target
- [ ] Context includes: dataset_id, datasource_id, URN, schema snapshot
- [ ] `--no-context` flag on any command ignores saved context

**Key Design Notes:**
- Context file is JSON with schema version for forward compatibility (see Appendix A, Q7)
- Persistent file `~/.dataing/context.json` + in-memory overlay for session state
- URN resolution uses `GET /api/v1/asset-instances/search`
- SQL attachment creates virtual context with inferred schema

**Key APIs:**
- `GET /api/v1/asset-instances/search` (exists)
- `GET /api/v1/datasources/{id}/schema` (exists)

**Dependencies:**
- None (can be built independently)

**Risks + Mitigations:**
- Risk: Stale context after schema changes → Mitigation: Warn if schema changed since attachment

**Effort:** S (2-3 days)

**Designation:** OSS

---

### Epic 0.2: Notebook Investigation Experience
**Goal:** A data scientist can run investigations directly in Jupyter with rich output.
**User Value:** Stay in the notebook environment for debugging—no context switching.
**Competitor Weakness:** Monte Carlo has no notebook story; GX is validation-only; Soda is testing-only.

---

#### Task 0.2.1: Enhanced `%dataing ask` with Rich Output

**Title:** Upgrade notebook ask command with streaming rich widgets

**Description:**
The existing `%dataing ask` magic should be enhanced with proper Jupyter widgets for streaming output. Hypotheses, queries, and evidence should render as interactive collapsible sections. The final synthesis should display with formatting.

**Why:** Notebooks are the natural home for data scientists. Rich output makes investigations feel native to the Jupyter experience.

**Acceptance Criteria:**
- [ ] `%dataing ask "<question>"` streams investigation to output
- [ ] Each hypothesis renders as collapsible accordion widget
- [ ] SQL queries render with syntax highlighting (pygments)
- [ ] Query results show as pandas DataFrames (truncated)
- [ ] Evidence sections show support/refute badges
- [ ] Final synthesis renders as styled HTML box
- [ ] Confidence displayed as progress bar
- [ ] Timeline visualization shows investigation flow
- [ ] Output is reproducible—re-running cell shows cached result
- [ ] `%%dataing ask` cell magic for multi-line questions

**Key Design Notes:**
- Use `ipywidgets` for interactive elements
- Fallback to plain text for non-widget environments (VS Code, etc.)
- Cache investigation results in notebook metadata for reproducibility
- See Appendix A, Q9 for replay permission handling

**Key APIs:**
- Existing investigation APIs
- SSE stream handling

**Dependencies:**
- Existing notebook magic infrastructure

**Risks + Mitigations:**
- Risk: Widget rendering varies across Jupyter environments → Mitigation: Feature detection, graceful fallback
- Risk: Large DataFrames crash output → Mitigation: Always truncate, show row count

**Effort:** M (4-5 days)

**Designation:** OSS

---

#### Task 0.2.2: Notebook Lineage Visualization

**Title:** Interactive lineage graph in notebook cells

**Description:**
`%dataing lineage` should render an interactive lineage graph showing upstream and downstream dependencies of the current context. Clicking nodes should show dataset details. The graph should support pan/zoom.

**Why:** Understanding data flow is essential for debugging. An interactive graph in the notebook keeps engineers in their environment.

**Acceptance Criteria:**
- [ ] `%dataing lineage` renders graph for current context
- [ ] `%dataing lineage <dataset>` renders graph for specific dataset
- [ ] `--depth <n>` controls traversal depth (default 2)
- [ ] `--direction upstream|downstream|both` controls direction
- [ ] Nodes show dataset name, type (table/view), and data source
- [ ] Edges show job names and last run time
- [ ] Clicking node shows panel with: schema, metrics, recent investigations
- [ ] Jobs (transformations) shown as diamond nodes
- [ ] Pan/zoom/reset controls
- [ ] Export to PNG/SVG
- [ ] Fallback to ASCII art when widgets unavailable

**Key Design Notes:**
- Use `ipycytoscape` for graph rendering (see Appendix A, Q2)
- Layout algorithm: dagre for hierarchy
- Color coding: tables=blue, views=green, current=highlighted

**Key APIs:**
- `GET /api/v1/lineage/graph` (exists)
- `GET /api/v1/lineage/job/{id}` (exists)

**Dependencies:**
- Task 0.1.4 (context management)

**Risks + Mitigations:**
- Risk: Large lineage graphs unreadable → Mitigation: Collapse distant nodes, expand on click
- Risk: Different notebook environments → Mitigation: Multiple backends (pyvis, graphviz, ASCII)

**Effort:** M (4-5 days)

**Designation:** OSS

---

#### Task 0.2.3: Investigation History and Replay

**Title:** Investigation history browser in notebook

**Description:**
`%dataing history` should show past investigations with the ability to load and replay them. This enables comparing investigations over time and building institutional knowledge.

**Why:** Investigations are valuable artifacts. Being able to browse and replay them turns debugging sessions into reusable knowledge.

**Acceptance Criteria:**
- [ ] `%dataing history` shows list of recent investigations
- [ ] Each entry shows: dataset, goal, status, duration, root cause summary
- [ ] `%dataing history --dataset <id>` filters to specific dataset
- [ ] `%dataing history --days <n>` filters by recency
- [ ] Clicking entry loads investigation details
- [ ] `%dataing replay <investigation_id>` loads investigation into context
- [ ] Replayed investigation shows all evidence and synthesis
- [ ] Compare mode: `%dataing compare <id1> <id2>` shows diff
- [ ] Pagination for large history

**Key Design Notes:**
- Use existing `GET /api/v1/investigations` endpoint
- History widget as selectable list
- Compare mode highlights different hypotheses and findings

**Key APIs:**
- `GET /api/v1/investigations` (exists)
- `GET /api/v1/investigations/{id}` (exists)

**Dependencies:**
- Task 0.2.1 (rich output infrastructure)

**Risks + Mitigations:**
- Risk: Large history slows load → Mitigation: Pagination, lazy loading

**Effort:** S (3 days)

**Designation:** OSS

---

### Epic 0.3: Code-to-Data Causality
**Goal:** Link data anomalies to specific code changes that caused them.
**User Value:** Stop guessing which deploy broke the data—see the commit.
**Competitor Weakness:** Monte Carlo shows lineage but not code; GX/Soda have no code integration.

---

#### Task 0.3.1: Git Integration for Pipeline Change Detection

**Title:** Ingest git history for pipeline code changes

**Description:**
Create a git integration that tracks changes to pipeline code (dbt models, Airflow DAGs, Spark jobs). When investigating anomalies, the agent should correlate timing with code deploys.

**Why:** Most data issues are caused by code changes. Without git integration, engineers manually check "what deployed recently?"—we automate this.

**Acceptance Criteria:**
- [ ] `dataing git connect <repo_url>` links a git repository
- [ ] Support for GitHub, GitLab, Bitbucket via OAuth
- [ ] Periodic sync pulls commit history (configurable interval)
- [ ] Changes to configurable paths tracked (e.g., `models/`, `dags/`)
- [ ] Each commit stored with: hash, author, message, changed files, timestamp
- [ ] File changes parsed to extract: table names, column changes, logic changes
- [ ] Agent can query: "What code changed affecting table X in last 7 days?"
- [ ] Investigation prompt includes relevant code changes in context
- [ ] Support for monorepo path filtering

**Key Design Notes:**
- Use `pygit2` or shell out to `git` for parsing
- Store in new `code_changes` table: id, repo_id, commit_hash, timestamp, affected_assets (JSONB)
- Asset matching: parse SQL/dbt to extract table references

**Key API / Data Model Changes:**
```sql
CREATE TABLE git_repositories (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    provider TEXT NOT NULL,  -- github, gitlab, bitbucket
    access_token_encrypted TEXT,
    tracked_paths TEXT[],
    last_sync_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE code_changes (
    id UUID PRIMARY KEY,
    repo_id UUID REFERENCES git_repositories(id),
    commit_hash TEXT NOT NULL,
    author_name TEXT,
    author_email TEXT,
    message TEXT,
    committed_at TIMESTAMPTZ,
    affected_assets JSONB,  -- [{dataset_id, change_type, diff_summary}]
    raw_diff TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_code_changes_asset ON code_changes
    USING GIN (affected_assets);
CREATE INDEX idx_code_changes_time ON code_changes (committed_at);
```

New endpoints:
- `POST /api/v1/git/repositories` - connect repo
- `GET /api/v1/git/repositories` - list repos
- `POST /api/v1/git/repositories/{id}/sync` - trigger sync
- `GET /api/v1/git/changes` - query changes by asset/time

**Dependencies:**
- None (new subsystem)

**Risks + Mitigations:**
- Risk: Large repos slow to sync → Mitigation: Incremental sync, shallow clone
- Risk: OAuth token expiry → Mitigation: Refresh token handling, sync failure alerts
- Risk: Parsing SQL from arbitrary code → Mitigation: Start with dbt (structured), expand later

**Effort:** L (7-10 days)

**Designation:** OSS (basic git sync with OAuth providers), Enterprise (scheduled/automatic sync only)

**Note:** See Appendix A, Q4 - entire git integration is OSS except scheduled sync features.

---

#### Task 0.3.2: Agent Code Context Injection

**Title:** Include relevant code changes in agent prompts

**Description:**
When generating hypotheses, the agent should have access to recent code changes affecting the investigated asset. The hypothesis prompt should include a "Recent Changes" section with commit summaries.

**Why:** An agent investigating "why did nulls spike?" needs to know "yesterday's deploy added a LEFT JOIN that produces nulls for unmatched rows."

**Acceptance Criteria:**
- [ ] Hypothesis generation prompt includes code changes section
- [ ] Changes filtered to: last 14 days, affecting investigated asset or upstream
- [ ] Each change shows: commit hash, author, message, affected files, diff summary
- [ ] Maximum 5 most relevant changes included (sorted by recency × relevance)
- [ ] Agent can generate hypothesis category "code_change" with commit reference
- [ ] Evidence can link to specific commit: "Commit abc123 introduced LEFT JOIN"
- [ ] Final synthesis includes "Related Code Changes" section if relevant

**Key Design Notes:**
- Relevance scoring: exact asset match > upstream asset > path pattern match
- Diff summary: use LLM to summarize large diffs (separate prompt)
- Store commit reference in hypothesis metadata for linking

**Key APIs:**
- New internal function: `get_relevant_code_changes(asset_id, lookback_days)`
- Modify hypothesis prompt builder

**Dependencies:**
- Task 0.3.1 (git integration)

**Risks + Mitigations:**
- Risk: Too many changes overwhelm context → Mitigation: Strict relevance filtering, summarization
- Risk: False correlation (unrelated changes) → Mitigation: Agent trained to evaluate causality

**Effort:** M (4-5 days)

**Designation:** OSS

---

#### Task 0.3.3: PR/Commit Link in Investigation Output

**Title:** Deep link to source code in investigation results

**Description:**
When an investigation identifies a code change as the root cause, the output should include a direct link to the PR or commit in GitHub/GitLab/Bitbucket.

**Why:** "The root cause was commit abc123" is good. A clickable link to the PR with context is better.

**Acceptance Criteria:**
- [ ] Investigation synthesis includes links to relevant commits
- [ ] Links formatted for web (https://github.com/...) and CLI (commit hash + URL)
- [ ] PR link preferred over commit link when available
- [ ] Link appears in: CLI output, notebook output, markdown export, API response
- [ ] Metadata includes: PR number, PR title, PR author, merge date
- [ ] Support for GitHub, GitLab, Bitbucket URL formats

**Key Design Notes:**
- Store PR metadata during git sync (requires GitHub API calls)
- URL templates per provider

**Key APIs:**
- Extend `code_changes` table with `pr_number`, `pr_url`, `pr_title`
- Modify investigation response schema

**Dependencies:**
- Task 0.3.1, 0.3.2

**Risks + Mitigations:**
- Risk: PR lookup adds latency → Mitigation: Async enrichment during sync

**Effort:** S (2 days)

**Designation:** OSS

---

### Epic 0.4: Evidence Integrity and Reproducibility
**Goal:** Every investigation produces a tamper-evident, reproducible audit trail.
**User Value:** Satisfy compliance requirements; reproduce investigations months later.
**Competitor Weakness:** No competitor has verifiable evidence chains.

---

#### Task 0.4.1: Evidence Hash Chain

**Title:** Implement hash-linked evidence for tamper detection

**Description:**
Each piece of evidence in an investigation should be hash-linked to the previous, creating a chain that detects tampering. This enables audit trails for compliance.

**Why:** F500 companies need to prove their data quality processes are sound. A hash chain provides cryptographic evidence of investigation integrity.

**Acceptance Criteria:**
- [ ] Each evidence item has `content_hash` (SHA-256 of content)
- [ ] Each evidence item has `prev_hash` (hash of previous item)
- [ ] First item has `prev_hash` = null
- [ ] Investigation has `root_hash` (hash of final item)
- [ ] `dataing verify <investigation_id>` validates chain integrity
- [ ] Broken chain detected and reported with specific item
- [ ] Chain includes: hypotheses, queries, results, synthesis
- [ ] Export includes chain metadata for external verification

**Key Design Notes:**
- Already partially implemented (see `EvidenceResponse` schema)
- Need to enforce chain building in Temporal workflow
- Verification is pure function (no DB needed once evidence exported)

**Key APIs:**
- `GET /api/v1/investigations/{id}/evidence` (exists, ensure chain fields populated)
- `GET /api/v1/investigations/{id}/verify` (new)

**Dependencies:**
- None (enhances existing evidence system)

**Risks + Mitigations:**
- Risk: Performance impact of hashing → Mitigation: Async hashing, minimal overhead

**Effort:** S (2-3 days)

**Designation:** OSS

---

#### Task 0.4.2: Investigation Snapshot Export

**Title:** Export complete investigation state for offline replay

**Description:**
`dataing run snapshot <investigation_id>` exports everything needed to replay an investigation: queries, results, lineage, code changes, and agent prompts. This enables debugging the agent itself and regulatory compliance.

**Why:** When a regulator asks "how did you determine this data issue?" you can provide a complete, verifiable snapshot.

**Acceptance Criteria:**
- [ ] Snapshot is a single compressed archive (.tar.gz)
- [ ] Contains: investigation metadata, all evidence, all queries, all results, lineage snapshot, code changes snapshot, agent prompts used
- [ ] Results stored as Parquet for space efficiency
- [ ] Snapshot can be loaded into any Dataing instance for replay
- [ ] `dataing run import <snapshot.tar.gz>` loads snapshot
- [ ] Imported investigation marked as "replay" with original timestamp
- [ ] Snapshot includes schema version for forward compatibility
- [ ] Maximum snapshot size configurable (default 100MB)

**Key Design Notes:**
- Archive structure:
  ```
  snapshot-<id>/
    metadata.json
    evidence/
      001-hypothesis.json
      002-query.json
      003-results.parquet
      ...
    lineage.json
    code_changes.json
    prompts/
      hypothesis.txt
      query.txt
      synthesis.txt
  ```
- Use streaming compression for large results

**Key APIs:**
- `GET /api/v1/investigations/{id}/snapshot` (new)
- `POST /api/v1/investigations/import` (new)

**Dependencies:**
- Task 0.4.1 (evidence chain)

**Risks + Mitigations:**
- Risk: Large result sets blow up snapshot → Mitigation: Truncation with hash of full results
- Risk: Schema changes break imports → Mitigation: Version field, migration on import

**Effort:** M (4-5 days)

**Designation:** OSS (export + same-tenant import), Enterprise (cross-tenant import, bulk import)

**Note:** See Appendix A, Q5 - OSS gets reproducibility, Enterprise gets organizational features.

---

## Phase 1: Distribution (Weeks 6–12)

### Epic 1.1: PyPI and OSS Release
**Goal:** Anyone can `pip install dataing` and run investigations.
**User Value:** Zero-friction adoption; evaluate without sales call.
**Competitor Weakness:** Monte Carlo requires sales; GX has steep learning curve.

---

#### Task 1.1.1: PyPI Package Publishing

**Title:** Publish dataing packages to PyPI

**Description:**
Publish `dataing-cli`, `dataing-sdk`, and `dataing-notebook` to PyPI with proper metadata, versioning, and dependency management.

**Why:** PyPI is how Python developers discover and install tools. Not being on PyPI is not being discoverable.

**Acceptance Criteria:**
- [ ] `pip install dataing-cli` works
- [ ] `pip install dataing-sdk` works
- [ ] `pip install dataing-notebook` works
- [ ] `pip install dataing[all]` installs all packages
- [ ] Version follows semver (start at 0.1.0)
- [ ] Changelog maintained in CHANGELOG.md
- [ ] README renders correctly on PyPI
- [ ] Dependencies pinned to ranges (not exact)
- [ ] Python 3.10+ support declared
- [ ] CI/CD publishes on tag push

**Key Design Notes:**
- Use `hatch` for modern packaging (see Appendix A, Q1)
- Monorepo structure with separate pyproject.toml per package
- GitHub Actions for release automation

**Dependencies:**
- Stable API (Phase 0 complete)

**Risks + Mitigations:**
- Risk: Name squatting → Mitigation: Already have `dataing` (check PyPI)
- Risk: Dependency conflicts → Mitigation: Minimal deps, wide version ranges

**Effort:** M (3-4 days)

**Designation:** OSS

---

#### Task 1.1.2: Docker Compose Self-Host Bundle

**Title:** One-command self-hosted deployment

**Description:**
Create a Docker Compose configuration that spins up the complete Dataing stack (API, Temporal, workers, database) for local or self-hosted deployment.

**Why:** Developers want to try before they buy. Self-host is table stakes for enterprise data tools.

**Acceptance Criteria:**
- [ ] `docker compose up` starts full stack
- [ ] Includes: API server, Temporal server, Temporal workers, PostgreSQL, Redis
- [ ] Default configuration works out of box
- [ ] Environment variables for customization documented
- [ ] Health checks on all services
- [ ] Persistent volumes for data
- [ ] `docker compose down -v` cleanly removes everything
- [ ] Works on: Linux, macOS (Intel + Apple Silicon), Windows (WSL2)
- [ ] Startup time < 60 seconds on warm cache
- [ ] README with quick start guide

**Key Design Notes:**
- Use official Temporal Docker images
- Multi-stage builds for small images
- Development mode vs production mode configs

**Dependencies:**
- Task 1.1.1 (packages for workers)

**Risks + Mitigations:**
- Risk: Resource requirements too high → Mitigation: Document minimums (4GB RAM, 2 CPU)
- Risk: Port conflicts → Mitigation: Configurable ports, conflict detection

**Effort:** M (4-5 days)

**Designation:** OSS

---

#### Task 1.1.3: Quickstart Documentation

**Title:** 5-minute quickstart guide

**Description:**
Create documentation that gets a developer from zero to first investigation in under 5 minutes. Include video walkthrough.

**Why:** Documentation is the product. Bad docs = no adoption.

**Acceptance Criteria:**
- [ ] Quickstart takes < 5 minutes to complete
- [ ] Steps: install CLI → connect demo datasource → run investigation
- [ ] Demo datasource with pre-seeded anomalies
- [ ] Copy-pasteable commands with expected output
- [ ] Video walkthrough embedded (< 3 min)
- [ ] Troubleshooting section for common issues
- [ ] "What's next" section with links to deeper docs
- [ ] Works on macOS, Linux, Windows
- [ ] No sign-up required for demo mode

**Key Design Notes:**
- Use MkDocs with Material theme (matches existing)
- Demo datasource: Leverage existing `./demo` infrastructure with DuckDB + parquet fixtures (see Appendix A, Q10)
- Package quickstart bundle: baseline + null_spike + volume_drop scenarios (~3MB)
- Reuse existing `load_duckdb.sql` and manifest.json format
- Host demo API at demo.dataing.io for zero-setup option

**Dependencies:**
- Task 1.1.1 (PyPI packages)
- Task 1.1.2 (Docker for self-host path)

**Risks + Mitigations:**
- Risk: Demo API overwhelmed → Mitigation: Rate limiting, ephemeral instances
- Risk: Outdated docs → Mitigation: CI tests that run quickstart

**Effort:** M (4-5 days)

**Designation:** OSS

---

### Epic 1.2: Alerting Integration Layer
**Goal:** Dataing receives alerts from existing tools and auto-investigates.
**User Value:** Keep existing monitoring; add intelligent investigation layer.
**Competitor Weakness:** Competitors are alert sources, not investigation destinations.

---

#### Task 1.2.1: Webhook Alert Ingestion

**Title:** Generic webhook endpoint for alert ingestion

**Description:**
Create a webhook endpoint that accepts alerts from any source (Monte Carlo, dbt, Airflow, custom) and auto-triggers investigations.

**Why:** Enterprises already have alerting. We don't replace it—we enhance it by investigating what the alerts mean.

**Acceptance Criteria:**
- [ ] `POST /api/v1/alerts/webhook` accepts alert payloads
- [ ] Flexible schema: requires `dataset` or `table`, optional `metric`, `value`, `description`
- [ ] Auto-maps dataset identifiers to internal assets
- [ ] Configurable: auto-investigate vs queue for review
- [ ] Deduplication: same alert within 1 hour doesn't re-trigger
- [ ] Rate limiting: max 100 alerts/minute per tenant
- [ ] Returns investigation ID if auto-triggered
- [ ] Audit log of all received alerts
- [ ] HMAC signature validation (optional)

**Key Design Notes:**
- Store raw alert in `alerts` table for debugging
- Asset resolution: fuzzy match on table name if URN not provided
- Investigation goal auto-generated from alert description
- Smart deduplication: configurable window per source (see Appendix A, Q8)

**Key API / Data Model Changes:**
```sql
CREATE TABLE alerts (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    source TEXT NOT NULL,
    payload JSONB NOT NULL,
    resolved_asset_id UUID,
    investigation_id UUID,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

New endpoints:
- `POST /api/v1/alerts/webhook`
- `GET /api/v1/alerts` - list alerts
- `POST /api/v1/alerts/{id}/investigate` - manually trigger

**Dependencies:**
- None (new subsystem)

**Risks + Mitigations:**
- Risk: Alert flood triggers too many investigations → Mitigation: Rate limiting, dedup, queue mode
- Risk: Can't resolve asset → Mitigation: Queue for manual mapping, learn from corrections

**Effort:** M (4-5 days)

**Designation:** OSS

---

#### Task 1.2.2: Monte Carlo Integration

**Title:** Native integration for Monte Carlo alerts

**Description:**
Create a specific integration for Monte Carlo that maps their alert schema to Dataing investigations. Include setup guide for MC webhook configuration.

**Why:** Monte Carlo is the market leader. Integration lets customers add investigation to their existing MC setup—an easy upsell path.

**Acceptance Criteria:**
- [ ] Monte Carlo webhook payload fully parsed
- [ ] Alert type mapped: freshness, volume, schema, field health, custom
- [ ] Table identifier resolved from MC's format
- [ ] Severity mapped to investigation priority
- [ ] MC incident ID stored for correlation
- [ ] Documentation: step-by-step MC webhook setup
- [ ] Test payload generator for validation
- [ ] Bi-directional: post investigation results back to MC incident (optional)

**Key Design Notes:**
- MC webhook format documented at their docs
- Table format: `<database>.<schema>.<table>` needs parsing
- Severity: critical → P1, warning → P2, info → P3

**Key APIs:**
- Extend `POST /api/v1/alerts/webhook` with MC-specific parsing
- New: `POST /api/v1/alerts/webhook/monte-carlo` (explicit endpoint)

**Dependencies:**
- Task 1.2.1 (webhook infrastructure)

**Risks + Mitigations:**
- Risk: MC changes webhook format → Mitigation: Version detection, graceful degradation

**Effort:** S (2-3 days)

**Designation:** OSS

---

#### Task 1.2.3: dbt Test Failure Integration

**Title:** Auto-investigate failed dbt tests

**Description:**
Create integration that receives dbt test failures (via webhook or dbt Cloud API) and triggers investigations on the failing model.

**Why:** dbt is ubiquitous in modern data stacks. Test failures are perfect investigation triggers—specific, actionable, and common.

**Acceptance Criteria:**
- [ ] dbt Cloud webhook integration documented and tested
- [ ] dbt Core: artifact parsing for `run_results.json`
- [ ] Test failure includes: model name, test name, test SQL, failure count
- [ ] Investigation goal generated from test type (e.g., "Why is unique test failing on orders.id?")
- [ ] Model name resolved to Dataing asset
- [ ] Test SQL included in investigation context
- [ ] Support for: unique, not_null, accepted_values, relationships, custom tests
- [ ] CLI: `dataing dbt investigate <run_results.json>`

**Key Design Notes:**
- dbt Cloud webhooks: job completion events
- dbt Core: parse JSON artifact directly
- Test type detection from test name patterns or macro references

**Key APIs:**
- `POST /api/v1/alerts/webhook/dbt`
- CLI command: `dataing dbt investigate`

**Dependencies:**
- Task 1.2.1 (webhook infrastructure)

**Risks + Mitigations:**
- Risk: Can't resolve model to asset → Mitigation: fuzzy match + manual mapping UI
- Risk: Many test failures at once → Mitigation: Group by model, investigate top failures

**Effort:** M (4-5 days)

**Designation:** OSS

---

### Epic 1.3: Community and Ecosystem
**Goal:** Build developer community around Dataing.
**User Value:** Support, plugins, and ecosystem growth.
**Competitor Weakness:** GX has community but it's fractured; MC/Soda have minimal OSS community.

---

#### Task 1.3.1: GitHub Repository Setup

**Title:** Public GitHub repo with contribution guidelines

**Description:**
Set up the public GitHub repository with proper structure, contributing guidelines, issue templates, and CI/CD.

**Why:** Open source requires open development. GitHub is where developers evaluate and contribute.

**Acceptance Criteria:**
- [ ] Repository at github.com/dataing/dataing (or similar)
- [ ] Monorepo structure: packages/, apps/, docs/
- [ ] README with: badges, description, quickstart, links
- [ ] CONTRIBUTING.md with: setup, code style, PR process
- [ ] CODE_OF_CONDUCT.md
- [ ] Issue templates: bug report, feature request, question
- [ ] PR template with checklist
- [ ] GitHub Actions: lint, test, build on PR
- [ ] Branch protection on main
- [ ] Dependabot enabled

**Key Design Notes:**
- Use conventional commits for changelog generation
- Require DCO sign-off for legal clarity
- Label system: good-first-issue, help-wanted, priority

**Dependencies:**
- Legal review of license (already MIT)

**Risks + Mitigations:**
- Risk: Low-quality contributions → Mitigation: Clear guidelines, responsive review

**Effort:** S (2-3 days)

**Designation:** OSS

---

#### Task 1.3.2: Discord/Slack Community

**Title:** Launch community chat for support and discussion

**Description:**
Create and launch a Discord or Slack community for Dataing users and contributors.

**Why:** Real-time community builds loyalty and surfaces issues before they become GitHub complaints.

**Acceptance Criteria:**
- [ ] Community platform live (Discord preferred for OSS)
- [ ] Channels: #general, #support, #contributing, #showcase, #announcements
- [ ] Welcome message with quickstart links
- [ ] Bot for: FAQ responses, GitHub issue linking
- [ ] Moderation guidelines and team
- [ ] Linked from: README, docs, website
- [ ] Response time target: < 24 hours for questions
- [ ] Weekly "office hours" scheduled

**Key Design Notes:**
- Discord: better for async, free, good for OSS
- Slack: better for enterprise, but costs scale
- Start Discord, offer Slack Connect for enterprises

**Dependencies:**
- Task 1.3.1 (GitHub for issue linking)

**Risks + Mitigations:**
- Risk: Community requires ongoing effort → Mitigation: Recruit community champions, automate FAQ

**Effort:** S (2-3 days)

**Designation:** OSS

---

## Phase 2: Enterprise (Months 3–6)

### Epic 2.1: Enterprise Access Control
**Goal:** RBAC, SSO, and audit logs for F500 compliance.
**User Value:** Pass security review and procurement.
**Competitor Weakness:** Standard enterprise features; table stakes.

---

#### Task 2.1.1: RBAC Implementation

**Title:** Role-based access control system

**Description:**
Implement RBAC with roles: Admin, Editor, Viewer. Control access to datasources, investigations, and settings at the role level.

**Why:** F500 companies require access control for compliance and security. No RBAC = no enterprise deal.

**Acceptance Criteria:**
- [ ] Roles: Admin (full access), Editor (create/modify), Viewer (read-only)
- [ ] Role assignment per user per organization
- [ ] Resource-level permissions: datasources, investigations, settings
- [ ] Admin can: manage users, manage roles, manage billing, delete data
- [ ] Editor can: create investigations, connect datasources, manage own items
- [ ] Viewer can: view investigations, view datasources, export data
- [ ] Permission checks on all API endpoints
- [ ] UI shows/hides actions based on permissions
- [ ] CLI respects permissions (graceful error messages)
- [ ] Custom roles (Enterprise+): define custom permission sets

**Key Design Notes:**
- Permission model: role → permissions (many-to-many)
- Check at service layer, not just API
- Cache permissions for performance

**Key API / Data Model Changes:**
```sql
CREATE TABLE roles (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    permissions JSONB NOT NULL,  -- ["investigation:create", "datasource:read", ...]
    is_system BOOLEAN DEFAULT FALSE,  -- system roles can't be deleted
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE user_roles (
    user_id UUID REFERENCES users(id),
    role_id UUID REFERENCES roles(id),
    tenant_id UUID NOT NULL,
    PRIMARY KEY (user_id, role_id, tenant_id)
);
```

**Dependencies:**
- Existing auth system

**Risks + Mitigations:**
- Risk: Breaking existing users → Mitigation: Default all users to Admin during migration
- Risk: Complex permission checks slow API → Mitigation: Caching, denormalized permission checks

**Effort:** L (7-10 days)

**Designation:** Enterprise

---

#### Task 2.1.2: SSO/SAML Integration

**Title:** Enterprise SSO with SAML 2.0 and OIDC

**Description:**
Implement single sign-on supporting SAML 2.0 and OIDC for enterprise identity providers (Okta, Azure AD, Google Workspace).

**Why:** No SSO = no enterprise deal. IT teams require centralized identity management.

**Acceptance Criteria:**
- [ ] SAML 2.0 SP implementation
- [ ] OIDC client implementation
- [ ] Tested with: Okta, Azure AD, Google Workspace, OneLogin
- [ ] JIT (just-in-time) user provisioning
- [ ] Attribute mapping: email, name, groups → roles
- [ ] IdP-initiated and SP-initiated flows
- [ ] Session management respects IdP session
- [ ] SCIM provisioning (stretch goal)
- [ ] Admin UI for SSO configuration
- [ ] Setup documentation per IdP

**Key Design Notes:**
- Use `python-saml` or `python3-saml` library
- Store IdP metadata and certificates securely
- Support multiple IdPs per tenant for complex orgs
- SCIM deferred post-Phase 2 per design partner feedback (see Appendix A, Q3)

**Key API / Data Model Changes:**
```sql
CREATE TABLE sso_configurations (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    provider_type TEXT NOT NULL,  -- saml, oidc
    idp_entity_id TEXT,
    idp_sso_url TEXT,
    idp_certificate TEXT,
    sp_entity_id TEXT,
    attribute_mapping JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Dependencies:**
- Task 2.1.1 (RBAC for group → role mapping)

**Risks + Mitigations:**
- Risk: Each IdP has quirks → Mitigation: Extensive testing, customer-specific debugging
- Risk: Certificate rotation breaks SSO → Mitigation: Support multiple certs during rotation

**Effort:** L (10-14 days)

**Designation:** Enterprise

---

#### Task 2.1.3: Comprehensive Audit Logs

**Title:** Audit logging for all sensitive operations

**Description:**
Log all sensitive operations (login, data access, configuration changes) with tamper-evident storage for compliance.

**Why:** SOC2, HIPAA, and enterprise security reviews require audit trails. This is non-negotiable for F500.

**Acceptance Criteria:**
- [ ] Events logged: login, logout, investigation start, investigation view, datasource connect, settings change, user management
- [ ] Each event has: timestamp, user_id, action, resource_type, resource_id, ip_address, user_agent, result
- [ ] Logs stored in append-only table (no deletes)
- [ ] Retention: configurable (default 1 year)
- [ ] Export: JSON, CSV, SIEM format (CEF)
- [ ] API: `GET /api/v1/audit-logs` with filters
- [ ] UI: audit log viewer with search
- [ ] Integrity: daily hash of logs for tamper detection
- [ ] Performance: async logging, doesn't block operations

**Key Design Notes:**
- Write to dedicated audit table (not main app DB for isolation)
- Use native PostgreSQL partitioning (monthly by tenant_id, created_at) - see Appendix A, Q6
- TimescaleDB considered for future if volume exceeds 10M logs/day per tenant
- SIEM integration via log forwarding (Splunk, Datadog, etc.)

**Key API / Data Model Changes:**
```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    user_id UUID,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    metadata JSONB,
    ip_address INET,
    user_agent TEXT,
    result TEXT,  -- success, failure, error
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Partitioning for performance
CREATE INDEX idx_audit_logs_tenant_time ON audit_logs (tenant_id, created_at DESC);
```

**Dependencies:**
- Task 2.1.1 (need user context for logging)

**Risks + Mitigations:**
- Risk: High volume slows system → Mitigation: Async write, batching
- Risk: Storage costs → Mitigation: Compression, tiered storage, retention policies

**Effort:** M (5-7 days)

**Designation:** Enterprise

---

### Epic 2.2: Multi-Tenant Scale
**Goal:** Support multiple teams/workspaces within an organization.
**User Value:** Team isolation, separate billing, organizational structure.
**Competitor Weakness:** Monte Carlo has this; GX/Soda don't.

---

#### Task 2.2.1: Workspace Implementation

**Title:** Multi-workspace support within organizations

**Description:**
Allow organizations to create multiple workspaces (sub-tenants) for team isolation. Each workspace has its own datasources, investigations, and users.

**Why:** Large organizations have multiple data teams. They need isolation without separate accounts.

**Acceptance Criteria:**
- [ ] Organization can have multiple workspaces
- [ ] Each workspace has: name, description, settings, members
- [ ] Datasources scoped to workspace
- [ ] Investigations scoped to workspace
- [ ] Users can belong to multiple workspaces
- [ ] Role assignment per workspace
- [ ] Workspace-level settings override org defaults
- [ ] Billing rolled up to organization
- [ ] API keys scoped to workspace
- [ ] CLI: `dataing workspace list`, `dataing workspace switch`
- [ ] Cross-workspace sharing (stretch): share investigation results

**Key Design Notes:**
- Add `workspace_id` to most tables
- Migration: existing data goes to "Default" workspace
- URL structure: app.dataing.io/<org>/<workspace>/...

**Key API / Data Model Changes:**
```sql
CREATE TABLE workspaces (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,  -- organization
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    settings JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (tenant_id, slug)
);

CREATE TABLE workspace_members (
    workspace_id UUID REFERENCES workspaces(id),
    user_id UUID REFERENCES users(id),
    role_id UUID REFERENCES roles(id),
    PRIMARY KEY (workspace_id, user_id)
);

-- Add to existing tables:
ALTER TABLE datasources ADD COLUMN workspace_id UUID;
ALTER TABLE investigations ADD COLUMN workspace_id UUID;
```

**Dependencies:**
- Task 2.1.1 (RBAC)

**Risks + Mitigations:**
- Risk: Complex query patterns → Mitigation: Always filter by workspace_id, index appropriately
- Risk: Migration breaks existing → Mitigation: Default workspace, extensive testing

**Effort:** L (10-14 days)

**Designation:** Enterprise

---

### Epic 2.3: Scheduled and Automated Investigations
**Goal:** Investigations run automatically on schedule or trigger.
**User Value:** Proactive monitoring without manual intervention.
**Competitor Weakness:** MC has scheduled monitors; we have scheduled investigations (deeper).

---

#### Task 2.3.1: Scheduled Investigation Jobs

**Title:** Cron-based scheduled investigations

**Description:**
Allow users to schedule investigations to run automatically on a cron schedule. Useful for regular health checks on critical tables.

**Why:** Engineers shouldn't have to remember to check data quality. Scheduled investigations provide continuous assurance.

**Acceptance Criteria:**
- [ ] Create scheduled investigation: asset, goal, schedule (cron expression)
- [ ] Schedules: hourly, daily, weekly, custom cron
- [ ] Investigation runs automatically at scheduled time
- [ ] Results stored and browsable in history
- [ ] Notification on completion (email, Slack, webhook)
- [ ] Notification only on findings (filter noise)
- [ ] Pause/resume schedules
- [ ] Schedule management UI
- [ ] CLI: `dataing schedule create`, `dataing schedule list`
- [ ] Timezone support
- [ ] Max concurrent scheduled jobs per tenant (prevent runaway)

**Key Design Notes:**
- Use Temporal for scheduling (cron workflows)
- Store schedule definition in DB, Temporal handles execution
- Dead letter handling for repeatedly failing schedules

**Key API / Data Model Changes:**
```sql
CREATE TABLE scheduled_investigations (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    workspace_id UUID,
    asset_id UUID NOT NULL,
    goal TEXT NOT NULL,
    cron_expression TEXT NOT NULL,
    timezone TEXT DEFAULT 'UTC',
    is_active BOOLEAN DEFAULT TRUE,
    notify_always BOOLEAN DEFAULT FALSE,
    notification_channels JSONB,  -- [{type: "slack", url: "..."}]
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    created_by UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Dependencies:**
- Temporal cron workflow capabilities

**Risks + Mitigations:**
- Risk: Too many scheduled jobs overload system → Mitigation: Per-tenant limits, priority queues
- Risk: Schedule drift → Mitigation: Temporal handles, monitor for delays

**Effort:** M (5-7 days)

**Designation:** Enterprise

---

#### Task 2.3.2: Auto-Investigation on Threshold Breach

**Title:** Threshold-based automatic investigation triggers

**Description:**
Define thresholds on metrics (null rate, row count, freshness) that automatically trigger investigations when breached.

**Why:** This is the bridge between monitoring and investigation. Threshold breach → automatic root cause analysis.

**Acceptance Criteria:**
- [ ] Define threshold: asset, metric, condition (>, <, =, etc.), value
- [ ] Threshold evaluation frequency configurable
- [ ] Breach triggers investigation automatically
- [ ] Investigation goal generated from threshold (e.g., "Why did null_rate exceed 5%?")
- [ ] Cooldown period: don't re-trigger within X hours
- [ ] Threshold UI: list, create, edit, delete
- [ ] CLI: `dataing threshold create`
- [ ] Multiple thresholds per asset
- [ ] Severity levels: info, warning, critical
- [ ] Integration with alert webhook (dedupe)

**Key Design Notes:**
- Threshold evaluation as scheduled job (not real-time)
- Store threshold state (normal, breached, recovering)
- Hysteresis: require sustained breach before trigger

**Key API / Data Model Changes:**
```sql
CREATE TABLE thresholds (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    asset_id UUID NOT NULL,
    metric_name TEXT NOT NULL,
    operator TEXT NOT NULL,  -- gt, lt, eq, gte, lte
    value NUMERIC NOT NULL,
    severity TEXT DEFAULT 'warning',
    cooldown_hours INT DEFAULT 24,
    is_active BOOLEAN DEFAULT TRUE,
    last_evaluated_at TIMESTAMPTZ,
    state TEXT DEFAULT 'normal',  -- normal, breached, recovering
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**Dependencies:**
- Metric collection system (existing)
- Task 2.3.1 (scheduled job infrastructure)

**Risks + Mitigations:**
- Risk: Noisy thresholds → Mitigation: Severity levels, cooldowns, hysteresis
- Risk: Missing breaches → Mitigation: Evaluation frequency monitoring

**Effort:** M (5-7 days)

**Designation:** Enterprise

---

## 5. North-Star Developer Workflows

### 5.1 Golden Path: Null Spike Investigation

**Persona:** Data Engineer at F500 retailer
**Trigger:** PagerDuty alert: "orders.customer_id null rate spiked to 15%"

```bash
# 1. Connect and attach context
$ dataing init --api-key $DATAING_API_KEY --url https://api.dataing.io
✓ Configuration saved to ~/.dataing/config.yaml

$ dataing ds attach warehouse://prod.sales.orders
✓ Attached to prod.sales.orders (Snowflake)
  Schema: 42 columns, 1.2B rows
  Last updated: 2 hours ago

# 2. Start investigation
$ dataing run start --goal "Why did customer_id null rate spike from 2% to 15%?"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Investigation: inv_7f3a2b1c │ Goal: Why did customer_id null rate spike...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[00:00:02] Generating hypotheses...

  1. [code_change] Recent dbt model change introduced bug
     → Commit abc123 modified customer_join.sql yesterday

  2. [upstream_data] Source system sending more nulls
     → Check raw_customers.customer_id null rate

  3. [schema_drift] Column type or constraint changed
     → Verify customer_id constraint still NOT NULL upstream

[00:00:15] Testing hypothesis 1: code_change

  Query: SELECT COUNT(*) FILTER (WHERE c.customer_id IS NULL) as nulls,
         COUNT(*) as total, commit_timestamp
         FROM orders o LEFT JOIN customers c ON o.customer_id = c.id
         GROUP BY commit_timestamp
         ORDER BY commit_timestamp DESC LIMIT 10

  Results:
  ┌─────────────────────┬───────┬─────────┐
  │ commit_timestamp    │ nulls │ total   │
  ├─────────────────────┼───────┼─────────┤
  │ 2026-01-25 14:00:00 │ 45000 │ 300000  │  ← Spike starts here
  │ 2026-01-25 10:00:00 │ 6000  │ 298000  │
  │ 2026-01-24 22:00:00 │ 5800  │ 301000  │
  └─────────────────────┴───────┴─────────┘

  ✓ SUPPORTS hypothesis: Null spike correlates with 14:00 deploy

[00:00:32] Checking code change details...

  Commit: abc123 (Jane Smith, 2026-01-25 13:45:00)
  PR: #1847 "Optimize customer join for performance"

  Diff summary:
  - Changed LEFT JOIN to INNER JOIN (reverted)
  + Changed INNER JOIN back to LEFT JOIN
  - Added COALESCE wrapper: COALESCE(c.id, -1)  ← BUG: -1 != NULL

  ⚠ FINDING: COALESCE converts actual NULLs to -1, but downstream
    expects NULL for unknown customers. Later filter removes -1 rows,
    leaving NULLs where -1s were expected.

[00:00:48] Synthesizing findings...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ROOT CAUSE IDENTIFIED │ Confidence: 92%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PR #1847 introduced a COALESCE(customer_id, -1) that incorrectly
converts legitimate NULL customer_ids to -1. A downstream filter
(WHERE customer_id != -1) then removes these rows, causing the
remaining rows to have NULL in unexpected places.

Causal Chain:
  1. PR #1847 merged at 13:45
  2. Deploy completed at 14:00
  3. COALESCE(-1) applied to ~45,000 rows with unknown customers
  4. Downstream filter removed -1 rows
  5. Remaining rows had NULL propagated from JOIN

Recommendations:
  • Revert PR #1847 or fix COALESCE logic
  • Add dbt test: customer_id should be NOT NULL OR explicitly -1
  • Review similar patterns in customer_join_v2.sql

Related:
  • PR #1847: https://github.com/acme/data-models/pull/1847
  • Commit: https://github.com/acme/data-models/commit/abc123
  • Similar issue: inv_3e2f1a (3 weeks ago, same model)

# 3. Export for incident report
$ dataing run export inv_7f3a2b1c --output incident_report.md
✓ Exported to incident_report.md (12 KB)

# 4. Share evidence hash for audit
$ dataing run verify inv_7f3a2b1c
✓ Evidence chain verified
  Root hash: sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b
  Evidence items: 7
  Chain integrity: VALID
```

---

### 5.2 Golden Path: Notebook Data Quality Check

**Persona:** Data Scientist validating model training data
**Trigger:** About to train model, wants to verify input data quality

```python
# In Jupyter Notebook

# 1. Load extension and connect
%load_ext dataing_notebook
%dataing connect --api-key $DATAING_API_KEY

# 2. Attach to training data
%dataing attach warehouse://ml.training.customer_features

# 3. Quick lineage check
%dataing lineage --depth 2

# [Interactive graph appears showing:]
# raw_customers → customer_features
# raw_transactions → transaction_agg → customer_features
# raw_products → product_features → customer_features

# 4. Ask about data freshness
%dataing ask "Is this data fresh enough for training? What's the most recent record?"

# [Streaming output:]
# Investigating data freshness...
#
# Latest record: 2026-01-25 23:45:00 (6 hours ago)
# Update frequency: Hourly
# Missing hours in last 7 days: 0
#
# ✓ Data is fresh and complete for training.
# Note: training_timestamp column is 99.97% populated.

# 5. Check for training/serving skew
%dataing ask "Are there any distribution shifts in the last 30 days that could cause training/serving skew?"

# [Streaming output:]
# Analyzing distribution stability...
#
# Feature: avg_purchase_amount
#   30-day mean: $127.45 → $142.30 (+11.7%)
#   ⚠ Significant drift detected (KS test p < 0.01)
#
# Feature: days_since_last_purchase
#   30-day mean: 12.3 → 11.1 (-9.8%)
#   ⚠ Moderate drift detected (KS test p < 0.05)
#
# Recommendation:
#   Consider retraining with recent data window
#   or adding drift monitoring to serving pipeline.

# 6. Export findings to share with team
%dataing export --format markdown

# [Markdown cell rendered with investigation summary]
```

---

### 5.3 Golden Path: CI/CD Data Test Integration

**Persona:** Analytics Engineer adding data quality to PR workflow
**Trigger:** PR that modifies dbt model should auto-validate

```yaml
# .github/workflows/data-quality.yml

name: Data Quality Check
on:
  pull_request:
    paths:
      - 'models/**/*.sql'
      - 'models/**/*.yml'

jobs:
  investigate-changes:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install Dataing CLI
        run: pip install dataing-cli

      - name: Configure Dataing
        run: |
          dataing init \
            --api-key ${{ secrets.DATAING_API_KEY }} \
            --url https://api.dataing.io

      - name: Get changed models
        id: changes
        run: |
          models=$(git diff --name-only origin/main... | grep 'models/' | xargs -I {} basename {} .sql | tr '\n' ' ')
          echo "models=$models" >> $GITHUB_OUTPUT

      - name: Run pre-flight investigation
        run: |
          for model in ${{ steps.changes.outputs.models }}; do
            echo "Investigating impact of changes to $model"

            # Check what downstream tables are affected
            dataing lineage downstream $model --format json > impact.json

            # Run investigation on potential impact
            dataing run start $model \
              --goal "What is the potential downstream impact of changes to this model?" \
              --json > investigation.json

            # Post results as PR comment
            dataing run export $(jq -r '.investigation_id' investigation.json) \
              --format markdown >> $GITHUB_STEP_SUMMARY
          done

      - name: Post investigation to PR
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const summary = fs.readFileSync(process.env.GITHUB_STEP_SUMMARY, 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## 🔍 Data Quality Investigation\n\n${summary}`
            });
```

**Output in PR:**

```markdown
## 🔍 Data Quality Investigation

### Model: customer_lifetime_value

**Investigation Goal:** What is the potential downstream impact of changes to this model?

**Downstream Impact:**
- `marketing.campaign_targeting` (direct dependency)
- `finance.revenue_forecast` (2 hops)
- `exec_dashboard.customer_health` (3 hops)

**Risk Assessment:**
- 🟡 Medium Risk: Changes to `ltv_score` calculation affect 12 downstream models
- 🟢 Low Risk: Column additions are backward compatible
- 🔴 High Risk: Removing `predicted_churn` would break `campaign_targeting`

**Recommendation:**
Before merging, validate:
1. `ltv_score` calculation produces similar distribution (run comparison query)
2. `campaign_targeting` tests pass with new model output
3. Document `predicted_churn` deprecation if intentional

[View full investigation →](https://app.dataing.io/investigations/inv_abc123)
```

---

## 6. Kill Shots

These are concrete, opinionated statements about how we win. Each maps to roadmap work.

---

### Kill Shot 1: "We explain, they alert"

**Statement:** While Monte Carlo tells you *something* is wrong, Dataing tells you *why* it's wrong—with evidence, confidence scores, and a link to the commit that caused it.

**Maps to:** Epic 0.1 (CLI Investigation), Epic 0.3 (Code-to-Data Causality)

**Demo moment:** Side-by-side comparison. MC shows "null rate anomaly." Dataing shows "PR #1847 introduced COALESCE bug, here's the exact line."

---

### Kill Shot 2: "pip install → investigate in 5 minutes"

**Statement:** Great Expectations requires 50 lines of Python to run one validation. Soda requires learning SodaCL. Dataing: `pip install dataing-cli && dataing run start`.

**Maps to:** Epic 1.1 (PyPI Distribution), Task 1.1.3 (Quickstart)

**Demo moment:** Screen recording of zero-to-investigation in under 5 minutes.

---

### Kill Shot 3: "Your alerts just got smarter"

**Statement:** Keep Monte Carlo for monitoring. Keep dbt tests. Dataing sits downstream and automatically investigates every alert—turning noise into signal.

**Maps to:** Epic 1.2 (Alerting Integration Layer)

**Demo moment:** Monte Carlo alert → webhook → auto-investigation → root cause in Slack.

---

### Kill Shot 4: "Open source investigation engine"

**Statement:** Monte Carlo is closed source and SaaS-only. Our investigation engine is MIT-licensed. Run it anywhere—your VPC, your laptop, air-gapped if needed.

**Maps to:** Section 3 (Open-Core Plan), Task 1.1.2 (Docker Compose)

**Demo moment:** `docker compose up` → full Dataing stack running locally in 60 seconds.

---

### Kill Shot 5: "Audit trail that satisfies SOC2"

**Statement:** Every investigation produces a hash-linked evidence chain. Export it, verify it, show it to auditors. No other tool has cryptographic investigation integrity.

**Maps to:** Epic 0.4 (Evidence Integrity)

**Demo moment:** `dataing run verify` → "Evidence chain VALID, 7 items, hash: sha256:..."

---

### Kill Shot 6: "Code changes visible in every investigation"

**Statement:** Soda doesn't know your code exists. GX is testing-only. Monte Carlo recently added PR linking. We've had git integration from day one—every investigation shows relevant commits.

**Maps to:** Epic 0.3 (Code-to-Data Causality)

**Demo moment:** Investigation output shows: "Commit abc123 by Jane Smith modified customer_join.sql" with diff summary.

---

### Kill Shot 7: "Notebook-native debugging"

**Statement:** Data scientists live in notebooks. Monte Carlo has no notebook story. GX requires boilerplate. Dataing: `%dataing ask "why is my training data stale?"` → rich streaming output.

**Maps to:** Epic 0.2 (Notebook Experience)

**Demo moment:** Jupyter notebook with `%dataing ask` showing interactive lineage graph and streaming investigation.

---

### Kill Shot 8: "Enterprise-ready from day one"

**Statement:** SSO, RBAC, audit logs, workspaces—not bolted on later. We built for F500 from the architecture up.

**Maps to:** Epic 2.1 (Enterprise Access Control), Epic 2.2 (Multi-Tenant Scale)

**Demo moment:** Okta SSO login → role-restricted view → audit log showing who accessed what.

---

### Kill Shot 9: "No alert fatigue because we investigate, not just alert"

**Statement:** Monte Carlo admits engagement drops 15% above 50 alerts/week. We don't add alerts—we resolve them. One investigation that explains five alerts is better than five separate notifications.

**Maps to:** Epic 1.2 (Alert Integration), Task 2.3.2 (Threshold-based auto-investigation)

**Demo moment:** Dashboard showing: "5 alerts received → 1 investigation → root cause identified in 3 minutes."

---

### Kill Shot 10: "The agent that learns your domain"

**Statement:** Generic ML anomaly detection doesn't understand your business. Our agent learns from feedback—upvote good hypotheses, downvote bad ones. It gets smarter per customer.

**Maps to:** Existing feedback system + future Custom Agent Training (Enterprise)

**Demo moment:** Investigation shows hypothesis: "Based on previous investigations, this pattern usually indicates [specific domain issue]."

---

## Appendix A: Open Questions & Answers

These questions arose during roadmap planning. Answers documented here to guide implementation.

---

### Q1: What Python packaging tool should we use for PyPI distribution?

**Answer:** Use **hatch** (not flit).

**Rationale:**
- Better support for monorepo structures with multiple packages
- More flexible build backend options
- Better tooling for version management across related packages
- Growing adoption in modern Python projects
- Works well with existing `uv` tooling

**Maps to:** Task 1.1.1

---

### Q2: Which notebook graph visualization library should we choose?

**Answer:** Use **ipycytoscape** (not pyvis).

**Rationale:**
- Better performance with large graphs (critical for lineage)
- More interactive controls out of the box
- Better Jupyter integration and widget lifecycle management
- Cleaner API for dynamic updates (useful for expanding/collapsing nodes)
- Better fallback story for non-widget environments

**Maps to:** Task 0.2.2

---

### Q3: Should we support SCIM provisioning in Phase 2 or defer it?

**Answer:** **Defer SCIM** to post-Phase 2.

**Rationale:**
- Listed as "stretch goal" but would add 3-5 days to an already L-sized task
- SSO with JIT provisioning covers 80% of enterprise needs
- SCIM is mainly needed for large enterprises (500+ users) doing automated deprovisioning
- Better to ship SSO fast and add SCIM based on design partner feedback
- Can be a separate upsell feature later

**Maps to:** Task 2.1.2

---

### Q4: How should we handle the OSS vs Enterprise boundary for git integration?

**Answer:** Make **entire git integration OSS** (override current mixed designation).

**Rationale:**
- Basic git connection and sync should be OSS to enable core "code-to-data causality" value prop
- OAuth providers (GitHub, GitLab, Bitbucket) should be OSS - they're just auth mechanisms
- Enterprise gate should be: scheduled/automatic sync, priority sync queues, and sync SLAs
- Makes the demo moment ("commit linked in investigation") work for OSS users
- Scheduled sync being enterprise aligns with Task 2.3.1 patterns

**Updated designation:** Task 0.3.1 → **OSS** (basic git sync), **Enterprise** (scheduled sync only)

**Maps to:** Task 0.3.1

---

### Q5: Should snapshot import (Task 0.4.2) be Enterprise-only or have an OSS tier?

**Answer:** **Split the feature** between OSS and Enterprise.

**Rationale:**
- OSS: Export snapshots + import for local/development use (same tenant)
- Enterprise: Cross-tenant import, import at scale (bulk imports), automated compliance exports
- Reproducibility is a core value prop and OSS users need it for debugging
- Enterprise pays for organizational-scale features like cross-team sharing and compliance workflows

**Updated designation:** Export + same-tenant import → **OSS**, Cross-tenant + bulk → **Enterprise**

**Maps to:** Task 0.4.2

---

### Q6: What's the right database partitioning strategy for audit logs?

**Answer:** Use **native PostgreSQL table partitioning** (not TimescaleDB initially).

**Rationale:**
- Partition by (tenant_id, created_at) using RANGE partitioning on created_at
- Monthly partitions with automatic partition creation
- Keep TimescaleDB as future optimization if volume exceeds 10M logs/day per tenant
- Native partitioning gives 90% of the benefit with zero new dependencies
- Easier to operate and backup

**Maps to:** Task 2.1.3

---

### Q7: Should CLI context (Task 0.1.4) use a file or in-memory state?

**Answer:** **Hybrid approach** - persistent file + in-memory overlay.

**Rationale:**
- Persistent context in `~/.dataing/context.json` for cross-session state
- In-memory overlay for session-specific state (current investigation, temp filters)
- Context versioning in the JSON for forward compatibility
- Matches how `kubectl` contexts work (familiar pattern for developers)

**Maps to:** Task 0.1.4

---

### Q8: What's the right deduplication window for webhook alerts?

**Answer:** **Configurable with smart defaults**.

**Implementation:**
- Default: 1 hour dedup window (as specified)
- Per-source configuration: allow different windows for different alert sources
- Smart dedup: same alert + same asset + similar values = dedupe
- Add "force investigate" flag to bypass dedup for debugging
- Store dedup key hash for audit trail

**Maps to:** Task 1.2.1

---

### Q9: How should we handle investigation replay permissions?

**Answer:** Respect RBAC with new ownership on replay.

**Implementation:**
- Viewing history: respect current RBAC (can only see investigations you have access to)
- Replaying investigations: allowed if you have read access to the original investigation
- Replayed investigations: create new investigation owned by replayer, linked to original
- Prevents permission escalation while enabling learning from past work

**Maps to:** Task 0.2.3

---

### Q10: What's the minimum viable demo datasource for quickstart?

**Answer:** Use **existing `./demo` infrastructure** with DuckDB + parquet fixtures.

**Implementation:**
- Leverage existing `demo/fixtures/` with 7 pre-baked anomaly scenarios
- Package subset as "quickstart bundle": baseline + null_spike + volume_drop (~3MB compressed)
- Use existing `load_duckdb.sql` script for local setup
- DuckDB advantages: lightweight, no server, fast analytical queries, familiar to data engineers
- Existing manifest.json format provides ground truth for validation
- Demo datasource already has 10k users, 5k orders, 500k events - perfect scale for demos

**Rationale:**
- Don't reinvent - we already have production-quality fixtures
- Parquet format is industry standard and works everywhere
- Existing anomalies are realistic (mobile app bug, CDN misconfiguration, etc.)
- Manifest.json provides ground truth for testing agent accuracy

**Maps to:** Task 1.1.3

---

## Appendix B: Effort Sizing Guide

| Size | Days | Description |
|------|------|-------------|
| S | 2-3 | Single engineer, well-defined scope, minimal dependencies |
| M | 4-7 | Single engineer, some design decisions, moderate dependencies |
| L | 7-14 | May need pair work, significant design, multiple integrations |
| XL | 14+ | Multiple engineers, architectural changes, high risk |

---

## Appendix C: Dependency Graph

```
Phase 0 (Weeks 0-6)
├── Epic 0.1: CLI Investigation
│   ├── 0.1.1: Streaming timeline
│   ├── 0.1.2: Export bundles (depends: 0.1.1)
│   ├── 0.1.3: Interactive mode (depends: 0.1.1)
│   └── 0.1.4: Context management (independent)
├── Epic 0.2: Notebook Experience
│   ├── 0.2.1: Rich ask output (depends: 0.1.1 concepts)
│   ├── 0.2.2: Lineage viz (depends: 0.1.4)
│   └── 0.2.3: History/replay (depends: 0.2.1)
├── Epic 0.3: Code Causality
│   ├── 0.3.1: Git integration (independent)
│   ├── 0.3.2: Agent context (depends: 0.3.1)
│   └── 0.3.3: PR linking (depends: 0.3.1, 0.3.2)
└── Epic 0.4: Evidence Integrity
    ├── 0.4.1: Hash chain (independent)
    └── 0.4.2: Snapshot export (depends: 0.4.1)

Phase 1 (Weeks 6-12)
├── Epic 1.1: Distribution
│   ├── 1.1.1: PyPI (depends: Phase 0 stable)
│   ├── 1.1.2: Docker Compose (depends: 1.1.1)
│   └── 1.1.3: Quickstart docs (depends: 1.1.1, 1.1.2)
├── Epic 1.2: Alert Integration
│   ├── 1.2.1: Webhook ingestion (independent)
│   ├── 1.2.2: Monte Carlo (depends: 1.2.1)
│   └── 1.2.3: dbt integration (depends: 1.2.1)
└── Epic 1.3: Community
    ├── 1.3.1: GitHub setup (independent)
    └── 1.3.2: Discord (depends: 1.3.1)

Phase 2 (Months 3-6)
├── Epic 2.1: Enterprise Access
│   ├── 2.1.1: RBAC (independent)
│   ├── 2.1.2: SSO/SAML (depends: 2.1.1)
│   └── 2.1.3: Audit logs (depends: 2.1.1)
├── Epic 2.2: Multi-Tenant
│   └── 2.2.1: Workspaces (depends: 2.1.1)
└── Epic 2.3: Automation
    ├── 2.3.1: Scheduled jobs (independent)
    └── 2.3.2: Threshold triggers (depends: 2.3.1)
```

---

## Appendix D: Implementation Context

This appendix provides the technical implementation details needed to execute tasks without additional codebase exploration. It documents: current file structure, existing implementations, code patterns, API schemas, algorithms, and development workflows.

---

### D.1: Codebase Structure Map

#### CLI Package
**Location**: `python-packages/dataing-cli/src/dataing_cli/`

```
├── main.py                    # Typer app definition, init, status commands
├── commands/
│   ├── run.py                # start, watch, export, verify investigations
│   ├── ask.py                # Interactive investigation mode
│   ├── ds.py                 # Datasource management
│   └── repo.py               # Dataset-to-repository mappings
├── config.py                  # XDG config (~/.config/dataing/), keyring integration
├── display.py                 # Rich panels, tables, syntax highlighting
├── repl.py                    # Interactive REPL for ask mode
├── export.py                  # Markdown/JSON report rendering
└── errors.py                  # CLI exception handling (@cli_error_handler)
```

**Framework**: Typer (async CLI)
**Auth Priority**: Flag → Env var (DATAING_API_KEY) → Keyring → Config file
**Config Storage**: `~/.config/dataing/config.toml` (XDG-compliant)

#### SDK Package
**Location**: `python-packages/dataing-sdk/src/dataing_sdk/`

```
├── client.py                  # DataingClient (httpx-based HTTP client)
├── types.py                   # RunEvent, Evidence models, Enums
└── exceptions.py              # DataingError, AuthError, NotFoundError, etc.
```

**HTTP Client**: httpx with connection pooling, 30s timeout
**Auth Method**: `X-API-Key` header

#### Backend Core
**Location**: `python-packages/dataing/src/dataing/`

```
├── core/
│   ├── domain_types.py       # AnomalyAlert, MetricSpec, Finding, Evidence
│   ├── state.py              # Event-sourced state management
│   └── investigation/        # Domain logic, repository, collaboration service
├── temporal/
│   ├── workflows.py          # InvestigationWorkflow with child workflows
│   ├── activities.py         # Activity functions for LLM calls, SQL execution
│   └── client.py             # TemporalInvestigationClient
├── agents/
│   └── prompts/              # Agent prompt templates
├── models/
│   └── investigation.py      # SQLAlchemy ORM models
├── entrypoints/api/
│   └── routes/
│       └── investigations.py # REST + SSE endpoints (line ~803 for SSEEventType)
└── adapters/
    ├── db/                    # Repository implementations, SDK repository
    ├── datasource/           # SQL, document, filesystem adapters
    └── lineage/              # OpenLineage, dbt, Dagster, Airflow providers
```

#### Notebook Extension
**Location**: `python-packages/dataing-notebook/src/dataing_notebook/`

```
├── magic.py                   # %dataing IPython magic commands (882 lines)
├── state.py                   # NotebookState singleton
├── rendering.py               # Rich HTML rendering for Jupyter output
└── serverextension/
    ├── handlers.py           # 19 HTTP handlers for notebook↔backend
    ├── credentials.py        # Keyring/env/session credential storage
    └── state.py              # WorkspaceManager state machine
```

**Magic Commands**: connect, attach, lineage, ask, export, status, clear, help
**SSE Streaming**: Lines 530-581 in `magic.py`

#### Demo Infrastructure
**Location**: `demo/`

```
├── generate.py                # Fixture generator (1497 lines, 7 scenarios)
├── fixtures/                  # Parquet files with manifests
│   ├── baseline/             # Clean data (10k users, 5k orders, 500k events)
│   ├── null_spike/           # 40% NULL user_id (mobile app v2.3.1 bug)
│   ├── volume_drop/          # 80% missing EU events (CDN misconfiguration)
│   ├── schema_drift/         # 28% products.price as string
│   ├── duplicates/           # 15% duplicate order_items
│   ├── late_arriving/        # 3% late event insertion
│   └── orphaned_records/     # 8% broken user FK in orders
├── load_duckdb.sql           # DuckDB loading script
├── demo_notebook.ipynb       # Example Jupyter notebook
└── README.md                 # Scenarios, credentials, validation queries
```

---

### D.2: Current Implementation State

#### Epic 0.1: CLI Investigation

**✅ EXISTS:**
- `dataing run start` command structure (needs streaming timeline enhancement)
- `dataing run watch` with polling (needs Rich Live upgrade)
- SSE streaming client: `DataingClient.stream_run(run_id, last_seq)`
- Rich display utilities: `display.py` (format_hypothesis, format_evidence_item, format_synthesis, format_query)
- Config management: `config.py` with XDG + keyring support

**❌ NEEDS BUILDING:**
- Real-time streaming timeline display with Rich Live (Task 0.1.1)
- Export command with markdown/JSON bundles (Task 0.1.2)
- Interactive ask REPL mode (Task 0.1.3 - `repl.py` stub exists)
- Context persistence to `~/.dataing/context.json` (Task 0.1.4)

**⚠️ PARTIALLY EXISTS:**
- `dataing ds attach` command exists, but no persistence layer

#### Epic 0.2: Notebook Experience

**✅ EXISTS:**
- `%dataing` magic with 8 subcommands (connect, attach, lineage, ask, export, status, clear, help)
- SSE streaming rendering: `magic.py` lines 530-581 (`render_timeline_event`)
- Rich HTML rendering: `rendering.py` (render_evidence, render_table, render_context)
- State management via server extension with versioned commands

**❌ NEEDS BUILDING:**
- ipywidgets for collapsible hypothesis/evidence sections (Task 0.2.1)
- ipycytoscape lineage graph with pan/zoom (Task 0.2.2)
- History/replay with compare mode (Task 0.2.3)

#### Epic 0.3: Code-to-Data Causality

**✅ EXISTS:**
- Repository mapping table: `dataset_repo_mappings` (PR #96 completed)
- CLI commands: `dataing repo map`, `dataing repo show`, `dataing repo list`, `dataing repo import-dbt`
- API endpoints: POST/GET `/api/v1/dataset-repo-mappings`, POST `/api/v1/dataset-repo-mappings/bulk`

**❌ NEEDS BUILDING:**
- Git repositories table and OAuth sync infrastructure (Task 0.3.1)
- Code changes table with commit parsing and asset matching (Task 0.3.1)
- Agent prompt injection for code context (Task 0.3.2)
- PR/commit link enrichment with metadata (Task 0.3.3)

#### Epic 0.4: Evidence Integrity

**✅ EXISTS:**
- Evidence hash chain fields in models: `content_hash`, `previous_hash` (in `RichEvidenceBase`)
- Verification endpoint: `GET /api/v1/investigations/{id}/verify` returns `ChainVerificationResponse`
- CLI command: `dataing run verify <investigation_id>`

**❌ NEEDS BUILDING:**
- Chain building enforcement in Temporal workflow (Task 0.4.1)
- Snapshot export/import with tar.gz archive format (Task 0.4.2)

---

### D.3: Code Patterns & Examples

#### Pattern: Rich Panel Formatting (for Task 0.1.1)

```python
# Add to display.py
from rich.panel import Panel
from rich.syntax import Syntax
from rich.live import Live
from rich.layout import Layout

def format_hypothesis(event: dict, index: int, elapsed: float) -> Panel:
    """Format hypothesis testing event as blue panel."""
    content = f"""
[bold]Hypothesis {index}:[/bold] {event['description']}
[dim]Category:[/dim] {event['category']}
[dim]Elapsed:[/dim] {format_timestamp(elapsed)}
"""
    return Panel(
        content,
        border_style="blue",
        title=f"[bold blue]Testing Hypothesis {index}[/bold blue]",
        title_align="left"
    )

def format_evidence_item(event: dict, elapsed: float) -> Panel:
    """Format evidence as green (SUPPORTS) or red (REFUTES) panel."""
    verdict = event.get('verdict', 'NEUTRAL')
    color = "green" if verdict == "SUPPORTS" else "red" if verdict == "REFUTES" else "yellow"

    content = f"""
[bold]SQL Query:[/bold]
{format_sql(event.get('sql', ''))}

[bold]Conclusion:[/bold] {event.get('conclusion', 'N/A')}
[dim]Confidence:[/dim] {event.get('confidence', 0.0):.0%}
[dim]Elapsed:[/dim] {format_timestamp(elapsed)}
"""
    return Panel(content, border_style=color, title=f"[bold {color}]Evidence[/bold {color}]")

def format_sql(sql: str) -> Syntax:
    """Format SQL with syntax highlighting."""
    return Syntax(sql, "sql", theme="monokai", line_numbers=False, word_wrap=True)

def format_timestamp(elapsed: float) -> str:
    """Format elapsed seconds as [MM:SS]."""
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)
    return f"[{minutes:02d}:{seconds:02d}]"

# Example usage in streaming timeline (Task 0.1.1)
def watch_investigation_live(client: DataingClient, run_id: str):
    """Stream investigation with Rich Live timeline."""
    start_time = time.time()
    panels = []

    with Live(auto_refresh=False) as live:
        for event in client.stream_run(run_id):
            elapsed = time.time() - start_time

            if event.event == "run_progress" and "hypothesis" in event.data:
                panels.append(format_hypothesis(event.data, len(panels) + 1, elapsed))
            elif event.event == "run_evidence":
                panels.append(format_evidence_item(event.data, elapsed))
            elif event.event == "run_completed":
                panels.append(format_synthesis(event.data, elapsed))

            # Update live display
            layout = Layout()
            for panel in panels:
                layout.split_column(*panels)
            live.update(layout, refresh=True)

            if event.is_terminal:
                break
```

#### Pattern: Context Persistence (for Task 0.1.4)

```python
# Add to config.py
import json
from pathlib import Path
from datetime import datetime

CONTEXT_FILE = Path.home() / ".dataing" / "context.json"

def save_context(dataset_id: str, datasource_id: str, urn: str, schema: dict | None = None):
    """Persist context to ~/.dataing/context.json with versioning."""
    context = {
        "version": "1.0",
        "dataset_id": dataset_id,
        "datasource_id": datasource_id,
        "urn": urn,
        "schema": schema,
        "attached_at": datetime.utcnow().isoformat()
    }
    CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_FILE.write_text(json.dumps(context, indent=2))

def load_context() -> dict | None:
    """Load context from file, return None if not exists."""
    if not CONTEXT_FILE.exists():
        return None
    try:
        return json.loads(CONTEXT_FILE.read_text())
    except json.JSONDecodeError:
        # Corrupt file, return None
        return None

def clear_context():
    """Remove context file."""
    if CONTEXT_FILE.exists():
        CONTEXT_FILE.unlink()
```

#### Pattern: Asset Fuzzy Matching (for Tasks 0.3.1, 1.2.1)

```python
# Algorithm for resolving table names to asset IDs
from difflib import SequenceMatcher

def fuzzy_match_asset(table_name: str, assets: list[Asset]) -> Asset | None:
    """
    Match table name to asset using similarity scoring.
    Returns best match if similarity >= 0.8, else None.

    Matching priority:
    1. Exact match on name or qualified_name
    2. Similarity match with 80% threshold
    """
    best_match = None
    best_score = 0.0

    for asset in assets:
        # Try exact match first
        if asset.name == table_name or asset.qualified_name == table_name:
            return asset

        # Try similarity match
        score = SequenceMatcher(None, table_name.lower(), asset.name.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = asset

    # Threshold: 80% similarity required
    return best_match if best_score >= 0.8 else None
```

#### Pattern: Evidence Hash Chain Building (for Task 0.4.1)

```python
# Add to temporal workflow or evidence repository
import hashlib
import json

def build_evidence_chain(evidence_items: list[Evidence]) -> str:
    """
    Build hash-linked evidence chain and return root hash.
    Modifies evidence items in-place with content_hash and previous_hash.

    Returns root hash (final item's content_hash) or None if empty list.
    """
    previous_hash = None

    for item in sorted(evidence_items, key=lambda e: e.seq):
        # Compute content hash (SHA256 of JSON-serialized content)
        content = json.dumps(item.content, sort_keys=True)
        item.content_hash = hashlib.sha256(content.encode()).hexdigest()

        # Link to previous item in chain
        item.previous_hash = previous_hash
        previous_hash = item.content_hash

    # Return root hash (last item's hash)
    return previous_hash if previous_hash else None

def verify_evidence_chain(evidence_items: list[Evidence]) -> tuple[bool, int | None]:
    """
    Verify evidence chain integrity.
    Returns (is_valid, first_broken_seq).
    If chain is valid, first_broken_seq is None.
    """
    if not evidence_items:
        return True, None

    sorted_items = sorted(evidence_items, key=lambda e: e.seq)
    previous_hash = None

    for item in sorted_items:
        # Check if previous_hash matches expected
        if item.previous_hash != previous_hash:
            return False, item.seq

        # Recompute content hash
        content = json.dumps(item.content, sort_keys=True)
        computed_hash = hashlib.sha256(content.encode()).hexdigest()

        # Check if stored hash matches computed
        if item.content_hash != computed_hash:
            return False, item.seq

        previous_hash = item.content_hash

    return True, None
```

#### Pattern: Deduplication Key Calculation (for Task 1.2.1)

```python
def calculate_dedup_key(alert: dict) -> str:
    """
    Generate stable hash for alert deduplication.

    Key components:
    - Asset identifier (dataset_id or table name)
    - Anomaly type (null_spike, volume_drop, etc.)
    - Metric name (if present)
    - Rounded deviation (nearest 10% to handle fluctuations)

    Returns SHA256 hash as hex string.
    """
    components = [
        alert.get("dataset_id") or alert.get("table", ""),
        alert.get("anomaly_type", ""),
        alert.get("metric_name", ""),
        str(round(alert.get("deviation_pct", 0) / 10) * 10)  # Round to nearest 10%
    ]

    key_string = "|".join(str(c) for c in components)
    return hashlib.sha256(key_string.encode()).hexdigest()
```

---

### D.4: API Response Schemas

#### Investigation State Response (existing endpoint)

```python
# From entrypoints/api/routes/investigations.py
class InvestigationStateResponse(BaseModel):
    investigation_id: UUID
    status: str  # pending, in_progress, waiting_approval, completed, failed
    main_branch: BranchStateResponse
    user_branch: BranchStateResponse | None = None
    root_hash: str | None = None  # SHA256 of final evidence item

class BranchStateResponse(BaseModel):
    branch_id: UUID
    status: str
    current_step: str  # gathering_context, hypothesis_testing, synthesis, completed
    synthesis: dict | None = None  # Final findings with root cause
    evidence: list[dict] = []  # Evidence items with hashes
    step_history: list[StepHistoryItemResponse] = []
    matched_patterns: list[MatchedPatternResponse] = []
    can_merge: bool
    parent_branch_id: UUID | None

class StepHistoryItemResponse(BaseModel):
    step: str
    started_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    status: str
```

#### SSE Event Structure (SDK types.py)

```python
# From SDK types.py
class SSEEventType(str, Enum):
    RUN_STARTED = "run_started"
    RUN_PROGRESS = "run_progress"
    RUN_EVIDENCE = "run_evidence"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_HEARTBEAT = "run_heartbeat"

class RunEvent(BaseModel):
    seq: int  # Sequence number for resumption after disconnect
    event: str  # Event type (see SSEEventType enum)
    run_id: str
    data: dict[str, Any]  # Event-specific payload
    timestamp: str | None  # ISO 8601 format

    @property
    def is_terminal(self) -> bool:
        """Check if event is run_completed or run_failed."""
        return self.event in ("run_completed", "run_failed")

    @property
    def is_evidence(self) -> bool:
        return self.event == "run_evidence"
```

#### Evidence Models (SDK types.py)

```python
class EvidenceKind(str, Enum):
    QUERY_RESULT = "query_result"
    HYPOTHESIS = "hypothesis"
    LINEAGE_TRACE = "lineage_trace"
    SCHEMA_SNAPSHOT = "schema_snapshot"
    METRIC_CALCULATION = "metric_calculation"
    RUN_SUMMARY = "run_summary"

class RichEvidenceBase(BaseModel):
    id: str  # Evidence UUID
    run_id: str
    seq: int  # 1-indexed sequence for ordering
    kind: EvidenceKind
    timestamp: datetime
    # Hash-linked evidence for tamper detection
    content_hash: str  # SHA256(content)
    previous_hash: str | None  # Links to previous evidence item
```

#### Lineage Graph Response (for Task 0.2.2)

```python
# From lineage API endpoints
class LineageGraphResponse(BaseModel):
    nodes: list[LineageNode]
    edges: list[LineageEdge]

class LineageNode(BaseModel):
    id: str  # Asset ID
    name: str  # Table/view name
    type: str  # table, view, external
    platform: str  # postgres, snowflake, bigquery, etc.
    dataset_id: str
    qualified_name: str  # database.schema.table

class LineageEdge(BaseModel):
    source_id: str  # Upstream asset ID
    target_id: str  # Downstream asset ID
    job_id: str | None  # Transformation job ID
    job_name: str | None  # Job display name
    last_run: datetime | None  # Most recent execution
```

#### Chain Verification Response (for Task 0.4.1)

```python
class ChainVerificationResponse(BaseModel):
    investigation_id: UUID
    is_valid: bool  # True if chain unbroken
    evidence_count: int
    root_hash: str | None  # Final evidence content_hash
    root_hash_matches: bool | None  # Stored vs computed match
    first_broken_seq: int | None  # Where chain breaks (None if valid)
    chain_available: bool = True  # False if no evidence
```

---

### D.5: Database Current State

#### Investigation Table (existing)

```sql
-- From models/investigation.py
CREATE TABLE investigations (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    dataset_id TEXT NOT NULL,
    metric_name TEXT,
    expected_value FLOAT,
    actual_value FLOAT,
    deviation_pct FLOAT,
    anomaly_date TEXT,
    severity TEXT,  -- low, medium, high, critical
    status TEXT NOT NULL,  -- pending, in_progress, completed, failed
    events JSONB NOT NULL DEFAULT '[]',  -- Event-sourced state
    finding JSONB,  -- Final root cause analysis
    root_hash TEXT,  -- SHA256 for evidence chain verification
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_seconds FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_investigations_tenant ON investigations(tenant_id);
CREATE INDEX idx_investigations_status ON investigations(status);
CREATE INDEX idx_investigations_created ON investigations(created_at DESC);
```

#### Repository Mappings (completed, reference for Task 0.3.1)

```sql
-- From PR #96 (dataset-to-repository mapping system)
CREATE TABLE dataset_repo_mappings (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    dataset_pattern TEXT NOT NULL,  -- Glob pattern or exact name
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    file_path TEXT,  -- Path within repo (e.g., models/orders.sql)
    confidence_score FLOAT,  -- 0.0-1.0, for suggested mappings
    status TEXT DEFAULT 'pending',  -- pending, confirmed, dismissed
    created_by UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ,
    confirmed_by UUID
);

CREATE INDEX idx_dataset_repo_tenant ON dataset_repo_mappings(tenant_id);
CREATE INDEX idx_dataset_repo_pattern ON dataset_repo_mappings(dataset_pattern);
```

---

### D.6: Algorithm Specifications

#### Relevance Scoring for Code Changes (Task 0.3.2)

```python
def calculate_code_relevance(
    change: CodeChange,
    investigated_asset_id: str,
    upstream_asset_ids: set[str]
) -> float:
    """
    Score code change relevance: 0.0-1.0, higher = more relevant.

    Scoring rules:
    - Exact match (change affects investigated asset): 1.0
    - Upstream match (change affects upstream dependency): 0.7
    - Path pattern match (change in same directory): 0.3
    - Otherwise: 0.0

    Usage: Sort changes by (recency_weight * relevance) descending, take top 5.
    """
    # Check if change directly affects investigated asset
    if investigated_asset_id in change.affected_asset_ids:
        return 1.0

    # Check if change affects upstream dependencies
    if any(aid in upstream_asset_ids for aid in change.affected_asset_ids):
        return 0.7

    # Check if change is in same directory (path pattern match)
    investigated_path = get_asset_file_path(investigated_asset_id)
    change_paths = [f["path"] for f in change.changed_files]

    if any(same_directory(investigated_path, cp) for cp in change_paths):
        return 0.3

    return 0.0

def same_directory(path1: str, path2: str) -> bool:
    """Check if two paths share same parent directory."""
    from pathlib import Path
    return Path(path1).parent == Path(path2).parent

# Selection logic for hypothesis prompt (Task 0.3.2)
def select_relevant_changes(
    changes: list[CodeChange],
    investigated_asset_id: str,
    upstream_asset_ids: set[str],
    lookback_days: int = 14,
    max_changes: int = 5
) -> list[tuple[CodeChange, float]]:
    """
    Select most relevant code changes for investigation context.

    Returns list of (change, score) tuples sorted by relevance.
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(days=lookback_days)

    # Filter to recent changes
    recent_changes = [c for c in changes if c.committed_at >= cutoff]

    # Score each change
    scored_changes = []
    for change in recent_changes:
        relevance = calculate_code_relevance(change, investigated_asset_id, upstream_asset_ids)
        if relevance > 0:
            # Weight by recency (more recent = higher weight)
            days_ago = (now - change.committed_at).days
            recency_weight = 1.0 / (1.0 + days_ago / 7.0)  # Decay over weeks
            score = relevance * recency_weight
            scored_changes.append((change, score))

    # Sort by score descending, take top N
    scored_changes.sort(key=lambda x: x[1], reverse=True)
    return scored_changes[:max_changes]
```

#### Alert Deduplication Logic (Task 1.2.1)

```python
def should_deduplicate_alert(
    alert: dict,
    existing_alerts: list[Alert],
    dedup_window_hours: int = 1
) -> tuple[bool, str | None]:
    """
    Check if alert should be deduplicated against recent alerts.

    Returns:
        (should_dedup, matching_alert_id)
        - If should_dedup is True, matching_alert_id is the existing alert
        - If should_dedup is False, matching_alert_id is None

    Deduplication key includes:
    - Asset identifier (dataset_id or table name)
    - Anomaly type
    - Metric name
    - Rounded deviation (nearest 10%)
    """
    dedup_key = calculate_dedup_key(alert)
    cutoff = datetime.utcnow() - timedelta(hours=dedup_window_hours)

    for existing in existing_alerts:
        # Check if within dedup window
        if existing.created_at < cutoff:
            continue

        # Check if keys match
        existing_key = calculate_dedup_key(existing.payload)
        if existing_key == dedup_key:
            return True, str(existing.id)

    return False, None
```

---

### D.7: External Integration Details

#### Monte Carlo Webhook Format (Task 1.2.2)

```json
{
  "event_type": "anomaly_detected",
  "incident_id": "inc_abc123",
  "table": "database.schema.table_name",
  "metric": "freshness",
  "severity": "critical",
  "description": "Table has not been updated in 24 hours",
  "anomaly_date": "2026-01-28",
  "expected_value": 3600,
  "actual_value": 86400,
  "url": "https://getmontecarlo.com/incidents/inc_abc123"
}
```

**Mapping to Dataing**:
```python
def parse_monte_carlo_webhook(payload: dict) -> AnomalyAlert:
    # Parse table identifier: "database.schema.table" → resolve to dataset_id
    table_parts = payload["table"].split(".")

    return AnomalyAlert(
        dataset_ids=[resolve_table_to_dataset(payload["table"])],
        metric_spec=MetricSpec(
            metric_type="table",
            expression=payload["metric"],
            display_name=payload["metric"].replace("_", " ").title()
        ),
        anomaly_type=payload["metric"],  # freshness, volume, schema, field_health
        expected_value=payload.get("expected_value"),
        actual_value=payload.get("actual_value"),
        deviation_pct=calculate_deviation(payload),
        anomaly_date=payload["anomaly_date"],
        severity=map_severity(payload["severity"]),  # critical→critical, warning→medium
        source_system="monte_carlo",
        source_alert_id=payload["incident_id"],
        source_url=payload.get("url")
    )
```

#### dbt Cloud Webhook Format (Task 1.2.3)

```json
{
  "event_type": "run_completed",
  "run_id": "12345",
  "status": "success_with_failures",
  "account_id": "67890",
  "project_id": "11111",
  "run_results": [
    {
      "unique_id": "test.my_project.unique_orders_id",
      "status": "fail",
      "failures": 42,
      "message": "Got 42 results, expected 0",
      "compiled_sql": "SELECT id, COUNT(*) FROM orders GROUP BY id HAVING COUNT(*) > 1"
    }
  ]
}
```

**Mapping to Dataing**:
```python
def parse_dbt_test_failure(test_result: dict) -> AnomalyAlert:
    # Parse unique_id: "test.project.test_name_model_column"
    # Example: "test.my_project.unique_orders_id" → model=orders, test=unique
    parts = test_result["unique_id"].split(".")
    model_name = extract_model_from_test_id(parts[-1])  # "unique_orders_id" → "orders"
    test_type = extract_test_type(parts[-1])  # "unique_orders_id" → "unique"

    # Generate investigation goal from test type
    goal_templates = {
        "unique": f"Why is unique test failing on {model_name}?",
        "not_null": f"Why are there nulls in {model_name}?",
        "relationships": f"Why is referential integrity failing for {model_name}?",
        "accepted_values": f"Why are there invalid values in {model_name}?"
    }

    return AnomalyAlert(
        dataset_ids=[resolve_model_to_dataset(model_name)],
        metric_spec=MetricSpec(
            metric_type="table",
            expression=test_result["compiled_sql"],
            display_name=f"dbt test: {test_type}"
        ),
        anomaly_type=test_type,
        expected_value=0,
        actual_value=test_result.get("failures", 0),
        deviation_pct=100.0,  # All or nothing for test failures
        anomaly_date=datetime.utcnow().date().isoformat(),
        severity="high",
        source_system="dbt_cloud",
        source_alert_id=test_result["unique_id"],
        metadata={"compiled_sql": test_result["compiled_sql"]}
    )
```

#### OAuth Provider URL Templates (Task 0.3.3)

```python
# PR and commit URL templates per provider
PR_URL_TEMPLATES = {
    "github": "https://github.com/{owner}/{repo}/pull/{pr_number}",
    "gitlab": "https://gitlab.com/{owner}/{repo}/-/merge_requests/{pr_number}",
    "bitbucket": "https://bitbucket.org/{owner}/{repo}/pull-requests/{pr_number}"
}

COMMIT_URL_TEMPLATES = {
    "github": "https://github.com/{owner}/{repo}/commit/{commit_hash}",
    "gitlab": "https://gitlab.com/{owner}/{repo}/-/commit/{commit_hash}",
    "bitbucket": "https://bitbucket.org/{owner}/{repo}/commits/{commit_hash}"
}

def build_pr_url(provider: str, owner: str, repo: str, pr_number: int) -> str:
    template = PR_URL_TEMPLATES.get(provider)
    if not template:
        raise ValueError(f"Unknown provider: {provider}")
    return template.format(owner=owner, repo=repo, pr_number=pr_number)

def build_commit_url(provider: str, owner: str, repo: str, commit_hash: str) -> str:
    template = COMMIT_URL_TEMPLATES.get(provider)
    if not template:
        raise ValueError(f"Unknown provider: {provider}")
    return template.format(owner=owner, repo=repo, commit_hash=commit_hash)
```

---

### D.8: Development Workflow

#### Running Backend with Demo Data

```bash
# Start full demo stack (documented in CLAUDE.md)
just demo

# This command:
# 1. Generates demo fixtures if not present (demo/fixtures/)
# 2. Starts PostgreSQL and runs migrations
# 3. Starts backend API at http://localhost:8000
# 4. Starts frontend at http://localhost:3000
# 5. Seeds "E-Commerce Demo" datasource with fixtures

# Demo credentials:
# - Email: demo@dataing.io
# - Password: demo123456
# - API Key (legacy): dd_demo_12345
# - Org ID: 00000000-0000-0000-0000-000000000001

# Backend only:
just dev-backend      # EE backend
just dev-backend-ce   # CE backend only

# Frontend only:
just dev-frontend
```

#### Testing CLI Commands Locally

```bash
# Set environment variables
export DATAING_API_KEY=dd_demo_12345
export DATAING_BASE_URL=http://localhost:8000

# Initialize CLI (saves to ~/.config/dataing/config.toml)
dataing init --api-key $DATAING_API_KEY --url $DATAING_BASE_URL

# Test connection
dataing status

# Test investigation streaming
dataing run start \
  --dataset public.orders \
  --anomaly-type null_spike \
  --goal "Why did nulls spike 40% in user_id?" \
  --expected 5 \
  --actual 200 \
  --deviation 3900

# Test export
dataing run export <run_id> --output report.md
```

#### Creating Database Migrations

```bash
# Location: python-packages/dataing/migrations/
# Uses Alembic for migration management

# Create new migration
cd python-packages/dataing
alembic revision -m "add_git_repositories_table"

# This creates: migrations/versions/<hash>_add_git_repositories_table.py
# Edit the file to add upgrade() and downgrade() functions

# Example migration for Task 0.3.1:
def upgrade() -> None:
    op.create_table(
        'git_repositories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('provider', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'))
    )

# Apply migration
just migrate  # or: alembic upgrade head

# Rollback if needed
alembic downgrade -1
```

#### Using Demo Fixtures in Tests

```python
# Load demo fixtures for testing
import polars as pl
from pathlib import Path
import json

# Load baseline (clean) data
baseline_orders = pl.read_parquet("demo/fixtures/baseline/orders.parquet")
baseline_users = pl.read_parquet("demo/fixtures/baseline/users.parquet")

# Load anomaly data
null_spike_orders = pl.read_parquet("demo/fixtures/null_spike/orders.parquet")

# Load manifest for ground truth
manifest_path = Path("demo/fixtures/null_spike/manifest.json")
manifest = json.loads(manifest_path.read_text())

# Get ground truth for validation
affected_count = manifest["ground_truth"]["affected_row_count"]  # 892
anomaly_info = manifest["anomalies"][0]
assert anomaly_info["type"] == "null_spike"
assert anomaly_info["severity"] == 0.41  # 41% null rate

# Get investigation hints
hints = anomaly_info["investigation_hints"]
differentiating_queries = hints["differentiating_queries"]
# ["GROUP BY channel to see mobile_app vs web NULL rates", ...]
```

#### Running Tests

```bash
# Run all tests (CE + EE + frontend)
just test

# Run specific test suites
just test-ce           # Community Edition tests
just test-ee           # Enterprise Edition tests
just test-frontend     # Frontend tests

# Run single test file
uv run pytest python-packages/dataing/tests/unit/core/test_state.py -v

# Run single test function
uv run pytest python-packages/dataing/tests/unit/core/test_state.py::test_name -v

# Run integration tests (requires demo infrastructure)
just demo-infra  # Start PostgreSQL
just test-integration
```

---

### D.9: Cross-Reference Guide

Quick reference for which appendix section applies to each Phase 0 task:

| Task | Structure (D.1) | State (D.2) | Patterns (D.3) | Schemas (D.4) | DB (D.5) | Algorithms (D.6) | External (D.7) | Workflow (D.8) |
|------|-----------------|-------------|----------------|---------------|----------|------------------|----------------|----------------|
| 0.1.1 | CLI commands/ | Epic 0.1 | Rich panels | SSE events | - | - | - | Testing CLI |
| 0.1.2 | CLI export.py | Epic 0.1 | - | Investigation | - | - | - | Testing CLI |
| 0.1.3 | CLI repl.py | Epic 0.1 | - | SSE events | - | - | - | Testing CLI |
| 0.1.4 | CLI config.py | Epic 0.1 | Context persist | - | - | - | - | - |
| 0.2.1 | Notebook magic.py | Epic 0.2 | - | SSE events | - | - | - | Demo notebook |
| 0.2.2 | Notebook magic.py | Epic 0.2 | - | Lineage graph | - | - | - | Demo notebook |
| 0.2.3 | Notebook magic.py | Epic 0.2 | - | Investigation | - | - | - | Demo notebook |
| 0.3.1 | Backend core | Epic 0.3 | Asset matching | - | Repo mappings | - | OAuth URLs | Migrations |
| 0.3.2 | Backend agents/ | Epic 0.3 | - | - | - | Relevance scoring | - | - |
| 0.3.3 | Backend adapters/ | Epic 0.3 | - | - | - | - | OAuth URLs | - |
| 0.4.1 | Backend temporal/ | Epic 0.4 | Hash chain | Chain verify | Investigations | - | - | - |
| 0.4.2 | Backend/CLI | Epic 0.4 | - | - | - | - | - | Demo fixtures |

---

*Appendix D complete. All Phase 0 tasks now have sufficient implementation context for autonomous execution.*

---

*Document ends. Execute with urgency.*
