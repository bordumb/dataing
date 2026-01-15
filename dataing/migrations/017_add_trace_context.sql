-- Add trace context and timing columns for distributed tracing and SLOs
-- Pre-launch: no need for CONCURRENTLY, table is small

ALTER TABLE investigation_jobs
ADD COLUMN traceparent TEXT,
ADD COLUMN tracestate TEXT,
ADD COLUMN enqueued_at TIMESTAMPTZ,
ADD COLUMN correlation_id TEXT;

-- Simple indexes (non-concurrent is fine pre-launch)
CREATE INDEX idx_investigation_jobs_traceparent
ON investigation_jobs(traceparent) WHERE traceparent IS NOT NULL;

CREATE INDEX idx_investigation_jobs_correlation_id
ON investigation_jobs(correlation_id) WHERE correlation_id IS NOT NULL;

COMMENT ON COLUMN investigation_jobs.traceparent IS 'W3C traceparent header for distributed tracing';
COMMENT ON COLUMN investigation_jobs.tracestate IS 'W3C tracestate header for vendor-specific context';
COMMENT ON COLUMN investigation_jobs.enqueued_at IS 'Timestamp when job was enqueued (for SLO measurement)';
COMMENT ON COLUMN investigation_jobs.correlation_id IS 'Correlation ID for log correlation across services';
