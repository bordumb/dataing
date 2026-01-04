import { api } from "./client";
import type { AuditEvent, AuditFilters } from "@/types/admin";

interface AuditLogsResponse {
  events: Array<{
    id: string;
    timestamp: string;
    actor_id: string | null;
    actor_email: string | null;
    actor_type: string;
    action: string;
    resource_type: string;
    resource_id: string | null;
    organization_id: string | null;
    metadata: Record<string, unknown> | null;
    ip_address: string | null;
    user_agent: string | null;
  }>;
  meta: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

interface ExportResponse {
  export_id: string;
  status: string;
  download_url: string | null;
  created_at: string;
}

export async function getAuditLogs(filters?: AuditFilters): Promise<{
  events: AuditEvent[];
  total: number;
  has_more: boolean;
}> {
  try {
    const params = new URLSearchParams();
    if (filters?.actor) params.set("actor", filters.actor);
    if (filters?.action) params.set("action", filters.action);
    if (filters?.resource_type) params.set("resource_type", filters.resource_type);
    if (filters?.resource_id) params.set("resource_id", filters.resource_id);
    if (filters?.start_time) params.set("start_time", filters.start_time);
    if (filters?.end_time) params.set("end_time", filters.end_time);
    if (filters?.limit) params.set("limit", String(filters.limit));
    if (filters?.offset) params.set("offset", String(filters.offset));

    const response = await api.get<AuditLogsResponse>(`/api/v1/audit/logs?${params}`);

    return {
      events: response.events.map((e) => ({
        id: e.id,
        timestamp: e.timestamp,
        actor: {
          id: e.actor_id || "system",
          email: e.actor_email || "system@datadr.io",
          type: e.actor_type as "user" | "system" | "api_key",
        },
        action: e.action,
        resource: {
          type: e.resource_type,
          id: e.resource_id || undefined,
        },
        metadata: e.metadata || undefined,
        ip_address: e.ip_address || undefined,
        user_agent: e.user_agent || undefined,
      })),
      total: response.meta.total,
      has_more: response.meta.has_more,
    };
  } catch (error) {
    console.error("Error fetching audit logs:", error);
    return { events: [], total: 0, has_more: false };
  }
}

export async function exportAuditLogs(params: {
  start_time: string;
  end_time: string;
  format?: "json" | "csv";
  filters?: AuditFilters;
}): Promise<ExportResponse> {
  const response = await api.post<ExportResponse>("/api/v1/audit/logs/export", {
    start_time: params.start_time,
    end_time: params.end_time,
    format: params.format || "json",
    filters: params.filters,
  });

  return response;
}

// Action type constants for filtering
export const AUDIT_ACTIONS = {
  INVESTIGATION_CREATED: "investigation.created",
  INVESTIGATION_RESOLVED: "investigation.resolved",
  INVESTIGATION_ESCALATED: "investigation.escalated",
  INVESTIGATION_COMMENTED: "investigation.commented",
  TEAM_CREATED: "team.created",
  TEAM_MEMBER_ADDED: "team.member_added",
  TEAM_MEMBER_REMOVED: "team.member_removed",
  USER_LOGIN: "user.login",
  USER_LOGOUT: "user.logout",
  API_KEY_CREATED: "api_key.created",
  API_KEY_REVOKED: "api_key.revoked",
  INTEGRATION_CREATED: "integration.created",
  INTEGRATION_UPDATED: "integration.updated",
  INTEGRATION_DELETED: "integration.deleted",
  WEBHOOK_RECEIVED: "webhook.received",
} as const;

// Resource type constants for filtering
export const AUDIT_RESOURCE_TYPES = {
  INVESTIGATION: "investigation",
  TEAM: "team",
  USER: "user",
  API_KEY: "api_key",
  INTEGRATION: "integration",
  WEBHOOK: "webhook",
  DATASET: "dataset",
} as const;
