-- Investigation Jobs table for durable execution
-- Tracks job execution state, checkpoints, and worker ownership

CREATE TABLE investigation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INT NOT NULL DEFAULT 0,

    -- Checkpoint state
    current_step TEXT,
    checkpoint JSONB,

    -- Execution tracking
    worker_id TEXT,
    attempts INT DEFAULT 0,
    max_attempts INT DEFAULT 3,

    -- Timing
    created_at TIMESTAMPTZ DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Failure handling
    error TEXT,
    last_error_at TIMESTAMPTZ
);

-- Index for efficient job polling: pending jobs ordered by priority and age
CREATE INDEX idx_jobs_pending ON investigation_jobs (priority DESC, created_at)
    WHERE status = 'pending';

-- Index for tenant-scoped queries
CREATE INDEX idx_jobs_tenant ON investigation_jobs (tenant_id);

-- Index for finding jobs by investigation
CREATE INDEX idx_jobs_investigation ON investigation_jobs (investigation_id);

-- Add comment explaining the table's purpose
COMMENT ON TABLE investigation_jobs IS 'Tracks durable job execution for investigations. Checkpoint column stores serialized InvestigationContext for crash recovery.';
