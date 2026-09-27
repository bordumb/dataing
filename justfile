# dataing v2 - Command Runner
# Universal task runner replacing Makefiles
# CE = Community Edition (dataing/), EE = Enterprise Edition (dataing-ee/)

# Default recipe to list available commands
default:
    @just --list

# Bootstrap dataing and frontend
setup:
    @echo "Setting up dataing (CE)..."
    uv sync
    @echo "Setting up frontend app..."
    cd frontend/app && pnpm install
    @echo "Setting up landing site..."
    cd frontend/landing && pnpm install
    @echo "Setting up JupyterLab extension..."
    cd frontend/jupyterlab-dataing && jlpm install && jlpm build
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

# =============================================================================
# JupyterLab Extension Commands
# =============================================================================

# Build the JupyterLab extension for production
build-jupyterlab:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Building JupyterLab Dataing extension..."
    cd frontend/jupyterlab-dataing
    jlpm install
    jlpm build:prod
    echo "Extension built successfully!"

# Install JupyterLab extension in development mode (watches for changes)
dev-jupyterlab:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Installing JupyterLab extension in development mode..."
    cd frontend/jupyterlab-dataing
    jlpm install
    jlpm build
    jupyter labextension develop --overwrite .
    echo "Extension installed! Run 'just dev-jupyterlab-watch' to watch for changes."

# Watch JupyterLab extension source for changes (run in separate terminal)
dev-jupyterlab-watch:
    #!/usr/bin/env bash
    echo "Watching JupyterLab extension for changes..."
    cd frontend/jupyterlab-dataing && jlpm watch

