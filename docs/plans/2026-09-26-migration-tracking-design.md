# Apply each migration exactly once

Status: approved 2026-09-26. Flow epic: fn-58.

## Problem

Every migration runner re-applied every file in `python-packages/dataing/migrations/`
on every run, ignoring errors (`psql -f … || true`, no `ON_ERROR_STOP`):

- `docker compose` service `db-migrate` (`infra/init-app-db.sh`), on each `up`,
  against the persistent `dataing-pgdata` volume.
- `just demo-infra` (a fresh container each time).
- `python-packages/dataing/scripts/migrate-prod.sh` (Railway), which also applied
  the demo seeds.
- The `migrated_db` pytest fixture (a fresh database per session).

Re-applying destroys data. Reproduced on pgvector/pgvector:pg16: one re-apply
empties `users` (007 `DROP TABLE IF EXISTS users CASCADE`) and `investigations`
(013 `DROP TABLE IF EXISTS investigations CASCADE`), drops 28 foreign keys
(126 → 98, because the dependent tables use `CREATE TABLE IF NOT EXISTS` or fail
as "already exists"), and leaves orphaned rows such as `org_memberships`.

The DROPs themselves are needed on a fresh database: `001_initial.sql` creates
older `users` and `investigations` tables that 007 and 013 replace. Running each
file once makes them harmless.

## Design

One runner, `infra/init-app-db.sh`, used by all four callers.

1. Input is `DATABASE_URL` (required), `MIGRATIONS_DIR` (defaults to the repo's
   migrations), `INCLUDE_SEEDS` (default `false`) and `MIGRATIONS_BASELINE`
   (optional, see below).
2. Applied files are recorded in
   `schema_migrations(filename text primary key, applied_at timestamptz)`. The
   table name is unqualified everywhere, so it follows `search_path` exactly like
   the tables the migrations create (e.g. a schema named after the user).
3. Each pending file runs as
   `psql -v ON_ERROR_STOP=1 -c BEGIN -c "SET LOCAL client_min_messages = warning" -f <file> -c "INSERT INTO schema_migrations …" -c COMMIT`.
   The file and its record commit together or not at all: on any error,
   including a failed psql meta-command, psql exits before COMMIT and the server
   rolls back. (`--single-transaction` is not used: psql 14 still commits after a
   failed meta-command.) The run stops at the first failing file.
4. A pending file containing its own `BEGIN`/`COMMIT`/`ROLLBACK` is refused
   before anything runs, because it would end the wrapping transaction.
   Statements that can't run in a transaction block (`CREATE INDEX CONCURRENTLY`)
   fail and roll back.
5. Schema migrations apply in byte order of their names (`LC_ALL=C`), everywhere.
6. Seed files, named `NNN_seed_*.sql`, are skipped unless `INCLUDE_SEEDS=true`.
   When included, they apply after every schema migration, whether that is the
   first run or a later one, so they always target the latest schema. They are
   recorded and apply once.

### Databases migrated before tracking

A database that has tables in `public` but no recorded migrations is refused:
the runner can't know which files ran, and re-running them destroys data. The
error says how to recover:

- Recreate it (`docker compose down -v`, then `up`). This is the default path,
  since every such database that was migrated more than once has already lost
  its users, investigations and 28 foreign keys.
- Or adopt it as-is with `MIGRATIONS_BASELINE=<last file it has>`, e.g.
  `034_code_changes_pr_metadata.sql`. Every non-seed file up to and including
  that name is recorded as applied without running; later files then apply
  normally. Adopting keeps any damage from earlier re-runs, and the messages say
  so. The baseline is ignored (with a note) on an empty database or one that
  already records migrations.

### Callers

- `db-migrate` (docker compose): `bash` entrypoint, `DATABASE_URL` without the
  password (which goes in `PGPASSWORD`, keeping it off psql's command line), and
  `MIGRATIONS_BASELINE` passed through from the host.
- `just demo-infra`: calls the runner with seeds off.
- `migrate-prod.sh`: thin wrapper around the runner. Seeds are now off unless
  `INCLUDE_SEEDS=true`, so production no longer gets the demo login.
- `migrated_dsn` fixture: calls the runner, so tests exercise the same code
  path as every deployment.

## Not doing

- Checksums of applied files. We are pre-launch and still edit migrations
  (008's duplicate `teams` was fixed in place). Rule instead: never edit, rename
  or delete a file that has been applied anywhere that matters; add a new one.
  A renamed file would apply again under its new name.
- Down migrations, advisory locks. The primary key on `schema_migrations` makes a
  concurrent double-apply fail and roll back instead of applying twice.
- Squashing 001–034 into a baseline file.

## Testing

Integration tests (`-m integration`) run the real script against throwaway
databases:

- a fresh database records every schema file once, in byte order whatever the
  caller's locale;
- a re-run applies nothing and keeps data and foreign keys;
- a file added later applies on the next run;
- a failing file, including one whose psql meta-command fails, rolls back and
  is not recorded; a file with its own BEGIN/COMMIT is refused;
- history follows `search_path` (a schema named after the user);
- seeds are skipped by default, apply after all schema files, and apply once;
- a pre-tracking database is refused, and `MIGRATIONS_BASELINE` adopts it;
- bad file names and a missing `pg_isready` are reported clearly.

The `db-migrate` path is checked by running `postgres:16-alpine` with the same
mounts, entrypoint and environment as the compose service.
