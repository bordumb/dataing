# 0003: Knowledge layer on the Open Knowledge Format (OKF)

**Status:** Draft, 2026-09-27

**Edition:**
- CE: ingest by CLI push, dataset pages, agents and export.
- EE: automatic sync on merge through the GitHub App.

**Depends on:**
- [0002](0002_dataset_connective_tissue.md): dataset identity and link roles
- [Checks as code](../plans/2026-09-26-checks-as-code-design.md): the GitHub App (EE)

**Related:**
- [0001](0001_issue_chat.md): the issue agent searches knowledge, and confirmed causes are exported
- `docs/prompts/backend/lineage/github_unification.md`: the unbuilt `.datalink.yaml` idea that OKF replaces

**Spec:** OKF v0.2, [`okf/SPEC.md`](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf) in `GoogleCloudPlatform/knowledge-catalog` (Apache-2.0).

---

## 1. Summary

Engineering and analysis repos keep knowledge about datasets next to their code, as OKF bundles: markdown files with YAML frontmatter. dataing:
- ingests those bundles
- attaches each document to the datasets it describes
- shows documents on the dataset page with their trust level and freshness
- gives them to agents with their provenance
- exports what dataing itself learns (dataset summaries, confirmed root causes) back as OKF

Git stays the source of truth. dataing reads, indexes and writes back only through export.

---

## 2. Why OKF, and what it doesn't cover

OKF is an open format published by Google Cloud in June 2026. It's now at v0.2.

**What the format defines:**
- **Bundles and concepts:** a bundle is a folder of markdown files, and each file is one "concept" (a table, metric, analysis, runbook and so on). A concept's id is its path.
- **Required field:** only `type`. `title`, `description`, `resource` (the URI of the asset described) and `tags` are recommended.
- **Provenance:** `sources` lists what a concept was derived from, with optional credibility signals (`author`, `usage_count`, `last_modified`). Individual claims cite sources through footnotes.
- **Trust:** `generated: {by, at}` and `verified: [{by, at}]`. These yield three tiers: unverified, machine-confirmed, and human-reviewed (any `human:` verifier).
- **Lifecycle:** `status` is `draft`, `stable` (the default) or `deprecated`. `stale_after` is an absolute timestamp.
- **Links:** ordinary markdown links form a graph. Links are untyped, and broken links are allowed.
- **Reserved files:** `index.md` for listings and `log.md` for history. The root `index.md` may declare `okf_version`.
- **Conformance (§11):** consumers must not reject a bundle for missing optional fields, unknown types, unknown keys or broken links. They should also preserve unknown keys.

**Why use it here:**
- It is the open-standard version of the `.datalink.yaml` idea already brainstormed in this repo.
- Repos can carry it without any dataing tooling.
- Other tools, including Google's Knowledge Catalog, can read the same files.

**What it doesn't cover, and how this spec handles that:**
- **Lineage:** out of scope for OKF v0.2 (§5.1). Lineage stays with the adapters (0002).
- **Dataset identity:** OKF has no standard for it. §4 D3 defines how dataing resolves `resource`.
- **Relationship types:** links carry none. dataing takes "engineering vs analysis" from the role of the knowledge source (D4).
- **Stability:** the format is young; v0.1 to v0.2 had breaking changes within about four months. dataing handles this by declaring the versions it supports and reading anything else best-effort (§7.3).

---

## 3. Goals and non-goals

**Goals**

1. Ingest OKF bundles from repos: by CLI push (CE and EE) or GitHub App sync (EE).
2. Attach documents to datasets and show them on the dataset page, grouped by the role of their source.
3. Show the trust tier, status and staleness exactly as OKF defines them.
4. Give agents trust-ranked knowledge with provenance.
5. Export dataing's own knowledge as a conformant bundle.

**Non-goals**

- Running Attested Computations (OKF §10). They are recorded, never executed.
- Editing OKF inside dataing. People edit in the repo.
- Embeddings or semantic search in v1. v1 uses keyword search plus dataset matching.
- Non-markdown sources such as Confluence or Notion.

---

## 4. Decisions

