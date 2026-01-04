import { api, API_BASE_URL } from "./client";
import type { Investigation, RelatedInvestigations, InvestigationComment, InvestigationArtifact } from "@/types/investigation";
import type { UserRole } from "@/types/user";

interface APIInvestigation {
  id: string;
  organization_id: string | null;
  user_id: string | null;
  user_name: string | null;
  user_email: string | null;
  status: "pending" | "running" | "completed" | "failed";
  anomaly_type: string;
  input_context: string | Record<string, unknown> | null;
  datasets?: string | Record<string, unknown>[] | null;
  result: string | Record<string, unknown> | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  team_id?: string | null;
  resolution_status?: string | null;
  resolved_by?: string | null;
  resolution_comment?: string | null;
}

interface InvestigationsListResponse {
  investigations: APIInvestigation[];
  total: number;
  meta?: {
    cursor?: string;
    has_more?: boolean;
  };
}

interface CommentsListResponse {
  comments: Array<{
    id: string;
    user_id: string;
    user_name: string;
    user_email: string;
    content: string;
    created_at: string;
    updated_at: string | null;
  }>;
  meta: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

interface ArtifactsListResponse {
  artifacts: Array<{
    id: string;
    type: string;
    title: string;
    mime_type: string | null;
    content_url: string | null;
    content: string | null;
    size_bytes: number | null;
    created_at: string;
    metadata: Record<string, unknown> | null;
  }>;
  meta: {
    total: number;
    limit: number;
    offset: number;
    has_more: boolean;
  };
}

interface RelatedInvestigationsResponse {
  same_dataset: APIInvestigation[];
  similar_root_cause: APIInvestigation[];
  lineage_related: APIInvestigation[];
}

export interface InvestigationFilters {
  status?: string;
  team_id?: string;
  dataset_id?: string;
  cursor?: string;
  limit?: number;
}

function mapAPIInvestigation(apiInv: APIInvestigation): Investigation {
  let inputContext: Record<string, unknown> = {};
  let result: Record<string, unknown> = {};

  // Handle input_context as either object or JSON string
  if (apiInv.input_context) {
    if (typeof apiInv.input_context === "string") {
      try {
        inputContext = JSON.parse(apiInv.input_context);
      } catch (e) {
        console.error("Failed to parse input_context:", e);
      }
    } else {
      inputContext = apiInv.input_context;
    }
  }

  // Handle result as either object or JSON string
  if (apiInv.result) {
    if (typeof apiInv.result === "string") {
      try {
        result = JSON.parse(apiInv.result);
      } catch (e) {
        console.error("Failed to parse result:", e);
      }
    } else {
      result = apiInv.result;
    }
  }

  let datasets: Investigation["datasets"];
  if (apiInv.datasets) {
    if (typeof apiInv.datasets === "string") {
      try {
        const parsed = JSON.parse(apiInv.datasets) as Investigation["datasets"];
        datasets = Array.isArray(parsed) ? parsed : undefined;
      } catch (e) {
        console.error("Failed to parse datasets:", e);
      }
    } else if (Array.isArray(apiInv.datasets)) {
      datasets = apiInv.datasets as Investigation["datasets"];
    }
  } else if (Array.isArray(inputContext.datasets)) {
    datasets = inputContext.datasets as Investigation["datasets"];
  } else if (Array.isArray(inputContext.all_datasets)) {
    datasets = inputContext.all_datasets as Investigation["datasets"];
  }

  const primaryDataset = datasets?.find((ds) => ds.role === "primary") || datasets?.[0];

  // Map API status to dashboard status
  let dashboardStatus: Investigation["status"];
  if (apiInv.resolution_status === "resolved" || apiInv.resolution_status === "false_positive") {
    dashboardStatus = "resolved";
  } else if (apiInv.resolution_status === "escalated") {
    dashboardStatus = "escalated";
  } else if (apiInv.status === "pending" || apiInv.status === "running") {
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

  // Handle both legacy (table_name) and new (job_name) schemas
  const datasetId = (primaryDataset?.identifier ||
    inputContext.table_name ||
    inputContext.job_name ||
    "unknown") as string;

  const diagnosisPayload = (result.diagnosis || {}) as Record<string, unknown>;
  const summary = (result.summary || diagnosisPayload.summary || "") as string;
  const rootCause = (result.root_cause || diagnosisPayload.root_cause || "") as string;
  const confidence = (result.confidence || diagnosisPayload.confidence || 0) as number;
  const recommendations =
    (diagnosisPayload.recommended_actions as string[]) ||
    (diagnosisPayload.recommendations as string[]) ||
    [];
  // Handle evidence - can be array of objects {dataset, query, result_summary} or array of strings
  const rawEvidence = diagnosisPayload.evidence as unknown;
  let evidence: Investigation["diagnosis"]["evidence"] | undefined = undefined;
  if (Array.isArray(rawEvidence)) {
    if (rawEvidence.every((item) => item && typeof item === "object" && "dataset" in item)) {
      evidence = rawEvidence as Investigation["diagnosis"]["evidence"];
    } else if (rawEvidence.every((item) => typeof item === "string")) {
      // Convert string array to structured format
      const dataset = primaryDataset?.identifier || inputContext.table_name || "unknown";
      evidence = (rawEvidence as string[]).map((str, idx) => ({
        dataset: dataset as string,
        query: str,
        result_summary: `Evidence item ${idx + 1}`,
      }));
    }
  }

  // Extract transcript from result (event timeline) and map to expected format
  const rawTranscript = (result.transcript as Array<{
    id: string;
    type: string;
    message?: string | null;
    phase?: string;
    timestamp: string;
    data?: Record<string, unknown>;
  }>) || [];
  const transcript: Investigation["transcript"] = rawTranscript.map((entry) => ({
    id: entry.id,
    title: entry.type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()), // "progress" -> "Progress"
    detail: entry.message || entry.phase || "",
    status: "complete" as const,
    created_at: entry.timestamp,
  }));

  // Extract artifacts from result
  const rawArtifacts = (result.artifacts as Array<{
    id: string;
    type: string;
    name: string;
    content: string;
    created_at: string;
  }>) || [];
  const artifacts: Investigation["artifacts"] = rawArtifacts.map((a) => ({
    id: a.id,
    type: (a.type as "sql" | "python" | "note" | "chart" | "log") || "sql",
    name: a.name || "Query",
    content: a.content || "",
    created_at: a.created_at,
  }));

  return {
    id: apiInv.id,
    title: summary || `${apiInv.anomaly_type} anomaly in ${datasetId}`,
    status: dashboardStatus,
    datasets,
    dataset_id: datasetId,
    team_id: apiInv.team_id || undefined,
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
    root_cause: rootCause,
    summary: summary || "Investigation in progress",
    transcript: transcript,
    artifacts: artifacts,
    diagnosis: {
      summary: summary,
      confidence: confidence,
      root_cause: rootCause,
      recommendations: recommendations,
      evidence,
    },
    hypothesis_results: (result.hypothesis_results as Investigation["hypothesis_results"]) || [],
    resolution_status: apiInv.resolution_status || undefined,
    resolution_comment: apiInv.resolution_comment || undefined,
  };
}

export async function getInvestigations(filters?: InvestigationFilters): Promise<{
  investigations: Investigation[];
  total: number;
  cursor?: string;
  has_more?: boolean;
}> {
  try {
    const params = new URLSearchParams();
    if (filters?.status) params.set("status", filters.status);
    if (filters?.team_id) params.set("team_id", filters.team_id);
    if (filters?.dataset_id) params.set("dataset_id", filters.dataset_id);
    if (filters?.cursor) params.set("cursor", filters.cursor);
    params.set("limit", String(filters?.limit || 100));

    const queryString = params.toString();
    const response = await fetch(`${API_BASE_URL}/api/v1/investigations?${queryString}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch investigations: ${response.statusText}`);
    }
    const data: InvestigationsListResponse = await response.json();
    return {
      investigations: data.investigations.map(mapAPIInvestigation),
      total: data.total,
      cursor: data.meta?.cursor,
      has_more: data.meta?.has_more,
    };
  } catch (error) {
    console.error("Error fetching investigations:", error);
    return { investigations: [], total: 0 };
  }
}

