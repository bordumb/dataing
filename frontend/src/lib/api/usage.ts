/**
 * API client for usage metrics.
 */

import { useQuery } from '@tanstack/react-query'
import { customInstance } from './client'
import { queryKeys } from './query-keys'

// Types

export interface UsageMetrics {
  llm_tokens: number
  llm_cost: number
  query_executions: number
  investigations: number
  total_cost: number
}

// API functions

async function fetchUsageMetrics(): Promise<UsageMetrics> {
  return customInstance<UsageMetrics>({
    url: '/api/v1/usage/metrics',
    method: 'GET',
  })
}

// Hooks

export function useUsageMetrics() {
  return useQuery({
    queryKey: queryKeys.usage.metrics,
    queryFn: fetchUsageMetrics,
    refetchInterval: 5000, // 5s polling
  })
}
