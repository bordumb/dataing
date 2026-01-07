# Repository Guidelines

## Project Structure & Module Organization
- `backend/src/dataing/`: FastAPI service (core domain, adapters, entrypoints); `backend/migrations/` holds SQL migrations.
- `frontend/src/`: React + Vite app; feature modules live in `frontend/src/features/` and shared UI in `frontend/src/components/ui/`.
- `tests/`: backend tests organized by `unit/`, `integration/`, and `e2e/`.
- `demo/`: demo fixtures and generator; `docs/`: MkDocs site; `scripts/`: helper scripts.
- `dashboard/`: Next.js app not referenced by the `just` commands.

## Build, Test, and Development Commands
Use the root `justfile` as the canonical task runner:
- `just setup` installs backend (uv) and frontend (pnpm) deps and pre-commit hooks.
- `just dev`, `just dev-backend`, `just dev-frontend` run dev servers (backend 8000, frontend 3000/5173).
- `just test`, `just test-backend`, `just test-frontend` run pytest and Vitest.
- `just lint`, `just format`, `just typecheck` enforce ruff/mypy and ESLint/Prettier.
- `just generate-client` exports OpenAPI and regenerates the frontend API client.
- `just demo` spins up the demo stack and fixtures; `just build` creates production builds.

## Coding Style & Naming Conventions
- Python: 4-space indent, `ruff format` with 100-char lines, Google-style docstrings (public methods and `__init__` require docstrings). Mypy is strict; prefer explicit types and `raise ... from e` in except blocks.
- TypeScript: strict mode, ESLint + Prettier; default 2-space indentation.
- Naming: `snake_case` for Python, `PascalCase` for classes, `camelCase` for TS/JS symbols; tests use `test_*.py`.

## Testing Guidelines
- Backend uses `pytest` + `pytest-asyncio` with coverage over `backend/src/dataing`. Place tests in `tests/unit`, `tests/integration`, or `tests/e2e`.
- Frontend uses Vitest (`pnpm test`); name files `*.test.ts(x)` so they are picked up.

## Commit & Pull Request Guidelines
- Commit history favors Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`). Use that format unless updating older "Add ..." style areas.
- PRs should include a clear description, testing notes/commands run, linked issues, and screenshots for UI changes.

## Configuration & Demo Notes
- Backend can read `backend/.env`; demo runs with `dd_demo_12345` via `just demo`.
