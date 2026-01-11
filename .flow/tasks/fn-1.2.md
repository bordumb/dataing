# fn-1.2 Connect frontend to usage API

## Description
Connect the frontend UsagePage to the backend API.

**UI Note**: Current mock UI shows limit-based progress bars (`used/limit`). Backend provides counts/costs (llm_tokens, query_executions, investigations, total_cost). Redesign UI to show these counts/costs as stats cards (like dashboard-page.tsx) instead of progress bars. Plan-based limits are out of scope for this epic.

## Files to Create/Modify

1. **Modify** `frontend/src/lib/api/query-keys.ts`
   - Add `usage` key factory with `metrics` key

2. **Create** `frontend/src/lib/api/usage.ts`
   - `fetchUsageMetrics()` function using URL `/api/v1/usage/metrics`
   - `useUsageMetrics()` hook with 5s polling

3. **Modify** `frontend/src/features/usage/usage-page.tsx`
   - Remove mock data (lines 7-20) and progress bars
   - Redesign to show stats cards: LLM Tokens, Query Executions, Investigations, Total Cost
   - Follow `dashboard-page.tsx` pattern with Skeleton loading states
   - Use `useUsageMetrics()` hook
   - Handle error state gracefully

## Key Patterns to Follow

```typescript
// Types (following investigations.ts pattern with manual interfaces)
export interface UsageMetrics {
  llm_tokens: number
  llm_cost: number
  query_executions: number
  investigations: number
  total_cost: number
}

// Query keys pattern
usage: {
  metrics: ['/api/v1/usage/metrics'] as const,
}

// API function (using customInstance like investigations.ts)
async function fetchUsageMetrics(): Promise<UsageMetrics> {
  return customInstance<UsageMetrics>({
    url: '/api/v1/usage/metrics',
    method: 'GET',
  })
}

// Hook pattern (from investigations.ts)
export function useUsageMetrics() {
  return useQuery({
    queryKey: queryKeys.usage.metrics,
    queryFn: fetchUsageMetrics,
    refetchInterval: 5000, // 5s polling
  })
}
```

**Optional**: Run `just generate-client` to update OpenAPI types for external tooling after backend is deployed.

## References

- `frontend/src/lib/api/investigations.ts` - Hook pattern with polling
- `frontend/src/lib/api/query-keys.ts` - Query key factory
- `frontend/src/features/usage/usage-page.tsx` - Current mock implementation
- `frontend/src/features/dashboard/dashboard-page.tsx` - Stats card UI pattern with Skeleton loading
## Acceptance
- [ ] Query keys added for usage in `query-keys.ts` with URL `/api/v1/usage/metrics`
- [ ] `UsageMetrics` TypeScript interface defined in `usage.ts`
- [ ] `usage.ts` API client created with `fetchUsageMetrics()` and `useUsageMetrics()` hook
- [ ] `usage-page.tsx` redesigned to show stats cards (LLM Tokens, Query Executions, Investigations, Total Cost)
- [ ] Progress bars removed (no limit data available yet)
- [ ] Page shows loading skeleton while fetching (follow dashboard-page.tsx pattern)
- [ ] Page shows error message if API fails
- [ ] Metrics auto-refresh every 5 seconds (verify in Network tab)
- [ ] ESLint passes: `cd frontend && pnpm lint`
## Done summary
Created usage.ts API client with useUsageMetrics hook. Updated usage-page.tsx to show stats cards with live data from API.
## Evidence
- Commits:
- Tests:
- PRs:
