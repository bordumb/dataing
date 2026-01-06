# RBAC + SCIM Integration Design

**Goal:** Implement resource-level access control with SCIM user/group provisioning.

**Date:** 2026-01-06

---

## Overview

Add flexible permission system where users can access investigations via:
- **Role** (owner/admin see everything)
- **Creator** (user created the investigation)
- **Direct grant** (User X → Investigation Y)
- **Tag grant** (User X → all investigations tagged "finance")
- **Team grant** (Team Engineering → investigations via any grant type)
- **Datasource grant** (User X → all investigations on datasource Z)

Permission logic: **Union (OR)** - if any rule grants access, user can access.

---

## Database Schema

### New Tables

```sql
-- Teams (synced from SCIM Groups)
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    external_id VARCHAR(255),  -- SCIM externalId for sync
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

-- Resource tags (for investigations initially, extensible)
CREATE TABLE resource_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(50) NOT NULL,
    color VARCHAR(7),  -- hex color for UI
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, name)
);

-- Tag assignments to investigations
CREATE TABLE investigation_tags (
    investigation_id UUID NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES resource_tags(id) ON DELETE CASCADE,
    PRIMARY KEY (investigation_id, tag_id)
);

-- Permission grants (the ACL table)
CREATE TABLE permission_grants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- Who (one of these is set)
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    team_id UUID REFERENCES teams(id) ON DELETE CASCADE,

    -- What they can access (one of these is set)
    resource_type VARCHAR(50) NOT NULL,  -- 'investigation'
    resource_id UUID,                     -- specific investigation
    tag_id UUID REFERENCES resource_tags(id) ON DELETE CASCADE,
    data_source_id UUID REFERENCES data_sources(id) ON DELETE CASCADE,

    -- Permission level
    permission VARCHAR(20) NOT NULL,  -- 'read', 'write', 'admin'

    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by UUID REFERENCES users(id)
);

-- Indexes
CREATE INDEX idx_teams_org ON teams(org_id);
CREATE INDEX idx_teams_external ON teams(external_id);
CREATE INDEX idx_team_members_user ON team_members(user_id);
CREATE INDEX idx_resource_tags_org ON resource_tags(org_id);
CREATE INDEX idx_investigation_tags_inv ON investigation_tags(investigation_id);
CREATE INDEX idx_permission_grants_org ON permission_grants(org_id);
CREATE INDEX idx_permission_grants_user ON permission_grants(user_id);
CREATE INDEX idx_permission_grants_team ON permission_grants(team_id);
CREATE INDEX idx_permission_grants_resource ON permission_grants(resource_type, resource_id);
```

### Modify Existing Tables

```sql
-- Update users.role constraint
ALTER TABLE users
    DROP CONSTRAINT IF EXISTS users_role_check,
    ADD CONSTRAINT users_role_check CHECK (role IN ('owner', 'admin', 'member'));

-- Ensure default is 'member'
ALTER TABLE users ALTER COLUMN role SET DEFAULT 'member';
```

---

## Roles

| Role | Permissions |
|------|-------------|
| `owner` | Full access to everything, can delete org, manage billing |
| `admin` | Manage users, teams, SSO, datasources; see all investigations |
| `member` | Access based on grants (direct, tag, team, datasource) |

---

## Permission Evaluation

```python
async def can_access_investigation(user_id: UUID, investigation_id: UUID) -> bool:
    """
    User can access investigation if ANY of these are true:
    1. User has role 'owner' or 'admin' (full access)
    2. User created the investigation
    3. Direct grant: user_id → investigation_id
    4. Tag grant: user has grant on any tag the investigation has
    5. Team grant: user's team has grant on investigation/tag/datasource
    6. Datasource grant: user has grant on the investigation's datasource
    """
```

Single SQL query with UNION for all grant paths.

---

## SCIM Mapping

### Users

| SCIM Operation | Action |
|----------------|--------|
| `POST /scim/v2/Users` | Create user, link `sso_identities`, role = member |
| `PUT /scim/v2/Users/{id}` | Update name/email/active |
| `DELETE /scim/v2/Users/{id}` | Soft delete: `is_active = false` |

### Groups

| Group Name | Action |
|------------|--------|
| `role-admin` | Set member role to `admin` |
| `role-owner` | Set member role to `owner` |
| Other names | Create/sync Team, manage membership |

Group membership changes sync immediately to team_members or user.role.

---

## API Endpoints

### Teams
```
GET    /api/v1/teams
POST   /api/v1/teams
GET    /api/v1/teams/{id}
PUT    /api/v1/teams/{id}
DELETE /api/v1/teams/{id}
POST   /api/v1/teams/{id}/members
DELETE /api/v1/teams/{id}/members/{user_id}
```

### Tags
```
GET    /api/v1/tags
POST   /api/v1/tags
PUT    /api/v1/tags/{id}
DELETE /api/v1/tags/{id}
POST   /api/v1/investigations/{id}/tags
DELETE /api/v1/investigations/{id}/tags/{tag_id}
```

### Permissions
```
GET    /api/v1/permissions
POST   /api/v1/permissions
DELETE /api/v1/permissions/{id}
GET    /api/v1/users/{id}/permissions
GET    /api/v1/investigations/{id}/permissions
```

### Modified Existing
- `GET /api/v1/investigations` - filtered by user's access
- `GET /api/v1/investigations/{id}` - 403 if no access

---

## Frontend

### New Settings Pages
- `/settings/teams` - Team management (SCIM-synced shown read-only)
- `/settings/tags` - Tag management with colors
- `/settings/permissions` - Permission grants overview

### Investigation UI Changes
- Tags section on detail page
- Share button → grant access modal
- "Who has access" collapsible panel
- Tag filter on list page

### Sidebar
Add Teams, Tags, Permissions links under Settings.

---

## Implementation Order

1. Database migration (new tables)
2. Core permission service (evaluation logic)
3. Teams repository + API
4. Tags repository + API
5. Permissions repository + API
6. Wire SCIM endpoints to create real users/teams
7. Add permission filtering to investigation endpoints
8. Frontend: settings pages
9. Frontend: investigation sharing UI
