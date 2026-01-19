-- Seed a second organization for multi-org demo
-- This allows testing the org selector and org switching features
--
-- Demo user (demo@dataing.io) will be:
--   - Owner of "Demo Organization" (original)
--   - Member of "Acme Corporation" (new)

-- Create second demo organization
INSERT INTO organizations (id, name, slug, plan)
VALUES (
    '00000000-0000-0000-0000-000000000010',
    'Acme Corporation',
    'acme',
    'enterprise'
)
ON CONFLICT (id) DO NOTHING;

-- Add demo user to second org as member (not owner)
-- This demonstrates different roles across orgs
INSERT INTO org_memberships (user_id, org_id, role)
VALUES (
    '00000000-0000-0000-0000-000000000002',  -- demo user
    '00000000-0000-0000-0000-000000000010',  -- acme org
    'member'
)
ON CONFLICT (user_id, org_id) DO NOTHING;

-- Create a team in the second org
INSERT INTO teams (id, org_id, name)
VALUES (
    '00000000-0000-0000-0000-000000000011',
    '00000000-0000-0000-0000-000000000010',
    'Engineering'
)
ON CONFLICT (id) DO NOTHING;
