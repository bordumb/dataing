/**
 * Hook for role-based access control in components.
 */

import { useJwtAuth } from './jwt-context'
import type { OrgRole } from './types'

const ROLE_HIERARCHY: OrgRole[] = ['viewer', 'member', 'admin', 'owner']

export function useRole() {
  const { effectiveRole } = useJwtAuth()

  /**
   * Check if user has at least the required role.
   */
  const hasRole = (requiredRole: OrgRole): boolean => {
    if (!effectiveRole) return false
    const userLevel = ROLE_HIERARCHY.indexOf(effectiveRole)
    const requiredLevel = ROLE_HIERARCHY.indexOf(requiredRole)
    return userLevel >= requiredLevel
  }

  return {
    role: effectiveRole,
    hasRole,
    isViewer: effectiveRole === 'viewer',
    isMember: hasRole('member'),
    isAdmin: hasRole('admin'),
    isOwner: hasRole('owner'),
  }
}