export async function getInvestigation(id: string): Promise<Investigation> {
  try {
    // Use the /record endpoint which returns the database format with input_context
    const response = await fetch(`${API_BASE_URL}/api/v1/investigations/record/${id}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch investigation: ${response.statusText}`);
    }
    const data: APIInvestigation = await response.json();
    return mapAPIInvestigation(data);
  } catch (error) {
    // Fallback: Fetch all investigations and find the one with matching ID
    try {
      const { investigations } = await getInvestigations();
      const investigation = investigations.find((inv) => inv.id === id);
      if (!investigation) {
        throw new Error("Investigation not found");
      }
      return investigation;
    } catch (fallbackError) {
      console.error("Error fetching investigation:", fallbackError);
      throw new Error("Investigation not found");
    }
  }
}

export async function getRelatedInvestigations(id: string): Promise<RelatedInvestigations> {
  try {
    const response = await api.get<RelatedInvestigationsResponse>(
      `/api/v1/investigations/${id}/related`
    );
    return {
      same_dataset: response.same_dataset.map(mapAPIInvestigation),
      similar_root_cause: response.similar_root_cause.map(mapAPIInvestigation),
      lineage_related: response.lineage_related.map(mapAPIInvestigation),
    };
  } catch (error) {
    console.error("Error fetching related investigations:", error);
    // Fallback to client-side filtering
    const investigation = await getInvestigation(id);
    const { investigations } = await getInvestigations();

    return {
      same_dataset: investigations.filter(
        (inv) => inv.dataset_id === investigation.dataset_id && inv.id !== id
      ).slice(0, 5),
      similar_root_cause: investigations.filter(
        (inv) => inv.root_cause && inv.root_cause === investigation.root_cause && inv.id !== id
      ).slice(0, 5),
      lineage_related: investigations.filter((inv) => inv.id !== id).slice(0, 3),
    };
  }
}

