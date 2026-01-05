-- Seed demo auth data: organization, user, and membership
-- Demo credentials:
--   Email: demo@dataing.io
--   Password: demo123456
--   Org ID: 00000000-0000-0000-0000-000000000001

-- Create demo organization (if not exists)
INSERT INTO organizations (id, name, slug, plan)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Demo Organization',
    'demo',
    'pro'
)
ON CONFLICT (id) DO NOTHING;

-- Create demo user with password hash for "demo123456"
-- bcrypt hash generated with: from dataing.core.auth.password import hash_password; hash_password("demo123456")
INSERT INTO users (id, email, name, password_hash, is_active)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    'demo@dataing.io',
    'Demo User',
    -- This is bcrypt hash of "demo123456" - pragma: allowlist secret
    '$2b$12$Km/KBXo9pGSNEl7PC0ALtOqNvTTUPX7C3fo/gKwlXngPdbZOVSN2K',
    true
)
ON CONFLICT (id) DO NOTHING;

-- Add user to org as owner
INSERT INTO org_memberships (user_id, org_id, role)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000001',
    'owner'
)
ON CONFLICT (user_id, org_id) DO NOTHING;

-- Create a demo team
INSERT INTO teams (id, org_id, name)
VALUES (
    '00000000-0000-0000-0000-000000000003',
    '00000000-0000-0000-0000-000000000001',
    'Data Team'
)
ON CONFLICT (id) DO NOTHING;

-- Add user to team
INSERT INTO team_memberships (user_id, team_id)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000003'
)
ON CONFLICT (user_id, team_id) DO NOTHING;
