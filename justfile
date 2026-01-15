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

# Run development servers in parallel (EE - includes all features)
dev:
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'kill 0' EXIT
    (uv run fastapi dev dataing-ee/src/dataing_ee/entrypoints/api/app.py --host 0.0.0.0 --port 8000) &
    (cd frontend/app && pnpm dev --port 3000) &
    wait

# Run backend only (EE)
dev-backend:
    uv run fastapi dev dataing-ee/src/dataing_ee/entrypoints/api/app.py --host 0.0.0.0 --port 8000

# Run CE backend only (no enterprise features)
dev-backend-ce:
    uv run fastapi dev dataing/src/dataing/entrypoints/api/app.py --host 0.0.0.0 --port 8000

# Run frontend only
dev-frontend:
    cd frontend/app && pnpm dev

# Run landing site only
dev-landing:
    cd frontend/landing && pnpm dev

# Build landing site
build-landing:
    cd frontend/landing && pnpm build

# Setup landing site dependencies
setup-landing:
    cd frontend/landing && pnpm install

# Run all tests (CE + EE)
test:
    @echo "Running dataing tests..."
    uv run pytest dataing/tests dataing-ee/tests
    @echo "Running frontend tests..."
    cd frontend/app && pnpm test

# Run CE tests only
test-ce:
    uv run pytest dataing/tests

# Run EE tests only
test-ee:
    uv run pytest dataing-ee/tests

# Run frontend tests only
test-frontend:
    cd frontend/app && pnpm test

# Run linters (CE + EE)
lint:
    @echo "Linting dataing..."
    uv run ruff check dataing/src dataing-ee/src
    uv run mypy dataing/src/dataing dataing-ee/src/dataing_ee
    @echo "Linting frontend..."
    cd frontend/app && pnpm lint

# Format code
format:
    uv run ruff format dataing/src dataing-ee/src
    cd frontend/app && pnpm format

# Generate OpenAPI client for frontend
generate-client:
    @echo "Exporting OpenAPI schema from backend..."
    uv run python dataing/scripts/export_openapi.py
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
    uv run mypy dataing/src/dataing dataing-ee/src/dataing_ee
    cd frontend/app && pnpm typecheck

# Clean build artifacts
clean:
    rm -rf dist .pytest_cache .ruff_cache .mypy_cache
    rm -rf dataing/.pytest_cache dataing/.ruff_cache
    rm -rf dataing-ee/.pytest_cache dataing-ee/.ruff_cache
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

