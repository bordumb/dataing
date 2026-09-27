#!/usr/bin/env bash
# Apply Dataing's SQL migrations to the database at DATABASE_URL, each exactly once.
#
# Applied files are recorded in schema_migrations. Each pending file runs in one
# transaction together with its record, with ON_ERROR_STOP set: it either applies
# completely and is recorded, or leaves no trace and stops the run. So a migration
# must not contain its own BEGIN/COMMIT/ROLLBACK (refused) or statements that can't
# run in a transaction block, such as CREATE INDEX CONCURRENTLY. Never edit, rename
# or delete a migration once it has been applied anywhere; add a new file instead.
#
# Schema migrations apply in byte order of their names. Seed files (demo data),
# named NNN_seed_*.sql, apply only with INCLUDE_SEEDS=true, after every schema
# migration, so they must match the latest schema. They are recorded and apply once.
#
# Environment:
#   DATABASE_URL         required, e.g. postgresql://user:pass@host:5432/db  # pragma: allowlist secret
#   MIGRATIONS_DIR       default: python-packages/dataing/migrations in this repo
#   INCLUDE_SEEDS        "true" to also apply seed files
#   MIGRATIONS_BASELINE  adopt a database migrated before migrations were tracked:
#                        record every schema migration up to and including this
#                        file as applied without running it, then apply the rest
#
# Used by docker compose (db-migrate), `just demo-infra`,
# python-packages/dataing/scripts/migrate-prod.sh and the migrated_dsn test fixture.
set -euo pipefail
export LC_ALL=C # byte order for file names, whatever the caller's locale

: "${DATABASE_URL:?DATABASE_URL must be set}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/python-packages/dataing/migrations}"
INCLUDE_SEEDS="${INCLUDE_SEEDS:-false}"
MIGRATIONS_BASELINE="${MIGRATIONS_BASELINE:-}"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

run_psql() {
  psql --no-psqlrc --quiet --set ON_ERROR_STOP=1 "$DATABASE_URL" "$@"
}

seed_name='^[0-9]+_seed_'
is_seed() {
  [[ "$1" =~ $seed_name ]]
}

for tool in psql pg_isready; do
  command -v "$tool" >/dev/null || die "$tool (PostgreSQL client) is not on PATH"
done

attempts=0
until pg_isready --quiet --dbname "$DATABASE_URL"; do
  attempts=$((attempts + 1))
  [ "$attempts" -lt 30 ] || die "PostgreSQL is not accepting connections at DATABASE_URL"
  echo "Waiting for PostgreSQL..."
  sleep 2
done

