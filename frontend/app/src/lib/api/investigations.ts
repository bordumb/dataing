/**
 * API client for unified investigations with branch support.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customInstance } from "./client";
import type {
  ExecutionProfile,
  HypothesisStatus,
  InvestigationBrief,
  RunError,
} from "./investigation-runs";
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

/** A hypothesis the manager proposed, and how testing it ended. */
export interface RunHypothesis {
  id: string;
  title: string;
  status: HypothesisStatus | string;
  reasoning: string | null;
}

export interface InvestigationState {
  investigation_id: string;
  status: string;
  main_branch: BranchState;
  user_branch: BranchState | null;
  /**
   * The issue the run belongs to, and the run's number among its runs.
   * Null for imported snapshots, which have no issue (spec 0001 §7.11).
   */
  issue_id?: string | null;
  issue_number?: number | null;
  issue_title?: string | null;
  run_number?: number | null;
  brief?: InvestigationBrief | null;
  execution_profile?: string | null;
  /** Why the run failed, when it did. */
  error?: RunError | null;
  hypotheses?: RunHypothesis[] | null;
}

export interface InvestigationListItem {
  investigation_id: string;
  status: string;
  created_at: string;
  dataset_id: string;
}

/**
 * Start a run from a brief (spec 0001 §7.11). Without `issue_id` the server
 * opens an issue for it, titled with the symptom.
 */
export interface StartInvestigationBody {
  brief: InvestigationBrief;
  execution_profile: ExecutionProfile;
  datasource_id?: string | null;
  issue_id?: string | null;
}

export interface StartInvestigationResponse {
  investigation_id: string;
  run_id: string;
  issue_id: string;
  issue_number: number;
  status: string;
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

export async function startInvestigation(
  body: StartInvestigationBody,
): Promise<StartInvestigationResponse> {
  return customInstance<StartInvestigationResponse>({
    url: API_BASE,
    method: "POST",
    data: body,
  });
}

/** The run as a snapshot archive (tar.gz), for replay or sharing. */
export async function fetchSnapshot(investigationId: string): Promise<Blob> {
  return customInstance<Blob>({
    url: `${API_BASE}/${investigationId}/snapshot`,
    method: "GET",
    responseType: "blob",
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

/** Workflow statuses a run doesn't leave. */
export const TERMINAL_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "inconclusive",
  "terminated",
  "timed_out",
]);

/** Whether the run has ended, by its status or a recorded failure. */
export function hasEnded(state: Pick<InvestigationState, "status" | "error">) {
  return TERMINAL_STATUSES.has(state.status) || !!state.error;
}

export function useInvestigation(investigationId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.investigations.detail(investigationId ?? ""),
    queryFn: () => getInvestigation(investigationId!),
    enabled: !!investigationId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (query.state.error || (data && hasEnded(data))) return false;
      return 2000;
    },
  });
}

export function useStartInvestigation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: startInvestigation,
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.investigations.all,
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.issues.all });
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
