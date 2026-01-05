import { useCallback } from 'react'
import { useEntitlementsContext } from './context'
import type { UsageLimit, Plan } from './types'

export interface UseEntitlementsReturn {
  plan: Plan
  hasFeature: (feature: string) => boolean
  isUnderLimit: (feature: string) => boolean
  getUsage: (feature: string) => UsageLimit | undefined
}

export function useEntitlements(): UseEntitlementsReturn {
  const entitlements = useEntitlementsContext()

  const hasFeature = useCallback(
    (feature: string): boolean => {
      return entitlements.features[feature] ?? false
    },
    [entitlements.features]
  )

  const isUnderLimit = useCallback(
    (feature: string): boolean => {
      const limit = entitlements.limits[feature]
      if (!limit) return true
      if (limit.limit === -1) return true // unlimited
      return limit.usage < limit.limit
    },
    [entitlements.limits]
  )

  const getUsage = useCallback(
    (feature: string): UsageLimit | undefined => {
      return entitlements.limits[feature]
    },
    [entitlements.limits]
  )

  return {
    plan: entitlements.plan,
    hasFeature,
    isUnderLimit,
    getUsage,
  }
}