| # | Decision | Why |
|---|---|---|
| D1 | **Knowledge lives in git, next to code.** dataing reads it and indexes it; it is not the source of truth. | The same principle as checks as code D2: review, history and ownership come from pull requests. |
| D2 | **Two ways in.** `dataing knowledge push <dir>` from CI works on CE and EE and with any git host. The EE GitHub App syncs on merge. | CE gets knowledge without the App, and GitLab users aren't locked out. |
| D3 | **Dataset identity.** `resource` and `sources[].resource` resolve in this order: <ol><li>`dataing://datasets/<uuid>`</li><li>an OpenLineage-style URI, `<namespace>/<name>` (for example `postgres://warehouse:5432/analytics.public.orders`), the recommended form</li><li>platform console URLs, such as BigQuery's `?p=&d=&t=`</li><li>a bare `schema.table` inside the source's default datasource</li></ol> Unresolved documents go to an "Unlinked" list for manual linking. | Authors need one documented form. The lineage adapters already speak OpenLineage naming, and Google's reference bundles use console URLs. |
| D4 | **A document's section on the dataset page comes from its source's role** (0002 D1): `producer` and `docs` show under "How it's built", `analysis` under "Analysis", `quality` under "Quality". Documents with no role are grouped by `type`. | OKF links carry no type, and the repo a document came from says what it is. |
| D5 | **Trust, status and staleness are computed exactly per OKF §5.3 to §5.5.** dataing stores no credibility score of its own. | OKF's reasoning (§5.1): a score is subjective, doesn't transfer between tools, and goes stale. |
| D6 | **Repo content is untrusted input.** <ul><li>Rendering is sanitized.</li><li>Size is capped.</li><li>Nothing in a bundle is executed.</li><li>Agents receive it as quoted data with provenance.</li></ul> | Bundles can be written by anyone with repo access, and by agents. |
| D7 | **Export marks dataing-written content** `generated.by: dataing/<version>`. A person's confirmation adds `verified: human:<id>`. | Consumers can tell machine-written from human-reviewed knowledge. |

---

## 5. Authoring conventions

These are recommendations published in dataing's docs; OKF itself allows any layout.

Repo A (engineering):

```
okf/
  index.md                  # frontmatter: okf_version: "0.2"
  tables/
    orders.md
  pipelines/
    orders_daily.md
```

```markdown
---
type: Table
title: orders
description: One row per completed customer order.
resource: postgres://warehouse:5432/analytics.public.orders
tags: [sales]
status: stable
generated: { by: human:maya, at: 2026-09-20T10:00:00Z }
verified: { by: human:maya, at: 2026-09-20T10:00:00Z }
---

# How it's built
Built nightly by [orders_daily](/pipelines/orders_daily.md) from `raw.app_events`.

# Gotchas
`status` is lowercase; `app_v2` wrote `COMPLETE` between 2026-09-14 and 2026-09-16.
```

Repo B (analysis):

```markdown
---
type: Analysis
title: Q3 churn by acquisition channel
description: Churn is 2x higher for app_v2 signups.
sources:
  - id: orders
    resource: postgres://warehouse:5432/analytics.public.orders
  - id: nb
    resource: https://github.com/acme/data-science/blob/main/notebooks/churn_q3.ipynb
generated: { by: human:raj, at: 2026-09-22T15:00:00Z }
stale_after: 2026-12-31T00:00:00Z
---
```

dataing groups these `type` values on the page: `Table`, `View`, `Pipeline`, `Model`, `Metric`, `Analysis`, `Notebook`, `Dashboard`, `Runbook`, `Known Issue` and `Reference`. Other types are accepted and shown as generic documents, as OKF requires.

---

## 6. Data model

Add one migration at the next free number:
- Use the current tenant key: `tenants(id)` today, `organizations(id)` once fn-59 lands.
- No `BEGIN`/`COMMIT` in the migration.

