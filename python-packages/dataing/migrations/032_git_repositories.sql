-- Git Repositories and Code Changes
-- Epic fn-36: Git Integration for Pipeline Change Detection

-- Git repositories connected for pipeline change tracking
CREATE TABLE git_repositories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    provider TEXT NOT NULL CHECK (provider IN ('github', 'gitlab', 'bitbucket')),
    access_token_encrypted TEXT,
    tracked_paths TEXT[],
    default_branch TEXT DEFAULT 'main',
    last_sync_at TIMESTAMPTZ,
    sync_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (sync_status IN ('pending', 'syncing', 'synced', 'error')),
    sync_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for git_repositories
CREATE INDEX idx_git_repositories_tenant ON git_repositories(tenant_id);
CREATE UNIQUE INDEX idx_git_repositories_tenant_url ON git_repositories(tenant_id, url);

-- Code changes (commits) synced from git repositories
CREATE TABLE code_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id UUID NOT NULL REFERENCES git_repositories(id) ON DELETE CASCADE,
    commit_hash TEXT NOT NULL,
    author_name TEXT,
    author_email TEXT,
    message TEXT,
    committed_at TIMESTAMPTZ,
    affected_assets JSONB DEFAULT '[]',
    raw_diff TEXT,
    files_changed TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for code_changes
CREATE INDEX idx_code_changes_repo_committed ON code_changes(repo_id, committed_at DESC);
CREATE UNIQUE INDEX idx_code_changes_repo_commit ON code_changes(repo_id, commit_hash);
CREATE INDEX idx_code_changes_affected_assets ON code_changes USING GIN (affected_assets);

-- Trigger for git_repositories updated_at
CREATE TRIGGER update_git_repositories_updated_at BEFORE UPDATE ON git_repositories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
