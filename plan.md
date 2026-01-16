Issues and Investigations Plan

0) Product shape

Two first-class objects
	•	Issue = intake + triage + collaboration + workflow + notifications + audit. Created by humans or integrations. Lives as the system of record for “a thing we need to resolve.”
	•	Investigation = execution artifact. Runs agents, gathers evidence, produces synthesis, can be rerun/branched, has strict guardrails.

Relationship
	•	An Issue can spawn 0..N Investigations.
	•	Spawning can be rules-driven or human-driven:
	•	Human: “Run investigation” from the Issue page
	•	Hooks/Rules: automatic triggers based on issue fields, integration payloads, time, SLA, or patterns

Key invariant: Issues never inherit Investigation UI/fields. They link to Investigations as “runs.”

⸻

1) Information architecture and UX

1.1 Routes
	•	/issues — Issues list + filters + bulk actions + saved views
	•	/issues/new — Create issue (+ templates)
	•	/issues/:issueId — Issue workspace (overview, discussion, timeline, linked runs)
	•	/investigations — Investigations list
	•	/investigations/new — Manual start (optional; most start from Issues)
	•	/investigations/:investigationId — Investigation execution/report UI

Optional but recommended:
	•	/datasets/:datasetId — Dataset hub (ownership, subscriptions, related issues/investigations)
	•	/integrations — Manage integrations + routing + secrets
	•	/rules — Automation rules for issues → investigations + notifications
	•	/runbooks — Knowledge base generated from resolved issues

⸻

1.2 Issues list (/issues)

Primary jobs
	•	Triage: what’s new, what’s blocked, what’s urgent
	•	Work allocation: assign, prioritize, escalate
	•	De-noise: dedupe and cluster correlated alerts into canonical issues

Table layout

Columns (in order):
	1.	Open/Closed icon (green dot circle for open; magenta check circle for closed)
	2.	Title + #number + small source badge (Human / Jira / MonteCarlo / GE / Slack / etc.)
	3.	Status (lifecycle badge)
	4.	Priority (P0–P3) and Severity (Low–Critical) as separate fields
	5.	Dataset
	6.	Assignee
	7.	Labels
	8.	SLA (time-to-ack / time-to-breach indicator)
	9.	Updated

Tabs
	•	Open
	•	Closed

