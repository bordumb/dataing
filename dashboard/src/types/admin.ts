export interface AuditActor {
  id: string;
  email: string;
  type: "user" | "system" | "api_key";
}

export interface AuditResource {
  type: string;
  id?: string;
}

export interface AuditEvent {
  id: string;
  timestamp: string;
  actor: AuditActor;
  action: string;
  resource: AuditResource;
  metadata?: Record<string, unknown>;
  ip_address?: string;
  user_agent?: string;
}

export interface AuditFilters {
  actor?: string;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
  offset?: number;
}

export interface UsagePoint {
  label: string;
  value: number;
}

export interface Integration {
  id: string;
  name: string;
  type: "notification" | "anomaly_source" | "lineage" | "data_catalog";
  provider: string;
  config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
  updated_at?: string;
  last_sync_at?: string;
  status: "connected" | "disconnected" | "error" | "pending";
}

export interface WebhookSource {
  id: string;
  name: string;
  provider: "monte-carlo" | "anomalo" | "great-expectations" | "generic";
  webhook_url: string;
  secret_token?: string;
  is_active: boolean;
  created_at: string;
  last_received_at?: string;
  event_count: number;
}
