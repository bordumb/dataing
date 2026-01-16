-- SLA Policies for Issues
-- Epic fn-14.11: SLA tracking and breach notifications

-- SLA Policies table
CREATE TABLE sla_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT false,
    -- Time limits in minutes (null = not tracked)
    time_to_acknowledge INT,  -- ack = OPEN -> TRIAGED
    time_to_progress INT,     -- progress = TRIAGED -> IN_PROGRESS
    time_to_resolve INT,      -- resolve = any -> RESOLVED
    -- Per severity overrides (JSONB: {"critical": {"time_to_acknowledge": 15}, ...})
    severity_overrides JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, name)
);

CREATE INDEX idx_sla_policies_tenant ON sla_policies(tenant_id);
CREATE INDEX idx_sla_policies_default ON sla_policies(tenant_id, is_default) WHERE is_default = true;

-- Add foreign key from issues to sla_policies
ALTER TABLE issues
    ADD CONSTRAINT fk_issues_sla_policy
    FOREIGN KEY (sla_policy_id) REFERENCES sla_policies(id) ON DELETE SET NULL;

-- Ensure only one default policy per tenant
CREATE UNIQUE INDEX idx_sla_policies_single_default ON sla_policies(tenant_id) WHERE is_default = true;

-- SLA breach tracking (tracks when breach notifications were sent)
CREATE TABLE sla_breach_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    sla_type TEXT NOT NULL,  -- acknowledge, progress, resolve
    threshold INT NOT NULL,  -- 50, 75, 90, 100
    notified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (issue_id, sla_type, threshold)
);

CREATE INDEX idx_sla_breach_notifications_issue ON sla_breach_notifications(issue_id);
