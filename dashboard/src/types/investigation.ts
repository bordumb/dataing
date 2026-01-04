import type { User } from "@/types/user";

export type InvestigationStatus =
  | "active"
  | "awaiting_approval"
  | "resolved"
  | "escalated"
  | "monitoring";

export interface InvestigationStep {
  id: string;
  title: string;
  detail: string;
  status: "complete" | "active" | "pending";
  created_at: string;
}

export interface InvestigationArtifact {
  id: string;
  type: "sql" | "python" | "note" | "chart" | "log";
  title?: string;
  name?: string;
  content: string;
  content_url?: string;
  size_bytes?: number;
  created_at?: string;
  metadata?: Record<string, unknown>;
}

export interface InvestigationDiagnosis {
  summary: string;
  confidence: number;
  root_cause: string;
  recommendations: string[];
  evidence?: Array<{
    dataset: string;
    query: string;
    result_summary: string;
  }>;
}

export interface HypothesisResult {
  hypothesis_id: string;
  title: string;
  status: "confirmed" | "rejected" | "refuted" | "inconclusive" | "error";
  confidence: number;
  evidence_summary: string;
  execution_time_seconds: number;
  datasets_used?: string[];
}

export interface InvestigationComment {
  id: string;
  user_id: string;
  user_name: string;
  user_email: string;
  content: string;
  created_at: string;
}

export interface Investigation {
  id: string;
  title: string;
  status: InvestigationStatus;
  datasets?: Array<{
    source: string;
    identifier: string;
    role: string;
    display_name?: string;
  }>;
  dataset_id: string;
  team_id?: string;
  triggered_by: User;
  trigger_source: string;
  started_at: string;
  updated_at: string;
  mttr_hours: number;
  root_cause?: string;
  summary: string;
  transcript: InvestigationStep[];
  artifacts: InvestigationArtifact[];
  diagnosis: InvestigationDiagnosis;
  hypothesis_results?: HypothesisResult[];
  resolution_status?: string;
  resolution_comment?: string;
}

export interface RelatedInvestigations {
  same_dataset: Investigation[];
  similar_root_cause: Investigation[];
  lineage_related: Investigation[];
}
