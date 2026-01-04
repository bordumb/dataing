export interface Dataset {
  id: string;
  name: string;
  identifier?: string;  // Full table identifier (e.g., "public.orders")
  source?: string;      // Data source type (e.g., "postgres", "mysql", "trino")
  description: string;
  owner_team_id: string;
  table_count: number;
  investigation_count: number;
  anomaly_count_30d: number;
  freshness_status: "healthy" | "warning" | "critical";
}

export interface DatasetColumn {
  name: string;
  type: string;
  nullable: boolean;
  description?: string;
  comment?: string;
  default_value?: string;
}

export interface DatasetSchema {
  table: string;
  columns: DatasetColumn[];
  partitioned_by?: string[];
  row_count_estimate?: number;
  size_bytes?: number;
  last_modified?: string;
  properties?: Record<string, string>;
}

export interface DatasetLineageNode {
  id: string;
  name: string;
  direction?: "upstream" | "downstream" | "self";
  kind?: "table" | "view" | "model";
  type?: string;
  depth?: number;
}

export interface DatasetLineage {
  upstream: DatasetLineageNode[];
  downstream: DatasetLineageNode[];
}

export interface DatasetAnomaly {
  id: string;
  detected_at: string;
  description: string;
  severity: "low" | "medium" | "high";
  type?: "distribution" | "volume" | "trend" | "schema" | "freshness" | "other";
  investigation_id?: string;
  metadata?: Record<string, unknown>;
}
