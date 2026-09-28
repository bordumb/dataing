/**
 * Centralized query key factory for React Query.
 *
 * Follows the query key factory pattern for consistent cache management.
 * See: https://tkdodo.eu/blog/effective-react-query-keys
 */

export const queryKeys = {
  // Investigations (unified with branches)
  investigations: {
    all: ["/api/v1/investigations"] as const,
    detail: (id: string) => [`/api/v1/investigations/${id}`] as const,
    stream: (id: string) => [`/api/v1/investigations/${id}/stream`] as const,
    events: (id: string) => [`/api/v1/investigations/${id}/events`] as const,
    status: (id: string) => [`/api/v1/investigations/${id}/status`] as const,
    steers: (id: string) => [`/api/v1/investigations/${id}/steers`] as const,
  },

  // Data Sources
  datasources: {
    all: ["/api/v1/datasources"] as const,
    detail: (id: string) => [`/api/v1/datasources/${id}`] as const,
    schema: (id: string, params?: { search?: string }) =>
      params
        ? ([`/api/v1/datasources/${id}/schema`, params] as const)
        : ([`/api/v1/datasources/${id}/schema`] as const),
    types: ["/api/v1/datasources/types"] as const,
  },

  // Lineage
  lineage: {
    upstream: (datasetId: string, depth?: number) =>
      [`/api/v1/lineage/upstream`, { dataset_id: datasetId, depth }] as const,
    downstream: (datasetId: string, depth?: number) =>
      [`/api/v1/lineage/downstream`, { dataset_id: datasetId, depth }] as const,
    graph: (
      datasetId: string,
      upstreamDepth?: number,
      downstreamDepth?: number,
    ) =>
      [
        `/api/v1/lineage/graph`,
        {
          dataset_id: datasetId,
          upstream_depth: upstreamDepth,
          downstream_depth: downstreamDepth,
        },
      ] as const,
    dataset: (datasetId: string) =>
      [`/api/v1/lineage/dataset/${datasetId}`] as const,
    datasets: (platform?: string) =>
      platform
        ? ([`/api/v1/lineage/datasets`, { platform }] as const)
        : ([`/api/v1/lineage/datasets`] as const),
    search: (query: string) => [`/api/v1/lineage/search`, { query }] as const,
    providers: ["/api/v1/lineage/providers"] as const,
  },

  // System health
  system: {
    llm: ["/api/v1/system/llm"] as const,
  },

  // Dashboard
  dashboard: {
    stats: ["/api/v1/dashboard/"] as const,
    recent: ["/api/v1/dashboard/recent"] as const,
  },

  // Usage
  usage: {
    metrics: ["/api/v1/usage/metrics"] as const,
  },

  // Settings
  settings: {
    tenant: ["/api/v1/settings/tenant"] as const,
    apiKeys: ["/api/v1/settings/api-keys"] as const,
    users: ["/api/v1/users/"] as const,
    webhooks: ["/api/v1/settings/webhooks"] as const,
  },

  // Datasets
  datasets: {
    all: (datasourceId: string) =>
      [`/api/v1/datasources/${datasourceId}/datasets`] as const,
    detail: (id: string) => [`/api/v1/datasets/${id}`] as const,
    investigations: (id: string) =>
      [`/api/v1/datasets/${id}/investigations`] as const,
  },

  // Investigation Feedback
  investigationFeedback: {
    investigation: (investigationId: string) =>
      [
        `/api/v1/investigation-feedback/investigations/${investigationId}`,
      ] as const,
  },

  // Schema Comments
  schemaComments: {
    all: (datasetId: string) =>
      [`/api/v1/datasets/${datasetId}/schema-comments`] as const,
    list: (datasetId: string, fieldName?: string) =>
      [
        `/api/v1/datasets/${datasetId}/schema-comments`,
        { field_name: fieldName },
      ] as const,
  },

  // Knowledge Comments
  knowledgeComments: {
    all: (datasetId: string) =>
      [`/api/v1/datasets/${datasetId}/knowledge-comments`] as const,
    list: (datasetId: string) =>
      [`/api/v1/datasets/${datasetId}/knowledge-comments`] as const,
  },

  // Notifications
  notifications: {
    all: ["notifications"] as const,
    list: (filters?: { unread_only?: boolean; cursor?: string }) =>
      ["notifications", "list", filters] as const,
    unreadCount: ["notifications", "unreadCount"] as const,
  },

  // Issues
  issues: {
    all: ["/api/v1/issues"] as const,
    list: (filters?: {
      status?: string;
      priority?: string;
      severity?: string;
      assignee?: string;
      search?: string;
      cursor?: string;
    }) => ["/api/v1/issues", filters] as const,
    detail: (id: string) => [`/api/v1/issues/${id}`] as const,
    watchers: (id: string) => [`/api/v1/issues/${id}/watchers`] as const,
    investigationRuns: (id: string) =>
      [`/api/v1/issues/${id}/investigation-runs`] as const,
  },

  // Issue threads (shared + scratch chats on an issue)
  issueThreads: {
    list: (issueId: string) => [`/api/v1/issues/${issueId}/threads`] as const,
    messages: (issueId: string, threadId: string) =>
      [`/api/v1/issues/${issueId}/threads/${threadId}/messages`] as const,
    queryResult: (issueId: string, threadId: string, resultId: string) =>
      [
        `/api/v1/issues/${issueId}/threads/${threadId}/query-results/${resultId}`,
      ] as const,
  },
} as const;

// Type helper for getting query key types
export type QueryKeys = typeof queryKeys;
