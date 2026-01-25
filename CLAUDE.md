# CLAUDE.md

We are pre-launch. Optimize for forward progress and quality; do not preserve legacy
behavior unless the request calls for it.

DO NOT WORRY ABOUT LEGACY CODE.

## Repository Map (Monorepo)

- python-packages/ - Python packages (dataing, dataing-ee)
  - dataing/ - Community Edition (CE) backend package, migrations, scripts
  - dataing-ee/ - Enterprise Edition (EE) extension package
- frontend/ - React + Vite + TypeScript + Tailwind + shadcn/ui
- docs/ - MkDocs site and ADRs
- demo/ - Demo fixtures, generator, docker-compose stack

### Package Dependency Order

```
dataing (bond-agent + temporal)
```

Note: `bond-agent` is an external PyPI package (`pip install bond-agent`).

## Development Commands

```bash
# Setup (Python + frontend)
just setup

# Run full dev stack (EE backend + frontend)
just dev

# Backend only
just dev-backend      # EE backend
just dev-backend-ce   # CE backend only

# Frontend only
just dev-frontend

# Tests
just test             # CE + EE + frontend
just test-ce
just test-ee
just test-frontend

# Linting / formatting / types
just lint
just format
just typecheck

# OpenAPI client for frontend
just generate-client

# Docs
just docs
just docs-serve

# Demo stack (fixtures + DB + CE backend + frontend)
just demo
```

Single test examples:

```bash
uv run pytest python-packages/dataing/tests/unit/core/test_state.py -v
uv run pytest python-packages/dataing/tests/unit/core/test_state.py::test_name -v
```

## Project Overview

Dataing is an autonomous data quality investigation platform. It detects and
diagnoses anomalies by gathering context, generating hypotheses with LLMs,
testing them via SQL queries in parallel, and synthesizing findings into root
cause analysis.

The repo is open-core:
- CE lives in `python-packages/dataing/`
- EE lives in `python-packages/dataing-ee/` and extends CE with enterprise-only features
- Agent runtime is provided by `bond-agent` PyPI package (`from bond import BondAgent`)

## Backend Architecture (CE)

Core domain: `python-packages/dataing/src/dataing/core/`
- `investigation/` - Domain entities, repository, collaboration service
- `auth/`, `rbac/`, `entitlements/` - Identity and feature gating
- `quality/` - LLM-as-judge quality validation
- `state.py`, `domain_types.py`, `interfaces.py` - Event-sourced state + protocols

Temporal workflows: `python-packages/dataing/src/dataing/temporal/`
- `workflows.py` - `InvestigationWorkflow` with child workflows for parallel hypothesis evaluation
- `activities.py` - Activity functions for LLM calls, SQL execution, context gathering
- `client.py` - `TemporalInvestigationClient` for starting/cancelling workflows
- `worker.py` - Worker setup with activity factory for dependency injection

Investigation workflow: Uses Temporal for durable execution with `INVESTIGATION_ENGINE=temporal`.

Adapters: `python-packages/dataing/src/dataing/adapters/`
- `datasource/` - SQL, document, filesystem adapters; API base types
- `lineage/` - Lineage providers (OpenLineage, dbt, Dagster, Airflow, DataHub)
- `context/`, `investigation/` - Context + LLM/DB step adapters
- `auth/`, `rbac/`, `entitlements/`, `notifications/`, `comments/`, `training/`
- `db/` - Application database access

Services + entrypoints:
- `python-packages/dataing/src/dataing/services/` - Auth, tenant, usage, notifications
- `python-packages/dataing/src/dataing/entrypoints/api/` - FastAPI app, routes, middleware
- `python-packages/dataing/src/dataing/models/` - SQLAlchemy models

Agents + safety:
- `python-packages/dataing/src/dataing/agents/` - Agent client + prompt templates
- `python-packages/dataing/src/dataing/safety/` - SQL validation, circuit breaker, PII checks

## Enterprise Edition (EE)

`python-packages/dataing-ee/src/dataing_ee/` extends CE with:
- SSO (OIDC/SAML), SCIM, audit logging, and admin settings APIs
- Enterprise datasource adapters (Salesforce, HubSpot, Stripe)

Keep CE free of EE imports; EE should wrap or extend CE behavior.

## Frontend

React + Vite + TypeScript + Tailwind + shadcn/ui.
- Features: `frontend/src/features/`
- Shared UI: `frontend/src/components/` and `frontend/src/components/ui/`
- API client: `frontend/src/lib/api/generated/` (orval) with wrappers in
  `frontend/src/lib/api/`
- Auth + entitlements: `frontend/src/lib/auth/`, `frontend/src/lib/entitlements/`

## Pre-commit Guidelines

**Ruff:**
- All public methods need docstrings (D102) - add `"""Brief description."""`
- All `__init__` methods need docstrings (D107) - add `"""Initialize the class."""`
- Lines must be <= 100 characters (E501) - break long strings across lines
- Use `isinstance(x, A | B)` instead of `isinstance(x, (A, B))` (UP038)
- In except blocks, use `raise ... from e` or `raise ... from None` (B904)

**Mypy:**
- Avoid returning `Any` - use explicit type annotations: `result: str = func()` then `return result`
- For untyped external library calls, add `# type: ignore[no-untyped-call]`
- Use `dict[str, Any]` for mixed-type dictionaries
- Logger methods don't accept kwargs - use f-strings: `logger.info(f"msg: {var}")`

## Key Conventions

- Tests: pytest-asyncio with `asyncio_mode = "auto"`
- Frontend: TypeScript strict mode, ESLint, Prettier
- Multi-tenancy: all operations scoped to tenant via API key or JWT auth
- Migrations live in `python-packages/dataing/migrations/` and are append-only
- When API shapes change, regenerate the frontend client with `just generate-client`

## Demo Fixtures

Pre-baked e-commerce anomalies live in `demo/fixtures/`:
- `null_spike`, `volume_drop`, `schema_drift`, `duplicates`,
  `late_arriving`, `orphaned_records`

`just demo` prints login credentials and also supports the legacy API key
`dd_demo_12345`.

<!-- BEGIN FLOW-NEXT -->
## Flow-Next

This project uses Flow-Next for task tracking. Use `.flow/bin/flowctl` instead of markdown TODOs or TodoWrite.

**Quick commands:**
```bash
.flow/bin/flowctl list                # List all epics + tasks
.flow/bin/flowctl epics               # List all epics
.flow/bin/flowctl tasks --epic fn-N   # List tasks for epic
.flow/bin/flowctl ready --epic fn-N   # What's ready
.flow/bin/flowctl show fn-N.M         # View task
.flow/bin/flowctl start fn-N.M        # Claim task
.flow/bin/flowctl done fn-N.M --summary-file s.md --evidence-json e.json
```

**Rules:**
- Use `.flow/bin/flowctl` for ALL task tracking
- Do NOT create markdown TODOs or use TodoWrite
- Re-anchor (re-read spec + status) before every task

**More info:** `.flow/bin/flowctl --help` or read `.flow/usage.md`
<!-- END FLOW-NEXT -->
