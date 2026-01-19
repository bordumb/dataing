-- User datasource credentials and query audit log tables
-- Principal-Bound Query Execution: Each user stores their own DB credentials

-- User-specific credentials for each datasource
CREATE TABLE user_datasource_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    datasource_id UUID NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE,

    -- Encrypted credential blob (JSON with username, password, role, etc.)
    credentials_encrypted BYTEA NOT NULL,

    -- Metadata (not sensitive, for display)
    db_username VARCHAR(255),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,

    UNIQUE(user_id, datasource_id)
);

CREATE INDEX idx_user_ds_creds_user ON user_datasource_credentials(user_id);
CREATE INDEX idx_user_ds_creds_ds ON user_datasource_credentials(datasource_id);

-- Query audit log for compliance and debugging
CREATE TABLE query_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Who
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,

    -- What
    datasource_id UUID NOT NULL,
    sql_hash VARCHAR(64) NOT NULL,
    sql_text TEXT,
    tables_accessed TEXT[],

    -- When
    executed_at TIMESTAMPTZ DEFAULT NOW(),
    duration_ms INT,

    -- Result
    row_count INT,
    status VARCHAR(20) NOT NULL,  -- success, denied, error, timeout
    error_message TEXT,

    -- Context
    investigation_id UUID,
    source VARCHAR(50)   -- 'agent', 'api', 'preview', etc.
);

CREATE INDEX idx_audit_tenant_time ON query_audit_log(tenant_id, executed_at DESC);
CREATE INDEX idx_audit_user_time ON query_audit_log(user_id, executed_at DESC);
CREATE INDEX idx_audit_datasource ON query_audit_log(datasource_id, executed_at DESC);
