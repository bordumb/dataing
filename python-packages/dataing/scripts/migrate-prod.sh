#!/usr/bin/env bash
#
# migrate-prod.sh - Run database migrations against a production PostgreSQL instance
#
# USAGE:
#   DATABASE_URL="postgresql://user:pass@host:5432/dbname" ./scripts/migrate-prod.sh  # pragma: allowlist secret
#
# DESCRIPTION:
#   Runs infra/init-app-db.sh, the migration runner every deployment uses, against
#   the database specified by DATABASE_URL. Each file in
#   python-packages/dataing/migrations/ is applied once and recorded in
#   schema_migrations, so re-running this script only applies new migrations.
#   Seed files (demo data, including a demo login with a published password) are
#   skipped unless INCLUDE_SEEDS=true; use that for demo deployments only.
#
#   A database migrated before migrations were tracked is refused. The error
#   explains how to recreate it, or adopt it as-is with MIGRATIONS_BASELINE.
#
# PREREQUISITES:
#   - psql and pg_isready (PostgreSQL client) must be installed locally
#   - DATABASE_URL environment variable must be set
#
# HOW TO GET DATABASE_URL FROM RAILWAY:
#   1. Go to Railway dashboard
#   2. Click your PostgreSQL service
#   3. Go to "Connect" tab
#   4. Copy the "Postgres Connection URL"
#
# EXAMPLE:
#   export DATABASE_URL="postgresql://postgres:PASSWORD@dataing.railway.internal:5432/railway"  # pragma: allowlist secret
#   ./scripts/migrate-prod.sh
#

set -euo pipefail

# Check DATABASE_URL is set
if [[ -z "${DATABASE_URL:-}" ]]; then
    echo "ERROR: DATABASE_URL environment variable is not set"
    echo ""
    echo "Usage:"
    echo "  DATABASE_URL=\"postgresql://user:pass@host:5432/db\" $0"  # pragma: allowlist secret
    echo ""
    echo "Get your DATABASE_URL from Railway:"
    echo "  Dashboard → PostgreSQL service → Connect → Copy connection URL"
    exit 1
fi

# Check psql is available
if ! command -v psql &> /dev/null; then
    echo "ERROR: psql (PostgreSQL client) is not installed"
    echo ""
    echo "Install it:"
    echo "  macOS:  brew install postgresql"
    echo "  Ubuntu: sudo apt-get install postgresql-client"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Running migrations against production database..."
MIGRATIONS_DIR="${SCRIPT_DIR}/../migrations" bash "${SCRIPT_DIR}/../../../infra/init-app-db.sh"

echo ""
echo "Next steps:"
echo "  1. Verify tables exist in Railway PostgreSQL dashboard"
echo "  2. Redeploy your backend service if needed"