# Run the full demo stack (fixtures + backend + frontend)
demo: demo-fixtures
    #!/usr/bin/env bash
    set -euo pipefail

    echo "Starting demo stack..."
    echo ""

    # Ensure Python dependencies are installed
    uv sync --quiet

    # Ensure frontend dependencies are installed
    if [ ! -d "frontend/app/node_modules" ]; then
        echo "Installing frontend dependencies..."
        cd frontend/app && pnpm install
        cd ../..
    fi

    # Generate OpenAPI client for frontend
    echo "Generating OpenAPI client..."
    uv run python dataing/scripts/export_openapi.py
    (cd frontend/app && pnpm orval)
    echo ""

    # Start PostgreSQL - clean start every time for reliability
    echo "Setting up PostgreSQL..."
    docker rm -f dataing-demo-postgres 2>/dev/null || true
    docker run -d --name dataing-demo-postgres \
        -e POSTGRES_DB=dataing_demo \
        -e POSTGRES_USER=dataing \
        -e POSTGRES_PASSWORD=dataing \
        -p 5432:5432 \
        pgvector/pgvector:pg16
    echo "Waiting for PostgreSQL to be ready..."
    for i in {1..30}; do
        if PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -c "SELECT 1" > /dev/null 2>&1; then
            echo "PostgreSQL is ready!"
            break
        fi
        sleep 1
    done

    # Start Redis
    echo "Setting up Redis..."
    docker rm -f dataing-demo-redis 2>/dev/null || true
    docker run -d --name dataing-demo-redis \
        -p 6379:6379 \
        redis:7-alpine
    echo "Waiting for Redis to be ready..."
    for i in {1..10}; do
        if docker exec dataing-demo-redis redis-cli ping > /dev/null 2>&1; then
            echo "Redis is ready!"
            break
        fi
        sleep 1
    done

    # Start Jaeger (for trace visualization)
    echo "Setting up Jaeger..."
    docker rm -f dataing-demo-jaeger 2>/dev/null || true
    docker run -d --name dataing-demo-jaeger \
        -e COLLECTOR_OTLP_ENABLED=true \
        -p 16686:16686 \
        -p 4317:4317 \
        -p 4318:4318 \
        jaegertracing/all-in-one:1.76.0
    echo "Waiting for Jaeger to be ready..."
    for i in {1..10}; do
        if curl -s http://localhost:16686 > /dev/null 2>&1; then
            echo "Jaeger is ready!"
            break
        fi
        sleep 1
    done

    # Run migrations in order
    # IMPORTANT: Order matters! 007_auth_tables creates organizations/users/teams,
    # 007_sso_scim adds SSO columns, 008_seed_demo_auth creates demo data
    echo "Running database migrations..."
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/001_initial.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/002_datasets.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/003_investigation_feedback_events.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/004_schema_comments.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/005_knowledge_comments.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/006_comment_votes.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/007_auth_tables.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/007_sso_scim_tables.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/008_rbac_tables.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/008_seed_demo_auth.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/009_password_reset_tokens.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/009_seed_multi_org_demo.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/010_audit_logs.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/011_rl_training_signals.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/012_agent_memories.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/013_unified_investigation.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/014_notifications.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/015_sso_states.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/016_investigation_jobs.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f dataing/migrations/017_add_trace_context.sql 2>&1 | grep -v "^NOTICE:" || true

    trap 'kill 0' EXIT

    echo ""
    echo "========================================="
    echo "  Dataing Demo Ready!"
    echo "========================================="
    echo ""
    echo "  Frontend:  http://localhost:3000"
    echo "  Backend:   http://localhost:8000"
    echo "  Telemetry: http://localhost:16686"
    echo ""
    echo "  Login credentials:"
    echo "    Email:    demo@dataing.io"
    echo "    Password: demo123456"
    echo "    Org ID:   00000000-0000-0000-0000-000000000001"
    echo ""
    echo "  Legacy API Key: dd_demo_12345"
    echo "========================================="
    echo ""

    export DATADR_DEMO_MODE=true
    export DATADR_FIXTURE_PATH="$(pwd)/demo/fixtures/null_spike"
    export DATABASE_URL=postgresql://dataing:dataing@localhost:5432/dataing_demo
    export APP_DATABASE_URL=postgresql://dataing:dataing@localhost:5432/dataing_demo
    export REDIS_HOST=localhost
    export REDIS_PORT=6379
    # Stable demo encryption key (valid Fernet key)
    export ENCRYPTION_KEY=ZnxhCyx4-ZjziPWtUguwGOFMMiLNioSwso5-qNPAGZI=
    # OpenTelemetry configuration (Jaeger supports traces only, not metrics)
    export OTEL_SERVICE_NAME=dataing-demo
    export OTEL_TRACES_ENABLED=true
    export OTEL_METRICS_ENABLED=false
    export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

    # Load .env file if it exists (check both root and dataing/)
    if [ -f .env ]; then
        export $(grep -v '^#' .env | xargs)
    elif [ -f dataing/.env ]; then
        export $(grep -v '^#' dataing/.env | xargs)
    fi

    # Start backend
    (uv run fastapi dev dataing/src/dataing/entrypoints/api/app.py --host 0.0.0.0 --port 8000) &
    BACKEND_PID=$!

    # Start worker (processes investigation jobs from Redis queue)
    echo "Starting worker..."
    (uv run python -m dataing.entrypoints.worker) &
    WORKER_PID=$!

    # Wait for backend to be ready, then sync datasets
    (
        echo "Waiting for backend to be ready..."
        for i in {1..30}; do
            if curl -s http://localhost:8000/health > /dev/null 2>&1; then
                echo "Backend ready, syncing datasets..."
                curl -s -X POST "http://localhost:8000/api/v1/datasources/00000000-0000-0000-0000-000000000003/sync" \
                    -H "X-API-Key: dd_demo_12345" > /dev/null 2>&1 && \
                    echo "Datasets synced successfully" || \
                    echo "Dataset sync failed (non-critical)"
                break
            fi
            sleep 1
        done
    ) &

    # Start frontend
    (cd frontend/app && pnpm dev --port 3000) &
    wait

# Stop demo (kills all processes and removes containers/volumes)
demo-stop:
    #!/usr/bin/env bash
    echo "Stopping demo services..."

    # Stop worker first and wait for it to exit (needs Redis for cleanup)
    WORKER_PIDS=$(pgrep -f "dataing.entrypoints.worker" 2>/dev/null || true)
    if [ -n "$WORKER_PIDS" ]; then
        echo "Stopping worker (pid: $WORKER_PIDS)..."
        pkill -TERM -f "dataing.entrypoints.worker" 2>/dev/null || true
        # Wait for worker to actually exit (up to 10 seconds)
        for i in {1..10}; do
            if ! pgrep -f "dataing.entrypoints.worker" > /dev/null 2>&1; then
                echo "Worker stopped."
                break
            fi
            sleep 1
        done
        # Force kill if still running
        pkill -9 -f "dataing.entrypoints.worker" 2>/dev/null || true
    fi

    # Now stop other processes
    pkill -f "fastapi dev" 2>/dev/null || true
    pkill -f "vite.*3000" 2>/dev/null || true
    pkill -f "pnpm dev" 2>/dev/null || true
    sleep 1

    # Kill by port (fallback)
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true

    # Now safe to stop infrastructure
    docker stop dataing-demo-redis 2>/dev/null || true
    docker rm -f dataing-demo-redis 2>/dev/null || true

    docker stop dataing-demo-postgres 2>/dev/null || true
    docker rm -f dataing-demo-postgres 2>/dev/null || true

    docker stop dataing-demo-jaeger 2>/dev/null || true
    docker rm -f dataing-demo-jaeger 2>/dev/null || true

    # Stop docker-compose stack with volume cleanup
    docker-compose -f demo/docker-compose.demo.yml down -v 2>/dev/null || true

    echo "Demo stopped."

# Run demo with Docker Compose
demo-docker: demo-fixtures
    docker-compose -f demo/docker-compose.demo.yml up --build

# Stop demo Docker Compose (with volume cleanup)
demo-docker-down:
    docker-compose -f demo/docker-compose.demo.yml down -v

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
