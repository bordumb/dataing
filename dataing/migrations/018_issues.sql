-- Issues and Investigations System
-- Epic fn-14: Issues as first-class objects for intake, triage, collaboration, and workflow

-- Issues core table
CREATE TABLE issues (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    number BIGINT NOT NULL,  -- per-tenant sequence
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    priority TEXT,  -- P0, P1, P2, P3
    severity TEXT,  -- low, medium, high, critical
    due_at TIMESTAMPTZ,
    dataset_id TEXT,
    assignee_user_id UUID REFERENCES users(id),
    acknowledged_by UUID REFERENCES users(id),  -- for triage queues without assignee
    created_by_user_id UUID REFERENCES users(id),
    author_type TEXT NOT NULL DEFAULT 'human',  -- human, integration
    source_provider TEXT,
    source_external_id TEXT,
    source_external_url TEXT,
    source_fingerprint TEXT,  -- secondary dedup key
    sla_policy_id UUID,  -- nullable, uses tenant default if null
    resolution_note TEXT,  -- required for RESOLVED state (or linked investigation/runbook)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    UNIQUE (tenant_id, number)
);

-- Indexes for common queries
CREATE INDEX idx_issues_tenant_status ON issues(tenant_id, status);
CREATE INDEX idx_issues_tenant_updated ON issues(tenant_id, updated_at DESC);
CREATE INDEX idx_issues_assignee ON issues(assignee_user_id) WHERE assignee_user_id IS NOT NULL;
CREATE INDEX idx_issues_dataset ON issues(dataset_id) WHERE dataset_id IS NOT NULL;

-- Primary dedup: (tenant, provider, external_id) when external ID present
CREATE UNIQUE INDEX idx_issues_primary_dedup ON issues(tenant_id, source_provider, source_external_id)
    WHERE source_external_id IS NOT NULL;

-- Secondary dedup via fingerprint
CREATE INDEX idx_issues_fingerprint ON issues(source_fingerprint) WHERE source_fingerprint IS NOT NULL;

-- Full-text search
ALTER TABLE issues ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(description, '')), 'B')
    ) STORED;
CREATE INDEX idx_issues_search ON issues USING GIN (search_vector);

-- Issue number sequence function
CREATE OR REPLACE FUNCTION next_issue_number(p_tenant_id UUID) RETURNS BIGINT AS $$
DECLARE
    next_num BIGINT;
BEGIN
    SELECT COALESCE(MAX(number), 0) + 1 INTO next_num FROM issues WHERE tenant_id = p_tenant_id;
    RETURN next_num;
END;
$$ LANGUAGE plpgsql;

-- Labels (many-to-many via join table with composite PK)
CREATE TABLE issue_labels (
    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    label TEXT NOT NULL,
    PRIMARY KEY (issue_id, label)
);
CREATE INDEX idx_issue_labels_label ON issue_labels(label);

-- Comments
CREATE TABLE issue_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    author_user_id UUID NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_issue_comments_issue ON issue_comments(issue_id, created_at);

-- Events/audit trail (immutable event log)
CREATE TABLE issue_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    actor_user_id UUID REFERENCES users(id),
    payload JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_issue_events_issue ON issue_events(issue_id, created_at DESC);

-- Relationships between issues (duplicates, blocks, relates_to)
CREATE TABLE issue_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    to_issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,  -- duplicates, blocks, relates_to
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (from_issue_id, to_issue_id, relationship_type)
);
CREATE INDEX idx_issue_relationships_from ON issue_relationships(from_issue_id);
CREATE INDEX idx_issue_relationships_to ON issue_relationships(to_issue_id);

-- Watchers (users subscribed to issue updates)
CREATE TABLE issue_watchers (
    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (issue_id, user_id)
);

-- Issue -> Investigation linkage
CREATE TABLE issue_investigation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    issue_id UUID NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    trigger_type TEXT NOT NULL,  -- human, rule, webhook
    trigger_ref JSONB,
    focus_prompt TEXT,
    execution_profile TEXT DEFAULT 'standard',  -- safe, standard, deep
    approval_status TEXT,  -- queued, approved, rejected (null = no approval needed)
    -- Structured result fields (populated on completion)
    confidence FLOAT,
    root_cause_tag TEXT,
    synthesis_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);
CREATE INDEX idx_issue_inv_runs_issue ON issue_investigation_runs(issue_id, created_at DESC);
CREATE INDEX idx_issue_inv_runs_investigation ON issue_investigation_runs(investigation_id);
