import { api } from "./client";
import type { CostAnalytics, CostBreakdownItem, OrgStats, TrendPoint, UsageMetric, UsageAnalytics } from "@/types/analytics";
import type { Investigation } from "@/types/investigation";
import type { UserRole } from "@/types/user";

interface APIInvestigation {
  id: string;
  organization_id: string | null;
  user_id: string | null;
  user_name: string | null;
  user_email: string | null;
  status: "pending" | "running" | "completed" | "failed";
  anomaly_type: string;
  input_context: string;
  result: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

interface APIStatsResponse {
  mttr_hours: number;
  mttr_trend: number;
  active_count: number;
  sla_pct: number;
  monthly_cost: number;
  activity_heatmap: Array<{
    date: string;
    value: number;
  }>;
}

interface CostAnalyticsResponse {
  items: Array<{
    dimension: string;
    compute_cost: number;
    llm_cost: number;
    storage_cost: number;
    total_cost: number;
    investigation_count: number;
  }>;
  total: {
    compute_cost: number;
    llm_cost: number;
    storage_cost: number;
    total_cost: number;
  };
  period: {
    start_date: string;
    end_date: string;
  };
}

interface UsageAnalyticsResponse {
  endpoints: Array<{
    endpoint: string;
    method: string;
    request_count: number;
    avg_latency_ms: number;
    error_count: number;
    error_rate: number;
  }>;
  totals: {
    total_requests: number;
    total_errors: number;
    avg_latency_ms: number;
  };
  rate_limits: {
    requests_per_minute: number;
    current_usage: number;
    quota_pct: number;
  };
  period: {
    start_date: string;
    end_date: string;
  };
}

function mapAPIInvestigation(apiInv: APIInvestigation): Investigation {
  let inputContext: Record<string, unknown> = {};
  let result: Record<string, unknown> = {};

  try {
    inputContext = JSON.parse(apiInv.input_context);
  } catch (e) {
    console.error("Failed to parse input_context:", e);
  }

  try {
    if (apiInv.result) {
      result = JSON.parse(apiInv.result);
    }
  } catch (e) {
    console.error("Failed to parse result:", e);
  }

  // Map API status to dashboard status
  let dashboardStatus: Investigation["status"];
  if (apiInv.status === "pending" || apiInv.status === "running") {
    dashboardStatus = "active";
  } else if (apiInv.status === "completed") {
    dashboardStatus = "resolved";
  } else {
    dashboardStatus = "escalated";
  }

  // Calculate MTTR in hours
  let mttrHours = 0;
  if (apiInv.started_at && apiInv.completed_at) {
    const start = new Date(apiInv.started_at).getTime();
    const end = new Date(apiInv.completed_at).getTime();
    mttrHours = (end - start) / (1000 * 60 * 60);
  }

  return {
    id: apiInv.id,
    title: (result.summary as string) || `${apiInv.anomaly_type} anomaly in ${(inputContext.table_name as string) || "unknown"}`,
    status: dashboardStatus,
    dataset_id: (inputContext.table_name as string) || "unknown",
    triggered_by: {
      id: apiInv.user_id || "unknown",
      name: apiInv.user_name || "Unknown User",
      email: apiInv.user_email || "unknown@example.com",
      role: "member" as UserRole,
      roles: ["member" as UserRole],
      teams: [],
      stats: {
        investigations_triggered: 0,
        approvals_given: 0,
        knowledge_entries: 0,
      },
    },
    trigger_source: (inputContext.source as string) || "manual",
    started_at: apiInv.started_at || apiInv.created_at,
    updated_at: apiInv.completed_at || apiInv.started_at || apiInv.created_at,
    mttr_hours: Math.round(mttrHours * 10) / 10,
    root_cause: result.root_cause as string | undefined,
    summary: (result.summary as string) || "Investigation in progress",
    transcript: [],
    artifacts: [],
    diagnosis: {
      summary: (result.summary as string) || "",
      confidence: (result.confidence as number) || 0,
      root_cause: (result.root_cause as string) || "",
      recommendations: [],
    },
  };
}

export async function getOrgStats(): Promise<OrgStats> {
  try {
    // Use caching tags so we can revalidate ONLY this data when needed
    const data = await api.get<APIStatsResponse>("/api/v1/analytics/stats", ["org-stats"]);

    return {
      mttr_hours: data.mttr_hours,
      mttr_trend: data.mttr_trend,
      active_count: data.active_count,
      sla_pct: data.sla_pct,
      monthly_cost: data.monthly_cost,
      activity_heatmap: data.activity_heatmap.map((item) => ({
        date: item.date,
        count: item.value,
      })),
    };
  } catch (error) {
    console.error("Error fetching org stats:", error);
    // Graceful degradation for UI
    return {
      mttr_hours: 0,
      mttr_trend: 0,
      active_count: 0,
      sla_pct: 0,
      monthly_cost: 0,
      activity_heatmap: [],
    };
  }
}

export async function getActiveInvestigations() {
  try {
    const data = await api.get<{ investigations: APIInvestigation[]; total: number }>(
      "/api/v1/investigations?status=running&limit=50",
      ["investigations", "active-investigations"]
    );
    return data.investigations.map(mapAPIInvestigation);
  } catch (error) {
    console.error("Error fetching active investigations:", error);
    return [];
  }
}

export async function getTrendSeries(): Promise<TrendPoint[]> {
  try {
    const data = await api.get<APIStatsResponse>("/api/v1/analytics/stats", ["org-stats"]);

    // For now, return the last 7 days of activity from the heatmap
    const last7Days = data.activity_heatmap.slice(-7);
    return last7Days.map((item) => ({
      label: new Date(item.date).toLocaleDateString("en-US", { weekday: "short" }),
      value: item.value,
    }));
  } catch (error) {
    console.error("Error fetching trend series:", error);
    return [];
  }
}

export async function getCostBreakdown(): Promise<CostBreakdownItem[]> {
  try {
    const data = await api.get<CostAnalyticsResponse>("/api/v1/analytics/costs?group_by=team");
    return [
      { label: "Compute", value: data.total.compute_cost },
      { label: "LLM", value: data.total.llm_cost },
      { label: "Storage", value: data.total.storage_cost },
    ];
  } catch (error) {
    console.error("Error fetching cost breakdown:", error);
    // Return placeholder data
    return [
      { label: "Compute", value: 26000 },
      { label: "LLM", value: 14000 },
      { label: "Storage", value: 8200 },
    ];
  }
}

export async function getCostAnalytics(params?: {
  group_by?: "team" | "dataset" | "day" | "week";
  start_date?: string;
  end_date?: string;
}): Promise<CostAnalytics> {
  try {
    const queryParams = new URLSearchParams();
    if (params?.group_by) queryParams.set("group_by", params.group_by);
    if (params?.start_date) queryParams.set("start_date", params.start_date);
    if (params?.end_date) queryParams.set("end_date", params.end_date);

    const data = await api.get<CostAnalyticsResponse>(`/api/v1/analytics/costs?${queryParams}`);

    return {
      items: data.items.map((item) => ({
        dimension: item.dimension,
        compute_cost: item.compute_cost,
        llm_cost: item.llm_cost,
        storage_cost: item.storage_cost,
        total_cost: item.total_cost,
        investigation_count: item.investigation_count,
      })),
      total: {
        compute_cost: data.total.compute_cost,
        llm_cost: data.total.llm_cost,
        storage_cost: data.total.storage_cost,
        total_cost: data.total.total_cost,
      },
      period: {
        start_date: data.period.start_date,
        end_date: data.period.end_date,
      },
    };
  } catch (error) {
    console.error("Error fetching cost analytics:", error);
    return {
      items: [],
      total: { compute_cost: 0, llm_cost: 0, storage_cost: 0, total_cost: 0 },
      period: { start_date: "", end_date: "" },
    };
  }
}

export async function getUsageAnalytics(): Promise<UsageAnalytics> {
  try {
    const data = await api.get<UsageAnalyticsResponse>("/api/v1/analytics/usage");

    return {
      endpoints: data.endpoints.map((e) => ({
        endpoint: e.endpoint,
        method: e.method,
        request_count: e.request_count,
        avg_latency_ms: e.avg_latency_ms,
        error_count: e.error_count,
        error_rate: e.error_rate,
      })),
      totals: {
        total_requests: data.totals.total_requests,
        total_errors: data.totals.total_errors,
        avg_latency_ms: data.totals.avg_latency_ms,
      },
      rate_limits: {
        requests_per_minute: data.rate_limits.requests_per_minute,
        current_usage: data.rate_limits.current_usage,
        quota_pct: data.rate_limits.quota_pct,
      },
      period: {
        start_date: data.period.start_date,
        end_date: data.period.end_date,
      },
    };
  } catch (error) {
    console.error("Error fetching usage analytics:", error);
    return {
      endpoints: [],
      totals: { total_requests: 0, total_errors: 0, avg_latency_ms: 0 },
      rate_limits: { requests_per_minute: 1000, current_usage: 0, quota_pct: 0 },
      period: { start_date: "", end_date: "" },
    };
  }
}

export async function getUsageMetrics(): Promise<UsageMetric[]> {
  try {
    const data = await api.get<APIStatsResponse>("/api/v1/analytics/stats", ["org-stats"]);

    // Calculate total investigations from heatmap
    const totalInvestigations = data.activity_heatmap.reduce((sum, item) => sum + item.value, 0);

    return [
      { label: "Investigations (MTD)", value: totalInvestigations, delta: 0 },
      { label: "MTTR (hours)", value: data.mttr_hours, delta: Math.round(data.mttr_trend) },
      { label: "SLA compliance (%)", value: data.sla_pct, delta: 0 },
      { label: "Active investigations", value: data.active_count, delta: 0 },
    ];
  } catch (error) {
    console.error("Error fetching usage metrics:", error);
    return [];
  }
}

export async function getRecentAnomalies({ limit }: { limit: number }) {
  try {
    const data = await api.get<{ investigations: APIInvestigation[]; total: number }>(
      `/api/v1/investigations?limit=${limit}`,
      ["investigations", "recent-anomalies"]
    );

    return data.investigations.map((inv) => {
      let inputContext: Record<string, unknown> = {};
      try {
        inputContext = JSON.parse(inv.input_context);
      } catch (e) {
        console.error("Failed to parse input_context:", e);
      }

      return {
        id: inv.id,
        title: `${inv.anomaly_type} anomaly in ${(inputContext.table_name as string) || "unknown"}`,
        severity: ((inputContext.severity as string) || "medium") as "high" | "medium" | "low",
        detected_at: inv.created_at,
      };
    });
  } catch (error) {
    console.error("Error fetching recent anomalies:", error);
    return [];
  }
}
