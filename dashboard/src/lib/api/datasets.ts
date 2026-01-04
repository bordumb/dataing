import { api, API_BASE_URL } from "./client";
import type { Dataset, DatasetAnomaly, DatasetLineage, DatasetSchema } from "@/types/dataset";
import type { Investigation } from "@/types/investigation";
import type { UserRole } from "@/types/user";

interface APIDataset {
  id: string;
  name: string;
  identifier: string;
  source: string;
  investigation_count: number;
  last_investigation: string | null;
}

export interface DatasetSearchResult {
  source: string;
  identifier: string;
  display_name: string;
  catalog?: string;
  schema?: string;
  table?: string;
  path?: string;
  metadata: {
    row_count?: number;
    size_bytes?: number;
    last_modified?: string;
    columns?: string[];
    format?: string;
  };
}

export interface SearchDatasetsParams {
  query: string;
  source?: "trino" | "postgres" | "mysql" | "hdfs" | "spark" | "all";
  limit?: number;
  catalog?: string;
}

interface SchemaResponse {
  table: string;
  columns: Array<{
    name: string;
    type: string;
    nullable: boolean;
    comment: string | null;
    default_value: string | null;
  }>;
  partitioned_by: string[];
  row_count_estimate: number | null;
  size_bytes: number | null;
  last_modified: string | null;
  properties: Record<string, string> | null;
}

interface LineageResponse {
  dataset_identifier: string;
  upstream: Array<{
    identifier: string;
    source: string;
    depth: number;
    metadata?: Record<string, unknown>;
  }>;
  downstream: Array<{
    identifier: string;
    source: string;
    depth: number;
    metadata?: Record<string, unknown>;
  }>;
}

interface AnomaliesResponse {
  anomalies: Array<{
    id: string;
    type: string;
    severity: string;
    description: string;
    detected_at: string;
    investigation_id: string | null;
    metadata: Record<string, unknown> | null;
  }>;
  meta: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

export async function getDatasets(): Promise<Dataset[]> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/analytics/datasets`);
    if (!response.ok) {
      throw new Error(`Failed to fetch datasets: ${response.statusText}`);
    }
    const data: { datasets: APIDataset[] } = await response.json();

    // Map API datasets to dashboard Dataset type, using real IDs and source from API
    return data.datasets.map((ds) => ({
      id: ds.id,
      name: ds.name,
      identifier: ds.identifier,
      source: ds.source,
      description: `${ds.source.toUpperCase()} dataset with ${ds.investigation_count} investigations`,
      owner_team_id: "team-001",
      table_count: 1,
      investigation_count: ds.investigation_count,
      anomaly_count_30d: Math.floor(ds.investigation_count / 3),
      freshness_status:
        ds.investigation_count > 10 ? "warning" : ("healthy" as "healthy" | "warning" | "critical"),
    }));
  } catch (error) {
    console.error("Error fetching datasets:", error);
    return [];
  }
}

export async function getDataset(datasetId: string): Promise<Dataset> {
  const datasets = await getDatasets();
  // Search by ID first, then by name or identifier (for compatibility with investigation dataset_id which uses table names)
  const dataset = datasets.find(
    (item) => item.id === datasetId || item.name === datasetId || item.identifier === datasetId
  );
  if (!dataset) {
    throw new Error("Dataset not found");
  }
  return dataset;
}

export async function getDatasetSchema(datasetId: string): Promise<DatasetSchema> {
  try {
    const dataset = await getDataset(datasetId);
    // Pass source parameter to tell the API which adapter to use
    const source = (dataset as Dataset & { source?: string }).source || "trino";
    const identifier = (dataset as Dataset & { identifier?: string }).identifier || dataset.name;
    const response = await api.get<SchemaResponse>(
      `/api/v1/datasets/${encodeURIComponent(identifier)}/schema?source=${source}`
    );

    return {
      table: response.table,
      columns: response.columns.map((c) => ({
        name: c.name,
        type: c.type,
        nullable: c.nullable,
        comment: c.comment || undefined,
        default_value: c.default_value || undefined,
      })),
      partitioned_by: response.partitioned_by,
      row_count_estimate: response.row_count_estimate || undefined,
      size_bytes: response.size_bytes || undefined,
      last_modified: response.last_modified || undefined,
      properties: response.properties || undefined,
    };
  } catch (error) {
    console.error("Error fetching dataset schema:", error);
    // Return empty schema if API not available - don't use mock data
    return {
      table: datasetId,
      columns: [],
      partitioned_by: [],
    };
  }
}

export async function getDatasetLineage(datasetId: string): Promise<DatasetLineage> {
  try {
    // Get the dataset to find its identifier
    const dataset = await getDataset(datasetId);
    const identifier = (dataset as Dataset & { identifier?: string }).identifier || dataset.name;

    // Try the new dedicated lineage endpoint first (uses dataset_lineage table)
    try {
      const response = await api.get<LineageResponse>(
        `/api/v1/datasets/${encodeURIComponent(identifier)}/lineage`
      );
      return {
        upstream: response.upstream.map((n) => ({
          id: n.identifier,
          name: n.identifier,
          type: n.source,
          depth: n.depth,
        })),
        downstream: response.downstream.map((n) => ({
          id: n.identifier,
          name: n.identifier,
          type: n.source,
          depth: n.depth,
        })),
      };
    } catch {
      // Fall back to analytics lineage endpoint (uses dbt manifest)
      const response = await fetch(
        `${API_BASE_URL}/api/v1/analytics/datasets/${encodeURIComponent(identifier)}/lineage`
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch lineage: ${response.statusText}`);
      }

      const data = await response.json();
      return {
        upstream: data.upstream || [],
        downstream: data.downstream || [],
      };
    }
  } catch (error) {
    console.error("Error fetching dataset lineage:", error);
    return { upstream: [], downstream: [] };
  }
}

