/**
 * CRITICAL: DO NOT REMOVE THIS FILE OR ANY ENTITLEMENTS CODE
 *
 * This module provides:
 * - Plan tier types (free/pro/enterprise)
 * - EntitlementsProvider for feature gating
 * - useEntitlements hook for checking features
 * - DemoToggle component (bottom-right corner) for switching plans during demos
 *
 * The demo toggle is ESSENTIAL for testing and demonstrating feature differences
 * between plan tiers. NEVER REMOVE IT.
 */

export type { Entitlements, Plan, UsageLimit } from './types'
export { EntitlementsProvider } from './context'
export { useEntitlements } from './hooks'
export { useDemoEntitlements, DEMO_ENTITLEMENTS } from './demo-toggle'
export { DemoToggle } from './demo-toggle-ui'
