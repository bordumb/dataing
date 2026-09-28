/**
 * API client for unified investigations with branch support.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "./client";
import { queryKeys } from "./query-keys";

// Types

export interface StepHistoryItem {
  step: string;
  completed: boolean;
  timestamp: string | null;
}

export interface MatchedPattern {
  pattern_id: string;
  pattern_name: string;
  confidence: number;
  description: string | null;
}

export interface BranchState {
  branch_id: string;
  status: string;
  current_step: string;
  synthesis: Record<string, unknown> | null;
  evidence: Record<string, unknown>[];
  step_history: StepHistoryItem[];
  matched_patterns: MatchedPattern[];
  can_merge: boolean;
  parent_branch_id: string | null;
}

export interface InvestigationState {
  investigation_id: string;
  status: string;
  main_branch: BranchState;
  user_branch: BranchState | null;
}

export interface InvestigationListItem {
  investigation_id: string;
  status: string;
  created_at: string;
  dataset_id: string;
}

export interface AlertData {
  dataset_ids: string[];
  metric_spec: {
    metric_type: string;
    expression: string;
    display_name: string;
    columns_referenced: string[];
    source_url?: string;
  };
  anomaly_type: string;
  expected_value: number;
  actual_value: number;
  deviation_pct: number;
  anomaly_date: string;
  severity?: string;
  source_system?: string;
  source_alert_id?: string;
  source_url?: string;
  metadata?: Record<string, unknown>;
}

export interface StartInvestigationResponse {
  investigation_id: string;
  main_branch_id: string;
}

export interface CodifyTest {
  test_type: string;
  column: string | null;
  table: string;
  description: string;
}

export interface CodifyResponse {
  investigation_id: string;
  format: string;
  content: string;
  tests: CodifyTest[];
  confidence: number;
}

// API functions

const API_BASE = "/api/v1/investigations";

async function listInvestigations(): Promise<InvestigationListItem[]> {
  return customInstance<InvestigationListItem[]>({
    url: API_BASE,
    method: "GET",
  });
}

async function getInvestigation(
  investigationId: string,
): Promise<InvestigationState> {
  return customInstance<InvestigationState>({
    url: `${API_BASE}/${investigationId}`,
    method: "GET",
  });
}

async function startInvestigation(
  alert: AlertData,
): Promise<StartInvestigationResponse> {
  return customInstance<StartInvestigationResponse>({
    url: API_BASE,
    method: "POST",
    data: { alert },
  });
}

async function codifyInvestigation(
  investigationId: string,
  format: "gx" | "dbt" | "soda" | "sql",
): Promise<CodifyResponse> {
  return customInstance<CodifyResponse>({
    url: `${API_BASE}/${investigationId}/codify`,
    method: "POST",
    data: { format },
  });
}

// Hooks

export function useInvestigations() {
  return useQuery({
    queryKey: queryKeys.investigations.all,
    queryFn: listInvestigations,
  });
}

export function useInvestigation(investigationId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.investigations.detail(investigationId ?? ""),
    queryFn: () => getInvestigation(investigationId!),
    enabled: !!investigationId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (
        ["completed", "failed", "cancelled", "inconclusive"].includes(
          data?.status ?? "",
        )
      ) {
        return false;
      }
      return 2000;
    },
  });
}

export function useStartInvestigation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: startInvestigation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.investigations.all });
    },
  });
}

export function useCodifyInvestigation() {
  return useMutation({
    mutationFn: ({
      investigationId,
      format,
    }: {
      investigationId: string;
      format: "gx" | "dbt" | "soda" | "sql";
    }) => codifyInvestigation(investigationId, format),
  });
}

// SSE subscription for real-time updates
export function subscribeToInvestigation(
  investigationId: string,
  handlers: {
    onStepChanged?: (data: { step: string; branch_id: string }) => void;
    onStatusChanged?: (data: {
      status: string;
      investigation_id: string;
    }) => void;
    onEnded?: (data: {
      status: string;
      synthesis: Record<string, unknown> | null;
    }) => void;
    onError?: (error: Event) => void;
  },
): () => void {
  // EventSource doesn't support custom headers, so pass JWT token as query param
  const token = localStorage.getItem("dataing_access_token");
  const url = token
    ? `${API_BASE}/${investigationId}/stream?token=${encodeURIComponent(token)}`
    : `${API_BASE}/${investigationId}/stream`;
  const eventSource = new EventSource(url);

  eventSource.addEventListener("step_changed", (e) =>
    handlers.onStepChanged?.(JSON.parse(e.data)),
  );
  eventSource.addEventListener("status_changed", (e) =>
    handlers.onStatusChanged?.(JSON.parse(e.data)),
  );
  eventSource.addEventListener("investigation_ended", (e) => {
    handlers.onEnded?.(JSON.parse(e.data));
    eventSource.close();
  });
  eventSource.onerror = (e) => {
    handlers.onError?.(e);
    eventSource.close();
  };

  return () => eventSource.close();
}
