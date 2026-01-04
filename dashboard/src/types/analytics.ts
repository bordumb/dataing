export interface OrgStats {
  mttr_hours: number;
  mttr_trend: number;
  active_count: number;
  sla_pct: number;
  monthly_cost: number;
  activity_heatmap: Array<{ date: string; count: number }>;
}

export interface TrendPoint {
  label: string;
  value: number;
}

export interface CostBreakdownItem {
  label: string;
  value: number;
}

export interface UsageMetric {
  label: string;
  value: number;
  delta?: number;
}

export interface OrgUsage {
  investigations_mtd: number;
  api_calls_mtd: number;
}

export interface CostAnalyticsItem {
  dimension: string;
  compute_cost: number;
  llm_cost: number;
  storage_cost: number;
  total_cost: number;
  investigation_count: number;
}

export interface CostAnalytics {
  items: CostAnalyticsItem[];
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

export interface UsageEndpoint {
  endpoint: string;
  method: string;
  request_count: number;
  avg_latency_ms: number;
  error_count: number;
  error_rate: number;
}

export interface UsageAnalytics {
  endpoints: UsageEndpoint[];
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
