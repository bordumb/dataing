-- Feedback events: append-only event log for investigation traces
-- Used for: user feedback, tribal knowledge, ML training data

CREATE TABLE feedback_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    investigation_id UUID REFERENCES investigations(id) ON DELETE SET NULL,
    dataset_id UUID REFERENCES datasets(id) ON DELETE SET NULL,
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}',
    actor_id UUID,
    actor_type VARCHAR(50) NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX idx_feedback_events_tenant ON feedback_events(tenant_id);
CREATE INDEX idx_feedback_events_investigation ON feedback_events(investigation_id);
CREATE INDEX idx_feedback_events_dataset ON feedback_events(dataset_id);
CREATE INDEX idx_feedback_events_type ON feedback_events(event_type);
CREATE INDEX idx_feedback_events_created ON feedback_events(created_at DESC);

-- Composite index for tenant + time range queries
CREATE INDEX idx_feedback_events_tenant_time ON feedback_events(tenant_id, created_at DESC);

-- GIN index for JSONB queries on event_data
CREATE INDEX idx_feedback_events_data ON feedback_events USING GIN (event_data);

COMMENT ON TABLE feedback_events IS 'Append-only event log for investigation traces, feedback, and ML training';
COMMENT ON COLUMN feedback_events.event_type IS 'Event type: investigation.started, hypothesis.generated, query.executed, feedback.submitted, etc.';
COMMENT ON COLUMN feedback_events.actor_type IS 'Actor type: system, user';