// Comments API
export async function getComments(investigationId: string): Promise<InvestigationComment[]> {
  try {
    const response = await api.get<CommentsListResponse>(
      `/api/v1/investigations/${investigationId}/comments`
    );
    return response.comments.map((c) => ({
      id: c.id,
      user_id: c.user_id,
      user_name: c.user_name,
      user_email: c.user_email,
      content: c.content,
      created_at: c.created_at,
    }));
  } catch (error) {
    console.error("Error fetching comments:", error);
    return [];
  }
}

export async function addComment(
  investigationId: string,
  content: string
): Promise<InvestigationComment> {
  const response = await api.post<{
    id: string;
    user_id: string;
    user_name: string;
    user_email: string;
    content: string;
    created_at: string;
  }>(`/api/v1/investigations/${investigationId}/comments`, { content });

  return {
    id: response.id,
    user_id: response.user_id,
    user_name: response.user_name,
    user_email: response.user_email,
    content: response.content,
    created_at: response.created_at,
  };
}

// Artifacts API
export async function getArtifacts(
  investigationId: string,
  params?: { type?: string; limit?: number }
): Promise<InvestigationArtifact[]> {
  try {
    const queryParams = new URLSearchParams();
    if (params?.type) queryParams.set("type", params.type);
    if (params?.limit) queryParams.set("limit", String(params.limit));

    const response = await api.get<ArtifactsListResponse>(
      `/api/v1/investigations/${investigationId}/artifacts?${queryParams}`
    );
    return response.artifacts.map((a) => ({
      id: a.id,
      type: a.type as "sql" | "python" | "note" | "chart" | "log",
      name: a.title,
      content: a.content || "",
      content_url: a.content_url || undefined,
      size_bytes: a.size_bytes || undefined,
      created_at: a.created_at,
      metadata: a.metadata || undefined,
    }));
  } catch (error) {
    console.error("Error fetching artifacts:", error);
    return [];
  }
}

// Status Update API
export async function updateInvestigationStatus(
  investigationId: string,
  data: {
    resolution_status: "resolved" | "false_positive" | "escalated" | "reopened";
    resolution_comment?: string;
  }
): Promise<void> {
  await api.patch(`/api/v1/investigations/${investigationId}/status`, data);
}

// Anomaly Period for explicit date handling
export interface AnomalyPeriod {
  mode: "single" | "range";
  start: string; // YYYY-MM-DD
  end: string;   // YYYY-MM-DD
}

// Start Investigation
export interface StartInvestigationParams {
  datasets: Array<{
    source: "trino" | "postgres" | "mysql" | "hdfs" | "spark";
    identifier: string;
    role?: "primary" | "secondary" | "reference";
  }>;
  description: string;
  priority: string;
  team_id?: string;
  anomalyPeriod?: AnomalyPeriod;
}

export async function startInvestigation(
  payload: StartInvestigationParams
): Promise<{ investigation_id: string }> {
  const primaryDataset = payload.datasets.find((ds) => ds.role === "primary") || payload.datasets[0];
  if (!primaryDataset) {
    throw new Error("At least one dataset is required");
  }

  // Domain maps to execution environment based on primary dataset source
  const domain = primaryDataset.source;

  // Use explicit anomaly period if provided, otherwise default to today
  const anomalyDate = payload.anomalyPeriod?.end || new Date().toISOString().split("T")[0];

  const response = await fetch(`${API_BASE_URL}/api/v1/investigations`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      datasets: payload.datasets.map((dataset, index) => ({
        source: dataset.source,
        identifier: dataset.identifier,
        role: dataset.role || (index === 0 ? "primary" : "secondary"),
      })),
      description: payload.description,
      priority: payload.priority,
      team_id: payload.team_id,
      // Explicit anomaly period - the backend will use this as the source of truth
      anomaly_period: payload.anomalyPeriod ? {
        mode: payload.anomalyPeriod.mode,
        start: payload.anomalyPeriod.start,
        end: payload.anomalyPeriod.end,
      } : undefined,
      // Alert for backwards compatibility and additional context
      alert: {
        metric_name: payload.description || "Manual investigation",
        job_name: primaryDataset.identifier,
        job_path: `./datasets/${primaryDataset.identifier}`,
        expected_value: 0,
        actual_value: 0,
        deviation_pct: 0,
        detected_at: `${anomalyDate}T00:00:00Z`,
        metadata: {
          priority: payload.priority,
          source: "manual",
          multi_dataset: payload.datasets.length > 1,
          all_datasets: payload.datasets,
        },
      },
      config: {
        timeout_minutes: 30,
        max_hypotheses: 5,
        domain,
      },
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to start investigation: ${response.statusText}`);
  }

  const data = await response.json();
  return { investigation_id: data.investigation_id };
}
