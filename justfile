# dataing v2 - Command Runner
# Universal task runner replacing Makefiles

# Default recipe to list available commands
default:
    @just --list

# Bootstrap backend and frontend
setup:
    @echo "Setting up backend..."
    cd backend && uv sync
    @echo "Setting up frontend..."
    cd frontend && pnpm install
    @echo "Setup complete!"

# Run development servers in parallel
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'kill 0' EXIT
    (cd backend && uv run fastapi dev src/dataing/entrypoints/api/app.py --host 0.0.0.0 --port 8000) &
    (cd frontend && pnpm dev) &
    wait

# Run backend only
dev-backend:
    cd backend && uv run fastapi dev src/dataing/entrypoints/api/app.py --host 0.0.0.0 --port 8000

# Run frontend only
dev-frontend:
    cd frontend && pnpm dev

# Run all tests
test:
    @echo "Running backend tests..."
    cd backend && uv run pytest
    @echo "Running frontend tests..."
    cd frontend && pnpm test

# Run backend tests only
test-backend:
    cd backend && uv run pytest

# Run frontend tests only
test-frontend:
    cd frontend && pnpm test

# Run linters
lint:
    @echo "Linting backend..."
    cd backend && uv run ruff check . && uv run mypy .
    @echo "Linting frontend..."
    cd frontend && pnpm lint

# Format code
format:
    cd backend && uv run ruff format .
    cd frontend && pnpm format

# Generate OpenAPI client for frontend
generate-client:
    @echo "Generating OpenAPI client..."
    cd frontend && pnpm orval

# Build for production
build:
    @echo "Building backend..."
    cd backend && uv build
    @echo "Building frontend..."
    cd frontend && pnpm build

# Run type checking
typecheck:
    cd backend && uv run mypy .
    cd frontend && pnpm typecheck

# Clean build artifacts
clean:
    rm -rf backend/dist backend/.pytest_cache backend/.ruff_cache
    rm -rf frontend/dist frontend/node_modules/.cache

# Start docker-compose stack
docker-up:
    docker-compose -f infra/docker-compose.yml up -d

# Stop docker-compose stack
docker-down:
    docker-compose -f infra/docker-compose.yml down

# View logs from docker-compose
docker-logs:
    docker-compose -f infra/docker-compose.yml logs -f

# Build docs
docs:
    cd docs && mkdocs build

# Serve docs locally
docs-serve:
    cd docs && mkdocs serve
