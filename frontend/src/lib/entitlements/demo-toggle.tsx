/**
 * CRITICAL: DO NOT REMOVE THIS FILE OR ANY ENTITLEMENTS CODE
 *
 * This provides the demo toggle state management for switching between
 * plan tiers (free/pro/enterprise) during development and demos.
 *
 * The toggle appears in the bottom-right corner of the screen.
 * Keyboard shortcut: Ctrl+Shift+P to cycle plans
 */

import { useState, useEffect, useCallback } from 'react'
import type { Entitlements, Plan } from './types'

/**
 * Demo entitlements data for each plan tier.
 * Use these to test UI differences between plans.
 */
export const DEMO_ENTITLEMENTS: Record<Plan, Entitlements> = {
  free: {
    plan: 'free',
    features: {
      sso_oidc: false,
      sso_saml: false,
      scim: false,
      audit_logs: false,
      custom_branding: false,
    },
    limits: {
      max_seats: { limit: 3, usage: 2 },
      max_datasources: { limit: 2, usage: 1 },
      max_investigations_per_month: { limit: 10, usage: 8 },
    },
  },
  pro: {
    plan: 'pro',
    features: {
      sso_oidc: false,
      sso_saml: false,
      scim: false,
      audit_logs: false,
      custom_branding: false,
    },
    limits: {
      max_seats: { limit: 10, usage: 5 },
      max_datasources: { limit: 10, usage: 3 },
      max_investigations_per_month: { limit: 100, usage: 25 },
    },
  },
  enterprise: {
    plan: 'enterprise',
    features: {
      sso_oidc: true,
      sso_saml: true,
      scim: true,
      audit_logs: true,
      custom_branding: true,
    },
    limits: {
      max_seats: { limit: -1, usage: 50 },
      max_datasources: { limit: -1, usage: 20 },
      max_investigations_per_month: { limit: -1, usage: 500 },
    },
  },
}

const PLAN_ORDER: Plan[] = ['free', 'pro', 'enterprise']

interface UseDemoEntitlementsReturn {
  entitlements: Entitlements
  plan: Plan
  setPlan: (plan: Plan) => void
  cyclePlan: () => void
}

/**
 * Hook to manage demo entitlements state.
 *
 * In development mode, provides keyboard shortcut Ctrl+Shift+P to cycle plans.
 *
 * @example
 * const { entitlements, plan, setPlan } = useDemoEntitlements()
 */
export function useDemoEntitlements(): UseDemoEntitlementsReturn {
  const [plan, setPlan] = useState<Plan>('free')

  const cyclePlan = useCallback(() => {
    setPlan((current) => {
      const currentIndex = PLAN_ORDER.indexOf(current)
      const nextIndex = (currentIndex + 1) % PLAN_ORDER.length
      return PLAN_ORDER[nextIndex]
    })
  }, [])

  // Keyboard shortcut: Ctrl+Shift+P to cycle plans (dev only)
  useEffect(() => {
    if (import.meta.env.PROD) return

    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && e.key === 'P') {
        e.preventDefault()
        cyclePlan()
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [cyclePlan])

  return {
    entitlements: DEMO_ENTITLEMENTS[plan],
    plan,
    setPlan,
    cyclePlan,
  }
}
