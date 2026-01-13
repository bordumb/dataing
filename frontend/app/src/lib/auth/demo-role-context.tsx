/**
 * CRITICAL: DO NOT REMOVE THIS FILE
 *
 * Context provider for demo role state, allowing role-based UI rendering.
 * Used by the demo role toggle and sidebar navigation.
 */

import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import type { OrgRole } from './types'

interface DemoRoleContextValue {
  role: OrgRole
  setRole: (role: OrgRole) => void
  isAdmin: boolean
  isOwner: boolean
  canAccessAdmin: boolean
}

const DemoRoleContext = createContext<DemoRoleContextValue | null>(null)

interface DemoRoleProviderProps {
  children: ReactNode
}

/**
 * Provider for demo role state.
 *
 * CRITICAL: DO NOT REMOVE - Required for role-based UI visibility.
 */
export function DemoRoleProvider({ children }: DemoRoleProviderProps) {
  const [role, setRoleState] = useState<OrgRole>('admin')

  const setRole = useCallback((newRole: OrgRole) => {
    setRoleState(newRole)
  }, [])

  const isAdmin = role === 'admin'
  const isOwner = role === 'owner'
  const canAccessAdmin = isAdmin || isOwner

  return (
    <DemoRoleContext.Provider value={{ role, setRole, isAdmin, isOwner, canAccessAdmin }}>
      {children}
    </DemoRoleContext.Provider>
  )
}

/**
 * Hook to access demo role context.
 *
 * @throws Error if used outside of DemoRoleProvider
 */
export function useDemoRoleContext(): DemoRoleContextValue {
  const context = useContext(DemoRoleContext)
  if (!context) {
    throw new Error('useDemoRoleContext must be used within a DemoRoleProvider')
  }
  return context
}