Filters
	•	Search (title, description, #number, external id)
	•	Status (multi)
	•	Priority (multi)
	•	Severity (multi)
	•	Labels (multi)
	•	Dataset (typeahead)
	•	Assignee (me / unassigned / user)
	•	Source (integration provider / human)
	•	Time (created/updated range)
	•	“Has investigations” / “No investigations”

Sorting
	•	Updated desc (default)
	•	SLA breach risk
	•	Priority desc
	•	Created desc

Bulk actions
	•	Assign
	•	Change status
	•	Add/remove labels
	•	Set priority/severity
	•	Merge duplicates
	•	Trigger investigation (manual bulk run with guardrails)
	•	Subscribe/unsubscribe watchers

Saved views
	•	“My open”
	•	“Team P0/P1”
	•	“Schema drift last 7 days”
	•	“SLA at risk”
	•	Custom saved filters

⸻

1.3 Create issue (/issues/new)

Create modes
	•	Blank issue
	•	Templates (prefill fields + labels + optional structured sections)
	•	Data anomaly
	•	Pipeline failure
	•	Schema drift
	•	Business KPI drop
	•	Customer report

Fields
	•	Title (required)
	•	Description (markdown; supports links and code blocks)
	•	Dataset (optional)
	•	Labels (optional)
	•	Assignee (optional)
	•	Priority (optional)
	•	Severity (optional)
	•	Due date (optional)
	•	Watchers (optional; default includes creator)
	•	Source metadata hidden for humans, set automatically for integrations

⸻

1.4 Issue workspace (/issues/:issueId)

Layout

Header (sticky)
	•	Title + #number
	•	Status dropdown
	•	Priority + Severity dropdowns
	•	SLA indicator + timers (ack/resolution)
	•	Primary actions:
	•	Run investigation
	•	Escalate (Slack/pager action based on policy)
	•	Close/Reopen
	•	Secondary actions:
	•	Merge / Mark duplicate
	•	Create runbook (if resolved)
	•	Export/share link

Main column
	•	Description (editable)
	•	Comments / discussion (threaded optional)
	•	Investigation runs (timeline list)
	•	Each run shows: status, created time, trigger (human/rule/provider), short “focus prompt,” and link to investigation
	•	“Re-run” action with modified focus and guardrails
	•	Activity feed (immutable events)
	•	status changes, assignment, label changes, merges, rule firings, webhook ingests, investigation spawn/completion, notifications sent
	•	Related issues (duplicates, blocks, relates-to)

Right rail
	•	Author (link to user profile or integration)
	•	Source (provider + external URL)
	•	Dataset (link to dataset hub)
	•	Assignee
	•	Labels
	•	Watchers/subscriptions
	•	Linked tickets (Jira key etc.)
	•	External references (monitor id, check id, alert id)
	•	Created/updated/closed timestamps

Issue lifecycle states (canonical)
	•	OPEN → TRIAGED → IN_PROGRESS → BLOCKED → RESOLVED → CLOSED

Rules around state:
	•	RESOLVED requires either: resolution note OR linked runbook OR linked investigation synthesis selected as “resolution”
	•	Closing requires: status RESOLVED unless admin override

⸻

1.5 Investigation spawning UX (from an Issue)

“Run investigation” modal

Minimal, general-purpose (not anomaly-form shaped):
	•	Dataset (prefilled if issue has it; editable)
	•	Time window (optional; date range or “since”)
	•	Focus prompt (required; defaults to issue title + key excerpt)
	•	Execution profile (dropdown):
	•	Safe (read-only, strict limits)
	•	Standard (read-only, broader context)
	•	Deep (expensive; requires extra approval)
	•	Data access request preview (tables, estimated rows, cost)
	•	Approval requirements (auto-determined by policy):
	•	none
	•	requires approver(s)
	•	requires dataset owner approval
	•	“Run” button

Human-in-the-loop gates
	•	If policies require it, show a Context Review step before execution:
	•	purpose, tables, estimated rows, query preview, data sensitivity flags
	•	Approve / Reject with reason
	•	Approve with constraints (row limits/time limits/table allowlist)

⸻

1.6 Investigation UI (/investigations/:id)

Investigation stays focused on execution and results.

Core sections:
	•	Summary header: status, branch count, cost/time, live indicator, cancel
	•	Synthesis (root cause, confidence, recommended actions, causal chain)
	•	Evidence (structured artifacts, query outputs, charts later)
	•	Steps timeline (agent plan/execution trace)
	•	Chat/direction input (guidance + follow-up)
	•	Branching (true branches, not “send message”)
	•	Share (real permissions + copy link)
	•	Export (markdown/PDF later)

⸻

1.7 Dedupe + correlation UX

From Issues list and Issue page:
	•	“Possible duplicates” panel (similarity + shared dataset/source/time)
	•	“Merge duplicates” workflow:
	•	choose canonical
	•	close duplicates as “Duplicate”
	•	preserve references and external links
	•	“Correlation cluster” view:
	•	shows multiple alerts/issues grouped into one incident-like cluster
	•	cluster can create a single canonical issue

⸻

1.8 Knowledge base and runbooks
	•	Any RESOLVED issue can be converted into a Runbook
	•	Runbook includes:
	•	symptoms
	•	likely causes
	•	verification queries
	•	remediation steps
	•	prevention / monitoring suggestions
	•	New issues get suggested runbooks (similarity + rules)
	•	“Prevent recurrence” prompts:
	•	propose new checks (GE expectations / Monte Carlo monitors) based on resolution patterns

⸻

2) Backend architecture

2.1 Data model (Postgres)

Core entities

