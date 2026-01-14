# fn-8.1 Update mkdocs.yml with enterprise Material theme config

## Description

Update the existing `docs/mkdocs.yml` to add enterprise-grade Material theme configuration with the new comprehensive navigation structure.

### Navigation Structure to Implement

```yaml
nav:
  - Home: index.md
  - Quickstart: quickstart.md
  - Architecture: architecture.md
  - Concepts:
      - "How Investigations Work": concepts/investigations.md
      - "The Agent Engine (Maestro)": concepts/agent-workflows.md
      - "Safety & Guardrails": concepts/guardrails.md
  - Integrations:
      - Warehouses:
          - Snowflake: integrations/warehouses/snowflake.md
          - BigQuery: integrations/warehouses/bigquery.md
          - DuckDB: integrations/warehouses/duckdb.md
          - Postgres: integrations/warehouses/postgres.md
      - Lineage:
          - dbt: integrations/lineage/dbt.md
          - DataHub: integrations/lineage/datahub.md
      - Notifications:
          - Slack: integrations/notifications/slack.md
  - Security:
      - "Data Privacy": security/data-privacy.md
      - "RBAC & SSO": security/rbac.md
      - "Compliance": security/compliance.md
```

### Theme Features to Add

1. **Navigation Features:**
   - `navigation.instant` and `navigation.instant.prefetch` for SPA feel
   - `navigation.tabs` and `navigation.tabs.sticky` for top-level tabs
   - `navigation.sections` and `navigation.top`
   - `search.suggest`, `search.highlight`, `search.share`
   - `content.code.copy` and `content.tabs.link`

2. **Typography:**
   - `font.text: Inter`
   - `font.code: JetBrains Mono`

3. **Fix Issues:**
   - Update mkdocstrings `paths` from `../backend/src` to `../dataing/src`
   - Add `extra_css: [stylesheets/extra.css]`

### Files to Modify

- `docs/mkdocs.yml` - Main configuration

### References

- Existing config: `/docs/mkdocs.yml`
- Material docs: https://squidfunk.github.io/mkdocs-material/setup/
## Acceptance
- [ ] `mkdocs build --strict` passes in `docs/` directory
- [ ] Navigation tabs visible at top of page
- [ ] Tabs remain sticky on scroll
- [ ] Light/dark mode toggle works
- [ ] Inter font loads for body text
- [ ] JetBrains Mono font loads for code blocks
- [ ] Copy button appears on code blocks
- [ ] Search suggestions appear when typing
- [ ] `extra_css` points to `stylesheets/extra.css`
- [ ] mkdocstrings path is `../dataing/src` (not `../backend/src`)
## Done summary
- Updated mkdocs.yml with enterprise Material theme features (tabs, fonts, extensions)
- Fixed mkdocstrings path from ../backend/src to ../dataing/src
- Added comprehensive nav structure with all new documentation sections
- Created placeholder files for all nav items to enable build success
- Build passes with `mkdocs build --strict`
## Evidence
- Commits: b68b6a91244063fc7d90fd21fda048c450b77ee7
- Tests: mkdocs build --strict
- PRs:
