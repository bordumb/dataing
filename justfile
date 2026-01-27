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

# Run the full demo stack (fixtures + backend + frontend)
demo: demo-fixtures
    #!/usr/bin/env bash
    set -euo pipefail

    echo "Starting demo stack..."
    echo ""

    # Ensure Python dependencies are installed (including SDK and notebook packages)
    uv sync --quiet --extra demo

    # Ensure frontend dependencies are installed
    if [ ! -d "frontend/app/node_modules" ]; then
        echo "Installing frontend dependencies..."
        cd frontend/app && pnpm install
        cd ../..
    fi

    # Generate OpenAPI client for frontend
    echo "Generating OpenAPI client..."
    uv run python python-packages/dataing/scripts/export_openapi.py
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

    # Start Temporal dev server (SQLite-backed, no external deps)
    echo "Setting up Temporal..."
    docker rm -f dataing-demo-temporal 2>/dev/null || true
    docker run -d --name dataing-demo-temporal \
        -p 7233:7233 \
        -p 8233:8233 \
        --entrypoint temporal \
        temporalio/admin-tools:latest server start-dev --ip 0.0.0.0
    echo "Waiting for Temporal to be ready..."
    for i in {1..30}; do
        if curl -s http://localhost:8233 > /dev/null 2>&1; then
            echo "Temporal is ready!"
            break
        fi
        sleep 1
    done

    # Start Jaeger (for trace visualization)
    echo "Setting up Jaeger..."
    docker rm -f dataing-demo-jaeger 2>/dev/null || true
    # Create Jaeger UI config for dark mode
    echo '{"darkMode":true}' > /tmp/jaeger-ui-config.json
    docker run -d --name dataing-demo-jaeger \
        -e COLLECTOR_OTLP_ENABLED=true \
        -v /tmp/jaeger-ui-config.json:/etc/jaeger/ui-config.json:ro \
        -e QUERY_UI_CONFIG=/etc/jaeger/ui-config.json \
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
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/001_initial.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/002_datasets.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/003_investigation_feedback_events.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/004_schema_comments.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/005_knowledge_comments.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/006_comment_votes.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/007_auth_tables.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/007_sso_scim_tables.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/008_rbac_tables.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/008_seed_demo_auth.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/009_password_reset_tokens.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/009_seed_multi_org_demo.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/010_audit_logs.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/011_rl_training_signals.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/012_agent_memories.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/013_unified_investigation.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/014_notifications.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/015_sso_states.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/016_investigation_jobs.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/017_add_trace_context.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/018_issues.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/019_sla_policies.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/020_integrations.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/021_automation_rules.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/022_runbooks.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/023_drop_investigation_jobs.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/024_user_credentials.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/025_sdk_bundles_runs.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/026_sdk_evidence.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/027_sdk_vp_fields.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/028_team_policies.sql 2>&1 | grep -v "^NOTICE:" || true
    PGPASSWORD=dataing psql -h localhost -U dataing -d dataing_demo -f python-packages/dataing/migrations/029_analytics_events.sql 2>&1 | grep -v "^NOTICE:" || true

    trap 'kill 0' EXIT

    echo ""
    echo "========================================="
    echo "  Dataing Demo Ready!"
    echo "========================================="
    echo ""
    echo "  Browser tabs will open automatically for:"
    echo "    - Frontend:  http://localhost:3000"
    echo "    - Backend:   http://localhost:8000/docs"
    echo "    - Temporal:  http://localhost:8233"
    echo "    - Telemetry: http://localhost:16686"
    echo "    - JupyterLab: http://localhost:8888/lab/tree/demo_notebook.ipynb"
    echo ""
    echo "  Login credentials:"
    echo "    Email:    demo@dataing.io"
    echo "    Password: demo123456"
    echo ""
    echo "  API Key: dd_demo_12345"
    echo ""
    echo "========================================="
    echo "  CLI Demo Commands (in another terminal)"
    echo "========================================="
    echo ""
    echo "  # List available datasources"
    echo "  dataing ds list"
    echo ""
    echo "  # Run investigation with streaming timeline (recommended)"
    echo "  dataing run start main.orders --anomaly-type null_rate --column user_id --date 2026-01-10 --goal \"investigate null spike in user_id\""
    echo ""
    echo "  # Stream as NDJSON for scripting"
    echo "  dataing --json run start main.orders --anomaly-type duplicate_rate --goal \"why are there duplicate orders?\""
    echo ""
    echo "  # Wait for result without streaming"
    echo "  dataing run start main.events --anomaly-type freshness --goal \"check for late arriving data\" --no-stream"
    echo ""
    echo "  # With expected/actual values (matches GUI)"
    echo "  dataing run start main.orders --anomaly-type null_rate --column user_id --expected 0.01 --actual 0.15 --date 2026-01-10 --goal \"investigate null spike\""
    echo ""
    echo "  # Available tables: main.orders, main.users, main.events, main.products, main.categories, main.order_items"
    echo ""
    echo "========================================="
    echo ""

    export DATADR_DEMO_MODE=true
    export DATADR_FIXTURE_PATH="$(pwd)/demo/fixtures/null_spike"
    export DATABASE_URL=postgresql://dataing:dataing@localhost:5432/dataing_demo
    export APP_DATABASE_URL=postgresql://dataing:dataing@localhost:5432/dataing_demo
    # Temporal configuration
    export INVESTIGATION_ENGINE=temporal
    export TEMPORAL_HOST=localhost:7233
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
    elif [ -f python-packages/dataing/.env ]; then
        export $(grep -v '^#' python-packages/dataing/.env | xargs)
    fi

    # Start backend
    (uv run fastapi dev python-packages/dataing/src/dataing/entrypoints/api/app.py --host 0.0.0.0 --port 8000) &
    BACKEND_PID=$!

    # Start Temporal worker (processes investigation workflows)
    echo "Starting Temporal worker..."
    (uv run python -m dataing.entrypoints.temporal_worker) &
    WORKER_PID=$!

    # Wait for backend to be ready, then sync datasets and configure CLI
    (
        echo "Waiting for backend to be ready..."
        for i in {1..30}; do
            if curl -s http://localhost:8000/health > /dev/null 2>&1; then
                echo "Backend ready, syncing datasets..."
                curl -s -X POST "http://localhost:8000/api/v1/datasources/00000000-0000-0000-0000-000000000003/sync" \
                    -H "X-API-Key: dd_demo_12345" > /dev/null 2>&1 && \
                    echo "Datasets synced successfully" || \
                    echo "Dataset sync failed (non-critical)"

                # Auto-configure CLI for demo
                echo "Configuring CLI for demo..."
                mkdir -p ~/.config/dataing
                {
                    echo 'api_url = "http://localhost:8000"'
                    echo 'api_key = "dd_demo_12345"'  # pragma: allowlist secret
                    echo 'default_datasource_id = "00000000-0000-0000-0000-000000000003"'
                    echo 'default_datasource_name = "demo-duckdb"'
                } > ~/.config/dataing/config.toml
                echo "CLI configured! Run 'dataing ds list' in another terminal."
                break
            fi
            sleep 1
        done
    ) &

    # Start JupyterLab with dataing extension (sidebar + magics)
    (
        echo "Starting JupyterLab on port 8888..."
        sleep 2
        DATAING_BACKEND_URL=http://localhost:8000 \
        DATAING_API_KEY=dd_demo_12345 \
        uv run jupyter lab --notebook-dir=demo --port 8888 --no-browser \
            --IdentityProvider.token='' 2>&1 | \
            grep -v "^\[" || true
    ) &

    # Open all browser tabs after services are ready
    (
        echo "Waiting for all services before opening browsers..."
        # Wait for frontend (usually the slowest to start)
        for i in {1..45}; do
            if curl -s http://localhost:3000 > /dev/null 2>&1; then
                echo "All services ready! Opening browser tabs..."
                sleep 1
                if command -v open &> /dev/null; then
                    # macOS
                    open "http://localhost:3000"                              # Frontend
                    open "http://localhost:8000/docs"                         # Backend API docs
                    open "http://localhost:8233"                              # Temporal UI
                    open "http://localhost:16686"                             # Jaeger UI
                    open "http://localhost:8888/lab/tree/demo_notebook.ipynb" # Demo notebook
                elif command -v xdg-open &> /dev/null; then
                    # Linux
                    xdg-open "http://localhost:3000" &
                    xdg-open "http://localhost:8000/docs" &
                    xdg-open "http://localhost:8233" &
                    xdg-open "http://localhost:16686" &
                    xdg-open "http://localhost:8888/lab/tree/demo_notebook.ipynb" &
                fi
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

    # Stop Temporal worker first and wait for it to exit
    WORKER_PIDS=$(pgrep -f "dataing.entrypoints.temporal_worker" 2>/dev/null || true)
    if [ -n "$WORKER_PIDS" ]; then
        echo "Stopping Temporal worker (pid: $WORKER_PIDS)..."
        pkill -TERM -f "dataing.entrypoints.temporal_worker" 2>/dev/null || true
        # Wait for worker to actually exit (up to 10 seconds)
        for i in {1..10}; do
            if ! pgrep -f "dataing.entrypoints.temporal_worker" > /dev/null 2>&1; then
                echo "Temporal worker stopped."
                break
            fi
            sleep 1
        done
        # Force kill if still running
        pkill -9 -f "dataing.entrypoints.temporal_worker" 2>/dev/null || true
    fi

    # Now stop other processes
    pkill -f "fastapi dev" 2>/dev/null || true
    pkill -f "vite.*3000" 2>/dev/null || true
    pkill -f "pnpm dev" 2>/dev/null || true
    pkill -f "jupyter lab" 2>/dev/null || true
    pkill -f "jupyter notebook" 2>/dev/null || true
    sleep 1

    # Kill by port (fallback)
    lsof -ti:8000 | xargs kill -9 2>/dev/null || true
    lsof -ti:3000 | xargs kill -9 2>/dev/null || true
    lsof -ti:8888 | xargs kill -9 2>/dev/null || true

    # Stop all dataing-demo-* containers
    for container in $(docker ps -aq --filter "name=dataing-demo-" 2>/dev/null); do
        docker stop "$container" 2>/dev/null || true
        docker rm -f "$container" 2>/dev/null || true
    done

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