issues
	•	id uuid pk
	•	number bigint unique (sequence)
	•	title text
	•	description text null
	•	status text (enum)
	•	priority text null (P0..P3)
	•	severity text null (low..critical)
	•	due_at timestamptz null
	•	dataset_id text null (or uuid; match your dataset identity)
	•	assignee_user_id uuid null
	•	created_by_user_id uuid null
	•	author_type text (human|integration)
	•	author_user_id uuid null
	•	author_integration_id uuid null
	•	source_provider text null (e.g. jira, montecarlo)
	•	source_external_id text null
	•	source_external_url text null
	•	source_fingerprint text null (dedupe key)
	•	created_at timestamptz
	•	updated_at timestamptz
	•	closed_at timestamptz null
	•	indexes: (status), (dataset_id), (assignee_user_id), (updated_at desc), (source_provider, source_external_id), full-text on title/description

issue_labels
	•	issue_id uuid
	•	label text
	•	primary key (issue_id, label)
	•	index on (label)

issue_comments
	•	id uuid pk
	•	issue_id uuid
	•	author_user_id uuid
	•	body text
	•	created_at timestamptz
	•	optional: parent_comment_id for threading

issue_events (audit + timeline)
	•	id uuid pk
	•	issue_id uuid
	•	type text (created, status_changed, assigned, label_added, webhook_received, rule_fired, investigation_spawned, investigation_completed, merged, etc.)
	•	payload jsonb
	•	created_at timestamptz
	•	index (issue_id, created_at)

issue_relationships
	•	id uuid pk
	•	from_issue_id uuid
	•	to_issue_id uuid
	•	type text (duplicates, blocks, relates_to)
	•	unique constraint to prevent duplicates

issue_watchers
	•	issue_id uuid
	•	user_id uuid
	•	primary key (issue_id, user_id)

Issue → Investigation linkage

issue_investigation_runs
	•	id uuid pk
	•	issue_id uuid
	•	investigation_id uuid
	•	trigger_type text (human|rule|webhook|api|sla_escalation)
	•	trigger_ref jsonb (user id, rule id, provider event id)
	•	focus_prompt text
	•	execution_profile text (safe|standard|deep)
	•	created_at timestamptz
	•	index (issue_id, created_at desc)

Integrations + routing

integrations
	•	id uuid pk
	•	provider text (jira, slack, montecarlo, great_expectations, webhook_generic, etc.)
	•	display_name text
	•	config jsonb (mapping rules, dataset resolver config, etc.)
	•	signing_secret text null
	•	is_enabled bool
	•	created_at timestamptz

integration_events (idempotency + debugging)
	•	id uuid pk
	•	integration_id uuid
	•	provider_event_id text
	•	received_at timestamptz
	•	payload jsonb
	•	unique (integration_id, provider_event_id)

Automation rules engine

automation_rules
	•	id uuid pk
	•	name text
	•	is_enabled bool
	•	scope text (global/team/dataset/label)
	•	conditions jsonb (DSL)
	•	actions jsonb (create investigation, set fields, notify, assign, escalate)
	•	rate_limits jsonb (max per hour, etc.)
	•	created_at, updated_at

rule_executions
	•	id uuid pk
	•	rule_id uuid
	•	issue_id uuid
	•	status text (fired, skipped, throttled, failed)
	•	reason text null
	•	created_at timestamptz
	•	indexes (rule_id, created_at), (issue_id, created_at)

Notifications

notification_subscriptions
	•	id uuid pk
	•	user_id uuid
	•	scope_type text (dataset|label|issue|team)
	•	scope_id text
	•	channel text (slack|email|webhook)
	•	target jsonb (slack channel/user, email)
	•	created_at timestamptz
	•	index (scope_type, scope_id)

notification_outbox (reliable delivery)
	•	id uuid pk
	•	event_type text
	•	event_ref jsonb (issue id, comment id, run id)
	•	recipient_user_id uuid
	•	channel text
	•	payload jsonb
	•	status text (pending, sent, failed)
	•	attempts int
	•	next_attempt_at timestamptz
	•	created_at timestamptz

Knowledge base

runbooks
	•	id uuid pk
	•	title text
	•	body text
	•	dataset_id text null
	•	labels text[]
	•	created_from_issue_id uuid null
	•	created_at, updated_at

runbook_links
	•	runbook_id uuid
	•	issue_id uuid
	•	score float
	•	(runbook_id, issue_id) unique

⸻

2.2 API surface (HTTP)

