#!/bin/bash
# Initialize Temporal databases in PostgreSQL
# This script runs on first PostgreSQL container startup

set -e

echo "Creating Temporal databases and user..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create temporal user if not exists
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'temporal') THEN
            CREATE USER temporal WITH PASSWORD 'temporal';  -- pragma: allowlist secret
        END IF;
    END
    \$\$;

    -- Create temporal database for workflow history
    SELECT 'CREATE DATABASE temporal OWNER temporal'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal')\gexec

    -- Create temporal_visibility database for visibility store
    SELECT 'CREATE DATABASE temporal_visibility OWNER temporal'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'temporal_visibility')\gexec

    -- Grant privileges
    GRANT ALL PRIVILEGES ON DATABASE temporal TO temporal;
    GRANT ALL PRIVILEGES ON DATABASE temporal_visibility TO temporal;
EOSQL

echo "Temporal databases created successfully"
