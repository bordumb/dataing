/**
 * Investigations started from an issue: briefs, live status, steers and the
 * outcome review (spec 0001 §7.7, §7.8, §7.10).
 *
 * Hand-written like issue-threads.ts: the generated types spell every nullable
 * field as its own alias, which makes the brief editor hard to read.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { customInstance } from "./client";
import type { InvestigationRunResponse } from "./model";
import { queryKeys } from "./query-keys";

// ============================================================================
// Briefs
// ============================================================================

/** A finding or exclusion, optionally backed by a thread message and a query. */
export interface BriefClaim {
  statement: string;
  message_id?: string | null;
  query_result_id?: string | null;
}

export interface BriefTimeWindow {
  from: string;
  to: string;
}

export interface BriefScope {
  datasource_id?: string | null;
  tables?: string[];
  time_window?: BriefTimeWindow | null;
}

/** What a thread hands to the manager and its subagents (InvestigationBrief). */
export interface InvestigationBrief {
  version?: number;
  symptom: string;
  scope?: BriefScope;
  findings?: BriefClaim[];
  ruled_out?: BriefClaim[];
  leads?: string[];
  notes?: string;
}

export type ExecutionProfile = "safe" | "standard" | "deep";

export interface StartRunBody {
  brief: InvestigationBrief;
  execution_profile: ExecutionProfile;
  dataset_id?: string | null;
  datasource_id?: string | null;
  source_thread_id?: string | null;
  parent_run_id?: string | null;
}

/** Read a brief out of an untyped payload, or null when it isn't one. */
export function asBrief(value: unknown): InvestigationBrief | null {
  if (!value || typeof value !== "object") return null;
  const brief = value as InvestigationBrief;
  return typeof brief.symptom === "string" ? brief : null;
}

// ============================================================================
// Live status and outcomes
// ============================================================================

export type HypothesisStatus =
  | "pending"
  | "running"
  | "supported"
  | "refuted"
  | "untested"
  | "ruled_out";

export interface HypothesisState {
  id: string;
  title: string;
  status: HypothesisStatus | string;
}

export interface InvestigationLiveStatus {
  investigation_id: string;
  workflow_status: string;
  current_step?: string | null;
  progress?: number | null;
  is_complete?: boolean | null;
  is_cancelled?: boolean | null;
  hypotheses_count?: number | null;
  hypotheses_evaluated?: number | null;
  evidence_count?: number | null;
  hypotheses?: HypothesisState[] | null;
  pending_steers?: { steer_id: string; kind: string }[] | null;
}

/** Why a run failed (spec 0001 §7.12): what broke, where, and what to fix. */
export interface RunError {
  code: string;
  message: string;
  step?: string | null;
}

/** The outcome a finished run posts to the thread (publish_investigation_outcome). */
export interface InvestigationOutcome {
  /** "completed", or "failed" with `error` and no root cause. */
  status?: string;
  root_cause?: string | null;
  confidence?: number | null;
  recommendations?: string[];
  supporting_evidence?: unknown[];
  hypotheses?: HypothesisState[];
  counter_analysis?: unknown;
  error?: RunError | null;
}

export function isFailedOutcome(
  outcome: InvestigationOutcome | null | undefined,
): boolean {
  return outcome?.status === "failed";
}

export function isRunning(status: InvestigationLiveStatus | undefined) {
  return (
    !!status && status.workflow_status === "running" && !status.is_complete
  );
}

export type OutcomeVerdict = "confirmed" | "rejected";

// ============================================================================
// Steers
// ============================================================================

export type SteerKind =
  | "add_context"
  | "rule_out"
  | "add_hypothesis"
  | "stop_and_synthesize";

export const STEER_KIND_LABEL: Record<string, string> = {
  add_context: "Add context",
  rule_out: "Rule out",
  add_hypothesis: "Add hypothesis",
  stop_and_synthesize: "Stop and conclude",
};

