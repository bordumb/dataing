/**
 * Admin page - only accessible to admin+ roles.
 * Contains team and user management.
 */

import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { Users, UsersRound } from 'lucide-react'
import { cn } from '@/lib/utils'

import { TeamManagement, UserManagement } from './components'

const adminNavItems = [
  { to: '/admin/teams', label: 'Teams', icon: UsersRound },
  { to: '/admin/users', label: 'Users', icon: Users },
]

export function AdminPage() {
  return (
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
  )
}
