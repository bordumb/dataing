-- Investigation feedback events: append-only event log for investigation traces
-- Used for: user feedback on investigations, tribal knowledge, ML training data

CREATE TABLE investigation_feedback_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    investigation_id UUID,  -- No FK - investigations are in-memory
    dataset_id UUID REFERENCES datasets(id) ON DELETE SET NULL,
    event_type VARCHAR(100) NOT NULL,
    event_data JSONB NOT NULL DEFAULT '{}',
    actor_id UUID,
    actor_type VARCHAR(50) NOT NULL DEFAULT 'system',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX idx_investigation_feedback_events_tenant ON investigation_feedback_events(tenant_id);
CREATE INDEX idx_investigation_feedback_events_investigation ON investigation_feedback_events(investigation_id);
CREATE INDEX idx_investigation_feedback_events_dataset ON investigation_feedback_events(dataset_id);
CREATE INDEX idx_investigation_feedback_events_type ON investigation_feedback_events(event_type);
CREATE INDEX idx_investigation_feedback_events_created ON investigation_feedback_events(created_at DESC);

-- Composite index for tenant + time range queries
CREATE INDEX idx_investigation_feedback_events_tenant_time ON investigation_feedback_events(tenant_id, created_at DESC);

-- GIN index for JSONB queries on event_data
CREATE INDEX idx_investigation_feedback_events_data ON investigation_feedback_events USING GIN (event_data);

COMMENT ON TABLE investigation_feedback_events IS 'Append-only event log for investigation traces, feedback, and ML training';
COMMENT ON COLUMN investigation_feedback_events.event_type IS 'Event type: investigation.started, hypothesis.generated, query.executed, feedback.submitted, etc.';
COMMENT ON COLUMN investigation_feedback_events.actor_type IS 'Actor type: system, user';
