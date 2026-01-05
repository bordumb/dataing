/**
 * Role-based access control components.
 *
 * Show/hide UI elements based on user role.
 */

import { type ReactNode, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useRole } from './use-role'
import type { OrgRole } from './types'

interface RoleGuardProps {
  /** Minimum role required to view children */
  minRole: OrgRole
  /** Content to show if user has required role */
  children: ReactNode
  /** Optional content to show if user lacks required role (for component-level use) */
  fallback?: ReactNode
  /** Redirect path if user lacks required role (for page-level use) */
  redirectTo?: string
}

/**
 * Only renders children if user has required role or higher.
 *
 * For page-level protection, use redirectTo to send users to another page.
 * For component-level hiding, use fallback to show alternative content.
 *
 * @example
 * // Page-level: redirect if not admin
 * <RoleGuard minRole="admin" redirectTo="/">
 *   <AdminPage />
 * </RoleGuard>
 *
 * @example
 * // Component-level: hide button if not admin
 * <RoleGuard minRole="admin">
 *   <AdminOnlyButton />
 * </RoleGuard>
 */
export function RoleGuard({ minRole, children, fallback = null, redirectTo }: RoleGuardProps) {
  const { hasRole } = useRole()
  const navigate = useNavigate()
  const hasAccess = hasRole(minRole)

  useEffect(() => {
    if (!hasAccess && redirectTo) {
      navigate(redirectTo, { replace: true })
    }
  }, [hasAccess, redirectTo, navigate])

  if (!hasAccess) {
    // If redirecting, render nothing while redirect happens
    if (redirectTo) {
      return null
    }
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