Issues
	•	GET /api/issues (filters, pagination, saved views)
	•	POST /api/issues (human/API create)
	•	GET /api/issues/:id
	•	PATCH /api/issues/:id (status/priority/severity/dataset/assignee/title/description)
	•	POST /api/issues/:id/comments
	•	GET /api/issues/:id/comments
	•	POST /api/issues/:id/watch / DELETE /api/issues/:id/watch
	•	POST /api/issues/:id/merge (merge duplicates)
	•	POST /api/issues/:id/relationships (blocks/relates)
	•	GET /api/issues/:id/events

Issue → Investigation spawn
	•	POST /api/issues/:id/investigation-runs
	•	body: dataset, time_window, focus_prompt, execution_profile
	•	returns: run_id, investigation_id
	•	GET /api/issues/:id/investigation-runs

Integrations
	•	GET /api/integrations
	•	POST /api/integrations
	•	PATCH /api/integrations/:id
	•	POST /api/integrations/:provider/webhook (signed)
	•	POST /api/integrations/:id/test (verify mapping + rules)

Rules engine
	•	GET /api/rules
	•	POST /api/rules
	•	PATCH /api/rules/:id
	•	POST /api/rules/:id/dry-run (simulate on a sample issue or payload)

Runbooks
	•	GET /api/runbooks
	•	POST /api/runbooks
	•	POST /api/issues/:id/create-runbook
	•	GET /api/issues/:id/suggested-runbooks

⸻

2.3 Eventing and real-time updates

Server-sent events (SSE) / WebSockets
	•	Issues need real-time for:
	•	status changes
	•	comments
	•	assignment
	•	investigation run spawned/completed
	•	SLA breach warnings
	•	Provide:
	•	GET /api/issues/:id/stream (SSE)
	•	optionally GET /api/issues/stream for list updates by saved view

Internal events

Every state change emits a domain event:
	•	issue.created
	•	issue.updated
	•	issue.status_changed
	•	issue.assigned
	•	issue.comment_added
	•	issue.merged
	•	issue.investigation_spawned
	•	issue.investigation_completed
	•	integration.webhook_received
	•	rule.fired
	•	notification.enqueued

These feed:
	•	rules engine
	•	notifications
	•	activity feed
	•	correlation/dedupe pipeline

⸻

2.4 Rules and hooks system (Issue → Investigation upgrade)

Rule conditions (examples)
	•	Source provider == MonteCarlo AND severity >= high
	•	Label contains “freshness” AND dataset tier == “critical”
	•	Status changes to TRIAGED and no investigation exists
	•	SLA time-to-ack exceeded
	•	Similarity cluster size >= N within 30 minutes

Rule actions (examples)
	•	Spawn investigation with:
	•	focus_prompt template referencing issue fields + source payload
	•	profile = Safe/Standard/Deep
	•	Update issue fields:
	•	set status to IN_PROGRESS
	•	auto-assign team or user
	•	add labels
	•	Notify:
	•	dataset owners
	•	slack channel
	•	Escalate:
	•	create pager event (optional integration)
	•	Create/attach runbook suggestions

Guardrails (must-have)
	•	Rate limit by dataset and integration (to avoid runaway auto-runs)
	•	Idempotency: rules should not spawn duplicate investigations for same issue state
	•	Policy gating: deep runs require approval, sensitive datasets require explicit approval
	•	Dry-run mode for rule testing

⸻

2.5 Permissions and tenancy

RBAC model

Permissions enforced on:
	•	issue read/write
	•	comment
	•	run investigation
	•	modify rules/integrations
	•	view investigation results (separate from issue visibility if needed)

Dataset-level policy (recommended):
	•	If a user cannot access a dataset, they cannot:
	•	see issues tied to it (or see a redacted stub, depending on tenant preference)
	•	receive notifications
	•	run investigations

Auditability:
	•	every mutation produces an issue_event with actor identity and diff payload

⸻

2.6 Notification system

Subscription types
	•	Dataset owner auto-subscription (opt-out allowed)
	•	Label subscriptions
	•	Issue watchers
	•	Assignee always notified
	•	Team subscriptions (optional but useful)

