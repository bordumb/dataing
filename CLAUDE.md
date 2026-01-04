# CLAUDE.md

DO NOT worry about legacy code or keeping backwards compatibility
We are pre-launch
The main focus should be on innovating forward, without regard for old logic
As long as you are making code better, that is fine

## Pre-commit Guidelines

To avoid pre-commit failures, follow these patterns:

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

## Project Overview

Dataing is an AI-powered autonomous data quality investigation platform. It automatically detects and diagnoses data anomalies by:
1. Gathering context (schema, lineage)
2. Generating hypotheses using LLM
3. Testing hypotheses via SQL queries in parallel
4. Synthesizing findings into root cause analysis

## Development Commands

```bash
# Setup (install all dependencies)
just setup

# Run full demo (backend + frontend + PostgreSQL + seed data)
just demo
# Demo API key: dd_demo_12345
# Frontend: http://localhost:3000, Backend: http://localhost:8000

# Development
just dev              # Run backend + frontend
just dev-backend      # Backend only (FastAPI on port 8000)
just dev-frontend     # Frontend only (Vite on port 3000)

# Testing
just test             # Run all tests
just test-backend     # Backend only
just test-frontend    # Frontend only

# Single test file
cd backend && uv run pytest tests/unit/core/test_orchestrator.py -v

# Single test function
cd backend && uv run pytest tests/unit/core/test_orchestrator.py::test_name -v

# Linting & Formatting
just lint             # Run ruff + mypy (backend) + eslint (frontend)
just format           # Format code
just typecheck        # Type checking only

# Generate OpenAPI client for frontend
just generate-client
```

## Architecture

### Hexagonal Architecture (Ports & Adapters)

The backend follows hexagonal architecture where the core domain depends only on protocol interfaces, never on concrete implementations.

**Core Domain** (`backend/src/dataing/core/`):
- `orchestrator.py` - Investigation workflow: Context -> Hypothesize -> Parallel Investigation -> Synthesis
- `interfaces.py` - Protocol definitions (DatabaseAdapter, LLMClient, ContextEngine)
- `domain_types.py` - Core domain types (AnomalyAlert, Hypothesis, Evidence, Finding)
- `state.py` - Event-sourced investigation state

**Adapters** (`backend/src/dataing/adapters/`):
- `datasource/` - Unified data source adapters (SQL, Document, API, Filesystem)
  - All adapters inherit from `BaseAdapter` and implement connection, schema discovery, and queries
  - Supported: PostgreSQL, MySQL, Trino, Snowflake, BigQuery, Redshift, DuckDB, MongoDB, DynamoDB, Cassandra, S3, GCS, Salesforce, HubSpot, Stripe
- `context/` - Context gathering (schema, lineage, anomaly confirmation, correlations)
- `llm/` - LLM client (Anthropic Claude)
- `db/` - Application database (PostgreSQL for app state)
- `notifications/` - Slack, email, webhook notifications

**Entrypoints** (`backend/src/dataing/entrypoints/`):
- `api/` - FastAPI application with routes, middleware (auth, rate limiting, audit)
- `mcp/` - Model Context Protocol server for IDE integration

### Investigation Flow

1. **Context Engine** gathers schema (required, fail-fast) and lineage (optional)
2. **LLM** generates hypotheses based on alert and context
3. **Orchestrator** investigates hypotheses in parallel with retry/reflexion loops
4. **Circuit Breaker** stops runaway investigations (query limits, stall detection)
5. **LLM** synthesizes evidence into root cause finding

### Frontend

React + TypeScript + Vite + TailwindCSS + shadcn/ui components.

Key paths:
- `frontend/src/features/` - Feature-based organization (dashboard, investigations, datasources, settings)
- `frontend/src/components/ui/` - Reusable UI components (shadcn/ui)
- `frontend/src/lib/api/` - API client (generated via orval from OpenAPI)
- `frontend/src/lib/auth/` - Authentication context

## Key Conventions

- **Python**: Google docstring convention, strict mypy typing, ruff for linting
- **Frontend**: TypeScript strict mode, ESLint, Prettier
- **Tests**: pytest-asyncio with `asyncio_mode = "auto"`
- **Multi-tenancy**: All operations scoped to tenant via API key authentication

## Demo Fixtures

Pre-baked e-commerce data with anomalies in `demo/fixtures/`:
- `null_spike` - NULL values in user_id (mobile app bug)
- `volume_drop` - Missing EU events (CDN misconfiguration)
- `schema_drift` - Price stored as string
- `duplicates`, `late_arriving`, `orphaned_records`

Generate: `cd demo && uv run python generate.py`
