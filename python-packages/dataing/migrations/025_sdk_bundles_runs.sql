-- Migration: SDK Bundles and Runs persistence
-- Purpose: Store bundles, runs, and run events for SDK/Notebook ecosystem

-- Bundles table: context snapshots with content-addressable deduplication
CREATE TABLE IF NOT EXISTS sdk_bundles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bundle_hash VARCHAR(64) NOT NULL,
    assets JSONB NOT NULL,
    time_window VARCHAR(50),
    lineage JSONB,
    operational JSONB,
    anomalies JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 days'),
    CONSTRAINT uq_bundle_tenant_hash UNIQUE (tenant_id, bundle_hash)
);

-- Index for efficient lookups
CREATE INDEX IF NOT EXISTS idx_sdk_bundles_tenant ON sdk_bundles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sdk_bundles_hash ON sdk_bundles(bundle_hash);
CREATE INDEX IF NOT EXISTS idx_sdk_bundles_expires ON sdk_bundles(expires_at);

-- Runs table: investigation runs bound to bundles
CREATE TABLE IF NOT EXISTS sdk_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    bundle_id UUID REFERENCES sdk_bundles(id) ON DELETE SET NULL,
    bundle_hash VARCHAR(64) NOT NULL,
    goal TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'running',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT chk_run_status CHECK (status IN ('running', 'completed', 'failed', 'cancelled'))
);

-- Indexes for runs
CREATE INDEX IF NOT EXISTS idx_sdk_runs_tenant ON sdk_runs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_sdk_runs_bundle ON sdk_runs(bundle_id);
CREATE INDEX IF NOT EXISTS idx_sdk_runs_status ON sdk_runs(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_sdk_runs_created ON sdk_runs(created_at DESC);

-- Run events table: SSE events with sequence ordering
CREATE TABLE IF NOT EXISTS sdk_run_events (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES sdk_runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    data JSONB NOT NULL DEFAULT '{}',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_run_event_seq UNIQUE (run_id, seq)
);

-- Indexes for events
CREATE INDEX IF NOT EXISTS idx_sdk_run_events_run ON sdk_run_events(run_id);
CREATE INDEX IF NOT EXISTS idx_sdk_run_events_run_seq ON sdk_run_events(run_id, seq);

-- Comments
COMMENT ON TABLE sdk_bundles IS 'Context bundles for SDK investigations';
COMMENT ON TABLE sdk_runs IS 'Investigation runs triggered via SDK/Notebook';
COMMENT ON TABLE sdk_run_events IS 'SSE events for streaming run progress';

COMMENT ON COLUMN sdk_bundles.bundle_hash IS 'Content-addressable hash for deduplication';
COMMENT ON COLUMN sdk_bundles.assets IS 'JSON array of asset references';
COMMENT ON COLUMN sdk_runs.bundle_hash IS 'Cached hash for quick lookups without join';
COMMENT ON COLUMN sdk_run_events.seq IS 'Sequential event number for SSE resumption';
