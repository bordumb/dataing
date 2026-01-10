-- Migration: 013_unified_investigation.sql
-- Unified Investigation Architecture - Core Tables

-- Drop old investigation table if exists (we're replacing it)
-- Note: This is safe because we're pre-launch
DROP TABLE IF EXISTS investigations CASCADE;

-- =============================================================================
-- Core Tables
-- =============================================================================

-- Investigations: Root aggregate
CREATE TABLE investigations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    alert JSONB NOT NULL,
    main_branch_id UUID,  -- Set after first branch created
    outcome JSONB,        -- Final finding when complete
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    -- Denormalized status for fast queries
    status TEXT GENERATED ALWAYS AS (
        CASE
            WHEN outcome IS NOT NULL THEN 'completed'
            ELSE 'active'
        END
    ) STORED
);

CREATE INDEX idx_investigations_tenant ON investigations(tenant_id);
CREATE INDEX idx_investigations_status ON investigations(status);
CREATE INDEX idx_investigations_created ON investigations(created_at DESC);

-- Branches: Lines of exploration
CREATE TABLE investigation_branches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    branch_type TEXT NOT NULL CHECK (branch_type IN ('main', 'hypothesis', 'user', 'counter', 'pattern')),
    name TEXT NOT NULL,

    -- Lineage
    parent_branch_id UUID REFERENCES investigation_branches(id),
    forked_from_snapshot_id UUID,

    -- Ownership (for user branches)
    owner_user_id UUID REFERENCES users(id),

    -- Current state (denormalized for performance)
    head_snapshot_id UUID,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'merged', 'abandoned', 'completed')),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_branches_investigation ON investigation_branches(investigation_id);
CREATE INDEX idx_branches_owner ON investigation_branches(owner_user_id) WHERE owner_user_id IS NOT NULL;
CREATE INDEX idx_branches_status ON investigation_branches(status);

-- Snapshots: Immutable state records
CREATE TABLE investigation_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,

    -- Version
    version_major INT NOT NULL DEFAULT 0,
    version_minor INT NOT NULL DEFAULT 0,
    version_patch INT NOT NULL DEFAULT 0,

    -- Lineage
    parent_snapshot_id UUID REFERENCES investigation_snapshots(id),

    -- Workflow position
    step TEXT NOT NULL,
    step_cursor JSONB DEFAULT '{}'::jsonb,

    -- The full context (the "brain")
    context JSONB NOT NULL,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),
    trigger TEXT NOT NULL DEFAULT 'system'
);

CREATE INDEX idx_snapshots_branch_head ON investigation_snapshots(branch_id, created_at DESC);
CREATE INDEX idx_snapshots_investigation ON investigation_snapshots(investigation_id, created_at DESC);

-- Add foreign key for head_snapshot_id after snapshots table exists
ALTER TABLE investigation_branches
    ADD CONSTRAINT fk_branches_head_snapshot
    FOREIGN KEY (head_snapshot_id) REFERENCES investigation_snapshots(id);

-- Add foreign key for forked_from_snapshot_id
ALTER TABLE investigation_branches
    ADD CONSTRAINT fk_branches_forked_snapshot
    FOREIGN KEY (forked_from_snapshot_id) REFERENCES investigation_snapshots(id);

-- Add foreign key for main_branch_id
ALTER TABLE investigations
    ADD CONSTRAINT fk_investigations_main_branch
    FOREIGN KEY (main_branch_id) REFERENCES investigation_branches(id);

-- =============================================================================
-- Execution Control Tables
-- =============================================================================

-- Execution locks for durable processing
CREATE TABLE execution_locks (
    branch_id UUID PRIMARY KEY REFERENCES investigation_branches(id) ON DELETE CASCADE,
    locked_by TEXT NOT NULL,      -- Worker instance ID
    locked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- Collaboration Tables
-- =============================================================================

-- Chat messages linked to branches
CREATE TABLE branch_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,

    -- Link to the snapshot that resulted from this message
    resulting_snapshot_id UUID REFERENCES investigation_snapshots(id),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_messages_branch ON branch_messages(branch_id, created_at);

-- Approval requests
CREATE TABLE approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,
    snapshot_id UUID NOT NULL REFERENCES investigation_snapshots(id),

    -- What needs approval
    action_type TEXT NOT NULL,
    action_payload JSONB NOT NULL,
    risk_reason TEXT NOT NULL,

    -- Resolution
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'expired')),
    decided_by UUID REFERENCES users(id),
    decided_at TIMESTAMPTZ,
    decision TEXT,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_approvals_branch ON approval_requests(branch_id);
CREATE INDEX idx_approvals_status ON approval_requests(status) WHERE status = 'pending';

-- Merge point tracking
CREATE TABLE branch_merge_points (
    parent_branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,
    child_branch_id UUID NOT NULL REFERENCES investigation_branches(id) ON DELETE CASCADE,
    merge_step TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (parent_branch_id, child_branch_id)
);

-- =============================================================================
-- Pattern Learning Tables
-- =============================================================================

-- Known root cause patterns
CREATE TABLE root_cause_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Pattern definition
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    trigger_signals JSONB NOT NULL,
    typical_root_cause TEXT NOT NULL,
    resolution_steps JSONB NOT NULL,

    -- Matching criteria
    affected_datasets JSONB DEFAULT '[]'::jsonb,
    affected_metrics JSONB DEFAULT '[]'::jsonb,
    time_patterns JSONB,

    -- Statistics
    occurrence_count INT DEFAULT 0,
    last_matched_at TIMESTAMPTZ,
    false_positive_count INT DEFAULT 0,
    avg_resolution_time_minutes INT,

    -- Lifecycle
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_from_investigation_id UUID REFERENCES investigations(id)
);

CREATE INDEX idx_patterns_tenant ON root_cause_patterns(tenant_id) WHERE status = 'active';
