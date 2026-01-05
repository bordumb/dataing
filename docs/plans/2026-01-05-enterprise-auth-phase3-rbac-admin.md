# Enterprise Auth Phase 3: RBAC, Admin Views & Multi-Org UX

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add role-based access control enforcement, admin-only views for team management, org switching for multi-org users, and a demo role toggle for testing different permission levels.

**Architecture:**
- Frontend role-aware components that show/hide based on user role
- Demo role toggle (like existing plan toggle) for testing different roles
- Admin settings section for team/user management
- Backend RBAC enforcement on sensitive routes

**Tech Stack:** React, TypeScript, FastAPI, PostgreSQL

---

## Overview

| Task | Description | Complexity |
|------|-------------|------------|
| 18 | Demo Role Toggle Component | Small |
| 19 | Role-Aware UI Components | Small |
| 20 | Org Selector for Multi-Org Users | Medium |
| 21 | Admin Settings Section | Medium |
| 22 | Team Management UI | Medium |
| 23 | User Management UI | Medium |
| 24 | Backend RBAC Enforcement | Medium |
| 25 | Integration Testing | Small |

---

## Task 18: Demo Role Toggle Component

**Goal:** Add a floating toggle (like DemoToggle for plans) that lets demo users switch between viewer/member/admin/owner roles for testing.

