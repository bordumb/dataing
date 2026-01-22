-- Team policy configuration for triage + investigation automation

-- Dataset tags (for policy overrides by tag)
CREATE TABLE dataset_tags (
    dataset_id UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES resource_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (dataset_id, tag_id)
);
CREATE INDEX idx_dataset_tags_dataset ON dataset_tags(dataset_id);
CREATE INDEX idx_dataset_tags_tag ON dataset_tags(tag_id);

-- Team default policy
CREATE TABLE team_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    sources TEXT[] NOT NULL DEFAULT '{}',
    default_action TEXT NOT NULL DEFAULT 'issue_only',
    auto_investigate_min_severity TEXT,
    review_required_max_severity TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team_id)
);
CREATE INDEX idx_team_policies_org ON team_policies(org_id);
CREATE INDEX idx_team_policies_team ON team_policies(team_id);

-- Dataset-specific or tag-specific overrides
CREATE TABLE team_policy_overrides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    dataset_id TEXT,
    tag_id UUID REFERENCES resource_tags(id) ON DELETE CASCADE,
    default_action TEXT,
    auto_investigate_min_severity TEXT,
    review_required_max_severity TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT one_override_selector CHECK (
        (dataset_id IS NOT NULL)::int +
        (tag_id IS NOT NULL)::int = 1
    )
);
CREATE INDEX idx_team_policy_overrides_org ON team_policy_overrides(org_id);
CREATE INDEX idx_team_policy_overrides_team ON team_policy_overrides(team_id);
CREATE INDEX idx_team_policy_overrides_dataset ON team_policy_overrides(dataset_id)
    WHERE dataset_id IS NOT NULL;
CREATE INDEX idx_team_policy_overrides_tag ON team_policy_overrides(tag_id)
    WHERE tag_id IS NOT NULL;

-- Team queue limits (per team rate limit + concurrency)
CREATE TABLE team_queue_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    rate_limit_per_minute INTEGER NOT NULL DEFAULT 60,
    burst_size INTEGER NOT NULL DEFAULT 10,
    max_concurrent INTEGER NOT NULL DEFAULT 5,
    batch_size INTEGER NOT NULL DEFAULT 5,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (team_id)
);
CREATE INDEX idx_team_queue_limits_org ON team_queue_limits(org_id);
CREATE INDEX idx_team_queue_limits_team ON team_queue_limits(team_id);

-- Triggers for updated_at
CREATE TRIGGER update_team_policies_updated_at BEFORE UPDATE ON team_policies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_team_policy_overrides_updated_at BEFORE UPDATE ON team_policy_overrides
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_team_queue_limits_updated_at BEFORE UPDATE ON team_queue_limits
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
