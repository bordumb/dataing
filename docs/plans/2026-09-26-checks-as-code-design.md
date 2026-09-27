# Checks as Code: Design

**Status:** Approved in brainstorming on 2026-09-26 (sections 1–6). D11, which credentials automated runs use, was decided the same day: option C (§5.2).

**Supersedes:** fn-47 (Scheduled Investigation Jobs), fn-48 (Threshold-Based Auto-Investigation)

**Related:**
- fn-51 (Codify)
- fn-13 (Helm, rescoped in §10)
- fn-36 (commit sync, follow-up)
- [Principal-bound query execution](2026-01-18-principal-bound-query-execution-design.md)
- [CE/EE reorganization](2026-01-09-ce-ee-reorganization-design.md)

**Goal:** Teams define data quality checks for each dataset once, in git. After that, checks re-run with one click or on a schedule, and changes are reviewed as pull requests. Failing checks open issues and trigger investigations, and investigations propose new checks.

**Tech stack:**
- Pydantic: the spec and the JSON Schema generated from it
- ruamel.yaml: parsing with line numbers, and editing that preserves comments
- sqlglot: compiling checks to SQL
- Temporal: runs and Schedules (SDK 1.20, already locked)
- GitHub App: github.com and GHES
- Redis: per-datasource concurrency limits

---

## 1. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | One **Checks** feature replaces separate scheduled-investigation and threshold systems | One place to say what good data looks like for a dataset |
| D2 | **Git is the source of truth** for check definitions | Review, history and change control come from pull requests |
| D3 | Check files are **YAML validated against a versioned spec** (`apiVersion: dataing/v1`). The JSON Schema is generated from a Pydantic `CheckSpec` model | See below |
| D4 | A **GitHub App** replaces the pasted-token integration | Owned by the org, not a person. Scoped to chosen repos, with short-lived tokens. Built-in webhooks. The only kind of integration that can post Check Runs |
| D5 | v1 supports **github.com and GitHub Enterprise Server (GHES)** | |
| D6 | **GHES customers self-host dataing** inside their network | Webhooks and API calls stay internal, and no firewall changes are needed |
| D7 | **CE is the engine. EE adds automation and GitHub** (§9) | Matches the existing Enterprise designation of fn-47 and fn-48 |
| D8 | When drafting checks, the LLM sees **profile numbers, never raw rows** | Limits how much customer data leaves the network |
| D9 | dataing **never pushes to the default branch**. Every change it makes arrives as a PR | A person reviews every change |
| D10 | **A query error never counts as a pass** | The current investigation path turns errors into "0 rows" |
| D11 | **People run as themselves. Automation runs with an explicit automation credential per datasource** (§5.2) | Keeps "user credentials" for people and "no credentials = no queries" for everyone, with a deliberate, audited exception for automation |

Why D3 chose YAML:
- Diffs are readable in PR review.
- dataing, the UI and the LLM can all write it.
- Editors get autocomplete from the JSON Schema.

Alternatives rejected for D3:
- **Python pickle:** a binary format, and loading a pickle runs arbitrary code.
- **Apple Pkl:** no official Python binding, hard to edit from code, and unfamiliar to data teams. It can still be added later as an optional way to write files, because `pkl eval -f yaml` outputs the same spec.

## 2. Architecture

```
GitHub / GHES repo: dataing/checks/*.yml
  │ merge to main                        │ pull request
  ▼                                      ▼
Sync → suite version (pinned to SHA)     Preview: validate + dry-run → result on the PR
  │
  ▼
Temporal Schedule  |  Run now (UI / API / CLI)
  │
  ▼
Runner: compile → read-only check → QueryGateway → warehouse
  │
  ▼
Result per check: pass | warn | fail | error   (+ metric history)
  │ fail
  ▼
Issue → team policy → auto-investigation → Codify drafts a check → PR to the repo
```

| Component | Edition | Home |
|---|---|---|
| Spec and loader | CE | `dataing/checks/spec.py`, `loader.py` |
| Compiler | CE | `dataing/checks/compiler.py` |
| Condition evaluator | CE | `dataing/checks/evaluator.py` |
| Runner (shared by Temporal and the CLI) | CE | `dataing/checks/runner.py`, `temporal/workflows/check_suite_run.py`, `temporal/activities/run_check.py` |
| API | CE | `entrypoints/api/routes/checks.py` |
| Schedules | EE | `dataing_ee/core/checks/schedules.py` |
| GitHub App | EE | `dataing_ee/adapters/github_app/` |

The runner uses its own Temporal task queue, `checks`, in the same worker binary. A burst of checks can't starve investigations.

## 3. Check file format

### 3.1 Repo layout

```
<tracked folder, default dataing/>
  checks/
    orders.yml         # one CheckSuite per dataset (enforced)
  metrics/
    revenue.yml        # optional MetricLibrary files
```

### 3.2 Suite

```yaml
apiVersion: dataing/v1
kind: CheckSuite
datasource: warehouse              # data_sources.key (new, unique per tenant)
dataset: analytics.orders          # datasets.native_path, as shown on the dataset page
owner: Payments                    # teams.name → failures route to this team's policy
schedule: { cron: "0 * * * *", timezone: UTC }    # EE
imports:
  - { repo: acme/dq-metrics, ref: v1.2 }         # resolved and pinned to a SHA at sync
defaults:
  window: { column: created_at, last: 1d }       # limits how much each check scans
  severity: medium
  timeout_seconds: 60
checks:
  - metric: null_rate                            # key defaults to null_rate_customer_id
    column: customer_id
    fail_when: { gt: 0.01 }
  - metric: row_count
    fail_when: { change_pct: { outside: [-30, 30], baseline: avg_7_runs } }   # signed %
  - metric: duplicate_count
    columns: [order_id, product_id]
    fail_when: { gt: 0 }
  - metric: acme.revenue_per_order
    warn_when: { outside: [20, 400] }
  - key: no_negative_totals                      # custom SQL must return one number
    sql: SELECT count(*) FROM {{ dataset }} WHERE total < 0
    fail_when: { gt: 0 }
    severity: high
```

### 3.3 Metric library

```yaml
apiVersion: dataing/v1
kind: MetricLibrary
namespace: acme
metrics:
  - name: revenue_per_order
    description: Average order value
    sql: SELECT sum(total) / nullif(count(*), 0) FROM {{ dataset }}
```

- Imports resolve to a commit SHA at sync, and the resolved spec stores that SHA. Use tags, so that upgrading a library is an explicit PR.
- In v1, library metrics take no parameters.

### 3.4 Rules

