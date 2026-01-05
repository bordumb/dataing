/**
 * Admin page - only accessible to admin+ roles.
 * Contains team and user management.
 */

import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { Users, UsersRound, Shield } from 'lucide-react'
import { cn } from '@/lib/utils'
import { RoleGuard } from '@/lib/auth'

import { TeamManagement, UserManagement } from './components'

const adminNavItems = [
  { to: '/admin/teams', label: 'Teams', icon: UsersRound },
  { to: '/admin/users', label: 'Users', icon: Users },
]

function AdminAccessDenied() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <Shield className="h-16 w-16 text-muted-foreground mb-4" />
      <h2 className="text-2xl font-semibold mb-2">Admin Access Required</h2>
      <p className="text-muted-foreground max-w-md">
        You need admin or owner privileges to access this section.
        Contact your organization owner if you need elevated permissions.
      </p>
    </div>
  )
}

export function AdminPage() {
  return (
    <RoleGuard minRole="admin" fallback={<AdminAccessDenied />}>
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Admin</h1>
        <p className="text-muted-foreground">
          Manage your organization's teams and users.
        </p>
      </div>

      <nav className="flex gap-2 border-b pb-2">
        {adminNavItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md transition-colors',
                isActive
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              )
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <Routes>
        <Route path="teams" element={<TeamManagement />} />
        <Route path="users" element={<UserManagement />} />
        <Route index element={<Navigate to="teams" replace />} />
      </Routes>
    </div>
    </RoleGuard>
  )
}