```sql
CREATE TABLE knowledge_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('github_app', 'cli_push')),
    repo_host TEXT NOT NULL DEFAULT 'github.com',
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    root_path TEXT NOT NULL DEFAULT 'okf',
    branch TEXT NOT NULL DEFAULT 'main',
    role TEXT NOT NULL CHECK (role IN ('producer', 'docs', 'analysis', 'consumer', 'quality')),
    default_datasource_id UUID,
    okf_version TEXT,
    last_ingested_sha TEXT,
    last_ingested_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'error')),
    error TEXT,
    UNIQUE (tenant_id, repo_host, repo_owner, repo_name, root_path, branch)
);

CREATE TABLE knowledge_concepts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    concept_id TEXT NOT NULL,                -- path without .md (OKF concept id)
    type TEXT NOT NULL,
    title TEXT,
    description TEXT,
    resource TEXT,
    tags TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'stable',
    stale_after TIMESTAMPTZ,
    generated JSONB,
    verified JSONB NOT NULL DEFAULT '[]',    -- always a list (bare mapping normalized)
    sources JSONB NOT NULL DEFAULT '[]',
    extra JSONB NOT NULL DEFAULT '{}',       -- unknown frontmatter keys, preserved
    body_md TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    commit_sha TEXT NOT NULL,
    search TSVECTOR,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, concept_id)
);
CREATE INDEX knowledge_concepts_search ON knowledge_concepts USING GIN (search);

CREATE TABLE knowledge_links (
    from_concept_id UUID NOT NULL REFERENCES knowledge_concepts(id) ON DELETE CASCADE,
    target_path TEXT NOT NULL,
    to_concept_id UUID REFERENCES knowledge_concepts(id) ON DELETE SET NULL,
    PRIMARY KEY (from_concept_id, target_path)
);

CREATE TABLE knowledge_concept_datasets (
    concept_id UUID NOT NULL REFERENCES knowledge_concepts(id) ON DELETE CASCADE,
    dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    match_kind TEXT NOT NULL CHECK (match_kind IN ('resource', 'source', 'link', 'manual')),
    matched_uri TEXT,
    PRIMARY KEY (concept_id, dataset_id)
);

CREATE TABLE knowledge_ingest_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,
    commit_sha TEXT NOT NULL,
    path TEXT NOT NULL,
    line INTEGER,
    severity TEXT NOT NULL CHECK (severity IN ('error', 'warning')),
    message TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 7. Ingest

### 7.1 Triggers

- **CLI push, CE and EE:** CI in the repo runs:

  ```
  dataing knowledge push ./okf --repo acme/data-pipelines --branch main --role producer
  ```

  1. The CLI packages the directory.
  2. It uploads to `POST /api/v1/knowledge/sources/push`, sending the tarball, the commit SHA, the repo, the path, the branch and the role. The call needs SCOPE_WRITE with an API key.
  3. The server creates or updates the `knowledge_sources` row.
- **GitHub App, EE:** admins register knowledge sources in Settings → Knowledge (repo, folder, branch, role), the same pattern as `check_sources` in checks as code §6.2. A push to the tracked branch that touches the folder triggers a sync. The 10-minute head check (§6.5 there) catches missed webhooks.

### 7.2 Pipeline

`IngestKnowledgeSource` is a Temporal workflow, serialized per source and idempotent per commit SHA.

1. **Fetch.**
   - CLI: unpack the uploaded tarball.
   - App: read the folder at the branch head.
   - Caps: 5,000 files, 20 MB per bundle, 1 MB per file.
2. **Parse** every non-reserved `.md` file.
   - Use a safe YAML loader with no custom tags.
   - Normalize a bare `verified` mapping into a one-element list.
   - Keep unknown keys in `extra`.
3. **Check conformance** (OKF §11): parseable frontmatter and a non-empty `type`. Everything else produces a warning, never a rejection.
4. **Store:**
   - upsert by `concept_id`
   - delete documents whose files are gone
   - fill the `search` tsvector from title, description and body
5. **Resolve:**
   - markdown links into `knowledge_links`
   - `resource` and `sources[].resource` into `knowledge_concept_datasets`, following D3
6. **Record findings** with file and line.

Each file is handled independently: one bad file doesn't block the rest, which matches checks as code §6.5.

### 7.3 Versions

- Supported: `0.2`, plus `0.1` read through the upgrade rules in OKF §13.
- An unknown `okf_version` produces a warning and a best-effort read, as OKF §12 asks.

---

## 8. Reading

**Dataset page, Knowledge tab** (0002 §7):
- Sections per D4, with comments kept alongside.
- **Each document card shows:**
  - title, type and description
  - trust tier badge
  - status
  - a "stale" badge when `now >= stale_after`
  - source (repo, path and commit, linked to GitHub)
  - last update
- **Opening a document** renders its markdown with 0001's sanitized renderer. Cross-links resolve to dataing pages when the target was ingested, and to GitHub otherwise. Footnotes keyed to `sources[].id` render as citations.

**Settings → Knowledge:**
- sources with their last sync
- findings with file and line
- "Unlinked" documents, with a "link to dataset" action

**API** (read: ANY_USER; manual linking: SCOPE_WRITE):

| Route | Purpose |
|---|---|
| `GET /datasets/{dataset_id}/knowledge` | Documents and comments for a dataset |
| `GET /knowledge/concepts/{concept_id}` | One document |
| `GET /knowledge/search?q=&dataset_id=` | Postgres full-text search |
| `POST /knowledge/concepts/{concept_id}/datasets` | Link a document to a dataset by hand |
| `GET /knowledge/sources` | Sources, with their findings |

---

## 9. Agents

- **Tools** for the issue agent (0001): `search_knowledge(query, dataset_id?)` and `get_concept(concept_id)`.
- **Investigations:** `gather_context` (0002 §6.6) adds the top documents for the datasets in scope.
- **Ranking,** in order:
  1. a dataset match
  2. trust tier (human-reviewed, then machine-confirmed, then unverified)
  3. not stale
  4. `stable` before `draft`
  5. most recent

  Deprecated documents are left out unless asked for.
- **Presentation:** documents reach the model as quoted data blocks. Each carries its provenance (repo, path and commit; trust tier; `generated` and `verified`) and an instruction that the content is reference material, never instructions.
- **Citations:** replies cite documents, and the UI turns the citations into links.

---

## 10. Export

`GET /api/v1/knowledge/export?dataset_id=…` (or every dataset) returns a `.tar.gz` bundle that conforms to OKF v0.2:

| Path | Type | Content |
|---|---|---|
| `index.md` | (reserved) | `okf_version: "0.2"` and a listing |
| `datasets/<datasource>/<schema>/<table>.md` | `Table` | Schema, owners and description. `resource` gives both the dataing URI and the OpenLineage-style URI. Code links from 0002 appear as `sources`. |
| `known-issues/<issue-number>.md` | `Known Issue` | A confirmed root cause from 0001, with the evidence queries as `references/` entries. `generated.by: dataing/<version>`; `verified` names the person who confirmed it. |
| `log.md` | (reserved) | The export history |

- The export is validated with the same parser as ingest before it's returned.
- **Later (EE):** open the export as a pull request into a chosen knowledge repo through the GitHub App, using the mechanics in checks as code §6.7.

---

## 11. CLI

- `dataing knowledge validate <dir> [--datasource <id>]`: the ingest parser and conformance checks, run locally. It exits non-zero on errors. With `--datasource`, it also warns about any `resource` that won't resolve.
- `dataing knowledge push <dir> --repo --branch --role`: see §7.1.

Both live in `python-packages/dataing-cli`.

---

## 12. Security

- **Parsing:** safe YAML, size caps, and no execution of anything in a bundle. Attested Computation `executor` and `attester` fields are stored, inert.
- **Rendering:** markdown is sanitized, and links are limited to `http`, `https` and relative paths.
- **Access:** push requires an API key with write scope. Sources are isolated per tenant.
- **Prompt injection:** documents reach agents as data, and agents have no write tools (0001 D5).

---

## 13. Milestones

| # | Scope | Estimate |
|---|---|---|
| M1 | CE core: <ul><li>parser and validator</li><li>`dataing knowledge validate` and `push`</li><li>storage and dataset resolution</li><li>Knowledge tab sections</li><li>Settings → Knowledge with findings and Unlinked</li></ul> | About 1.5 weeks |
| M2 | Agents: search and document tools, investigation context, citations | About 1 week |
| M3 (EE) | GitHub App sync for knowledge sources | About 1 week |
| M4 | Export: download, and known issues from confirmed causes | About 1 week |

---

## 14. Testing

- **Parser and conformance:**
  - OKF's spec examples
  - Google's sample bundles from `okf/bundles/` as fixtures (Apache-2.0, keep the license notice)
  - edge cases: a bare `verified` mapping; unknown types and keys preserved; broken links tolerated; reserved files; a missing `index.md`; an unknown `okf_version`
- **Resolution:** each URI form in D3, and the Unlinked list.
- **Ingest:**
  - pushing the same SHA twice is idempotent
  - one bad file doesn't block the others
  - documents are deleted when their files are removed
  - caps are enforced
- **Trust:** tier, status and staleness computed against the OKF rules, as table-driven tests.
- **Export:** the round trip export → validate → ingest reproduces the same documents.
- **Agents:** ranking unit tests. Tool tests use pydantic-ai's `TestModel`.
- **Authorization:** `POLICY` entries for the new mutating routes.

---

## 15. Open questions

1. **Dataset URI.** Is the OpenLineage-style form (D3) the one to recommend to authors?
2. **Attested Computations.** Should a checks-as-code metric (checks as code §3.3) later be able to reference an OKF Attested Computation?
3. **Export destination.** Download only in v1, with EE pull requests later?
4. **Exporting comments.** Should highly voted comments be exported too, or only confirmed and verified content?

---

## 16. References

- OKF v0.2: `SPEC.md` in [GoogleCloudPlatform/knowledge-catalog/okf](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf). The sections used here are §3 (bundle structure), §4.1 (frontmatter), §5 (provenance, trust, lifecycle), §6 (links), §10 (attested computations), §11 (conformance) and §12 (versioning).
- [How the Open Knowledge Format can improve data sharing](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing), Google Cloud blog
- [Checks as code](../plans/2026-09-26-checks-as-code-design.md): §6 GitHub App, §6.5 sync on merge, §6.7 dataing-opened PRs
- `docs/prompts/backend/lineage/github_unification.md`: the `.datalink.yaml` brainstorm
- `python-packages/dataing-cli`: CLI home for `knowledge validate` and `push`
