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
