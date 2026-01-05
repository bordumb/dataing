/**
 * Role-based access control components.
 *
 * Show/hide UI elements based on user role.
 */

import type { ReactNode } from 'react'
import { useRole } from './use-role'
import type { OrgRole } from './types'

interface RoleGuardProps {
  /** Minimum role required to view children */
  minRole: OrgRole
  /** Content to show if user has required role */
  children: ReactNode
  /** Optional content to show if user lacks required role */
  fallback?: ReactNode
}

/**
 * Only renders children if user has required role or higher.
 *
 * @example
 * <RoleGuard minRole="admin">
 *   <AdminOnlyButton />
 * </RoleGuard>
 *
 * @example
 * <RoleGuard minRole="admin" fallback={<UpgradePrompt />}>
 *   <AdminSettings />
 * </RoleGuard>
 */
export function RoleGuard({ minRole, children, fallback = null }: RoleGuardProps) {
  const { hasRole } = useRole()

  if (!hasRole(minRole)) {
    return <>{fallback}</>
  }

  return <>{children}</>
}

interface ExactRoleGuardProps {
  /** Exact role required (not higher) */
  role: OrgRole
  /** Content to show if user has exact role */
  children: ReactNode
  /** Optional content to show if user lacks exact role */
  fallback?: ReactNode
}

/**
 * Only renders children if user is exactly the specified role (not higher).
 *
 * @example
 * <ExactRoleGuard role="viewer">
 *   <ViewerOnlyMessage />
 * </ExactRoleGuard>
 */
export function ExactRoleGuard({ role, children, fallback = null }: ExactRoleGuardProps) {
  const { role: userRole } = useRole()

  if (userRole !== role) {
    return <>{fallback}</>
  }

  return <>{children}</>
}
