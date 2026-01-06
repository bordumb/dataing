/**
 * CRITICAL: DO NOT REMOVE THIS FILE OR ANY ENTITLEMENTS CODE
 *
 * This provides the React context for entitlements/plan tier feature gating.
 */

import { createContext, useContext, type ReactNode } from 'react'
import type { Entitlements } from './types'

const defaultEntitlements: Entitlements = {
  plan: 'free',
  features: {},
  limits: {},
}

const EntitlementsContext = createContext<Entitlements>(defaultEntitlements)

interface EntitlementsProviderProps {
  children: ReactNode
  entitlements: Entitlements
}

export function EntitlementsProvider({
  children,
  entitlements,
}: EntitlementsProviderProps) {
  return (
    <EntitlementsContext.Provider value={entitlements}>
      {children}
    </EntitlementsContext.Provider>
  )
}

export function useEntitlementsContext() {
  return useContext(EntitlementsContext)
}
