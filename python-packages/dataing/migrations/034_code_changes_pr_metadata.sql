-- PR metadata for code changes
-- Epic fn-38: PR/Commit Link in Investigation Output

ALTER TABLE code_changes
    ADD COLUMN IF NOT EXISTS pr_number INTEGER,
    ADD COLUMN IF NOT EXISTS pr_url TEXT,
    ADD COLUMN IF NOT EXISTS pr_title TEXT,
    ADD COLUMN IF NOT EXISTS pr_author TEXT,
    ADD COLUMN IF NOT EXISTS pr_merged_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS provider TEXT;

-- Index for PR lookups by commit
CREATE INDEX IF NOT EXISTS idx_code_changes_pr_number
    ON code_changes(repo_id, pr_number)
    WHERE pr_number IS NOT NULL;

COMMENT ON COLUMN code_changes.pr_number IS 'PR/MR number in the provider';
COMMENT ON COLUMN code_changes.pr_url IS 'Full URL to the PR/MR in the provider UI';
COMMENT ON COLUMN code_changes.pr_title IS 'Title of the PR/MR';
COMMENT ON COLUMN code_changes.pr_author IS 'Author login/username of the PR/MR';
COMMENT ON COLUMN code_changes.pr_merged_at IS 'When the PR/MR was merged';
COMMENT ON COLUMN code_changes.provider IS 'Git provider: github, gitlab, bitbucket';
