-- Integration Webhooks Infrastructure
-- Epic fn-14.8: Integration webhooks infrastructure

-- Integrations table (EE feature, but schema lives in CE migrations)
-- Stores configuration for external integration providers
CREATE TABLE integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    provider TEXT NOT NULL,  -- jira, linear, pagerduty, opsgenie, custom
    enabled BOOLEAN NOT NULL DEFAULT true,
    -- Provider-specific configuration (encrypted)
    config JSONB NOT NULL DEFAULT '{}',
    -- Signing secret for webhook verification (encrypted)
    signing_secret TEXT,
    -- Rate limiting
    rate_limit_per_minute INT DEFAULT 60,
    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_webhook_at TIMESTAMPTZ,
    webhook_count INT NOT NULL DEFAULT 0,
    error_count INT NOT NULL DEFAULT 0,
    UNIQUE (tenant_id, name)
);

CREATE INDEX idx_integrations_tenant ON integrations(tenant_id);
CREATE INDEX idx_integrations_provider ON integrations(tenant_id, provider);

-- Integration events table for idempotency and audit
-- Prevents duplicate processing of the same webhook event
CREATE TABLE integration_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    integration_id UUID NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
    -- Idempotency key from provider (e.g., X-Request-Id, event ID)
    idempotency_key TEXT NOT NULL,
    -- Event metadata
    event_type TEXT NOT NULL,
    payload_hash TEXT NOT NULL,  -- SHA256 of payload for dedup
    -- Processing status
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, processed, failed, skipped
    error_message TEXT,
    -- Result
    issue_id UUID REFERENCES issues(id) ON DELETE SET NULL,
    -- Timestamps
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    UNIQUE (integration_id, idempotency_key)
);

CREATE INDEX idx_integration_events_integration ON integration_events(integration_id, received_at DESC);
CREATE INDEX idx_integration_events_status ON integration_events(status) WHERE status = 'pending';
CREATE INDEX idx_integration_events_payload_hash ON integration_events(integration_id, payload_hash);

-- Provider-specific field mappings (allows customization)
CREATE TABLE integration_field_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    integration_id UUID NOT NULL REFERENCES integrations(id) ON DELETE CASCADE,
    source_field TEXT NOT NULL,  -- Field path in provider payload (e.g., "issue.summary")
    target_field TEXT NOT NULL,  -- Issue field (e.g., "title", "description", "severity")
    transform TEXT,  -- Optional transform (e.g., "uppercase", "severity_map")
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (integration_id, source_field)
);

CREATE INDEX idx_integration_field_mappings ON integration_field_mappings(integration_id);