export async function getDatasetAnomalies(
  datasetId: string,
  params?: { limit?: number; offset?: number }
): Promise<{
  anomalies: DatasetAnomaly[];
  total: number;
  has_more: boolean;
}> {
  try {
    const dataset = await getDataset(datasetId);
    const queryParams = new URLSearchParams();
    if (params?.limit) queryParams.set("limit", String(params.limit));
    if (params?.offset) queryParams.set("offset", String(params.offset));

    const response = await api.get<AnomaliesResponse>(
      `/api/v1/datasets/${dataset.name}/anomalies?${queryParams}`
    );

    return {
      anomalies: response.anomalies.map((a) => ({
        id: a.id,
        type: a.type as DatasetAnomaly["type"],
        severity: a.severity as DatasetAnomaly["severity"],
        description: a.description,
        detected_at: a.detected_at,
        investigation_id: a.investigation_id || undefined,
        metadata: a.metadata || undefined,
      })),
      total: response.meta.total,
      has_more: response.meta.has_more,
    };
  } catch (error) {
    console.error("Error fetching dataset anomalies:", error);
    // Fallback to investigations-based anomalies
    const investigations = await getDatasetInvestigations(datasetId, { limit: 50 });
    const anomalies = investigations.map((inv) => ({
      id: inv.id,
      description: inv.title,
      detected_at: inv.started_at,
      severity: (inv.status === "active" ? "high" : "medium") as DatasetAnomaly["severity"],
      type: (inv.title.includes("distribution")
        ? "distribution"
        : inv.title.includes("volume")
          ? "volume"
          : inv.title.includes("trend")
            ? "trend"
            : "other") as DatasetAnomaly["type"],
    }));
    return { anomalies, total: anomalies.length, has_more: false };
  }
}

export async function getDatasetInvestigations(
  datasetId: string,
  { limit }: { limit?: number } = {}
): Promise<Investigation[]> {
  try {
    // Get the dataset to find its name
    const dataset = await getDataset(datasetId);

    // Fetch investigations for this dataset
    const response = await fetch(`${API_BASE_URL}/api/v1/investigations?limit=${limit || 50}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch investigations: ${response.statusText}`);
    }

    const data: { investigations: any[]; total: number } = await response.json();

    // Filter investigations by dataset name and map to Investigation type
    const filtered = data.investigations
      .filter((inv) => {
        try {
          const inputContext =
            typeof inv.input_context === "string"
              ? JSON.parse(inv.input_context)
              : inv.input_context || {};
          if (inputContext.table_name === dataset.name || inputContext.job_name === dataset.name) {
            return true;
          }
          const datasets = inputContext.datasets || inputContext.all_datasets;
          if (Array.isArray(datasets)) {
            return datasets.some((entry: { identifier?: string }) => entry?.identifier === dataset.name);
          }
          return false;
        } catch {
          return false;
        }
      })
      .map((apiInv) => {
        let inputContext: Record<string, unknown> = {};
        let result: Record<string, unknown> = {};

        try {
          inputContext =
            typeof apiInv.input_context === "string"
              ? JSON.parse(apiInv.input_context)
              : apiInv.input_context || {};
        } catch {
          console.error("Failed to parse input_context");
        }

        try {
          if (apiInv.result) {
            result =
              typeof apiInv.result === "string" ? JSON.parse(apiInv.result) : apiInv.result;
          }
        } catch {
          console.error("Failed to parse result");
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
          title:
            (result.summary as string) ||
            `${apiInv.anomaly_type} anomaly in ${inputContext.table_name || "unknown"}`,
          status: dashboardStatus,
          dataset_id: datasetId,
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
      });

    return typeof limit === "number" ? filtered.slice(0, limit) : filtered;
  } catch (error) {
    console.error("Error fetching dataset investigations:", error);
    return [];
  }
}

export async function searchDatasets(params: SearchDatasetsParams): Promise<{
  datasets: DatasetSearchResult[];
  total: number;
  has_more: boolean;
}> {
  const searchParams = new URLSearchParams({
    q: params.query,
    ...(params.source && { source: params.source }),
    ...(params.limit && { limit: params.limit.toString() }),
    ...(params.catalog && { catalog: params.catalog }),
  });

  const response = await fetch(`${API_BASE_URL}/api/v1/datasets/search?${searchParams}`);

  if (!response.ok) {
    throw new Error(`Search failed: ${response.statusText}`);
  }

  return response.json();
}
