-- Dataset-to-Repository Mappings
-- Epic fn-32: Git integration for pipeline change detection

CREATE TABLE dataset_repo_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    dataset_pattern TEXT NOT NULL,
    pattern_type TEXT NOT NULL DEFAULT 'exact' CHECK (pattern_type IN ('exact', 'glob')),
    priority INT NOT NULL DEFAULT 0,
    repo_owner TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    file_path TEXT,
    branch TEXT,
    job_name TEXT,
    source TEXT NOT NULL DEFAULT 'manual'
        CHECK (source IN ('manual', 'openlineage', 'dbt_manifest', 'bulk_import')),
    confidence FLOAT NOT NULL DEFAULT 1.0
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    confirmed BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB DEFAULT '{}',
    last_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_drm_tenant_pattern ON dataset_repo_mappings(tenant_id, dataset_pattern);
CREATE INDEX idx_drm_tenant_source ON dataset_repo_mappings(tenant_id, source);
CREATE INDEX idx_drm_tenant_confirmed ON dataset_repo_mappings(tenant_id, confirmed);

-- Prevent duplicate confirmed mappings for the same dataset+repo
CREATE UNIQUE INDEX idx_drm_unique_mapping
    ON dataset_repo_mappings(tenant_id, dataset_pattern, repo_owner, repo_name)
    WHERE confirmed = true;
