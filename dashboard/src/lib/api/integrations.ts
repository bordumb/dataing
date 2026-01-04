import { api } from "./client";
import type { Integration, WebhookSource } from "@/types/admin";

interface IntegrationsListResponse {
  integrations: Array<{
    id: string;
    name: string;
    type: string;
    provider: string;
    config: Record<string, unknown>;
    is_active: boolean;
    created_at: string;
    updated_at: string | null;
    last_sync_at: string | null;
    status: string;
  }>;
  meta: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

interface WebhookSourcesResponse {
  sources: Array<{
    id: string;
    name: string;
    provider: string;
    webhook_url: string;
    secret_token: string | null;
    is_active: boolean;
    created_at: string;
    last_received_at: string | null;
    event_count: number;
  }>;
  meta: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

interface TestIntegrationResponse {
  success: boolean;
  message: string;
  latency_ms: number | null;
}

export async function getIntegrations(): Promise<Integration[]> {
  try {
    const response = await api.get<IntegrationsListResponse>("/api/v1/integrations");
    return response.integrations.map((i) => ({
      id: i.id,
      name: i.name,
      type: i.type as Integration["type"],
      provider: i.provider,
      config: i.config,
      is_active: i.is_active,
      created_at: i.created_at,
      updated_at: i.updated_at || undefined,
      last_sync_at: i.last_sync_at || undefined,
      status: i.status as Integration["status"],
    }));
  } catch (error) {
    console.error("Error fetching integrations:", error);
    return [];
  }
}

export async function getIntegration(integrationId: string): Promise<Integration> {
  const response = await api.get<{
    integration: IntegrationsListResponse["integrations"][0];
  }>(`/api/v1/integrations/${integrationId}`);

  const i = response.integration;
  return {
    id: i.id,
    name: i.name,
    type: i.type as Integration["type"],
    provider: i.provider,
    config: i.config,
    is_active: i.is_active,
    created_at: i.created_at,
    updated_at: i.updated_at || undefined,
    last_sync_at: i.last_sync_at || undefined,
    status: i.status as Integration["status"],
  };
}

export async function createIntegration(data: {
  name: string;
  type: string;
  provider: string;
  config: Record<string, unknown>;
}): Promise<Integration> {
  const response = await api.post<{
    integration: IntegrationsListResponse["integrations"][0];
  }>("/api/v1/integrations", data);

  const i = response.integration;
  return {
    id: i.id,
    name: i.name,
    type: i.type as Integration["type"],
    provider: i.provider,
    config: i.config,
    is_active: i.is_active,
    created_at: i.created_at,
    status: i.status as Integration["status"],
  };
}

export async function updateIntegration(
  integrationId: string,
  data: {
    name?: string;
    config?: Record<string, unknown>;
    is_active?: boolean;
  }
): Promise<Integration> {
  const response = await api.put<{
    integration: IntegrationsListResponse["integrations"][0];
  }>(`/api/v1/integrations/${integrationId}`, data);

  const i = response.integration;
  return {
    id: i.id,
    name: i.name,
    type: i.type as Integration["type"],
    provider: i.provider,
    config: i.config,
    is_active: i.is_active,
    created_at: i.created_at,
    updated_at: i.updated_at || undefined,
    status: i.status as Integration["status"],
  };
}

export async function deleteIntegration(integrationId: string): Promise<void> {
  await api.delete(`/api/v1/integrations/${integrationId}`);
}

export async function testIntegration(integrationId: string): Promise<TestIntegrationResponse> {
  return api.post<TestIntegrationResponse>(`/api/v1/integrations/${integrationId}/test`, {});
}

// Webhook Sources
export async function getWebhookSources(): Promise<WebhookSource[]> {
  try {
    const response = await api.get<WebhookSourcesResponse>("/api/v1/webhooks/sources");
    return response.sources.map((s) => ({
      id: s.id,
      name: s.name,
      provider: s.provider as WebhookSource["provider"],
      webhook_url: s.webhook_url,
      secret_token: s.secret_token || undefined,
      is_active: s.is_active,
      created_at: s.created_at,
      last_received_at: s.last_received_at || undefined,
      event_count: s.event_count,
    }));
  } catch (error) {
    console.error("Error fetching webhook sources:", error);
    return [];
  }
}

export async function createWebhookSource(data: {
  name: string;
  provider: string;
  config?: Record<string, unknown>;
}): Promise<WebhookSource> {
  const response = await api.post<{
    source: WebhookSourcesResponse["sources"][0];
    webhook_url: string;
    secret_token: string;
  }>("/api/v1/webhooks/sources", data);

  return {
    id: response.source.id,
    name: response.source.name,
    provider: response.source.provider as WebhookSource["provider"],
    webhook_url: response.webhook_url,
    secret_token: response.secret_token,
    is_active: response.source.is_active,
    created_at: response.source.created_at,
    event_count: 0,
  };
}

export async function deleteWebhookSource(sourceId: string): Promise<void> {
  await api.delete(`/api/v1/webhooks/sources/${sourceId}`);
}

// Integration type constants
export const INTEGRATION_TYPES = {
  NOTIFICATION: "notification",
  ANOMALY_SOURCE: "anomaly_source",
  LINEAGE: "lineage",
  DATA_CATALOG: "data_catalog",
} as const;

// Provider constants
export const NOTIFICATION_PROVIDERS = {
  SLACK: "slack",
  PAGERDUTY: "pagerduty",
  EMAIL: "email",
  WEBHOOK: "webhook",
} as const;

export const ANOMALY_SOURCE_PROVIDERS = {
  MONTE_CARLO: "monte-carlo",
  ANOMALO: "anomalo",
  GREAT_EXPECTATIONS: "great-expectations",
  GENERIC: "generic",
} as const;

export const LINEAGE_PROVIDERS = {
  OPENLINEAGE: "openlineage",
  DBT: "dbt",
  DATAHUB: "datahub",
} as const;
