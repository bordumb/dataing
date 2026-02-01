#!/bin/bash
# Initialize Dataing application database with migrations
# This script runs all SQL migrations in order, idempotently.
set -e

echo "Waiting for PostgreSQL to be ready..."
until pg_isready -h "${PGHOST:-postgres}" -p "${PGPORT:-5432}" -U "${PGUSER:-dataing}"; do
  sleep 2
done

echo "Running Dataing migrations..."

MIGRATIONS_DIR="${MIGRATIONS_DIR:-/app/migrations}"

# Run all migrations in sorted order
# Set INCLUDE_SEEDS=true to include seed migrations (demo data)
for f in "$MIGRATIONS_DIR"/*.sql; do
  if [ -f "$f" ]; then
    # Skip seed migrations unless INCLUDE_SEEDS is true
    if [[ "$(basename "$f")" == *seed* ]]; then
      if [[ "${INCLUDE_SEEDS:-false}" != "true" ]]; then
        echo "Skipping seed: $(basename "$f")"
        continue
      fi
    fi
    echo "Applying: $(basename "$f")"
    PGPASSWORD="${PGPASSWORD:-dataing}" psql \
      -h "${PGHOST:-postgres}" \
      -p "${PGPORT:-5432}" \
      -U "${PGUSER:-dataing}" \
      -d "${PGDATABASE:-dataing}" \
      -f "$f" 2>&1 | grep -v "^NOTICE:" || true
  fi
done

echo "Migrations complete!"