# Run JupyterLab with the Dataing extension (standalone, for extension development)
run-jupyterlab:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Starting JupyterLab..."
    DATAING_BACKEND_URL=${DATAING_BACKEND_URL:-http://localhost:8000} \
    DATAING_API_KEY=${DATAING_API_KEY:-dd_demo_12345} \
    uv run jupyter lab --notebook-dir=demo --no-browser

# =============================================================================

# Run development servers (EE backend + frontend). Requires infrastructure running.
dev:
    #!/usr/bin/env bash
    set -euo pipefail

    # Check if infrastructure is running
    if ! docker ps --format '{{{{.Names}}}}' | grep -q 'dataing-demo-postgres'; then
        echo "Error: Database not running. Run 'just demo-infra' first."
        exit 1
    fi

    # Core environment only (no demo mode)
    export DATABASE_URL=postgresql://dataing:dataing@localhost:5432/dataing_demo
    export APP_DATABASE_URL=postgresql://dataing:dataing@localhost:5432/dataing_demo
    export REDIS_HOST=localhost
    export REDIS_PORT=6379
    export ENCRYPTION_KEY=ZnxhCyx4-ZjziPWtUguwGOFMMiLNioSwso5-qNPAGZI=

    # Load .env if exists (for ANTHROPIC_API_KEY etc)
    if [ -f .env ]; then
        export $(grep -v '^#' .env | xargs)
    fi

    trap 'kill 0' EXIT

    echo "Starting EE backend + frontend..."
    echo "  Backend:  http://localhost:8000"
    echo "  Frontend: http://localhost:3000"
    echo ""

    (uv run fastapi dev python-packages/dataing-ee/src/dataing_ee/entrypoints/api/app.py --host 0.0.0.0 --port 8000) &
    (cd frontend/app && pnpm dev --port 3000) &
    wait

# Run backend only (EE). Requires infrastructure.
dev-backend:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! docker ps --format '{{{{.Names}}}}' | grep -q 'dataing-demo-postgres'; then
        echo "Error: Database not running. Run 'just demo-infra' first."
        exit 1
    fi
    export DATABASE_URL=postgresql://dataing:dataing@localhost:5432/dataing_demo
    export APP_DATABASE_URL=postgresql://dataing:dataing@localhost:5432/dataing_demo
    export REDIS_HOST=localhost
    export REDIS_PORT=6379
    export ENCRYPTION_KEY=ZnxhCyx4-ZjziPWtUguwGOFMMiLNioSwso5-qNPAGZI=
    if [ -f .env ]; then export $(grep -v '^#' .env | xargs); fi
    uv run fastapi dev python-packages/dataing-ee/src/dataing_ee/entrypoints/api/app.py --host 0.0.0.0 --port 8000

# Run CE backend only (no enterprise features). Requires infrastructure.
dev-backend-ce:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! docker ps --format '{{{{.Names}}}}' | grep -q 'dataing-demo-postgres'; then
        echo "Error: Database not running. Run 'just demo-infra' first."
        exit 1
    fi
    export DATABASE_URL=postgresql://dataing:dataing@localhost:5432/dataing_demo
    export APP_DATABASE_URL=postgresql://dataing:dataing@localhost:5432/dataing_demo
    export REDIS_HOST=localhost
    export REDIS_PORT=6379
    export ENCRYPTION_KEY=ZnxhCyx4-ZjziPWtUguwGOFMMiLNioSwso5-qNPAGZI=
    if [ -f .env ]; then export $(grep -v '^#' .env | xargs); fi
    uv run fastapi dev python-packages/dataing/src/dataing/entrypoints/api/app.py --host 0.0.0.0 --port 8000

# Stop dev servers
dev-stop:
    #!/usr/bin/env bash
    echo "Stopping dev servers..."
    pkill -f "fastapi dev" 2>/dev/null || true
    pkill -f "vite.*3000" 2>/dev/null || true
    pkill -f "pnpm dev" 2>/dev/null || true
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    echo "Done."

# Run frontend only
dev-frontend:
    cd frontend/app && pnpm dev

# Run landing site only
dev-landing:
    cd frontend/landing && pnpm dev

# Run Temporal worker (durable workflow execution)
dev-temporal-worker:
    uv run python -m dataing.entrypoints.temporal_worker

# Build landing site
build-landing:
    cd frontend/landing && pnpm build

# Setup landing site dependencies
setup-landing:
    cd frontend/landing && pnpm install

# Run all tests (CE + EE)
test:
    @echo "Running dataing tests..."
    uv run pytest python-packages/dataing/tests python-packages/dataing-ee/tests
    @echo "Running frontend tests..."
    cd frontend/app && pnpm test

# Run CE tests only
test-ce:
    uv run pytest python-packages/dataing/tests

# Run EE tests only
test-ee:
    uv run pytest python-packages/dataing-ee/tests

# Run frontend tests only
test-frontend:
    cd frontend/app && pnpm test

# Run integration tests (requires running PostgreSQL — use `just demo-infra` first)
test-integration:
    uv run pytest python-packages/dataing/tests/integration/ -v -m integration

# Run linters (CE + EE)
lint:
    @echo "Linting dataing..."
    uv run ruff check python-packages/dataing/src python-packages/dataing-ee/src
    uv run mypy python-packages/dataing/src/dataing python-packages/dataing-ee/src/dataing_ee
    @echo "Linting frontend..."
    cd frontend/app && pnpm lint

# Format code
format:
    uv run ruff format python-packages/dataing/src python-packages/dataing-ee/src
    cd frontend/app && pnpm format

# Generate OpenAPI client for frontend
generate-client:
    @echo "Exporting OpenAPI schema from backend..."
    uv run python python-packages/dataing/scripts/export_openapi.py
    @echo "Generating OpenAPI client..."
    cd frontend/app && pnpm orval

# Build for production
build:
    @echo "Building dataing..."
    uv build
    @echo "Building landing site..."
    cd frontend/landing && pnpm build
    @echo "Building frontend app..."
    cd frontend/app && pnpm build

# Run type checking
typecheck:
    uv run mypy python-packages/dataing/src/dataing python-packages/dataing-ee/src/dataing_ee
    cd frontend/app && pnpm typecheck

# Clean build artifacts
clean:
    rm -rf dist .pytest_cache .ruff_cache .mypy_cache
    rm -rf python-packages/dataing/.pytest_cache python-packages/dataing/.ruff_cache
    rm -rf python-packages/dataing-ee/.pytest_cache python-packages/dataing-ee/.ruff_cache
    rm -rf frontend/app/dist frontend/app/node_modules/.cache
    rm -rf frontend/landing/dist frontend/landing/node_modules/.cache

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

# Start infrastructure only (postgres, redis, jaeger + migrations). Use with `just dev`.
demo-infra:
    #!/usr/bin/env bash
    set -euo pipefail

    echo "Starting demo infrastructure..."

    # Start PostgreSQL
    echo "Setting up PostgreSQL..."
    docker rm -f dataing-demo-postgres 2>/dev/null || true
    docker run -d --name dataing-demo-postgres \
        -e POSTGRES_DB=dataing_demo \
        -e POSTGRES_USER=dataing \
        -e POSTGRES_PASSWORD=dataing \
        -p 5432:5432 \
        pgvector/pgvector:pg16
    echo "Waiting for PostgreSQL..."
    for i in {1..30}; do
        if PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -c "SELECT 1" > /dev/null 2>&1; then
            echo "PostgreSQL ready!"
            break
        fi
        sleep 1
    done

    # Start Redis
    echo "Setting up Redis..."
    docker rm -f dataing-demo-redis 2>/dev/null || true
    docker run -d --name dataing-demo-redis -p 6379:6379 redis:7-alpine
    for i in {1..10}; do
        if docker exec dataing-demo-redis redis-cli ping > /dev/null 2>&1; then
            echo "Redis ready!"
            break
        fi
        sleep 1
    done

    # Start Jaeger
    echo "Setting up Jaeger..."
    docker rm -f dataing-demo-jaeger 2>/dev/null || true
    echo '{"darkMode":true}' > /tmp/jaeger-ui-config.json
    docker run -d --name dataing-demo-jaeger \
        -e COLLECTOR_OTLP_ENABLED=true \
        -v /tmp/jaeger-ui-config.json:/etc/jaeger/ui-config.json:ro \
        -e QUERY_UI_CONFIG=/etc/jaeger/ui-config.json \
        -p 16686:16686 -p 4317:4317 -p 4318:4318 \
        jaegertracing/all-in-one:1.76.0

    # Run migrations (skip seed files for clean dev environment)
    echo "Running migrations..."
    for f in python-packages/dataing/migrations/*.sql; do
        # Skip seed migrations - those are demo-only
        if [[ "$f" == *"seed"* ]]; then
            echo "  Skipping seed: $(basename $f)"
            continue
        fi
        PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f "$f" 2>&1 | grep -v "^NOTICE:" || true
    done

    echo ""
    echo "Infrastructure ready! Now run: just dev"
    echo ""
    echo "  PostgreSQL: localhost:5432"
    echo "  Redis:      localhost:6379"
    echo "  Jaeger:     http://localhost:16686"

# Generate demo fixtures if not present
demo-fixtures:
    #!/usr/bin/env bash
    # Check for actual parquet files, not just directory
    if [ ! -f "demo/fixtures/null_spike/orders.parquet" ]; then
        echo "Generating demo fixtures..."
        cd demo && uv run python generate.py
    else
        echo "Demo fixtures already exist"
    fi

# Run full demo stack with Docker Compose (fixtures + all services)
demo: demo-fixtures
    #!/usr/bin/env bash
    set -euo pipefail
    echo "Starting demo stack..."
    # Force recreate db-migrate to ensure seeds run
    docker compose -f docker-compose.yml -f demo/docker-compose.demo.yml up -d --build --force-recreate db-migrate
    docker compose -f docker-compose.yml -f demo/docker-compose.demo.yml up -d --build
    echo ""
    echo "========================================="
    echo "  Dataing Demo Ready!"
    echo "========================================="
    echo ""
    echo "  Frontend:    http://localhost:3000"
    echo "  API Docs:    http://localhost:8000/docs"
    echo "  Temporal UI: http://localhost:8233"
    echo ""
    echo "  Login credentials:"
    echo "    Email:           demo@dataing.io"
    echo "    Password:        demo123456"
    echo "    Organization ID: 00000000-0000-0000-0000-000000000001"
    echo ""
    echo "  Add DuckDB datasource in UI:"
    echo "    Type: PostgreSQL | Host: duckdb | Port: 5432"
    echo "    Database: demo | User: demo | Password: demo"
    echo ""
    echo "========================================="

# Stop demo stack
demo-stop:
    docker compose -f docker-compose.yml -f demo/docker-compose.demo.yml down

# Clean demo (stop + remove volumes)
demo-clean:
    docker compose -f docker-compose.yml -f demo/docker-compose.demo.yml down -v
    rm -rf demo/fixtures/baseline demo/fixtures/null_spike demo/fixtures/volume_drop
    rm -rf demo/fixtures/schema_drift demo/fixtures/duplicates demo/fixtures/late_arriving
    rm -rf demo/fixtures/orphaned_records

# Regenerate demo fixtures (force)
demo-regenerate:
    rm -rf demo/fixtures/*/
    cd demo && uv run python generate.py