1. **Every check has a stable `key`.**
   - It defaults to `<metric>_<column or columns>`. `sql` checks must set it explicitly.
   - Keys must be unique within a suite.
   - History, baselines and issue dedup are tied to the key, so changing a threshold keeps the history.
2. **Only one active suite per dataset is allowed across the tenant.** A partial unique index in the database enforces this. Codify always knows which file to edit.
3. **Conditions are structured YAML** (§3.5), not strings.
4. **`{{ dataset }}` is the only template variable.**
   - The compiler replaces it in the parsed SQL as a quoted table, never by joining strings.
   - When `window` or `where` is set, each `{{ dataset }}` reference becomes a filtered subquery that keeps any alias, so custom SQL gets the same scan limits.
   - There's no Jinja.
5. **Custom SQL must return exactly one row with one number.** Anything else is an `error`.

### 3.5 Conditions

| Form | Example |
|---|---|
| Comparison | `{ gt: 0.01 }`, also `gte`, `lt`, `lte`, `eq`, `ne` |
| Range | `{ between: [a, b] }`, `{ outside: [a, b] }` |
| Change vs baseline | `{ change_pct: { lt: -30, baseline: previous \| avg_<N>_runs } }`. The change is **signed**, and `change_pct` accepts the same operators as comparisons and ranges, e.g. `outside: [-30, 30]` |

- A check can have `fail_when`, `warn_when`, or both. If both match, `fail_when` wins.
- Baselines come from `pass` results of *earlier* scheduled, manual and API runs. "Earlier" means a lower `seq`; the current run and later runs are excluded. PR previews, errors, warnings and failures are ignored, so an ongoing incident can't become the baseline.
- History is filtered by `compiled_sql_hash`, a hash of the query's resolved meaning: the dialect, the dataset, the metric or resolved SQL, the window column and duration, and the filters. Only the generated `as_of` time anchor is normalized out. Changing the window, a filter, the metric or library SQL restarts warm-up; changing only a threshold or `as_of` doesn't.
- Warm-up: `avg_<N>_runs` needs N eligible results and `previous` needs 1. Until then, the check reports a pass, marked "baseline warming up".
- A zero baseline: 0 → 0 counts as 0%. 0 → non-zero can't be a percentage, so the check reports a pass, marked "baseline is zero".
- A NaN or infinite value gives an `error`, and is never stored.

### 3.6 Built-in metrics (v1)

| Metric | Parameters | Replaces Codify's |
|---|---|---|
| `row_count` | none | `row_count_change` |
| `null_count`, `null_rate` | `column` | `not_null` |
| `distinct_count` | `column` or `columns` | none |
| `duplicate_count` | `column` or `columns` | `unique` |
| `min`, `max`, `avg`, `sum` | `column` | `in_range` |
| `freshness_minutes` | `column` (timestamp) | `freshness` |
| `accepted_values_violations` | `column`, `values` | `accepted_values` |
| `orphan_count` | `column`, `references: { dataset, column }` | `referential_integrity` |
| `sql` (custom) | none | `custom_sql` |

Semantics:
- `duplicate_count` is `count(*) - count(distinct key)` over rows whose key columns are all non-NULL, so 3 identical rows count as 2.
- `distinct_count` ignores rows with a NULL key.
- `accepted_values_violations` counts non-NULL values that aren't in the list; NULL isn't a violation.
- `orphan_count` doesn't count a NULL foreign key.

## 4. Data model

This needs one new migration. Use the next free number when it lands, because other branches may also add migrations.

| Table | Key columns | Notes |
|---|---|---|
| `check_sources` | tenant_id, kind (`github_app` \| `api`), github_installation_id, repo_id (GitHub's immutable ID), repo_full_name, folder, branch, last_synced_sha, sync_status, sync_errors (JSONB) | `api` is used by `dataing checks apply` from any CI |
| `check_suites` | tenant_id, source_id, file_path, datasource_id, dataset_id (nullable), native_path, owner_team_id, current_version_id, is_active | Stable identity for each file. Unique on (source_id, file_path) and on (source_id, datasource_id, native_path) where active |
| `check_suite_versions` | suite_id, commit_sha, spec (resolved JSONB), spec_hash | Never changed after it's written. Unique on (suite_id, commit_sha) |
| `check_runs` | tenant_id, suite_id, suite_version_id, trigger (`schedule` \| `manual` \| `api` \| `pr_preview`), status, triggered_by, temporal_workflow_id, started_at, finished_at | |
| `check_results` | run_id, suite_id, check_key, outcome (`pass` \| `warn` \| `fail` \| `error`), metric_value, condition (JSONB), message, compiled_sql_hash, duration_ms | Indexed on (suite_id, check_key, created_at DESC) for history and sparklines |

The same migration also:
- Adds `datasource_automation_credentials` (§5.2), modeled on `user_datasource_credentials`:
  - tenant_id
  - datasource_id, unique
  - credentials_encrypted
  - db_username
  - configured_by
  - created_at, updated_at, last_used_at
- Changes `query_audit_log`: `user_id` becomes nullable, and `principal_kind` and `actor` are added, with a check constraint (§5.2).
- Adds `data_sources.key`: unique per tenant, generated from the name, editable. Names aren't unique today.
- Starts writing `issues.source_fingerprint` (§7.1). The column exists but is never written today.
- Drops `generated_tests` and `test_runs`, removes the `/tests/*` routes and `services/test_tracking.py`, and updates their tests. Because of a UUID bug ([test_tracking.py:115](../../python-packages/dataing/src/dataing/services/test_tracking.py)), nothing ever wrote to those tables.

The EE tables are covered in §6.10.

## 5. Runner

### 5.1 One suite run

`CheckSuiteRunWorkflow` runs on task queue `checks`:

1. **Load** the suite's *current* version. A schedule then only needs updating when its cron changes, not when the checks do.
2. **Compile** each check with sqlglot for the datasource's dialect. Identifiers are quoted, `window` and `where` are applied, and the result is always one query that returns one number.
3. **Validate** each query right before it runs: read-only, a single statement, and the datasource's real dialect. This reuses `safety.validator.validate_query`, which today only checks LLM output ([agents/models.py:71](../../python-packages/dataing/src/dataing/agents/models.py)). It needs a dialect parameter and a way to skip the LIMIT requirement for aggregates. The SQL-hardening fix in flight is changing its signature.
4. **Execute** through `QueryGateway`, up to 4 checks from a suite in parallel. Runs use a `UserPrincipal` for "Run now" and an `AutomationPrincipal` for everything else (§5.2).
5. **Evaluate** conditions in Python and write the `check_runs` and `check_results` rows. Then hand failures to §7. PR previews skip that last step.

### 5.2 Credentials (D11: option C)

The [principal-bound query design](2026-01-18-principal-bound-query-execution-design.md) says:
- Principle 2: "User credentials, not service accounts."
- Principle 4: "No credentials = no queries."

Scheduled runs, PR previews and auto-investigations have no user. Option C keeps both principles for people and adds a deliberate, audited exception for automation. The options that were rejected:
- **A.** Use the suite owner's credentials. This breaks when that person leaves, and the audit log would name someone who didn't run the query.
- **B.** Silently use the datasource's stored connection config. This quietly weakens principle 2.

**Principals.** `QueryPrincipal` becomes one of two types. `QueryGateway` resolves credentials by type and never falls back from one type to the other.

| Principal | Fields | Credentials | Used by |
|---|---|---|---|
| `UserPrincipal` | user_id, tenant_id, datasource_id | `user_datasource_credentials` (existing) | "Run now" in the UI, which uses the clicking user's credentials |
| `AutomationPrincipal` | tenant_id, datasource_id, actor (e.g. `check:<suite_id>/<check_key>`, `investigation:<id>`) | `datasource_automation_credentials` (new) | Scheduled runs, API-triggered runs, PR previews, investigations triggered by checks |

**Automation credential.**
- An admin sets it deliberately for each datasource, under Settings → Datasource → Automation.
- It's meant to be a read-only service account, and the UI says so.
- Nothing ever falls back to it, and it never falls back to anything else.

**If a datasource has no automation credential** ("no credentials = no queries", and dataing says why):
- Schedules for its suites are created **paused**, with the reason shown in the Checks tab. They resume automatically once an admin sets the credential.
- PR previews only validate.
- API-triggered runs return an error.
- When a check fails, a policy action of `auto` is downgraded to `review`, with a note. No investigation runs without credentials.
- "Run now" works as usual, using the clicking user's own credentials. If that user has none, it returns a 403 that links to their credentials page. Both are **new**: today nothing maps `CredentialsNotConfiguredError` to a 403, and there is no per-user credentials page.

**Audit.** `query_audit_log.user_id` becomes nullable, and two columns are added:
- `principal_kind`: `user` or `automation`
- `actor`: which check or investigation ran the query

A check constraint requires `user_id` whenever `principal_kind = 'user'`.

**Scope.** This epic uses `AutomationPrincipal` for check runs and for investigations started by checks. Investigations from other sources (integration webhooks, EE automation rules) also run without a user today, through the worker's direct adapter path. Moving them onto the gateway is a follow-up.

### 5.3 Protecting the customer's warehouse

- `window` and `where` limit every scan.
- Every query returns one number, never table rows.
- Each check has a timeout, 60 seconds by default, which the suite or the check can override.
- Each datasource gets a cap on concurrent queries, enforced in Redis. Adapters already declare `max_concurrent_queries`, but nothing enforces it today.

### 5.4 Errors and retries

`error` is its own result and never counts as a pass or a fail. The adapters already raise typed errors ([errors.py](../../python-packages/dataing/src/dataing/adapters/datasource/errors.py)):

| Retry (Temporal policy, 3 attempts) | Fail fast, no retry |
|---|---|
| `ConnectionFailedError`, `ConnectionTimeoutError`, `QueryTimeoutError`, `RateLimitedError`, `ResourceExhaustedError` | `QuerySyntaxError`, `TableNotFoundError`, `ColumnNotFoundError`, `AccessDeniedError`, `InsufficientPermissionsError`, `AuthenticationFailedError` |

After 3 errors in a row, the check's owner is told the check is broken (§7.5).

### 5.5 Scheduling (EE)

- Each suite with a `schedule` gets one Temporal Schedule, with ID `check-suite-<suite_id>`. Sync creates, updates, pauses and deletes it.
- The overlap policy is SKIP: if a run is still going when the next is due, the next one is skipped.
- Jitter spreads out runs that are due at the same moment.
- Each firing starts a **dispatcher workflow**, which:
  - admits the occurrence exactly once, through a unique `(suite_id, scheduled_time)` admissions ledger;
  - creates the pinned run;
  - waits for it to finish, so overlap-skip covers the actual warehouse work.
- **Catch-up is Temporal's native behavior.**
  - `catchup_window` is the cron's longest gap between consecutive occurrences in its time zone, capped at 7 days: 1h for hourly, 72h for weekdays at 09:00.
  - So after any outage shorter than the cap, the latest missed occurrence is always inside the window.
  - With overlap SKIP, a backlog turns into a run that's in flight while the others are skipped, never a sequential replay.
  - There are no custom recovery records.
- A suite is scheduled only when all of these hold: it's active, it has a `schedule`, the tenant is entitled, and its datasource has an automation credential. Every run checks this again when it starts.
- "Run now" (UI and API) starts the same workflow directly with `trigger=manual`.

### 5.6 CLI (CE)

- `dataing checks validate <path>`: validates the schema and the references.
- `dataing checks run <path>`: runs the same compile, validate, execute and evaluate code without Temporal. Teams can call it from Airflow or cron, and engineers can use it to try checks locally.
- `dataing checks apply <path> --sha <commit>`: pushes suite files to a `check_sources` row of kind `api`. This is git-as-source-of-truth without the GitHub App.

## 6. GitHub App (EE)

### 6.1 Registration

- **SaaS:** one shared github.com app, configured through environment variables.
- **Self-hosted, on GHES or github.com:** each install registers its own app in one click with GitHub's [manifest flow](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest), because webhooks must point at that install.
  - The admin enters the host and org.
  - dataing sends them to `https://<host>/organizations/<org>/settings/apps/new` with the manifest (name, URLs, permissions, events, `request_oauth_on_install: true`).
  - GitHub returns a code. dataing exchanges it within 1 hour through `POST /app-manifests/{code}/conversions`, gets the app ID, private key and webhook secret, and stores them encrypted.
- API base URL: `https://api.github.com` or `https://<host>/api/v3`.

### 6.2 Installation

- The org admin picks repos on GitHub's install screen. With `request_oauth_on_install`, GitHub disables the Setup URL, so the install returns to dataing's **callback URL** with `code`, `installation_id` and `setup_action`.
- **Claim check:** GitHub warns that `installation_id` can be spoofed.
  - The installing user's OAuth token must list that installation in `GET /user/installations` (check every page). That alone isn't enough, because read-only collaborators see installations too.
  - So the user must also be an **org admin** of the installation's account, or the account owner for a personal installation.
    - The check uses an entry for that org ID in the paginated `GET /user/memberships/orgs`, with `state: active` and `role: admin`, so pending invitations don't count.
    - That endpoint needs no extra app permission. The single-org endpoint would need Members:read.
  - Only repositories the user can administer can become sources.
  - Claiming requires an admin session in dataing.
  - `(github_app_id, installation_id)` is unique.
- **States:** registration and installation each use a single-use, expiring `state`, stored server-side and tied to the user's session, the tenant, the app and the host.
- The admin then picks repo, folder and branch. This creates a `check_sources` row.

### 6.3 Permissions and events

- **Permissions:** Contents, Pull requests and Checks (read and write), plus Metadata (read). Never Administration.
- **Events:** `push`, `pull_request`, `installation`, `installation_repositories`, `check_run` and `check_suite`. GitHub's "Re-run" button sends `check_run`, and "Re-run all" sends `check_suite`.
- **Tokens:**
  - Installation tokens last 1 hour. Request them per repository, with only the permissions each job needs.
  - Cache them by installation, repositories and permissions, and refresh from `expires_at`.
  - Don't assume a token length.
- **API:** always send `X-GitHub-Api-Version: 2022-11-28`, the only version every supported GHES release accepts. GHES may have rate limits turned off, so the client must not require `X-RateLimit-*` headers.

### 6.4 Webhooks

- The endpoint is `POST /api/v1/github/webhooks/{app_id}`.
- dataing checks `X-Hub-Signature-256` against that app's webhook secret, computed over the **raw body** with a constant-time compare. **If there's no secret, the webhook is rejected.** It also checks that `X-GitHub-Hook-Installation-Target-ID` matches the app. On GHES, it checks that `X-GitHub-Enterprise-Host` matches the registered host.
- Redeliveries keep the same `X-GitHub-Delivery` GUID. So a `github_deliveries` table records each delivery's status for 30 days:
  - A completed delivery that arrives again starts nothing.
  - A failed one is processed again.
  - Handlers are idempotent.
  Temporal's workflow-ID reuse on its own isn't enough, because it only lasts as long as Temporal keeps the history.
- dataing replies 202 right away and hands the work to Temporal, which keeps it within GitHub's 10-second timeout.

### 6.5 Sync on merge

- **On push to the tracked branch:** webhooks only signal that something changed, because deliveries can arrive out of order.
  1. The sync, serialized per source, asks the GitHub API for the branch's **current head**.
  2. It reads the folder there, fetches and validates the changed files, and resolves imports.
  3. It applies the complete change set **in one transaction**. Renames keep a suite's identity, history and open issue.
  4. It re-checks the head before committing.
  5. It reconciles schedules.
- **Each file is handled on its own.** An invalid file keeps its suite's last good version, and the owner sees the file and line of the error. Other files still sync.
- **Missed webhooks:** every 10 minutes, dataing compares the branch head with `last_synced_sha`. GitHub does not redeliver failed webhooks, so this catches missed ones. It also covers installs that can't receive webhooks.

### 6.6 Pull request previews

Previews run on pull requests that target the tracked branch and touch the folder.

- **Validation:** results go into a Check Run called "dataing checks". Errors appear as annotations on the offending lines. Any invalid file gives the conclusion `failure`, so branch protection can block the merge.
- **Dry-run:** new and changed checks run against current data. This executes SQL nobody has reviewed yet, so it happens only when all of the following are true:
  - the pull request comes from a branch in the same repo, never a fork;
  - its author has write access to the repo;
  - the pull request will show pass or fail only, never metric values. Values stay in dataing, behind its own login;
  - the datasource has an automation credential (§5.2).

  Otherwise the preview only validates.
- A check that would fail on today's data is reported as `neutral`, not `failure`. It may be deliberately catching a problem that's happening now.
- **Previews execute an immutable snapshot** of the files at the PR head. It's stored separately (`check_preview_runs`) and never affects production versions, baselines, issues or schedules.
- **Conclusions** (failure beats neutral):
  - Any permanent execution error, including unknown errors, gives `failure`.
  - When execution isn't possible, the conclusion is `neutral`, with the reason.
  - `success` means everything was validated *and* executed.

### 6.7 Changes from dataing

- Codify and starter suites open pull requests from `dataing/<kind>-<id>` branches.
- dataing edits YAML with ruamel.yaml in round-trip mode, so comments and formatting survive.
- It commits through the Git Data API and never force-pushes.

### 6.8 New repos

GitHub's "Use this template" can't copy a github.com template into GHES. Instead:
1. The user creates a repo with just a README.
2. dataing's first pull request adds the folder layout, a `.vscode/settings.json` schema mapping, and a starter suite.

This works the same on both hosts.

### 6.9 Removed

- **Removed:** the pasted-token flow (`POST /git/repos`, whose tokens are stored unencrypted at [git_repos.py:168](../../python-packages/dataing/src/dataing/entrypoints/api/routes/git_repos.py)), the unused OAuth code in `adapters/git/github.py`, and `dataing git connect --token`.
- **Follow-up:** commit sync (fn-36) moves onto the push webhook.

**Trade-off:** a self-hosted install that uses github.com from behind a firewall can't receive webhooks. It still syncs through the 10-minute check, but gets no pull request previews.

### 6.10 Tables

| Table | Key columns |
|---|---|
| `github_apps` | tenant_id, host, api_base_url, app_id, slug, client_id, client_secret_encrypted, private_key_encrypted, webhook_secret_encrypted |
| `github_installations` | github_app_id, installation_id, account_login, account_type, tenant_id, suspended_at |

## 7. Failure loop

This applies to results from scheduled, manual and API runs. PR previews never open issues.

### 7.1 Incident model

Each check has at most one open issue.
- `source_provider = 'dataing_checks'`
- `source_fingerprint = '<suite_id>:<check_key>'`. This is how dataing finds the open issue for a check.
- `source_external_id = '<suite_id>:<check_key>:<first_failing_run_id>'`. This is unique per incident. The existing unique index on `(tenant_id, source_provider, source_external_id)` ignores status, so this is what lets a check open a new issue after an earlier one was resolved. The Soda integration keys on the check ID alone and gets blocked forever.

What happens on each result:
- **Fail, no open issue:** create one, with title, severity, `dataset_id` = native_path, and a link to the run. Then go to §7.2.
- **Fail, issue already open:** add an event with the new value. Don't start another investigation.

Guarantees:
- **One open issue per check:** a partial unique index on `source_fingerprint` covers issues that aren't finished, so two failing runs at the same moment create one issue.
- **Order:** a reducer, one per suite, applies each check's results in `seq` order to durable per-check incident state (`check_incident_state`).
  - A result that finishes early waits for the earlier ones, so a pass → fail edge is never lost, and a pass from an older run never resolves a newer failure.
  - The reducer consumes `run_finalized` events. Every finalized run carries a result or a skip marker for each check, including runs that crashed or were skipped, so no run can block the ones after it.
  - A person's status changes and system recovery both use conditional updates.
- **Flapping:** if a check fails again within a cool-down (default 24h) after auto-recovery, its last issue is reopened instead of opening a new one, and no second investigation starts.
- **Closed by a person:** if someone closes the issue while the check is still failing, a new issue opens only after the check passes and then fails again.

### 7.2 Routing

- Move `_evaluate_and_apply_policy` out of `routes/integrations.py` into an intake service. The webhook route and the runner both call it.
- Pass the suite's owner team to it. Today the policy always uses the tenant's oldest team ([team_policy_repository.py:493](../../python-packages/dataing/src/dataing/adapters/db/team_policy_repository.py)).
- Policy actions are unchanged: `auto`, `review`, `issue_only`.

### 7.3 Auto-investigation

This uses the suite's real datasource. The hard-coded placeholder UUID goes away ([integrations.py:519](../../python-packages/dataing/src/dataing/entrypoints/api/routes/integrations.py)).

The investigation runs as an `AutomationPrincipal` with `actor = investigation:<id>`. If the datasource has no automation credential, `auto` is downgraded to `review` (§5.2).

A failing check fills in the existing `AnomalyAlert` directly, so the investigation's reasoning steps don't change. Only the credential path changes:

| AnomalyAlert field | From the check |
|---|---|
| `dataset_ids` | `[native_path]` |
| `anomaly_type` | metric name (`null_rate`, `row_count`, `freshness_minutes`, `custom`, …) |
| `expected_value` / `actual_value` / `deviation_pct` | threshold or baseline / metric value / computed |
| `anomaly_date`, `severity` | run time, check severity |
| `source_system`, `source_alert_id`, `source_url` | `dataing_checks`, the incident external ID, a link to the Checks tab |
| `metadata` | check key, suite version SHA, compiled SQL hash |

### 7.4 Recovery

When a check passes again, dataing adds a "recovered" event. If the issue is still `open` or `triaged`, it's resolved automatically, with the resolution note "passed at run X". Otherwise it's left for whoever is assigned.

### 7.5 Warnings and broken checks

- `warn` results only appear in the UI.
- After 3 `error` results in a row from automated runs, dataing sends one notification per streak saying the check is broken, which is different from the data being wrong. No investigation starts.
  - If the automation credential is dead, that sends one notification for the datasource, not one per check.
  - In v1, notifications go tenant-wide and name the owner team, because notifications can't target a team yet.

### 7.6 Codify

- The main button becomes **"Add as check"**. On EE it opens a pull request against the dataset's suite file. On CE it shows YAML to copy.
- Checks are produced by the LLM writing `CheckSpec` directly as structured output. Each one is validated against the schema and dry-run before the pull request opens. This replaces keyword matching in `extract_tests_from_synthesis`.
- The dbt, Great Expectations and Soda downloads stay, now generated from `CheckSpec`.

### 7.7 Starter suite

1. "Draft checks" profiles the dataset with the built-in metrics: row count, per-column null rate and distinct count, min and max, and candidates for freshness and uniqueness.
2. The LLM gets the profile numbers and the JSON Schema, **never raw rows**, and drafts a suite.
3. dataing validates the draft and dry-runs it. Checks that would already fail are flagged: either the data has a real problem or the threshold is wrong.
4. On EE, dataing opens a pull request. On CE, it shows YAML to copy.

## 8. UI

- **Dataset page:** a **Checks** tab replaces the "Alerts coming soon" placeholder ([dataset-detail-page.tsx:314](../../frontend/app/src/features/datasets/dataset-detail-page.tsx)).
  - Each check shows its status, value against the threshold, a sparkline of recent values, and a link to any open issue.
  - The header has "Run now" and a link to the file at its SHA on GitHub.
  - With no suite, the tab offers "Draft checks".
- **Tabs in the URL:** tabs become controlled and use a `?tab=` parameter, so issues and notifications can link straight to a tab.
- **Run detail:** shows the compiled SQL, timing and errors for each check.
- **Settings → Git (EE):** register or install the app, pick repo, folder and branch, and see sync status and errors with file and line.
- **Settings → Datasource → Automation:** set, test or remove the automation credential, with a "use a read-only account" warning. The Checks tab explains when schedules are paused because this credential is missing.
- **Editing in v1** is "Edit on GitHub". Editing inside dataing, which would open pull requests, comes later.
- **CE users** see EE controls (schedules, Connect GitHub) with upgrade prompts, following the [CE/EE design](2026-01-09-ce-ee-reorganization-design.md).

## 9. CE vs EE

| Capability | CE | EE |
|---|---|---|
| Spec, JSON Schema, loader, compiler, runner | ✓ | ✓ |
| Manual "Run now", results history, Checks tab | ✓ | ✓ |
| CLI: `validate`, `run`, `apply` | ✓ | ✓ |
| Failure → issue → policy → investigation | ✓ | ✓ |
| Codify and starter suites | YAML to copy | Pull request |
| Schedules | Run the CLI from Airflow or cron | ✓ |
| GitHub App (github.com and GHES), sync, PR previews, dataing-opened PRs | | ✓ |

- New `Feature` flags `CHECK_SCHEDULES` and `GITHUB_APP`, on the enterprise plan.
- EE routes are mounted by `create_ee_app`. The backend returns 403 when the plan doesn't include them.

## 10. Fixes that are part of this work

1. **Deployments need an edition switch.** The Procfile and [Dockerfile.backend:81](../../infra/Dockerfile.backend) start the CE app. EE only runs through the justfile.
2. **Rescope Helm (fn-13).** Its spec leaves out Temporal and the frontend, and makes EE a non-goal. GHES customers need all three, plus an ingress route for `/api/v1/github/webhooks`.
3. **Replace and pin Temporal.** Compose uses `temporalio/auto-setup:latest`, and that image is now deprecated and unmaintained.
   - Compose should use pinned `temporalio/server` and `temporalio/admin-tools`.
   - Self-hosted installs should use Temporal's official Helm chart, which deploys only the server (you bring Postgres), or an external cluster.
4. **One encryption helper that refuses to start without a key.**
   - Fernet handling is copied across `core/credentials.py`, `models/data_source.py`, `adapters/datasource/encryption.py`, `routes/datasets.py`, `deps.py` and `temporal_worker.py`.
   - When the key variable is missing, some paths generate a random key ([deps.py:349](../../python-packages/dataing/src/dataing/entrypoints/api/deps.py)), and anything stored that way can't be decrypted after a restart.
   - GitHub App private keys will depend on this helper.
5. **The entitlement decorator must fail closed.** Today it skips the check when a route lacks `request` or `auth` ([entitlements.py:43](../../python-packages/dataing/src/dataing/entrypoints/api/middleware/entitlements.py)).

## 11. Testing

- **Unit:**
  - Sample YAML files: valid ones, and invalid ones with the expected file and line of each error.
  - Snapshots of the compiled SQL for Postgres, Snowflake, BigQuery, DuckDB and Trino.
  - Condition and baseline math.
  - The incident state machine for open, still failing, recovered and reopened.
- **Acceptance (DuckDB demo fixtures):**
  - For each fixture, run the suite on `baseline/` first, which must pass and also builds history. Then run it on the anomaly fixture, where the matching check must fail and the others must pass.

  | Fixture | Dataset | Check |
  |---|---|---|
  | `null_spike` | orders | `null_rate` on `user_id` |
  | `volume_drop` | events | `row_count`, 1-day window, `change_pct` against the baseline |
  | `duplicates` | order_items | `duplicate_count` on `[order_id, product_id]` |
  | `orphaned_records` | orders | `orphan_count` from `user_id` to `users.user_id` |
  | `late_arriving` | events | `sql`: count of rows where `inserted_at - created_at` exceeds 1 day |
  | `schema_drift` | products | `sql`: count of rows where `TRY_CAST(price AS DOUBLE)` is null but `price` isn't |

- **GitHub App:**
  - Recorded webhook payloads and a fake GitHub API (respx). Every test runs twice, once with the github.com base URL and once with `https://ghes.test/api/v3`.
  - Covers the manifest exchange, the installation claim check, signature checks (including rejecting when there's no secret), delivery de-duplication, and the preview rules for forks and non-writers. Values must never appear in PR output.
- **Temporal:**
  - Retries, timeouts and error vs fail use the time-skipping environment.
  - Schedule behavior (overlap skip, pause) needs `WorkflowEnvironment.start_local()`, because the time-skipping server can't create Schedules.
- **SQL snapshots** are also *executed* on DuckDB and Postgres in CI, not only compared as strings.
- **Fixture runs** set the run's `as_of` to the end of the fixture's simulation period, so `window` covers the fixture data.

## 12. Milestones (one engineer, about 9 weeks after plan review)

| # | Milestone | Size | Done when |
|---|---|---|---|
| 1 | Engine (CE), including the tracked migration runner | ~3 wks | A suite pushed with `dataing checks apply` runs from "Run now" (as a `UserPrincipal` through `QueryGateway`) and from `dataing checks run`, results show in the Checks tab, and the fixture acceptance test passes |
| 2 | Failure loop and automation credential (CE) | ~2 wks | Automation credentials and the audit changes are in. A failing check opens exactly one issue, routes by owner team, and starts an investigation on the real datasource as an `AutomationPrincipal`. Without an automation credential, `auto` is downgraded to `review`. Recovery resolves the issue. Codify and starter suites return YAML. Start after the tenant-isolation and failed-query fixes merge, because all three touch `temporal_worker.py` |
| 3 | Schedules and GitHub App (EE) | ~2.5 wks | Register, install, sync, preview and write-back work against the fake GitHub API for both hosts, and schedules run |
| 4 | Self-hosting for GHES | ~1.5–2 wks | `helm install` on kind brings up EE, Temporal and the frontend, webhooks reach the API, and versions are pinned. Can run in parallel with 1–3 |

Milestones 1 and 2 together deliver "define once, hit Run".

## 13. What the code survey found

These findings shaped the design:
- **Query errors.** The investigation worker turns them into "0 rows", and the activity drops the error ([temporal_worker.py:210](../../python-packages/dataing/src/dataing/entrypoints/temporal_worker.py), [execute_query.py:108](../../python-packages/dataing/src/dataing/temporal/activities/execute_query.py)). A fix is in flight.
- **The SQL renderer can't be reused for checks** ([renderers/sql.py](../../python-packages/dataing/src/dataing/renderers/sql.py)):
  - identifiers aren't quoted;
  - freshness uses Postgres-only `EXTRACT(EPOCH …)`;
  - result shapes are inconsistent;
  - values aren't escaped.
- **Nothing uses `QueryGateway`** ([gateway.py:80](../../python-packages/dataing/src/dataing/adapters/datasource/gateway.py)), and SQL is only validated on LLM output, never when it runs.
- **The git integration** is a pasted token stored unencrypted, sync is manual only, and synced commits never reach investigations.
- **Codify tracking never writes** because of a UUID bug.
- **Issue routing:**
  - policy always uses the oldest team;
  - there's a placeholder datasource UUID;
  - the dedup index ignores status;
  - `source_fingerprint` is never written.

Fixes in flight, each in its own worktree:
- tenant ownership on investigation routes and the worker's datasource lookup;
- query errors passed through as errors;
- the ad-hoc SQL route and fail-open EE webhook verification;
- the dataset Investigations tab query.

## 14. Later (out of scope for v1)

- Editing checks inside dataing, which would open pull requests
- Built-in schema and contract checks
- ML anomaly baselines
- Metric library parameters
- Per-check schedules
- Warehouse cost caps (bytes scanned, BigQuery dry-run)
- GitLab, Bitbucket and Azure DevOps
- Commit sync on the push webhook (fn-36)
- Moving investigations from integrations and automation rules onto `QueryGateway` with an `AutomationPrincipal` (§5.2)
- Data quality scorecards built from `check_results`
- A retention period for check results
- LLM data-egress controls for investigations

## 15. Open questions

1. **Minimum supported GHES version.** Decide in milestone 3. GitHub supports the 4 latest releases, which today is roughly 3.19–3.22; 3.19 loses support on 2026-12-09. Target the oldest release that is still supported when M3 ships.

## 16. Planning refinements (2026-09-26)

Code research and gap analysis for the Flow epic added these. None changes a decision in §1.

- **Time anchor.**
  - Each run has an `as_of` time (the workflow start time; `--as-of` in the CLI and tests).
  - `window` and freshness compile to literals computed from `as_of`.
- **Empty windows.**
  - Count metrics return 0.
  - Other aggregates return no value, which gives `warn` ("no rows in window").
  - `freshness_minutes` over an empty window gives `fail`.
- **Compiler details.**
  - Identifiers take their case from the catalog, which matters for Snowflake.
  - Tables are built from catalog parts, never by splitting `native_path`.
  - `orphan_count` uses `NOT EXISTS`. A NULL foreign key isn't an orphan, and `window`/`where` apply only to the checked dataset.
  - Multi-column distinct and duplicate counts compile to a grouped subquery, because BigQuery rejects `COUNT(DISTINCT a, b)`.
  - Division casts explicitly and uses `NULLIF`.
  - Custom SQL is parsed in the datasource's dialect and never transpiled.
- **Read-only validation** walks the whole SQL tree against an allowlist.
  - It rejects DML inside CTEs, `SELECT … INTO`, more than one statement, and dangerous functions such as `pg_sleep` and `dblink`.
  - The LIMIT rule is waived only for aggregates that return one row.
  - The real guard is still a read-only credential.
- **Error classes.** `QueryGateway` no longer turns any error containing "auth" into a credentials error; for example, a column named `author_id` must not trigger it. Fail-fast errors raise `ApplicationError(non_retryable=True)`.
- **Concurrency cap.**
  - A Redis ZSET holds the leases, managed by a Lua script and timed with Redis `TIME`.
  - The TTL is longer than the check timeout, and leases are renewed while the query runs.
  - If Redis is down, dataing refuses to run the query and raises a retryable error.
  - The CLI uses an in-process limiter.
  - `QueryGateway` gets a session that reuses one adapter for a whole suite run.
- **Races.**
  - `check_results` is unique on `(run_id, check_key)`.
  - Double-clicking "Run now" returns the run already in progress.
  - Syncs are serialized per source, and always resolve the branch head from the API (§6.5).
- **Sync details.**
  - Changed files are found by comparing blob SHAs.
  - Editing a metric library re-versions every suite that imports it.
  - A truncated Trees API response is handled.
  - YAML files are capped in size, anchors and aliases are rejected, and both `.yml` and `.yaml` are accepted.
  - If the folder doesn't exist, dataing offers the bootstrap PR instead of reporting an error.
- **Strict spec.**
  - Unknown keys, a check with no condition, and duplicate YAML keys are all errors.
  - Error line numbers are 1-based and never cause a 500.
  - Pydantic unions use callable discriminators, so a typo produces one error, not five.
- **PR previews.**
  - Files are fetched at the exact head SHA that was evaluated.
  - Previews for older head SHAs are cancelled.
  - Warehouse error text can contain row values, so a PR shows only the error class.
  - An invalid spec or a missing column gives `failure`; a transient error gives `neutral`.
- **Intake service.**
  - One service is used by the CE webhook, the EE webhook and the runner.
  - It adds a system-only transition from OPEN/TRIAGED to RESOLVED; users still can't make that move.
  - It enforces `MAX_INVESTIGATIONS_PER_MONTH`, which nothing enforces today. At the limit, `auto` becomes `review`.
  - It reuses `InvestigationStarterService`.
- **EE wiring.** `dataing-ee` gets a Temporal worker for sync, preview and delivery workflows. CE exposes hooks that EE implements, and a test checks that CE never imports `dataing_ee`.
- **Setup.**
  - `just demo` seeds a user credential and an automation credential for DuckDB, because `QueryGateway` requires credentials for every datasource.
  - `data_sources.key` is backfilled with distinct keys even when names repeat.
  - One suite per dataset is enforced across the whole tenant; a second source gets a sync error.
- **Codify.** When a new check's key matches an existing one, dataing asks instead of overwriting. Suites that came from an `api` source fall back to YAML. Edits start from the branch HEAD.
- **CLI.**
  - `dataing checks run <path>` stays local.
  - `dataing checks run --remote <suite>` starts a saved `api` run and exits non-zero on `fail` or `error`, which gives CE users scheduling through cron or Airflow.
  - The commands live where fn-55 puts the `dataing` console script. fn-55 and `dataing-cli` would both register one; coordinate before building.
- **Dependencies.** Add `ruamel.yaml>=0.19.1` and pin sqlglot to one minor version, because its minor releases can break compatibility.
- **Migrations.** Number 035 is already claimed on several branches, so take the next free number when merging.

## 17. Plan-review corrections (2026-09-26)

A chunked Codex review of the fn-69 task plan found 57 issues, 2 of them Critical. All of them are folded into the tasks. These are the ones that change the design; none changes a decision in §1.

- **Credential isolation (Critical).**
  - Today's gateway merge (`gateway.py:218-224`) keeps the base config's authentication, such as BigQuery's `credentials_json`, so a user credential could run as the service account.
  - Each adapter now declares which of its fields are authentication material, plus a credential schema.
  - Connection config strips all base authentication and injects only the principal's credential (fn-69.31).
- **GitHub claim authority (Critical).** Being listed in `/user/installations` isn't enough. The claimant must be an org admin (or the owner of a personal account), and only repositories they can administer can be bound (§6.2).
- **Execution boundary.**
  - Each run is one suite activity that owns the gateway session.
  - Results are saved as each check completes. Retries skip checks already done, and the audit actor is passed per query.
  - A run's version, `as_of` and `seq` are fixed when it's created, and its workflow ID is deterministic.
  - A reconciler moves stuck runs to a terminal status.
  - The executed SQL, dialect, baseline and flags are stored with each result.
- **Adapters and leases.**
  - Blocking drivers run off the event loop, and timeouts cancel the query in the warehouse (fn-69.32).
  - A lease can be renewed only while it's still held, and a lost lease cancels the query.
  - Capacity is released only after the query has stopped.
- **Spec and compiler.**
  - Library metric references are a separate check variant, handled through a `ResolvedSuite`.
  - Custom SQL must parse to exactly one statement, because `parse_one` silently truncates.
  - Metric semantics are defined in §3.6.
  - The validator's "scalar aggregate" rule is defined precisely.
- **API and CLI.**
  - Manual runs, which use the user's credentials and are preflighted with a 403, are separate from automation runs (`checks:automate` scope, 409 without an automation credential).
  - `apply` uses compare-and-swap on the source revision.
  - The dataset endpoint returns a bounded history.
  - The CLI's local mode uses a local history store and never needs the API, Postgres or Redis.
- **Uniqueness.** A DB partial unique index enforces one active suite per dataset across the tenant. Datasource keys are assigned when a datasource is created, and can be edited.
- **Intake and incidents.**
  - The investigation's intent, a stable ID and the quota reservation are written atomically. The workflow ID is the investigation ID, so a retried start can't create a second one.
  - Only OPEN and TRIAGED issues auto-resolve.
  - An ordered reducer applies results to durable incident state.
  - Notifications are deduplicated in the same transaction.
- **Investigations started by checks.**
  - The automation principal is passed through context gathering and schema lookup too.
  - `AnomalyAlert` now covers every case: it includes `metric_spec`, its numeric fields are optional with a `measurement` status, and it handles ranges and zero baselines.
- **Codify and exports.**
  - The LLM gets a structured input with no free-text synthesis, which keeps row values out (D8).
  - Exports have explicit semantics, and checks they can't express get a diagnostic (fn-69.33).
- **Starter suites.** Timestamps are profiled as epoch seconds. There are rules for picking a window, and a guard on row count.
- **EE wiring.** One shared dependency builder injects EE implementations into both the API and the worker. Every place a suite is activated or deactivated calls the hooks.
- **Schedules.** One desired-state rule decides everything, and every run checks it again when it starts. The reconciler compares Temporal's actual state with the desired state, and handles catch-up (§5.5).
- **Sync and previews.**
  - Every sync resolves the head through the API, and applies changes transactionally with rename handling.
  - A delivery ledger lasts beyond Temporal's retention.
  - Previews run immutable snapshots, and every possible result maps to an exact conclusion.
  - PR operations have stable IDs, and retries reconcile before acting.
  - Removing the PAT flow also removes the manual sync endpoint and the ORM fields that depended on it.
- **Deployment.**
  - Temporal starts in a fixed order, including namespace registration.
  - The Railway build installs EE.
  - Helm:
    - no pre-install migration hook, which deadlocks on the bundled Postgres;
    - Kubernetes-compatible upstreams for nginx;
    - pgvector required;
    - migrations that fail loudly, which first needs migration 008 fixed;
    - separate configuration for the SaaS and self-hosted GitHub App modes;
    - a named fn-13 integration task gating M4.
- **Demo.** The orphan check uses `users.user_id`. Demo suites don't depend on the clock, and `just demo` persists its first runs.

### 17.1 Round 2 of the plan review

Round 2 resolved 49 of the 57 findings. Revision 2 fixes the remaining ones, plus the new issues round 2 raised:

- **Unconfirmed remote queries hold capacity.** A BigQuery cancel returns before the job actually stops. So each execution registers its remote job ID, and its slot stays occupied until the warehouse confirms the job has ended. If that can't be confirmed, dataing fails closed.
- **The scalar rule** requires an aggregate in the outer SELECT scope, so `SELECT 1 FROM t` is rejected.
- **Run finalization** is one idempotent protocol, used by the workflow, cancellation and the reconciler. Every check in the pinned version gets a result or a marker, late writes are rejected, and a `run_finalized` outbox row feeds the incident reducer.
- **Deployment order:** `dataing checks apply` refuses a commit that isn't a descendant of the applied SHA (a stale CI job). Compare-and-swap handles concurrent applies.
- **CE automation keys:** an admin can issue keys scoped to `checks:automate`.
- **Intents:** investigation intents live in their own table, because `investigations.status` is a generated column. Workflow starts use REJECT_DUPLICATE and check `describe` before redispatching. Usage is counted for every way an investigation gets created, backfilled from this month's data.
- **Export polarity:** export predicates match `fail_when`, including the evaluator's NULL rules, and parity tests enforce it.
- **Schedules:** a dispatcher and admissions ledger bridge Schedules to pinned runs. Catch-up uses Temporal's missed and skipped counters, and the time-zone-aware cron.
- **GitHub membership check:** it uses the list endpoint and requires `state: active`.
- **Tracked migrations:** migrations are tracked and applied once each (fn-69.34), because replaying `001`, `007` and `013` either fails or destroys data.
- **`just demo`:** the fixtures are mounted into the API and worker, and there's an idempotent `bootstrap-checks` step.

### 17.2 Round 3 of the plan review

Round 3 confirmed the round-2 fixes. Revision 3 closes the remaining gaps:
- **Capacity is reserved before submission.** Every warehouse attempt is reserved under a local attempt token *before* it's submitted, and the reservation doesn't expire. After a crash, each attempt is resolved in one of three ways:
  - a preassigned ID (BigQuery);
  - a query tag (Snowflake, Trino);
  - the adapter's termination guarantee: in-process engines die with their worker, and Postgres and Snowflake enforce the statement timeout on the server.
- **A durable start claim.** Before a run starts, it's claimed with a compare-and-swap, so the reconciler can't finalize a run that's about to start, and an abandoned run can never start. Skipped runs are created and finalized in one transaction, and the reconciler recovers any row with `finalized_at IS NULL`.
- **One transaction per run in the reducer.** All of a run's incident effects, including intake and the cursor advance, commit in a single transaction.
- **An execution receipt for investigations.** Each investigation writes a receipt before its first side effect, so dispatch never runs an investigation twice, even after Temporal's retention period.
- **Catch-up** goes through `ScheduleHandle.trigger(overlap=SKIP)`, deduplicated by a unique recovery batch (§5.5).
- **The tracked migration runner (fn-69.34) now gates M1 deployment.** Demo seeds stay opt-in and separate, and are never baselined into production.

### 17.3 Round 4 of the plan review

M4 passed (SHIP). Revision 4:
- **Capacity is freed only on positive evidence**, never because time has passed:
  - BigQuery: `jobs.get`, and on a 404, "fencing" the job ID by inserting a trivial job with the same ID.
  - Postgres: no `pg_stat_activity` session for the attempt, and the connect deadline has passed.
  - Snowflake: `QUERY_TAG` history.
  - Trino: the attempt token goes in the query's `source`, because `system.runtime.queries` doesn't expose client tags.
  - Attempts that can't be resolved keep holding capacity. They're surfaced to admins, who can release them manually (audited).
  - Embedded engines (DuckDB, SQLite) use per-process limits only.
- **Workflow admission is a compare-and-swap** that races the reconciler's abandonment on the same row. Exactly one wins, and the dispatcher never revives an abandoned run.
- **Catch-up is native Temporal behavior** with the window sized to the cron's longest gap (§5.5). The custom recovery batches from revision 3 are removed.

### 17.4 Round 5 of the plan review: SHIP

All five review chunks returned SHIP (M4 in round 4; M1a, M1b, M2 and M3 in round 5). The four Minor suggestions were folded in without another round:
- Postgres confirms the attempt tag is set before sending any check SQL.
- A BigQuery slot is held until the fencing job itself is done.
- Catch-up discards occurrences by their individual age.
- Sparse crons (annual, leap-day) fall back to the 7-day window.
