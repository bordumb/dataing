-- Migration: 010_audit_logs.sql
-- Audit logging table for compliance (SOC 2, GDPR)

CREATE TABLE IF NOT EXISTS audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- When
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Who
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    actor_id UUID,
    actor_email VARCHAR(255),
    actor_ip VARCHAR(45),
    actor_user_agent TEXT,

    -- What
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id UUID,
    resource_name VARCHAR(255),

    -- Details
    request_method VARCHAR(10),
    request_path TEXT,
    status_code INTEGER,
    changes JSONB,
    metadata JSONB,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add missing columns if table already existed (idempotent)
DO $$ BEGIN
    ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS resource_name VARCHAR(255);
EXCEPTION
    WHEN duplicate_column THEN null;
END $$;

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_audit_logs_tenant_timestamp
    ON audit_logs(tenant_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor
    ON audit_logs(tenant_id, actor_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_action
    ON audit_logs(tenant_id, action, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_resource
    ON audit_logs(tenant_id, resource_type, resource_id);

-- Partial index for recent logs (most common queries)
CREATE INDEX IF NOT EXISTS idx_audit_logs_recent
    ON audit_logs(tenant_id, timestamp DESC)
    WHERE timestamp > NOW() - INTERVAL '30 days';
