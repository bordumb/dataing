# CE/EE Reorganization Design

## Overview

Reorganize the codebase into an open-core Community Edition (CE) and Enterprise Edition (EE) structure using two separate Python packages.

## Decisions

| Decision | Choice |
|----------|--------|
| Package structure | Two separate packages: `dataing` (CE) and `dataing-ee` (EE) |
| Directory layout | Flat: `dataing/`, `dataing-ee/`, `frontend/` |
| App composition | EE wraps CE (EE's main.py imports and extends CE's app) |
| Tests | With each package (`dataing/tests/`, `dataing-ee/tests/`) |
| Shared tooling | Root-level config, per-package deps |
| Frontend | Single frontend with feature flags + upsell for EE features |

## Target Directory Structure

```
dataing/                          # CE package (was backend/)
├── pyproject.toml
├── src/dataing/
│   ├── adapters/
│   │   ├── datasource/          # postgres, mysql, trino, snowflake, bigquery, etc.
│   │   │   └── api/             # base.py only
│   │   ├── context/
│   │   ├── db/
│   │   ├── llm/
│   │   └── notifications/
│   ├── core/                    # orchestrator, interfaces, domain_types, state
│   ├── entrypoints/
│   │   └── api/
│   │       ├── middleware/      # auth, rate_limit (NOT audit)
│   │       └── routes/          # investigations, datasources, alerts, etc.
│   ├── models/                  # all except audit_log
│   ├── services/
│   └── ...
└── tests/

dataing-ee/                       # EE package
├── pyproject.toml
├── src/dataing_ee/
│   ├── adapters/
│   │   ├── datasource/api/      # hubspot, salesforce, stripe
│   │   ├── audit/
│   │   └── sso/
│   ├── core/
│   │   ├── scim/
│   │   └── sso/
│   ├── entrypoints/api/
│   │   ├── main.py              # wraps CE app
│   │   ├── middleware/          # audit
│   │   └── routes/              # audit, sso, scim, settings
│   ├── jobs/                    # audit_cleanup
│   └── models/                  # audit_log
└── tests/

frontend/                         # single frontend with feature flags
pyproject.toml                    # root: shared ruff/mypy config
justfile                          # root: commands for both packages
```

## Files Moving to EE

From `backend/src/dataing/`:

- `adapters/datasource/api/hubspot.py`
- `adapters/datasource/api/salesforce.py`
- `adapters/datasource/api/stripe.py`
- `adapters/audit/*`
- `adapters/sso/*`
- `core/scim/*`
- `core/sso/*`
- `entrypoints/api/middleware/audit.py`
- `entrypoints/api/routes/audit.py`
- `entrypoints/api/routes/sso.py`
- `entrypoints/api/routes/scim.py`
- `entrypoints/api/routes/settings.py`
- `jobs/audit_cleanup.py`
- `models/audit_log.py`

## Expected Fixes After Migration

### Import Path Updates
- CE code importing EE features: remove those imports
- EE code importing CE features: `from dataing.X` (unchanged, EE depends on CE)
- Internal EE imports: change to `from dataing_ee.X`

### `__init__.py` Cleanup
- CE's `adapters/__init__.py`: remove audit/sso re-exports
- CE's `core/__init__.py`: remove scim/sso re-exports
- CE's `entrypoints/api/routes/__init__.py`: remove EE router listings

### CE's `main.py` Cleanup
- Remove router includes for audit, sso, scim, settings
- Remove audit middleware registration

### New EE `main.py`
- Import CE's app
- Add EE routers and middleware

### pyproject.toml
- CE: update package path from `backend/src` to `dataing/src`
- EE: new file, depends on `dataing`, points to `dataing-ee/src`
- Root: shared tool config (ruff, mypy)

### Tests
- Move EE-related test files to `dataing-ee/tests/`
- Fix test imports

## Execution Order

1. Create and run `scripts/ce_ee_reorg.sh` (file moves)
2. Create `dataing/pyproject.toml` and `dataing-ee/pyproject.toml`
3. Create root `pyproject.toml` with shared tool config
4. Run `uv run ruff check --fix` and fix remaining lint issues
5. Run `uv run mypy` and fix import errors iteratively
6. Run `uv run pytest` and fix test failures
7. Update `justfile` for new structure
8. Verify frontend still builds and connects

## Success Criteria

```bash
cd dataing && uv run mypy src/        # passes
cd dataing && uv run ruff check src/  # passes
cd dataing && uv run pytest tests/    # passes

cd dataing-ee && uv run mypy src/        # passes
cd dataing-ee && uv run ruff check src/  # passes
cd dataing-ee && uv run pytest tests/    # passes
```

## App Composition Pattern

EE wraps CE's FastAPI app:

```python
# dataing-ee/src/dataing_ee/entrypoints/api/main.py
from dataing.entrypoints.api.main import app as ce_app
from dataing_ee.entrypoints.api.routes import audit, sso, scim, settings
from dataing_ee.entrypoints.api.middleware.audit import AuditMiddleware

app = ce_app
app.add_middleware(AuditMiddleware)
app.include_router(audit.router)
app.include_router(sso.router)
app.include_router(scim.router)
app.include_router(settings.router)
```

## Frontend Strategy

Single frontend with feature flags. EE features are shown to all users but with upsell prompts for non-EE customers. Backend returns 403 for unlicensed EE endpoints.