export interface SteerCreate {
  kind: SteerKind;
  text?: string;
  hypothesis_id?: string | null;
  /** The agent reply whose proposal this sends; sending it twice is a no-op. */
  proposal_message_id?: string | null;
}

export type SteerStatus = "pending" | "applied" | "rejected";

export interface Steer {
  id: string;
  investigation_id: string;
  issue_id: string | null;
  message_id: string | null;
  kind: string;
  text: string;
  hypothesis_id: string | null;
  actor_user_id: string | null;
  status: SteerStatus | string;
  applied_phase: string | null;
  outcome: string | null;
  created_at: string;
  applied_at: string | null;
}

// ============================================================================
// Requests
// ============================================================================

const INVESTIGATIONS = "/api/v1/investigations";

export function startRun(issueId: string, body: StartRunBody) {
  return customInstance<InvestigationRunResponse>({
    url: `/api/v1/issues/${issueId}/investigation-runs`,
    method: "POST",
    data: body,
  });
}

export function getLiveStatus(investigationId: string, signal?: AbortSignal) {
  return customInstance<InvestigationLiveStatus>({
    url: `${INVESTIGATIONS}/${investigationId}/status`,
    method: "GET",
    signal,
  });
}

export function reviewOutcome(
  investigationId: string,
  body: { verdict: OutcomeVerdict; note?: string | null },
) {
  return customInstance<InvestigationRunResponse>({
    url: `${INVESTIGATIONS}/${investigationId}/outcome-review`,
    method: "POST",
    data: body,
  });
}

export function listSteers(investigationId: string, signal?: AbortSignal) {
  return customInstance<{ items: Steer[] }>({
    url: `${INVESTIGATIONS}/${investigationId}/steers`,
    method: "GET",
    signal,
  });
}

export function createSteer(investigationId: string, body: SteerCreate) {
  return customInstance<Steer>({
    url: `${INVESTIGATIONS}/${investigationId}/steers`,
    method: "POST",
    data: body,
  });
}

// ============================================================================
// Hooks
// ============================================================================

/** How often a running investigation's card refreshes. */
export const LIVE_POLL_MS = 3000;

export function useStartRun(issueId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: StartRunBody) => startRun(issueId, body),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.issues.investigationRuns(issueId),
      }),
  });
}

/** A run's live status, polled while it runs. */
export function useLiveStatus(investigationId: string | null) {
  return useQuery({
    queryKey: queryKeys.investigations.status(investigationId ?? ""),
    queryFn: ({ signal }) => getLiveStatus(investigationId!, signal),
    enabled: !!investigationId,
    refetchInterval: (query) =>
      query.state.error
        ? false
        : !query.state.data || isRunning(query.state.data)
          ? LIVE_POLL_MS
          : false,
  });
}

/** A run's steers, polled while any is still waiting for a checkpoint. */
export function useSteers(investigationId: string | null, running: boolean) {
  return useQuery({
    queryKey: queryKeys.investigations.steers(investigationId ?? ""),
    queryFn: ({ signal }) => listSteers(investigationId!, signal),
    enabled: !!investigationId,
    refetchInterval: (query) =>
      running || query.state.data?.items.some((s) => s.status === "pending")
        ? LIVE_POLL_MS
        : false,
  });
}

export function useCreateSteer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      investigationId,
      body,
    }: {
      investigationId: string;
      body: SteerCreate;
    }) => createSteer(investigationId, body),
    onSuccess: (_steer, { investigationId }) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.investigations.steers(investigationId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.investigations.status(investigationId),
      });
    },
  });
}

export function useReviewOutcome(issueId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      investigationId,
      verdict,
      note,
    }: {
      investigationId: string;
      verdict: OutcomeVerdict;
      note?: string | null;
    }) => reviewOutcome(investigationId, { verdict, note }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.issues.investigationRuns(issueId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.issues.detail(issueId),
      });
    },
  });
}