**Files:**
- Create: `frontend/src/lib/auth/demo-role-toggle.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Create DemoRoleToggle component**

```typescript
// frontend/src/lib/auth/demo-role-toggle.tsx
import * as React from 'react'
import { Shield, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type { OrgRole } from './types'

interface DemoRoleToggleProps {
  currentRole: OrgRole
  onRoleChange: (role: OrgRole) => void
}

const ROLE_DESCRIPTIONS: Record<OrgRole, string> = {
  viewer: 'Read-only access',
  member: 'Can create investigations',
  admin: 'Can manage team settings',
  owner: 'Full control + billing',
}

export function DemoRoleToggle({ currentRole, onRoleChange }: DemoRoleToggleProps) {
  // Only show in demo mode
  const isDemoMode = import.meta.env.VITE_DEMO_MODE === 'true' ||
    localStorage.getItem('dataing_demo_mode') === 'true'

  if (!isDemoMode) return null

  return (
    <div className="fixed bottom-4 left-4 z-50">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="gap-2">
            <Shield className="h-4 w-4" />
            Role: {currentRole}
            <ChevronDown className="h-3 w-3" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-56">
          <DropdownMenuLabel>Demo Role Switcher</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuRadioGroup value={currentRole} onValueChange={(v) => onRoleChange(v as OrgRole)}>
            {(['viewer', 'member', 'admin', 'owner'] as OrgRole[]).map((role) => (
              <DropdownMenuRadioItem key={role} value={role}>
                <div className="flex flex-col">
                  <span className="font-medium capitalize">{role}</span>
                  <span className="text-xs text-muted-foreground">
                    {ROLE_DESCRIPTIONS[role]}
                  </span>
                </div>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
```

**Step 2: Add demo role state to JWT context**

Add to `frontend/src/lib/auth/jwt-context.tsx`:

```typescript
// Add to JwtAuthContextType
demoRole: OrgRole | null
setDemoRole: (role: OrgRole) => void
effectiveRole: OrgRole | null  // demoRole overrides real role in demo mode

// In the provider, add state:
const [demoRole, setDemoRole] = React.useState<OrgRole | null>(null)

// Compute effective role
const effectiveRole = demoRole ?? role
```

**Step 3: Add toggle to App.tsx**

```typescript
// In App.tsx, alongside DemoToggle
import { DemoRoleToggle } from '@/lib/auth/demo-role-toggle'

// In AppWithEntitlements:
const { effectiveRole, setDemoRole } = useJwtAuth()

// Add alongside DemoToggle:
{effectiveRole && (
  <DemoRoleToggle currentRole={effectiveRole} onRoleChange={setDemoRole} />
)}
```

**Step 4: Verify**

- Run demo, login
- Should see role toggle in bottom-left
- Switching roles should be reflected in effectiveRole

**Step 5: Commit**

```bash
git add frontend/src/lib/auth frontend/src/App.tsx
git commit -m "feat(auth): add demo role toggle for testing different permission levels"
```

---

## Task 19: Role-Aware UI Components

**Goal:** Create utilities and components that show/hide content based on user role.

**Files:**
- Create: `frontend/src/lib/auth/role-guard.tsx`
- Create: `frontend/src/lib/auth/use-role.ts`

**Step 1: Create useRole hook**

```typescript
// frontend/src/lib/auth/use-role.ts
import { useJwtAuth } from './jwt-context'
import type { OrgRole } from './types'

const ROLE_HIERARCHY: OrgRole[] = ['viewer', 'member', 'admin', 'owner']

export function useRole() {
  const { effectiveRole } = useJwtAuth()

  const hasRole = (requiredRole: OrgRole): boolean => {
    if (!effectiveRole) return false
    const userLevel = ROLE_HIERARCHY.indexOf(effectiveRole)
    const requiredLevel = ROLE_HIERARCHY.indexOf(requiredRole)
    return userLevel >= requiredLevel
  }

  const isViewer = effectiveRole === 'viewer'
  const isMember = hasRole('member')
  const isAdmin = hasRole('admin')
  const isOwner = hasRole('owner')

  return {
    role: effectiveRole,
    hasRole,
    isViewer,
    isMember,
    isAdmin,
    isOwner,
  }
}
```

**Step 2: Create RoleGuard component**

```typescript
// frontend/src/lib/auth/role-guard.tsx
import type { OrgRole } from './types'
import { useRole } from './use-role'

interface RoleGuardProps {
  minRole: OrgRole
  children: React.ReactNode
  fallback?: React.ReactNode
}

/**
 * Only renders children if user has required role or higher.
 *
 * Usage:
 *   <RoleGuard minRole="admin">
 *     <AdminOnlyButton />
 *   </RoleGuard>
 */
export function RoleGuard({ minRole, children, fallback = null }: RoleGuardProps) {
  const { hasRole } = useRole()

  if (!hasRole(minRole)) {
    return <>{fallback}</>
  }

  return <>{children}</>
}

/**
 * Only renders children if user is exactly the specified role (not higher).
 */
export function ExactRoleGuard({
  role,
  children,
  fallback = null
}: {
  role: OrgRole
  children: React.ReactNode
  fallback?: React.ReactNode
}) {
  const { role: userRole } = useRole()

  if (userRole !== role) {
    return <>{fallback}</>
  }

  return <>{children}</>
}
```

**Step 3: Update exports**

```typescript
// frontend/src/lib/auth/index.ts
export { useRole } from './use-role'
export { RoleGuard, ExactRoleGuard } from './role-guard'
export { DemoRoleToggle } from './demo-role-toggle'
```

**Step 4: Commit**

```bash
git add frontend/src/lib/auth
git commit -m "feat(auth): add role-aware UI components (RoleGuard, useRole)"
```

---

## Task 20: Org Selector for Multi-Org Users

**Goal:** Allow users who belong to multiple organizations to switch between them.

**Files:**
- Create: `frontend/src/components/layout/org-selector.tsx`
- Modify: `frontend/src/components/layout/app-sidebar.tsx`
- Create: `frontend/src/lib/auth/api.ts` - add getUserOrgs endpoint

**Step 1: Add API to fetch user's orgs**

```typescript
// Add to frontend/src/lib/auth/api.ts

export interface UserOrg {
  org: Organization
  role: OrgRole
}

export async function getUserOrgs(accessToken: string): Promise<UserOrg[]> {
  const response = await fetch(`${API_BASE}/api/v1/auth/me/orgs`, {
    headers: {
      'Authorization': `Bearer ${accessToken}`,
    },
  })

  if (!response.ok) {
    throw new Error('Failed to fetch organizations')
  }

  return response.json()
}
```

**Step 2: Add backend endpoint**

```python
# Add to backend/src/dataing/entrypoints/api/routes/auth.py

@router.get("/me/orgs")
async def get_user_organizations(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> list[dict]:
    """Get all organizations the current user belongs to."""
    from dataing.entrypoints.api.middleware.jwt_auth import verify_jwt

    # Get auth context from JWT
    # This requires the route to be protected by JWT middleware
    if not hasattr(request.state, "auth_context"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth = request.state.auth_context
    orgs = await service.get_user_orgs(auth.user_id)

    return [
        {
            "org": {
                "id": str(org.id),
                "name": org.name,
                "slug": org.slug,
                "plan": org.plan,
            },
            "role": role.value,
        }
        for org, role in orgs
    ]
```

**Step 3: Create OrgSelector component**

```typescript
// frontend/src/components/layout/org-selector.tsx
import * as React from 'react'
import { Check, ChevronsUpDown, Building } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/Button'
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { useJwtAuth } from '@/lib/auth'
import type { Organization } from '@/lib/auth'

interface OrgSelectorProps {
  orgs: Array<{ org: Organization; role: string }>
  currentOrg: Organization | null
  onOrgChange: (orgId: string) => void
  isLoading?: boolean
}

export function OrgSelector({ orgs, currentOrg, onOrgChange, isLoading }: OrgSelectorProps) {
  const [open, setOpen] = React.useState(false)

  if (orgs.length <= 1) {
    // Don't show selector if user only has one org
    return null
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between"
          disabled={isLoading}
        >
          <div className="flex items-center gap-2">
            <Building className="h-4 w-4" />
            <span className="truncate">
              {currentOrg?.name ?? 'Select organization...'}
            </span>
          </div>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[250px] p-0">
        <Command>
          <CommandInput placeholder="Search organizations..." />
          <CommandList>
            <CommandEmpty>No organization found.</CommandEmpty>
            <CommandGroup>
              {orgs.map(({ org, role }) => (
                <CommandItem
                  key={org.id}
                  value={org.id}
                  onSelect={() => {
                    onOrgChange(org.id)
                    setOpen(false)
                  }}
                >
                  <Check
                    className={cn(
                      'mr-2 h-4 w-4',
                      currentOrg?.id === org.id ? 'opacity-100' : 'opacity-0'
                    )}
                  />
                  <div className="flex flex-col">
                    <span>{org.name}</span>
                    <span className="text-xs text-muted-foreground capitalize">
                      {role}
                    </span>
                  </div>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
```

**Step 4: Add to sidebar**

Update `app-sidebar.tsx` to include org selector in the header area for users with multiple orgs.

**Step 5: Commit**

```bash
git add frontend/src backend/src
git commit -m "feat(auth): add org selector for multi-org users"
```

---

## Task 21: Admin Settings Section

**Goal:** Create an admin-only section in settings for team/user management.

**Files:**
- Create: `frontend/src/features/settings/admin/index.tsx`
- Create: `frontend/src/features/settings/admin/admin-settings.tsx`
- Modify: `frontend/src/features/settings/settings-page.tsx`

**Step 1: Create admin settings layout**

```typescript
// frontend/src/features/settings/admin/admin-settings.tsx
import { Routes, Route, NavLink } from 'react-router-dom'
import { Users, UsersRound, Shield } from 'lucide-react'
import { RoleGuard } from '@/lib/auth'
import { cn } from '@/lib/utils'

const adminNavItems = [
  { to: '/settings/admin/team', label: 'Team Management', icon: UsersRound },
  { to: '/settings/admin/users', label: 'User Management', icon: Users },
  { to: '/settings/admin/roles', label: 'Roles & Permissions', icon: Shield },
]

export function AdminSettings() {
  return (
    <RoleGuard
      minRole="admin"
      fallback={
        <div className="text-center py-12">
          <Shield className="mx-auto h-12 w-12 text-muted-foreground" />
          <h3 className="mt-4 text-lg font-semibold">Admin Access Required</h3>
          <p className="text-muted-foreground">
            You need admin privileges to access this section.
          </p>
        </div>
      }
    >
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Admin Settings</h2>
          <p className="text-muted-foreground">
            Manage your organization's teams, users, and permissions.
          </p>
        </div>

        <nav className="flex gap-2 border-b pb-2">
          {adminNavItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'flex items-center gap-2 px-3 py-2 text-sm rounded-md transition-colors',
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted'
                )
              }
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <Routes>
          <Route path="team" element={<TeamManagement />} />
          <Route path="users" element={<UserManagement />} />
          <Route path="roles" element={<RolesAndPermissions />} />
          <Route index element={<TeamManagement />} />
        </Routes>
      </div>
    </RoleGuard>
  )
}

// Placeholder components - will be implemented in Tasks 22 & 23
function TeamManagement() {
  return <div>Team Management (Task 22)</div>
}

function UserManagement() {
  return <div>User Management (Task 23)</div>
}

function RolesAndPermissions() {
  return (
    <div className="prose dark:prose-invert">
      <h3>Role Hierarchy</h3>
      <ul>
        <li><strong>Owner:</strong> Full control including billing and org deletion</li>
        <li><strong>Admin:</strong> Manage teams, users, and settings</li>
        <li><strong>Member:</strong> Create and manage investigations</li>
        <li><strong>Viewer:</strong> Read-only access to investigations</li>
      </ul>
    </div>
  )
}
```

**Step 2: Add admin route to settings page**

```typescript
// Add to settings-page.tsx routes
<Route path="admin/*" element={<AdminSettings />} />
```

**Step 3: Add admin link to settings sidebar (for admins only)**

```typescript
// In settings sidebar nav
<RoleGuard minRole="admin">
  <NavLink to="/settings/admin">
    <Shield className="h-4 w-4" />
    Admin
  </NavLink>
</RoleGuard>
```

**Step 4: Commit**

```bash
git add frontend/src/features/settings
git commit -m "feat(settings): add admin settings section with role guard"
```

---

## Task 22: Team Management UI

**Goal:** Admin UI to create, edit, and delete teams; assign users to teams.

**Files:**
- Create: `frontend/src/features/settings/admin/team-management.tsx`
- Create: `backend/src/dataing/entrypoints/api/routes/teams.py`

**Step 1: Create backend endpoints**

```python
# backend/src/dataing/entrypoints/api/routes/teams.py
"""Team management API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dataing.adapters.auth.postgres import PostgresAuthRepository
from dataing.entrypoints.api.middleware.jwt_auth import RequireAdmin, JwtContext

router = APIRouter(prefix="/teams", tags=["teams"])


class CreateTeamRequest(BaseModel):
    name: str


class TeamResponse(BaseModel):
    id: str
    name: str
    member_count: int


class AddTeamMemberRequest(BaseModel):
    user_id: UUID


@router.get("/", response_model=list[TeamResponse])
async def list_teams(auth: RequireAdmin) -> list[TeamResponse]:
    """List all teams in the organization. Requires admin role."""
    # Implementation...
    pass


@router.post("/", response_model=TeamResponse, status_code=201)
async def create_team(
    body: CreateTeamRequest,
    auth: RequireAdmin,
) -> TeamResponse:
    """Create a new team. Requires admin role."""
    pass


@router.delete("/{team_id}", status_code=204)
async def delete_team(team_id: UUID, auth: RequireAdmin) -> None:
    """Delete a team. Requires admin role."""
    pass


@router.post("/{team_id}/members", status_code=201)
async def add_team_member(
    team_id: UUID,
    body: AddTeamMemberRequest,
    auth: RequireAdmin,
) -> None:
    """Add a user to a team. Requires admin role."""
    pass


@router.delete("/{team_id}/members/{user_id}", status_code=204)
async def remove_team_member(
    team_id: UUID,
    user_id: UUID,
    auth: RequireAdmin,
) -> None:
    """Remove a user from a team. Requires admin role."""
    pass
```

**Step 2: Create frontend component**

```typescript
// frontend/src/features/settings/admin/team-management.tsx
// Full implementation with:
// - List of teams with member counts
// - Create team dialog
// - Delete team (with confirmation)
// - Expand team to see/manage members
// - Add/remove members from team
```

**Step 3: Commit**

```bash
git add frontend/src backend/src
git commit -m "feat(admin): add team management UI and API"
```

---

## Task 23: User Management UI

**Goal:** Admin UI to view org members, change roles, remove users.

**Files:**
- Create: `frontend/src/features/settings/admin/user-management.tsx`
- Create: `backend/src/dataing/entrypoints/api/routes/org_members.py`

**Step 1: Create backend endpoints**

```python
# backend/src/dataing/entrypoints/api/routes/org_members.py
"""Organization member management API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from dataing.core.auth.types import OrgRole
from dataing.entrypoints.api.middleware.jwt_auth import RequireAdmin, RequireOwner

router = APIRouter(prefix="/org/members", tags=["org-members"])


class OrgMemberResponse(BaseModel):
    user_id: str
    email: str
    name: str | None
    role: str
    joined_at: str


class UpdateMemberRoleRequest(BaseModel):
    role: OrgRole


@router.get("/", response_model=list[OrgMemberResponse])
async def list_org_members(auth: RequireAdmin) -> list[OrgMemberResponse]:
    """List all members in the organization. Requires admin role."""
    pass


@router.patch("/{user_id}/role")
async def update_member_role(
    user_id: UUID,
    body: UpdateMemberRoleRequest,
    auth: RequireOwner,  # Only owners can change roles
) -> OrgMemberResponse:
    """Update a member's role. Requires owner role."""
    pass


@router.delete("/{user_id}", status_code=204)
async def remove_member(
    user_id: UUID,
    auth: RequireOwner,  # Only owners can remove members
) -> None:
    """Remove a member from the organization. Requires owner role."""
    pass
```

**Step 2: Create frontend component**

```typescript
// frontend/src/features/settings/admin/user-management.tsx
// Full implementation with:
// - Table of org members with role badges
// - Role dropdown to change roles (owner only)
// - Remove member button (owner only, with confirmation)
// - Search/filter members
```

**Step 3: Commit**

```bash
git add frontend/src backend/src
git commit -m "feat(admin): add user management UI and API"
```

---

## Task 24: Backend RBAC Enforcement

**Goal:** Apply role-based access control to sensitive API routes.

**Files:**
- Modify: `backend/src/dataing/entrypoints/api/routes/datasources.py`
- Modify: `backend/src/dataing/entrypoints/api/routes/settings.py`
- Modify: `backend/src/dataing/entrypoints/api/routes/investigations.py`

**Step 1: Define route permissions**

| Route | Required Role | Rationale |
|-------|--------------|-----------|
| GET /datasources | viewer | Read-only |
| POST /datasources | admin | Adding connections is admin task |
| DELETE /datasources | admin | Removing connections is admin task |
| GET /investigations | viewer | Read-only |
| POST /investigations | member | Creating investigations |
| DELETE /investigations | admin | Deleting investigations |
| GET /settings | viewer | View settings |
| PUT /settings | admin | Modify settings |

**Step 2: Update routes with role requirements**

Since we've already made the auth middleware accept both JWT and API keys, we need to extract role from JWT context when available.

```python
# Example: backend/src/dataing/entrypoints/api/routes/datasources.py

from dataing.entrypoints.api.middleware.auth import verify_api_key, ApiKeyContext
from dataing.core.auth.types import OrgRole

# For routes that need specific roles with JWT:
@router.post("/")
async def create_datasource(
    auth: Annotated[ApiKeyContext, Depends(verify_api_key)],
    # ... other params
):
    # For JWT auth, check role from request.state.auth_context
    # Role checking happens in verify_api_key now, but we may want stricter checks
    pass
```

**Step 3: Add role checking helper**

```python
# backend/src/dataing/entrypoints/api/middleware/auth.py

def require_jwt_role(min_role: OrgRole):
    """Require minimum role for JWT-authenticated requests."""
    async def checker(request: Request, auth: ApiKeyContext = Depends(verify_api_key)):
        # If authenticated via JWT (not API key), check role
        if hasattr(request.state, 'jwt_role'):
            user_role = OrgRole(request.state.jwt_role)
            # ... role hierarchy check
        return auth
    return checker
```

**Step 4: Commit**

```bash
git add backend/src
git commit -m "feat(auth): add RBAC enforcement to API routes"
```

---

## Task 25: Integration Testing

**Goal:** Verify the complete RBAC flow works end-to-end.

**Manual Testing Checklist:**

1. **Demo Role Toggle**
   - [ ] Login as demo user
   - [ ] Toggle appears in bottom-left
   - [ ] Switching roles updates UI immediately

2. **Viewer Role**
   - [ ] Can view dashboard
   - [ ] Can view investigations (read-only)
   - [ ] Cannot create new investigation
   - [ ] Cannot access admin settings
   - [ ] Cannot see "New Investigation" button

3. **Member Role**
   - [ ] Can create investigations
   - [ ] Can view own investigations
   - [ ] Cannot delete others' investigations
   - [ ] Cannot access admin settings

4. **Admin Role**
   - [ ] Can access Admin Settings
   - [ ] Can create/delete teams
   - [ ] Can view org members
   - [ ] Cannot change member roles (owner only)

5. **Owner Role**
   - [ ] Can change member roles
   - [ ] Can remove members
   - [ ] Has all admin permissions

6. **Multi-Org (if applicable)**
   - [ ] Org selector appears for multi-org users
   - [ ] Switching orgs refreshes data
   - [ ] Role may differ per org

**Commit:**

```bash
git commit --allow-empty -m "docs: add RBAC integration testing checklist"
```

---

## Summary

| Task | Component | Admin-Only |
|------|-----------|------------|
| 18 | Demo Role Toggle | No (dev tool) |
| 19 | RoleGuard, useRole | No (utility) |
| 20 | Org Selector | No |
| 21 | Admin Settings Section | Yes |
| 22 | Team Management | Yes |
| 23 | User Management | Yes (Owner for roles) |
| 24 | Backend RBAC | N/A |
| 25 | Integration Tests | N/A |

**After Phase 3:**
- Demo users can test all role levels
- Admins have dedicated settings section
- Teams can be created and managed
- Users can be managed (roles, removal)
- API routes enforce role requirements
- Multi-org users can switch organizations
