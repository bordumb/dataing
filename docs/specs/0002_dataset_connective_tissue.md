# 0002: Dataset connective tissue: code, lineage, changes and analysis

**Status:** Draft, 2026-09-27

**Edition:** Mostly CE. Commit history and repository file listings are EE because they read repositories through the GitHub App (§8).

**Depends on:**
- [Checks as code](../plans/2026-09-26-checks-as-code-design.md): the GitHub App (EE), `?tab=` dataset tabs, and the single encryption helper
- PR #160: the dataset Investigations tab query

**Related:**
- [0001](0001_issue_chat.md): the issue agent uses the tools defined here
- [0003](0003_okf_knowledge_layer.md): reads knowledge bundles from the code links defined here

---

## 1. Summary

A data engineer builds dataset X and documents it in repo A. A data scientist analyzes X, and that analysis lives in repo B. Today, dataing knows neither. This spec makes every dataset page, and every agent, able to answer five questions:

- **How is it built?** Code and docs links, by role.
- **What feeds it, and what does it feed?** Real lineage.
- **What changed recently?** Commits and PRs that touched it.
- **Who analyzes it?** Analysis links and notebook usage.
- **What went wrong before?** Issues and confirmed root causes.

Most pieces already exist in the backend and aren't wired together. This spec wires them up, adds roles to repo links, and adds change matching.

---

## 2. Current state

Verified on main at `6e8812c8`. Paths are under `python-packages/dataing/src/dataing/` or `frontend/app/src/`.

