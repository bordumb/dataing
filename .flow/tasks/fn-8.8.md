# fn-8.8 Create integrations section (warehouses, lineage, notifications)

## Description

Create the integrations section documenting supported warehouses, lineage providers, and notifications.

### Create Files

**Warehouses:**
- `docs/docs/integrations/warehouses/snowflake.md`
- `docs/docs/integrations/warehouses/bigquery.md`
- `docs/docs/integrations/warehouses/duckdb.md`
- `docs/docs/integrations/warehouses/postgres.md`

**Lineage:**
- `docs/docs/integrations/lineage/dbt.md`
- `docs/docs/integrations/lineage/datahub.md`

**Notifications:**
- `docs/docs/integrations/notifications/slack.md`

### Warehouse Page Template

Each warehouse page should include:
1. **Prerequisites:** Account requirements, permissions needed
2. **Configuration:** Environment variables, connection string
3. **Example:** Tabbed code showing CLI and Python SDK
4. **Supported Features:** Table of what's supported
5. **Troubleshooting:** Common issues

### Lineage Page Template

1. **What It Enables:** Upstream/downstream understanding
2. **Setup:** How to upload manifest.json (dbt) or connect API
3. **Integration Points:** How it enriches investigations

### Notification Page Template

1. **Setup:** Webhook URL, API token
2. **Message Format:** What gets sent
3. **Customization:** Filtering, channels

### Source Code References

- `/dataing/src/dataing/adapters/datasource/sql/snowflake.py`
- `/dataing/src/dataing/adapters/datasource/sql/bigquery.py`
- `/dataing/src/dataing/adapters/datasource/sql/duckdb.py`
- `/dataing/src/dataing/adapters/datasource/sql/postgres.py`
- `/dataing/src/dataing/adapters/lineage/dbt.py`
- `/dataing/src/dataing/adapters/lineage/datahub.py`
- `/dataing/src/dataing/adapters/notifications/slack.py`
## Acceptance
- [ ] All warehouse pages exist (snowflake, bigquery, duckdb, postgres)
- [ ] All lineage pages exist (dbt, datahub)
- [ ] Slack notification page exists
- [ ] Each page has prerequisites, configuration, example
- [ ] Tabbed code blocks for CLI vs Python
- [ ] Source code references are accurate
- [ ] Navigation renders all integration pages
- [ ] No broken internal links
## Done summary
- Created comprehensive integrations section with 7 documentation pages
- Warehouses (4 pages): snowflake.md, bigquery.md, duckdb.md, postgres.md
  - Each includes prerequisites, permissions, env vars, Python SDK, features table
- Lineage (2 pages): dbt.md (manifest.json, column lineage), datahub.md (GraphQL, cross-platform)
- Notifications (1 page): slack.md (webhook setup, message format, filtering)
- All pages use tabbed code blocks for env vars, SDK, CLI
- Troubleshooting sections for common issues
- Build passes with `mkdocs build --strict`
## Evidence
- Commits: 7417e8ab7871809484ed7bb977a2047bcc320d89
- Tests: mkdocs build --strict
- PRs:
