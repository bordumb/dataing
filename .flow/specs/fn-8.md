# Enterprise MkDocs Documentation Site

## Overview

Create a production-ready, enterprise-grade documentation site for dataing using MkDocs with Material theme. The documentation should be 90% focused on `dataing` (the B2B platform), with a "How it Works" section explaining `maistro` and `bond` to prove engineering robustness.

## Scope

**In Scope:**
- Update existing `docs/mkdocs.yml` with enterprise Material theme config
- Create `docs/docs/stylesheets/extra.css` for visual polish
- Create comprehensive documentation structure:
  - `index.md` - Landing page (Value Prop)
  - `quickstart.md` - 5-minute DuckDB guide
  - `architecture.md` - High-level Core vs Adapters diagram
  - `concepts/` - Investigations, Agent Workflows (Maistro), Guardrails
  - `integrations/` - Warehouses, Lineage, Notifications
  - `security/` - Data Privacy, RBAC, Compliance

**Out of Scope:**
- Full API reference auto-generation (can add later)
- Blog section
- Versioning with mike
- i18n/translations

## Documentation Structure

```
docs/docs/
├── index.md                     # Landing page (AI Data Reliability Engineer)
├── quickstart.md                # "Connect DuckDB & Run" (5 min)
├── architecture.md              # High-level diagram of Core vs Adapters
├── concepts/
│   ├── investigations.md        # Gather -> Hypothesize -> Verify loop
│   ├── agent-workflows.md       # Maistro (Steps, Signals, FSM)
│   └── guardrails.md            # Safety (Validators, Circuit Breakers)
├── integrations/
│   ├── warehouses/              # dataing/adapters/datasource/sql/
│   │   ├── snowflake.md
│   │   ├── bigquery.md
│   │   ├── duckdb.md
│   │   └── postgres.md
│   ├── lineage/                 # dataing/adapters/lineage/
│   │   ├── dbt.md
│   │   └── datahub.md
│   └── notifications/           # dataing/adapters/notifications/
│       └── slack.md
├── security/
│   ├── data-privacy.md          # Read-only, metadata only
│   ├── rbac.md                  # dataing/services/auth.py
│   └── compliance.md            # SOC 2 / Self-Hosting
└── stylesheets/
    └── extra.css                # Enterprise polish
```

## Approach

### Phase 1: Foundation (Tasks 1-2)
1. Update `mkdocs.yml` with enterprise config and new nav structure
2. Create custom CSS for enterprise polish

### Phase 2: Core Pages (Tasks 3-5)
3. Create landing page with value proposition
4. Create quickstart guide (DuckDB focus)
5. Create architecture overview

### Phase 3: Concepts (Task 6)
6. Create concepts section (investigations, agent-workflows, guardrails)

### Phase 4: Integrations (Task 7)
7. Create integrations section (warehouses, lineage, notifications)

### Phase 5: Security (Task 8)
8. Create security section (data-privacy, rbac, compliance)

## Navigation Structure

```yaml
nav:
  - Home: index.md
  - Quickstart: quickstart.md
  - Architecture: architecture.md
  - Concepts:
      - "How Investigations Work": concepts/investigations.md
      - "The Agent Engine (Maistro)": concepts/agent-workflows.md
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

## Quick Commands

```bash
# Build docs
just docs

# Serve docs locally
just docs-serve

# Verify build succeeds
cd docs && mkdocs build --strict
```

## Acceptance Criteria

- [ ] `mkdocs build --strict` passes with no warnings
- [ ] All navigation tabs and sections render correctly
- [ ] Light/dark mode toggle works
- [ ] Custom CSS applies (admonitions, code blocks)
- [ ] Landing page clearly communicates value prop
- [ ] Quickstart can be completed in ~5 minutes
- [ ] Architecture diagram renders (Mermaid)
- [ ] All integration pages map to actual adapters
- [ ] Security pages reference actual safety code
- [ ] No broken internal links
- [ ] No Lorem Ipsum or placeholder content

## Source Code References

**Core Investigation:**
- `/dataing/src/dataing/core/investigation/steps/*.py`

**Safety/Guardrails:**
- `/dataing/src/dataing/safety/validator.py` - Query validation
- `/dataing/src/dataing/safety/circuit_breaker.py` - Rate limiting
- `/dataing/src/dataing/safety/pii.py` - PII detection

**Maistro Workflow Engine:**
- `/maistro/src/maistro/workflow.py` - Workflow executor
- `/maistro/src/maistro/step.py` - Step protocol
- `/maistro/src/maistro/signals.py` - Signal enum (CONTINUE, COMPLETE, SUSPEND)

**Adapters:**
- `/dataing/src/dataing/adapters/datasource/sql/` - Warehouse adapters
- `/dataing/src/dataing/adapters/lineage/` - Lineage providers
- `/dataing/src/dataing/adapters/notifications/` - Notification adapters

**Auth:**
- `/dataing/src/dataing/services/auth.py` - Authentication service

## Open Questions

1. Which integrations should be marked as "Beta" vs "GA"?
2. Should we include document DBs (MongoDB, DynamoDB) in initial launch?
3. What specific compliance certifications are in progress?