| What the scenario needs | Today | Where |
|---|---|---|
| How X was made (repo A) | Links exist, but only the SDK and CLI create or read them; the frontend never calls them. Nothing reads repository files. `GET /datasets/{dataset_id}/repo` takes a name string while the sibling routes take UUIDs. Links aren't tied to connected repos. Re-importing a dbt manifest duplicates suggestions, because the unique index covers only confirmed rows. | `migrations/030_dataset_repo_mappings.sql`; `entrypoints/api/routes/repo_mappings.py`; `core/repo_mapping.py` |
| Lineage | Real adapters exist for dbt, OpenLineage/Marquez, Airflow, Dagster, DataHub, static SQL and a composite of them. The routes take provider settings as query parameters, with the OpenLineage namespace fixed to `default` and the dbt platform to `snowflake`. EE stores `lineage_providers` per tenant, but `get_tenant_lineage_adapter` is never called. Column lineage comes only from DataHub. dbt's `source_code_path` and OpenLineage's `sourceCodeLocation` are parsed but never linked to repos. | `adapters/lineage/adapters/`; `entrypoints/api/routes/lineage.py`; `entrypoints/api/deps.py`; EE `entrypoints/api/routes/settings.py` |
| Lineage on the page | The Lineage tab invents upstream and downstream tables from the table name. | `features/investigation/components/lineage-panel.tsx` |
| Engineering history | GitHub sync (pasted token, manual trigger) stores commit metadata and file names. It sets `raw_diff` to `None`, so `parse_affected_assets` returns nothing and no commit ever matches a dataset. `CodeChangesRepository.get_relevant_code_changes` is called only from tests. Its path match joins mappings on tenant alone and counts every glob as a match. PR columns are never written, and `PREnrichmentService` has no callers. | `adapters/git/github.py`; `core/git_asset_parser.py`; `adapters/db/code_changes.py`; `adapters/git/pr_enrichment.py` |
| Analysis work (repo B) | Links have no role, so an analysis repo looks the same as the code that builds the table. Nothing records notebooks, which users created SDK bundles, or queries by dataset. | `migrations/030_...`; `migrations/025_sdk_bundles_runs.sql` |
| Agents | The investigation agent has no tools. `gather_context` sets `lineage_info=None`. The workflow never passes code changes, although `agents/prompts/hypothesis.py` has a section for them. Comments and runbooks never reach a prompt. | `agents/client.py`; `temporal/activities/gather_context.py`; `temporal/workflows/investigation.py` |
| Dataset page | The Investigations tab queries columns that migration 013 dropped (PR #160 fixes this). The Knowledge tab says "Markdown supported" but renders plain text. Edit and delete APIs exist but have no UI. There is no Issues tab. Issues can't be filtered by dataset, and `issues.dataset_id` is free text. | `features/datasets/dataset-detail-page.tsx`; `features/datasets/components/knowledge-tab.tsx`; `routes/issues.py` |

**What's solid:**
- The mapping resolver: exact and glob patterns, priority, confidence and path templates.
- The lineage adapter layer: capability flags and composite merging.
- Threaded, voted comments.

---

## 3. Goals and non-goals

**Goals**

1. Each dataset page shows how the dataset is built, its lineage, recent changes, who analyzes it, and its issue history.
2. Links carry a role, and a dataset can link to any number of repos and paths.
3. The same context powers the investigation agent and the issue agent (0001).
4. One aggregate endpoint serves the page and the agents.

**Non-goals**

- Reading or rendering repository file contents and docs. That's 0003.
- Embeddings or semantic search.
- GitLab and Bitbucket. The GitHub App covers github.com and GHES.
- Column lineage beyond what DataHub already returns.
- Editing code from dataing.

---

## 4. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | Links have a **role**: `producer`, `docs`, `analysis`, `consumer` or `quality`. A dataset can have any number of links, including several in one repo. | The two-repo scenario needs "built here" and "analyzed here" to be different things. |
| D2 | **Exact links point at `datasets.id`.** Glob patterns remain for bulk rules and are resolved at read time. | Name strings drift and UUIDs don't. Globs are still the fastest way to map a whole schema. |
| D3 | **Lineage settings are per tenant** and stored encrypted, and routes stop taking provider settings as query parameters. Lineage is fetched live with a short cache; nothing is persisted in v1. | Settings passed per request can't carry credentials, and they leak configuration into URLs. |
| D4 | **Reading repositories** (commits, PRs, file listings) goes through the checks-as-code GitHub App, which is EE. CE keeps links, lineage, dbt manifest import and, from 0003, CLI push. | Checks as code D4 and D7 remove the pasted-token integration and put the App in EE. |
| D5 | **A commit matches a dataset** when it touches a linked file, touches the dbt model file for the dataset, or references the dataset in SQL in its diff. Each match records why. | Matches are explainable, and file links work even without diffs. |
| D6 | **Agents get this context through tools** and a bounded context section, not by pasting everything into prompts. | Prompts stay small and cacheable, and the agent asks for what it needs. |
| D7 | **The dataset page follows the `?tab=` convention** from checks as code §8. Its tabs are Overview, Schema, Lineage, Code & changes, Activity, Checks and Knowledge. | Both efforts share one layout, and issues can deep-link to a tab. |

---

## 5. Data model

Add one migration at the next free number:
- Use the current tenant key: `tenants(id)` today, `organizations(id)` once fn-59 lands.
- No `BEGIN`/`COMMIT` in the migration.

**`dataset_repo_mappings`** becomes the table of code links:
- Add `role TEXT NOT NULL DEFAULT 'producer' CHECK (role IN ('producer', 'docs', 'analysis', 'consumer', 'quality'))`.
- Add `dataset_id UUID REFERENCES datasets(id) ON DELETE CASCADE` for exact links. Require it unless the row is a glob rule: `CHECK (dataset_id IS NOT NULL OR pattern_type = 'glob')`.
- Add `repo_host TEXT NOT NULL DEFAULT 'github.com'` for GHES.
- Add `github_repository_id`, a nullable reference to the repository record the GitHub App creates. CE rows leave it empty.
- Add `note TEXT` and `created_by UUID`.
- Extend `source` with `lineage`, for suggestions from any lineage job's source-code URL.
- Replace the unique index with one that also covers unconfirmed rows, so manifest re-imports upsert instead of duplicating: `(tenant_id, COALESCE(dataset_id::text, dataset_pattern), repo_host, repo_owner, repo_name, COALESCE(file_path, ''), role)`.

**`code_change_datasets`** (new) replaces the always-empty `code_changes.affected_assets`:

```sql
CREATE TABLE code_change_datasets (
    code_change_id UUID NOT NULL REFERENCES code_changes(id) ON DELETE CASCADE,
    dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    match_kind TEXT NOT NULL CHECK (match_kind IN ('linked_file', 'dbt_model', 'sql_reference')),
    file_path TEXT,
    mapping_id UUID REFERENCES dataset_repo_mappings(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (code_change_id, dataset_id, match_kind)
);
```

**`issues`:**
- Rename the free-text `dataset_id` to `dataset_native_path`.
- Add `dataset_id UUID REFERENCES datasets(id)`, backfilled by matching the native path within the tenant.
- The API accepts either form.

**`sdk_bundles`:**
- Add `created_by_user_id UUID`.
- Add a join table, `sdk_bundle_datasets (bundle_id, dataset_id)`, filled by resolving each bundle's `assets`.

**Lineage settings:**
- Stored in the tenant settings store that EE already uses for `lineage_providers`.
- Credentials are encrypted with the single encryption helper from checks as code §10.4.
- The route that manages them moves to CE, because lineage is a CE feature.

---

## 6. Backend

### 6.1 `GET /datasets/{dataset_id}/context`

One call returns everything the page and the agents need. Each section carries `status: ok | empty | error | unavailable`, so one failing source never blanks the page. `unavailable` means the edition doesn't include that section.

| Section | Contents |
|---|---|
| `dataset` | Identity, datasource, description, and row and column counts |
| `code` | Links grouped by role: repo, path, branch, source, whether confirmed, and the last change |
| `lineage` | Upstream and downstream at depth 1: names, dataset ids when known, and each job with its `source_code_url` |
| `changes` | The last 10 matched commits and PRs, each with why it matched (EE) |
| `activity` | Open issues (count and top 5), the last 5 investigations with outcomes, and confirmed causes from 0001 |
| `checks` | A summary from checks as code, when present |
| `knowledge` | The top 5 comments by votes, plus knowledge documents once 0003 lands |
| `analysis` | Analysis links and recent notebook and SDK usage: who, and when |

Gate: ANY_USER. Each section also has its own route so tabs can page through it.

### 6.2 Code links

**Routes**, UUID-based and under `/api/v1`:

| Route | Gate |
|---|---|
| `GET /datasets/{dataset_id}/code-links` | ANY_USER |
| `POST /datasets/{dataset_id}/code-links` | SCOPE_WRITE |
| `PATCH /datasets/{dataset_id}/code-links/{link_id}` | SCOPE_WRITE |
| `DELETE /datasets/{dataset_id}/code-links/{link_id}` | SCOPE_WRITE |
| `POST /datasets/{dataset_id}/code-links/{link_id}/confirm` | SCOPE_WRITE |
| `POST /datasets/{dataset_id}/code-links/{link_id}/dismiss` | SCOPE_WRITE |

- The tenant-level `/dataset-repo-mappings` routes stay for glob rules and bulk import.
- The name-based `GET /datasets/{dataset_id}/repo` is replaced by the routes above.
- Every mutating route gets an entry in `POLICY` (`tests/unit/entrypoints/api/routes/test_route_authorization.py`).

**Resolver.** `resolve_all_repo_mappings` returns every link grouped by role instead of ranking down to one primary. Exact UUID links come first, then globs by priority and confidence.

**Suggestions.** People confirm or dismiss each one:
- **dbt manifest import:** role `producer`, `file_path` set to the model's original file. Re-imports upsert.
- **Lineage job source-code URLs,** including OpenLineage's `sourceCodeLocation`: role `producer`.

### 6.3 Lineage

- **Tenant settings everywhere:** every lineage route resolves its adapter with `get_tenant_lineage_adapter`. Provider query parameters are removed, and so is the fixed `default` namespace and `snowflake` platform; both come from settings.
- **Caching:** results are cached for 10 minutes per tenant, dataset, direction and depth.
- **Links to dataing:** lineage nodes are resolved to dataing datasets by datasource platform and name, so the graph links to dataset pages.
- **Source code:** job nodes show their `source_code_url`, which also feeds producer-link suggestions (§6.2).

### 6.4 Changes (EE)

This builds on the GitHub App. Checks as code §6.9 already says "commit sync moves onto the push webhook".

**Sync:**
- On a push to the tracked branch of a linked repo, fetch commits since `last_synced_sha`.
- For each commit, keep the changed file names (as today), and also fetch patches for files under linked paths or dbt model paths. Cap it at 50 files and 200 KB per commit.
- The 10-minute head check from checks as code §6.5 also covers commit sync.

**Matching:**
- Match each commit to datasets per D5, and store the matches in `code_change_datasets`.
- When a `pull_request` is merged, `PREnrichmentService` records the PR's number, title, URL and author.

**Fixes:**
- `CodeChangesRepository` joins mappings by dataset, not by tenant alone, and evaluates globs with `match_pattern`. Add regression tests for both bugs.
- The pasted-token commit sync is retired, as checks as code §6.9 removes it.

### 6.5 Analysis activity

- **Analysis links:** links with role `analysis`, for example `data-science/notebooks/orders/`. On EE, dataing lists the files under that path with their last commit (author, date, message), which shows who analyzed the dataset and when.
- **Notebook usage:** `%dataing attach` and SDK bundle creation record `created_by_user_id` and resolve the bundle's assets to datasets. The page shows "Used in notebooks by …".

### 6.6 Agents

**Investigations** (`gather_context` and prompts):
- `lineage_info` comes from the tenant adapter (upstream and downstream, depth 2) instead of `None`.
- Code changes for the datasets in scope, from a window before the anomaly (7 days by default), ranked by `CodeChangesRepository`. They are passed to hypothesis generation and synthesis, whose prompt section already exists.
- The most-voted knowledge comments, and confirmed causes of earlier issues on the same dataset (from 0001's outcome reviews).
- Everything is bounded (at most 20 changes and 10 comments) and cites its sources.

**The issue agent** (0001) gets four tools:
- `get_lineage(dataset, direction, depth)`
- `get_recent_changes(dataset, since)`
- `get_code_links(dataset)`
- `get_dataset_knowledge(dataset)`

### 6.7 Fixes included

- Land PR #160, which lists dataset investigations from the alert JSONB.
- **Knowledge tab:** render markdown with 0001's renderer, and add edit and delete to the UI (the APIs already exist).
- **Issues:** add a `GET /issues?dataset_id=` filter.
- Delete the mock `LineagePanel`.

---

## 7. Frontend

The dataset page uses controlled tabs with `?tab=`:

| Tab | Shows |
|---|---|
| Overview (default) | One card per `/context` section, each linking to its tab |
| Schema | Unchanged |
| Lineage | The real graph at depth 1 to 3. Clicking a dataset node opens its page; a job node links to its source code. If lineage isn't configured, the empty state links to lineage settings. |
| Code & changes | Links grouped by role, with add, edit, confirm and dismiss, plus pending suggestions. Recent changes with why each matched (EE). Analysis files and notebook usage. |
| Activity | Issues for this dataset (open first), investigations, and confirmed causes |
| Checks | From checks as code |
| Knowledge | Comments with markdown, edit and delete; knowledge documents arrive in 0003 |

**Settings → Lineage providers** (CE and EE): add, test and remove providers. Credentials are write-only.

---

## 8. CE vs EE

| Capability | CE | EE |
|---|---|---|
| Code links with roles; suggestions from dbt and lineage | ✓ | ✓ |
| Real lineage with tenant settings | ✓ | ✓ |
| Notebook and SDK usage | ✓ | ✓ |
| Agent context from lineage, links and knowledge | ✓ | ✓ |
| Commit and PR history; analysis file listings | | ✓ (GitHub App) |
| Agent context from changes | | ✓ |

---

## 9. Milestones

| # | Scope | Estimate |
|---|---|---|
| M1 | Truth on the page: <ul><li>real Lineage tab with tenant lineage settings in CE; mock removed</li><li>land PR #160</li><li>Knowledge tab markdown, edit and delete</li><li>issue dataset filter and the Activity tab</li><li>typed issue dataset</li></ul> | About 1.5 weeks |
| M2 | Code links with roles: <ul><li>migration and UUID routes</li><li>resolver by role</li><li>suggestions</li><li>Code & changes tab</li><li>`/context` and the Overview tab</li></ul> | About 1.5 weeks |
| M3 | Agents: <ul><li>lineage, knowledge and prior causes in `gather_context`</li><li>the four issue-agent tools</li></ul> | About 1 week |
| M4 (EE, after the GitHub App) | Changes: <ul><li>push-webhook sync and patches for linked paths</li><li>matching and PR metadata</li><li>analysis file listings</li><li>changes in agent context</li></ul> | About 1.5 weeks |
| M5 | Notebook and SDK usage attribution | About 0.5 week |

---

## 10. Testing

- **Resolver:**
  - exact links versus globs
  - roles
  - priority
  - UUID links taking precedence over patterns
- **Matching:**
  - linked file, dbt model file and SQL reference each match
  - a commit that touches no linked path matches nothing
  - regression tests for the tenant-only join and the always-matching glob
- **Lineage:**
  - adapter contract tests with recorded responses
  - encrypted settings
  - the cache
  - resolving nodes to datasets
- **`/context`:** each section fails independently, and sections outside the edition report `unavailable`.
- **Authorization:** `POLICY` entries for every new route.
- **Frontend:**
  - tabs with `?tab=`
  - the lineage graph from fixtures
  - editing code links
  - activity lists
- **Demo:** add a dbt manifest and a lineage fixture under `demo/`, so `just demo` shows real lineage and code links.

---

## 11. Coordination

- **Checks as code (fn-69):**
  - Provides the GitHub App, push-webhook sync, `?tab=` tabs, the Checks tab and the encryption helper.
  - Its §7.1 writes the native path into `issues.dataset_id`. That column becomes `dataset_native_path` plus a UUID `dataset_id`, so whichever change lands second adapts.
- **0001:** consumes the tools in §6.6 and provides confirmed causes.
- **0003:** finds knowledge bundles through the code links and their roles.
- **fn-59:** decides which tenant key new tables reference.

---

## 12. Open questions

1. **Commit history in CE.** Is it EE-only through the GitHub App, or should CE accept change events pushed from CI (for example `dataing changes push`)?
2. **Lineage settings.** Move them to CE, since the lineage adapters are CE?
3. **Roles.** Are `producer`, `docs`, `analysis`, `consumer` and `quality` enough?
4. **Default tab.** Should Overview be the default?

---

## 13. Code references

- `python-packages/dataing/migrations/030_dataset_repo_mappings.sql`, `032_git_repositories.sql`, `034_code_changes_pr_metadata.sql`
- `python-packages/dataing/src/dataing/core/repo_mapping.py`: `match_pattern`, `resolve_repo_mapping`, `resolve_all_repo_mappings`
- `python-packages/dataing/src/dataing/entrypoints/api/routes/repo_mappings.py`: mapping CRUD, dbt manifest import, `include_all`
- `python-packages/dataing/src/dataing/adapters/git/github.py`: commit sync with `raw_diff=None`
- `python-packages/dataing/src/dataing/core/git_asset_parser.py`: `parse_affected_assets`
- `python-packages/dataing/src/dataing/adapters/db/code_changes.py`: `CodeChangesRepository.get_relevant_code_changes`
- `python-packages/dataing/src/dataing/adapters/git/pr_enrichment.py`: `PREnrichmentService`
- `python-packages/dataing/src/dataing/entrypoints/api/routes/lineage.py`: `/providers`, `/upstream`, `/downstream`, `/graph`, `/column-lineage`, `/job/{job_id}`, `/job/{job_id}/runs`
- `python-packages/dataing/src/dataing/adapters/lineage/adapters/dbt.py` (`source_code_path`), `openlineage.py` (`sourceCodeLocation`), `datahub.py` (column lineage)
- `python-packages/dataing/src/dataing/entrypoints/api/deps.py`: `get_tenant_lineage_adapter`
- `python-packages/dataing-ee/src/dataing_ee/entrypoints/api/routes/settings.py`: `LineageProviderConfig`, `lineage_providers`
- `python-packages/dataing/src/dataing/temporal/activities/gather_context.py`: `lineage_info=None`
- `python-packages/dataing/src/dataing/agents/prompts/hypothesis.py`: `_build_code_changes_section`
- `python-packages/dataing/src/dataing/entrypoints/api/routes/datasets.py`: `GET /datasets/{dataset_id}`, `/investigations`
- `frontend/app/src/features/datasets/dataset-detail-page.tsx`, `components/knowledge-tab.tsx`, `components/comment-item.tsx`
- `frontend/app/src/features/investigation/components/lineage-panel.tsx`: mock lineage
- `docs/prompts/backend/lineage/github_unification.md`: the earlier `.datalink.yaml` brainstorm this supersedes, together with 0003
