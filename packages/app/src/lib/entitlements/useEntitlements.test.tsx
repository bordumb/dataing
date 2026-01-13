import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useEntitlements, EntitlementsProvider } from './index'
import type { Entitlements } from './types'
import type { ReactNode } from 'react'

const mockEntitlements: Entitlements = {
  plan: 'free',
  features: {
    sso_oidc: false,
    sso_saml: false,
    scim: false,
    audit_logs: false,
  },
  limits: {
    max_seats: { limit: 3, usage: 1 },
    max_datasources: { limit: 2, usage: 0 },
    max_investigations_per_month: { limit: 10, usage: 5 },
  },
}

function wrapper({ children }: { children: ReactNode }) {
  return (
    <EntitlementsProvider entitlements={mockEntitlements}>
      {children}
    </EntitlementsProvider>
  )
}

describe('useEntitlements', () => {
  it('returns hasFeature that checks feature availability', () => {
    const { result } = renderHook(() => useEntitlements(), { wrapper })

    expect(result.current.hasFeature('sso_oidc')).toBe(false)
    expect(result.current.hasFeature('nonexistent')).toBe(false)
  })

  it('returns isUnderLimit that checks usage limits', () => {
    const { result } = renderHook(() => useEntitlements(), { wrapper })

    // 5 < 10, so under limit
    expect(result.current.isUnderLimit('max_investigations_per_month')).toBe(true)
  })

  it('returns getUsage that shows current usage', () => {
    const { result } = renderHook(() => useEntitlements(), { wrapper })

    const usage = result.current.getUsage('max_investigations_per_month')
    expect(usage).toEqual({ limit: 10, usage: 5 })
  })

  it('returns plan', () => {
    const { result } = renderHook(() => useEntitlements(), { wrapper })
    expect(result.current.plan).toBe('free')
  })
})
