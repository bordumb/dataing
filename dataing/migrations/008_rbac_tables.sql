-- RBAC tables for teams, tags, and permission grants
-- Migration 008: RBAC

-- Teams (synced from SCIM Groups or created manually)
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    external_id VARCHAR(255),
    is_scim_managed BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, name)
);

-- Team membership
CREATE TABLE team_members (
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (team_id, user_id)
);

-- Resource tags
CREATE TABLE resource_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL,
    color VARCHAR(7) DEFAULT '#6366f1',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, name)
);

-- Tag assignments to investigations
CREATE TABLE investigation_tags (
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES resource_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (investigation_id, tag_id)
);

-- Permission grants (ACL table)
CREATE TABLE permission_grants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- Who (one of these)
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,

    -- What (one of these)
    resource_type VARCHAR(50) NOT NULL DEFAULT 'investigation',
    resource_id UUID,
    tag_id UUID REFERENCES resource_tags(id) ON DELETE CASCADE,
    data_source_id UUID REFERENCES data_sources(id) ON DELETE CASCADE,

    -- Permission level
    permission VARCHAR(20) NOT NULL DEFAULT 'read',

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id),

    -- Ensure exactly one grantee
    CONSTRAINT one_grantee CHECK (
        (user_id IS NOT NULL AND team_id IS NULL) OR
        (user_id IS NULL AND team_id IS NOT NULL)
    ),
    -- Ensure exactly one access target
    CONSTRAINT one_target CHECK (
        (resource_id IS NOT NULL)::int +
        (tag_id IS NOT NULL)::int +
        (data_source_id IS NOT NULL)::int = 1
    )
);

-- SCIM role groups tracking (for role-* groups)
CREATE TABLE scim_role_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    external_id VARCHAR(255) NOT NULL,
    role_name VARCHAR(20) NOT NULL CHECK (role_name IN ('owner', 'admin', 'member')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, external_id)
);

-- Indexes
CREATE INDEX idx_teams_org ON teams(org_id);
CREATE INDEX idx_teams_external ON teams(external_id) WHERE external_id IS NOT NULL;
CREATE INDEX idx_team_members_user ON team_members(user_id);
CREATE INDEX idx_team_members_team ON team_members(team_id);
CREATE INDEX idx_resource_tags_org ON resource_tags(org_id);
CREATE INDEX idx_investigation_tags_inv ON investigation_tags(investigation_id);
CREATE INDEX idx_investigation_tags_tag ON investigation_tags(tag_id);
CREATE INDEX idx_permission_grants_org ON permission_grants(org_id);
CREATE INDEX idx_permission_grants_user ON permission_grants(user_id) WHERE user_id IS NOT NULL;
CREATE INDEX idx_permission_grants_team ON permission_grants(team_id) WHERE team_id IS NOT NULL;
CREATE INDEX idx_permission_grants_resource ON permission_grants(resource_type, resource_id) WHERE resource_id IS NOT NULL;
CREATE INDEX idx_permission_grants_tag ON permission_grants(tag_id) WHERE tag_id IS NOT NULL;
CREATE INDEX idx_permission_grants_datasource ON permission_grants(data_source_id) WHERE data_source_id IS NOT NULL;

-- Triggers for updated_at
CREATE TRIGGER update_teams_updated_at BEFORE UPDATE ON teams
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
