-- Migration: Add VP Product-critical fields to SDK tables
-- Purpose: Add error tracking, display names, and retention fields

-- Add error tracking to runs
ALTER TABLE sdk_runs
    ADD COLUMN IF NOT EXISTS error_code VARCHAR(50),
    ADD COLUMN IF NOT EXISTS error_message TEXT,
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '30 days');

-- Add event display name for stable client rendering
ALTER TABLE sdk_run_events
    ADD COLUMN IF NOT EXISTS event_name VARCHAR(100);

-- Index for error queries
CREATE INDEX IF NOT EXISTS idx_sdk_runs_error_code ON sdk_runs(error_code) WHERE error_code IS NOT NULL;

-- Index for retention cleanup
CREATE INDEX IF NOT EXISTS idx_sdk_runs_expires ON sdk_runs(expires_at);

-- Comments
COMMENT ON COLUMN sdk_runs.error_code IS 'Structured error code (e.g., timeout, rate_limit)';
COMMENT ON COLUMN sdk_runs.error_message IS 'Human-readable error description';
COMMENT ON COLUMN sdk_runs.expires_at IS 'Retention: when run data can be deleted';
COMMENT ON COLUMN sdk_run_events.event_name IS 'Display name for stable client rendering';
