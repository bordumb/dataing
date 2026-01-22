-- Analytics Events for Activation and Usage Tracking
-- fn-24.7: Activation + weekly usage analytics

-- Analytics events table for recording business-level events
CREATE TABLE analytics_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,  -- issue_created, investigation_started, investigation_completed, issue_resolved
    entity_type TEXT NOT NULL,  -- issue, investigation
    entity_id UUID NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common analytics queries
CREATE INDEX idx_analytics_events_tenant_type ON analytics_events(tenant_id, event_type);
CREATE INDEX idx_analytics_events_tenant_created ON analytics_events(tenant_id, created_at DESC);
CREATE INDEX idx_analytics_events_team_type ON analytics_events(team_id, event_type) WHERE team_id IS NOT NULL;
CREATE INDEX idx_analytics_events_type_created ON analytics_events(event_type, created_at);

-- Tenant activation tracking
CREATE TABLE tenant_activation (
    tenant_id UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL,
    first_issue_at TIMESTAMPTZ,
    first_investigation_at TIMESTAMPTZ,
    activated_at TIMESTAMPTZ,  -- set when both first_issue_at and first_investigation_at exist within 7 days of created_at
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for activation funnel queries
CREATE INDEX idx_tenant_activation_status ON tenant_activation(activated_at) WHERE activated_at IS NOT NULL;

-- Materialized view for weekly usage aggregates (refreshed by cron or on-demand)
CREATE MATERIALIZED VIEW weekly_usage_stats AS
SELECT
    date_trunc('week', ae.created_at) AS week_start,
    ae.tenant_id,
    ae.team_id,
    COUNT(*) FILTER (WHERE ae.event_type = 'issue_created') AS issues_created,
    COUNT(*) FILTER (WHERE ae.event_type = 'investigation_started') AS investigations_started,
    COUNT(*) FILTER (WHERE ae.event_type = 'investigation_completed') AS investigations_completed,
    COUNT(*) FILTER (WHERE ae.event_type = 'issue_resolved') AS issues_resolved,
    COUNT(DISTINCT CASE WHEN ae.event_type IN ('issue_created', 'investigation_started') THEN ae.team_id END) AS active_teams
FROM analytics_events ae
GROUP BY date_trunc('week', ae.created_at), ae.tenant_id, ae.team_id;

-- Create unique index for concurrent refresh
CREATE UNIQUE INDEX idx_weekly_usage_stats_pk ON weekly_usage_stats(week_start, tenant_id, team_id);

-- Function to record an analytics event
CREATE OR REPLACE FUNCTION record_analytics_event(
    p_tenant_id UUID,
    p_team_id UUID,
    p_event_type TEXT,
    p_entity_type TEXT,
    p_entity_id UUID,
    p_payload JSONB DEFAULT '{}'
) RETURNS UUID AS $$
DECLARE
    event_id UUID;
BEGIN
    INSERT INTO analytics_events (tenant_id, team_id, event_type, entity_type, entity_id, payload)
    VALUES (p_tenant_id, p_team_id, p_event_type, p_entity_type, p_entity_id, p_payload)
    RETURNING id INTO event_id;

    -- Update activation tracking for tenant
    IF p_event_type = 'issue_created' THEN
        INSERT INTO tenant_activation (tenant_id, created_at, first_issue_at, updated_at)
        VALUES (p_tenant_id, (SELECT created_at FROM tenants WHERE id = p_tenant_id), NOW(), NOW())
        ON CONFLICT (tenant_id) DO UPDATE SET
            first_issue_at = COALESCE(tenant_activation.first_issue_at, NOW()),
            updated_at = NOW();
    ELSIF p_event_type = 'investigation_completed' THEN
        INSERT INTO tenant_activation (tenant_id, created_at, first_investigation_at, updated_at)
        VALUES (p_tenant_id, (SELECT created_at FROM tenants WHERE id = p_tenant_id), NOW(), NOW())
        ON CONFLICT (tenant_id) DO UPDATE SET
            first_investigation_at = COALESCE(tenant_activation.first_investigation_at, NOW()),
            updated_at = NOW();
    END IF;

    -- Check and set activation status
    UPDATE tenant_activation
    SET activated_at = NOW()
    WHERE tenant_id = p_tenant_id
      AND activated_at IS NULL
      AND first_issue_at IS NOT NULL
      AND first_investigation_at IS NOT NULL
      AND (first_issue_at <= created_at + INTERVAL '7 days' OR first_investigation_at <= created_at + INTERVAL '7 days');

    RETURN event_id;
END;
$$ LANGUAGE plpgsql;

-- Function to refresh weekly stats
CREATE OR REPLACE FUNCTION refresh_weekly_usage_stats() RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY weekly_usage_stats;
END;
$$ LANGUAGE plpgsql;