shopt -s nullglob
files=("$MIGRATIONS_DIR"/*.sql)
[ "${#files[@]}" -gt 0 ] || die "no migrations (*.sql) in $MIGRATIONS_DIR"
valid_name='^[A-Za-z0-9_.-]+$'
for file in "${files[@]}"; do
  [[ "${file##*/}" =~ $valid_name ]] || die "unsupported migration file name: ${file##*/}"
done

# schema_migrations is unqualified everywhere, so it resolves through search_path
# just like the tables the migrations create.
state="$(run_psql -At -F ' ' -c "SELECT to_regclass('schema_migrations') IS NOT NULL,
  EXISTS (SELECT FROM pg_tables WHERE schemaname IN ('public', current_schema())
          AND tablename <> 'schema_migrations')")" ||
  die "could not query the database at DATABASE_URL"
has_history="${state%% *}"
has_tables="${state##* }"
applied=""
if [ "$has_history" = t ]; then
  applied="$(run_psql -At -c "SELECT filename FROM schema_migrations")"
fi
history_columns="(filename text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"

if [ -z "$applied" ] && [ "$has_tables" = t ]; then
  if [ -z "$MIGRATIONS_BASELINE" ]; then
    cat >&2 <<'EOF'
ERROR: this database has tables but no migration history (schema_migrations).
It was migrated before migrations were tracked, so which files already ran is
unknown, and re-running them destroys data. Either:
  - recreate it (docker compose: `docker compose down -v`, then `up`), or
  - adopt it as-is: set MIGRATIONS_BASELINE to the last migration it has,
    e.g. MIGRATIONS_BASELINE=034_code_changes_pr_metadata.sql
Adopting keeps the schema as it is, including damage from earlier re-runs
(emptied users and investigations, missing foreign keys). Recreate it unless
you need its data.
EOF
    exit 1
  fi
  # Record every schema migration up to the baseline. Seeds are left out: they
  # are opt-in, and apply on a later run with INCLUDE_SEEDS=true.
  adopt="BEGIN; SET LOCAL client_min_messages = warning;
    CREATE TABLE IF NOT EXISTS schema_migrations $history_columns;"
  found=false
  for file in "${files[@]}"; do
    name="${file##*/}"
    is_seed "$name" || adopt="$adopt INSERT INTO schema_migrations (filename) VALUES ('$name');"
    if [ "$name" = "$MIGRATIONS_BASELINE" ]; then
      found=true
      break
    fi
  done
  $found || die "MIGRATIONS_BASELINE=$MIGRATIONS_BASELINE is not a migration in $MIGRATIONS_DIR"
  echo "Adopting this database: recording migrations up to $MIGRATIONS_BASELINE as applied"
  run_psql -c "$adopt COMMIT;"
  has_history=t
  applied="$(run_psql -At -c "SELECT filename FROM schema_migrations")"
elif [ -n "$MIGRATIONS_BASELINE" ]; then
  echo "Ignoring MIGRATIONS_BASELINE: only a database with tables but no migration history is adopted"
fi

is_applied() {
  case $'\n'"$applied"$'\n' in
    *$'\n'"$1"$'\n'*) return 0 ;;
  esac
  return 1
}

# Pending migrations in the order they apply: schema migrations by name, then
# seeds (when included), so seeds always run against the latest schema.
pending=()
for file in "${files[@]}"; do
  name="${file##*/}"
  if ! is_seed "$name" && ! is_applied "$name"; then
    pending+=("$file")
  fi
done
if [ "$INCLUDE_SEEDS" = true ]; then
  for file in "${files[@]}"; do
    name="${file##*/}"
    if is_seed "$name" && ! is_applied "$name"; then
      pending+=("$file")
    fi
  done
fi
if [ "${#pending[@]}" -eq 0 ]; then
  echo "Migrations complete: 0 applied"
  exit 0
fi

# A file's own BEGIN/COMMIT would end the transaction it runs in (see the top).
transaction_control='^[[:space:]]*(BEGIN|COMMIT|ROLLBACK|START[[:space:]]+TRANSACTION)([[:space:]]+(WORK|TRANSACTION))?[[:space:]]*;'
for file in "${pending[@]}"; do
  if grep -Eiq "$transaction_control" "$file"; then
    die "${file##*/} contains BEGIN/COMMIT/ROLLBACK; remove them, each migration already runs in its own transaction"
  fi
done

if [ "$has_history" != t ]; then
  run_psql -c "CREATE TABLE schema_migrations $history_columns" ||
    die "could not create schema_migrations (is another migration run in progress?)"
fi

for file in "${pending[@]}"; do
  name="${file##*/}"
  echo "Applying: $name"
  # BEGIN/COMMIT rather than --single-transaction: with ON_ERROR_STOP, psql exits
  # before COMMIT on any error, including a failed meta-command, which psql 14's
  # --single-transaction would still commit.
  run_psql -c "BEGIN" -c "SET LOCAL client_min_messages = warning" --file "$file" \
    -c "INSERT INTO schema_migrations (filename) VALUES ('$name')" -c "COMMIT" ||
    die "$name failed and was rolled back; later migrations were not applied"
done
echo "Migrations complete: ${#pending[@]} applied"
