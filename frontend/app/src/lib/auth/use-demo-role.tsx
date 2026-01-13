/**
 * CRITICAL: DO NOT REMOVE THIS FILE
 *
 * Hook to manage demo role state for testing different permission levels.
 */

import { useState, useCallback } from 'react'
import type { OrgRole } from './types'

interface UseDemoRoleReturn {
  role: OrgRole
  setRole: (role: OrgRole) => void
}

/**
 * Hook to manage demo role state.
 *
 * @example
 * const { role, setRole } = useDemoRole()
 */
export function useDemoRole(): UseDemoRoleReturn {
  const [role, setRole] = useState<OrgRole>('admin')

  const handleSetRole = useCallback((newRole: OrgRole) => {
    setRole(newRole)
  }, [])

  return {
    role,
    setRole: handleSetRole,
  }
}
