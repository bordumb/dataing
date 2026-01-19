-- Automation rules for auto-triggering actions on issue events (EE)

-- Automation rules table
CREATE TABLE automation_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    enabled BOOLEAN NOT NULL DEFAULT true,

    -- Rule definition (JSON DSL)
    conditions JSONB NOT NULL DEFAULT '{}',
    actions JSONB NOT NULL DEFAULT '[]',

    -- Rate limiting
    rate_limit_per_hour INT NOT NULL DEFAULT 100,
    rate_limit_window_start TIMESTAMPTZ,
    rate_limit_count INT NOT NULL DEFAULT 0,

    -- Circuit breaker
    consecutive_failures INT NOT NULL DEFAULT 0,
    circuit_breaker_tripped BOOLEAN NOT NULL DEFAULT false,
    circuit_breaker_tripped_at TIMESTAMPTZ,

    -- Statistics
    total_executions INT NOT NULL DEFAULT 0,
    successful_executions INT NOT NULL DEFAULT 0,
    failed_executions INT NOT NULL DEFAULT 0,
    last_executed_at TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

-- Index for tenant lookup
CREATE INDEX idx_automation_rules_tenant_id ON automation_rules(tenant_id);
CREATE INDEX idx_automation_rules_enabled ON automation_rules(tenant_id, enabled);

-- Rule execution audit log
CREATE TABLE rule_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES automation_rules(id) ON DELETE CASCADE,
    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,

    -- Execution context
    trigger_event TEXT NOT NULL,  -- 'issue_created', 'issue_updated', etc.
    matched_conditions JSONB NOT NULL DEFAULT '{}',

    -- Results
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, success, failed, skipped
    actions_executed JSONB NOT NULL DEFAULT '[]',
    error_message TEXT,

    -- Timing
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_ms INT
);

-- Index for rule and issue lookup
CREATE INDEX idx_rule_executions_rule_id ON rule_executions(rule_id);
CREATE INDEX idx_rule_executions_issue_id ON rule_executions(issue_id);
CREATE INDEX idx_rule_executions_started_at ON rule_executions(started_at DESC);

-- Unique constraint to prevent duplicate executions for same event
CREATE UNIQUE INDEX idx_rule_executions_unique ON rule_executions(rule_id, issue_id, trigger_event);
