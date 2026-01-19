#!/usr/bin/env bash
#
# migrate-prod.sh - Run database migrations against a production PostgreSQL instance
#
# USAGE:
#   DATABASE_URL="postgresql://user:pass@host:5432/dbname" ./scripts/migrate-prod.sh  # pragma: allowlist secret
#
# DESCRIPTION:
#   This script runs all migration SQL files in dataing/migrations/ against
#   the database specified by DATABASE_URL. Use this to initialize a fresh
#   Railway/production PostgreSQL database.
#
# PREREQUISITES:
#   - psql (PostgreSQL client) must be installed locally
#   - DATABASE_URL environment variable must be set
#
# HOW TO GET DATABASE_URL FROM RAILWAY:
#   1. Go to Railway dashboard
#   2. Click your PostgreSQL service
#   3. Go to "Connect" tab
#   4. Copy the "Postgres Connection URL"
#
# MIGRATIONS RUN (in order):
#   001_initial.sql                    - Core tables (tenants, datasources, investigations)
#   002_datasets.sql                   - Dataset tables
#   003_investigation_feedback_events.sql - Feedback tracking
#   004_schema_comments.sql            - Schema annotation comments
#   005_knowledge_comments.sql         - Knowledge base comments
#   006_comment_votes.sql              - Comment voting
#   007_auth_tables.sql                - Auth tables (users, organizations, teams)
#   007_sso_scim_tables.sql            - SSO/SCIM enterprise tables
#   008_rbac_tables.sql                - Role-based access control
#   008_seed_demo_auth.sql             - Demo user/org seed data
#   009_password_reset_tokens.sql      - Password recovery
#   009_seed_multi_org_demo.sql        - Multi-org demo data
#   010_audit_logs.sql                 - Audit logging
#   011_rl_training_signals.sql        - RL training signals
#
# EXAMPLE:
#   export DATABASE_URL="postgresql://postgres:dataing.railway.internal:5432/railway"  # pragma: allowlist secret
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

# Find migrations directory (relative to script location)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATIONS_DIR="${SCRIPT_DIR}/../dataing/migrations"

if [[ ! -d "$MIGRATIONS_DIR" ]]; then
    echo "ERROR: Migrations directory not found: $MIGRATIONS_DIR"
    exit 1
fi

echo "Running migrations against production database..."
echo "Migrations directory: $MIGRATIONS_DIR"
echo ""

# Run each migration in order
for migration in "$MIGRATIONS_DIR"/*.sql; do
    filename=$(basename "$migration")
    echo "Running: $filename"

    if psql "$DATABASE_URL" -f "$migration" 2>&1 | grep -v "^NOTICE:" | grep -v "^$"; then
        true  # Suppress empty output
    fi
done

echo ""
echo "Migrations complete!"
echo ""
echo "Next steps:"
echo "  1. Verify tables exist in Railway PostgreSQL dashboard"
echo "  2. Redeploy your backend service if needed"
