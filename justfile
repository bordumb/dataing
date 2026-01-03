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
    @echo "Installing pre-commit hooks..."
    uv tool install pre-commit || pip install pre-commit
    pre-commit install
    @echo "Setup complete!"

# Install/update pre-commit hooks
pre-commit-install:
    pre-commit install
    pre-commit install --hook-type commit-msg

# Run pre-commit on all files
pre-commit:
    pre-commit run --all-files

# Run development servers in parallel
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'kill 0' EXIT
    (cd backend && uv run fastapi dev src/dataing/entrypoints/api/app.py --host 0.0.0.0 --port 8000) &
    (cd frontend && pnpm dev --port 3000) &
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

# ============================================
# Demo Commands
# ============================================

# Generate demo fixtures if not present
demo-fixtures:
    #!/usr/bin/env bash
    if [ ! -d "demo/fixtures/null_spike" ]; then
        echo "Generating demo fixtures..."
        cd demo && uv run python generate.py
    else
        echo "Demo fixtures already exist"
    fi

# Run the full demo stack (fixtures + backend + frontend)
demo: demo-fixtures
    #!/usr/bin/env bash
    set -euo pipefail

    echo "Starting demo stack..."
    echo ""

    # Start PostgreSQL if not running
    if ! docker ps | grep -q datadr-demo-postgres; then
        echo "Starting PostgreSQL..."
        docker run -d --name datadr-demo-postgres \
            -e POSTGRES_DB=datadr_demo \
            -e POSTGRES_USER=datadr \
            -e POSTGRES_PASSWORD=datadr \
            -p 5432:5432 \
            postgres:16-alpine
        echo "Waiting for PostgreSQL to be ready..."
        sleep 3
    fi

    # Run migrations
    echo "Running database migrations..."
    PGPASSWORD=datadr psql -h localhost -U datadr -d datadr_demo -f backend/migrations/001_initial.sql 2>/dev/null || true

    trap 'kill 0' EXIT

    echo ""
    echo "  API Key for testing: dd_demo_12345"
    echo "  Frontend: http://localhost:3000"
    echo "  Backend:  http://localhost:8000"
    echo ""

    export DATADR_DEMO_MODE=true
    export DATADR_FIXTURE_PATH="$(pwd)/demo/fixtures/null_spike"
    export DATABASE_URL=postgresql://datadr:datadr@localhost:5432/datadr_demo
    export APP_DATABASE_URL=postgresql://datadr:datadr@localhost:5432/datadr_demo
    # Stable demo encryption key (valid Fernet key)
    export ENCRYPTION_KEY=ZnxhCyx4-ZjziPWtUguwGOFMMiLNioSwso5-qNPAGZI=

    # Load .env file if it exists
    if [ -f backend/.env ]; then
        export $(grep -v '^#' backend/.env | xargs)
    fi

    (cd backend && uv run fastapi dev src/dataing/entrypoints/api/app.py --host 0.0.0.0 --port 8000) &
    (cd frontend && pnpm dev --port 3000) &
    wait

# Stop demo PostgreSQL container
demo-stop:
    docker stop datadr-demo-postgres 2>/dev/null || true
    docker rm datadr-demo-postgres 2>/dev/null || true

# Run demo with Docker Compose
demo-docker: demo-fixtures
    docker-compose -f demo/docker-compose.demo.yml up --build

# Stop demo Docker Compose
demo-docker-down:
    docker-compose -f demo/docker-compose.demo.yml down

# Clean demo data (fixtures and database)
demo-clean:
    rm -rf demo/fixtures/baseline demo/fixtures/null_spike demo/fixtures/volume_drop
    rm -rf demo/fixtures/schema_drift demo/fixtures/duplicates demo/fixtures/late_arriving
    rm -rf demo/fixtures/orphaned_records
    docker-compose -f demo/docker-compose.demo.yml down -v 2>/dev/null || true

# Regenerate demo fixtures (force)
demo-regenerate:
    rm -rf demo/fixtures/*/
    cd demo && uv run python generate.py
