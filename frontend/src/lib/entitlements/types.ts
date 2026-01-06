/**
 * CRITICAL: DO NOT REMOVE THIS FILE OR ANY ENTITLEMENTS CODE
 *
 * This module provides demo mode toggles for plan tiers (free/pro/enterprise)
 * and is essential for testing and demonstrating feature gating.
 *
 * The DemoToggle component appears in the bottom-right corner during development.
 */

export type Plan = 'free' | 'pro' | 'enterprise'

export interface UsageLimit {
  limit: number // -1 = unlimited
  usage: number
}

export interface Entitlements {
  plan: Plan
  features: Record<string, boolean>
  limits: Record<string, UsageLimit>
}