Notification triggers
	•	Issue created (esp. integration-created)
	•	Assignment changes
	•	Status changes (BLOCKED / RESOLVED / CLOSED)
	•	New comment
	•	SLA thresholds (approaching breach, breached)
	•	Investigation spawned/completed with summary snippet
	•	Dedupe/merge events

Delivery reliability
	•	Outbox table + worker retries
	•	Slack + email connectors as adapters
	•	Per-tenant rate limiting

⸻

2.7 Correlation + dedupe pipeline

Dedupe keys
	•	For integrations: (provider, external_id) + provider_event_id
	•	For generic sources: source_fingerprint computed from:
	•	dataset id
	•	monitor/check id
	•	dimension (freshness/volume/schema)
	•	time bucket

Similarity detection
	•	Lightweight embedding or TF-IDF on title+description+source payload excerpt
	•	Candidate duplicates shown in UI (user decides merge)
	•	Automatic clustering creates a “canonical issue” optionally (configurable)

⸻

2.8 Knowledge base (runbooks) and prevention loop

Runbook generation
	•	From resolved issue + investigation synthesis + evidence links
	•	Structured fields:
	•	Symptoms
	•	Root cause
	•	Verification
	•	Fix
	•	Prevention

Prevention suggestions
	•	Suggest monitors/checks based on resolution patterns
	•	Link suggested “monitor improvements” back to Jira/GE/MonteCarlo via integration action (optional)

⸻

3) UI component contracts (frontend architecture)

Frontend module boundaries
	•	pages/issues/* — list, create, detail
	•	components/issues/* — IssueTable, IssueHeader, IssueSidebar, IssueTimeline, IssueComments, InvestigationRunsPanel, DuplicateCandidates
	•	lib/api/issues/* — hooks + client
	•	lib/api/rules/*, lib/api/integrations/*, lib/api/runbooks/*
	•	pages/investigations/* remains separate

Shared primitives
	•	Badge, Card, Button, Table, Popover, Dialog, Tabs, Textarea
	•	Popovers/menus must use real popover/dialog components (not absolute div hacks)
	•	All “copied” and “saved” feedback uses toast, not alert()

State management
	•	Data fetching via your existing query layer
	•	Real-time via SSE hooks:
	•	useIssueStream(issueId)
	•	useIssueListStream(savedViewKey)
	•	Optimistic updates for status/labels/assignment with rollback on failure

⸻

4) Operational concerns (one-shot readiness)

Performance
	•	Pagination and indexed filtering for /issues
	•	Avoid N+1 by denormalizing small display fields (assignee name, dataset display name) or joining efficiently
	•	Background jobs for:
	•	notifications
	•	rule evaluation
	•	similarity clustering
	•	runbook suggestion indexing

Reliability
	•	Outbox pattern for notifications and rule-triggered actions
	•	Idempotency for webhooks and rule actions
	•	Rate limiting on integration endpoints and auto-investigation spawning

Observability
	•	Structured logs on:
	•	webhook ingest
	•	rule evaluation decisions
	•	investigation spawn
	•	notification delivery
	•	Metrics:
	•	issues created/day by source
	•	MTTA/MTTR
	•	SLA breach counts
	•	auto-run investigation counts + costs
	•	rule fire rate + throttles
	•	Tracing around “webhook → issue → rule → investigation → notification”

Security
	•	Signed webhooks
	•	API keys scoped by integration / tenant
	•	Dataset-level access checks enforced before:
	•	issue view
	•	investigation spawn
	•	notification subscription

⸻

5) “Upgrade to investigation” rules (explicit behavior)

Human upgrade
	•	Always available if user has permission and dataset policies allow it
	•	Can require context approval based on execution profile or dataset sensitivity

Automatic upgrade (hooks/rules)
	•	Rules can auto-run investigations when:
	•	severity/priority thresholds met
	•	SLA threatens breach
	•	specific labels appear
	•	integration payload matches known patterns
	•	Auto-run is constrained by:
	•	per-dataset and per-provider rate limits
	•	idempotency (one run per issue per state transition unless configured)
	•	approval gates (deep runs queued awaiting approval)
