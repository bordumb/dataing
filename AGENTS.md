# Repository Guidelines

## Contributor Paths
- Internal contributors: work from a branch, link the internal issue, and request review from the owning team.
- External contributors: open a PR from a fork, keep changes focused, and avoid infra/secrets updates.

## Project Structure & Module Organization
- `backend/src/dataing/`: FastAPI service (core domain, adapters, entrypoints).
- `backend/migrations/`: SQL migrations.
- `frontend/src/`: React + Vite app; feature modules in `frontend/src/features/`, shared UI in `frontend/src/components/ui/`.
- `tests/`: backend tests organized into `unit/`, `integration/`, and `e2e/`.
- `demo/`: demo fixtures and generator; `docs/`: MkDocs site; `scripts/`: helper scripts.
- `dashboard/`: Next.js app (not wired into the `just` commands).

## Architecture Overview
Backend and frontend communicate via a generated OpenAPI client; database changes flow through SQL migrations.

```mermaid
flowchart LR
  FE[Frontend (Vite/React)] -->|OpenAPI client| API[FastAPI service]
  API --> DB[(Database)]
  MIG[SQL migrations] --> DB
```

## Build, Test, and Development Commands
Use the root `justfile` as the canonical task runner:
- `just setup`: install backend deps (uv), frontend deps (pnpm), and pre-commit hooks.
- `just dev`: run both dev servers; `just dev-backend` (FastAPI on 8000) and `just dev-frontend` (Vite on 3000/5173).
- `just test`: run all tests; `just test-backend` (pytest) and `just test-frontend` (Vitest).
- `just lint`, `just format`, `just typecheck`: run ruff/mypy and ESLint/Prettier checks.
- `just generate-client`: export OpenAPI schema and regenerate the frontend API client.
- `just demo`: spin up the demo stack and fixtures; `just build`: production builds.

## Coding Style & Naming Conventions
- Python: 4-space indentation; `ruff format` with 100-char lines; Google-style docstrings for public methods and `__init__`.
- Mypy is strict; prefer explicit types and `raise ... from e` in except blocks.
- TypeScript: strict mode, 2-space indentation, ESLint + Prettier.
- Naming: `snake_case` (Python), `PascalCase` (classes), `camelCase` (TS/JS); tests are `test_*.py` and `*.test.ts(x)`.

## Testing Guidelines
- Backend: `pytest` + `pytest-asyncio`, coverage focused on `backend/src/dataing/`.
- Place backend tests in `tests/unit/`, `tests/integration/`, or `tests/e2e/`.
- Frontend: Vitest via `pnpm test` or `just test-frontend`.

## Commit & Pull Request Guidelines
- Prefer Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`). Use existing "Add ..." style where already established.
- PRs should include a clear description, linked issues, testing commands run, and screenshots for UI changes.

## Configuration & Demo Notes
- Backend can read `backend/.env`.
- Demo runs with `dd_demo_12345` via `just demo`.
