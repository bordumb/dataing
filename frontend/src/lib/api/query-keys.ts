/**
 * Centralized query key factory for React Query.
 *
 * Follows the query key factory pattern for consistent cache management.
 * See: https://tkdodo.eu/blog/effective-react-query-keys
 */

export const queryKeys = {
  // Investigations
  investigations: {
    all: ['/api/v1/investigations/'] as const,
    detail: (id: string) => [`/api/v1/investigations/${id}`] as const,
    events: (id: string) => [`/api/v1/investigations/${id}/events`] as const,
  },

  // Data Sources
  datasources: {
    all: ['/api/v1/datasources/'] as const,
    detail: (id: string) => [`/api/v1/datasources/${id}`] as const,
    schema: (id: string, params?: { search?: string }) =>
      params
        ? ([`/api/v1/datasources/${id}/schema`, params] as const)
        : ([`/api/v1/datasources/${id}/schema`] as const),
    types: ['/api/v1/datasources/types'] as const,
  },

  // Lineage
  lineage: {
    upstream: (datasetId: string, depth?: number) =>
      [`/api/v1/lineage/upstream`, { dataset_id: datasetId, depth }] as const,
    downstream: (datasetId: string, depth?: number) =>
      [`/api/v1/lineage/downstream`, { dataset_id: datasetId, depth }] as const,
    graph: (datasetId: string, upstreamDepth?: number, downstreamDepth?: number) =>
      [
        `/api/v1/lineage/graph`,
        { dataset_id: datasetId, upstream_depth: upstreamDepth, downstream_depth: downstreamDepth },
      ] as const,
    dataset: (datasetId: string) => [`/api/v1/lineage/dataset/${datasetId}`] as const,
    datasets: (platform?: string) =>
      platform
        ? ([`/api/v1/lineage/datasets`, { platform }] as const)
        : ([`/api/v1/lineage/datasets`] as const),
    search: (query: string) => [`/api/v1/lineage/search`, { query }] as const,
    providers: ['/api/v1/lineage/providers'] as const,
  },

  // Dashboard
  dashboard: {
    stats: ['/api/v1/dashboard/'] as const,
    recent: ['/api/v1/dashboard/recent'] as const,
  },

  // Settings
  settings: {
    tenant: ['/api/v1/settings/tenant'] as const,
    apiKeys: ['/api/v1/settings/api-keys'] as const,
    users: ['/api/v1/users/'] as const,
    webhooks: ['/api/v1/settings/webhooks'] as const,
  },

  // Approvals
  approvals: {
    all: ['/api/v1/approvals/'] as const,
    pending: ['/api/v1/approvals/', { status: 'pending' }] as const,
    detail: (id: string) => [`/api/v1/approvals/${id}`] as const,
  },

  // Datasets
  datasets: {
    all: (datasourceId: string) => [`/api/v1/datasources/${datasourceId}/datasets`] as const,
    detail: (id: string) => [`/api/v1/datasets/${id}`] as const,
    investigations: (id: string) => [`/api/v1/datasets/${id}/investigations`] as const,
  },
} as const

// Type helper for getting query key types
export type QueryKeys = typeof queryKeys
