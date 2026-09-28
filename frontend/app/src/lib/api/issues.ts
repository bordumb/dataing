/**
 * API client wrapper for Issues.
 *
 * List/watch/run hooks come from the orval output. Issue get/create/update are
 * hand-written because the committed openapi.json predates the fields the
 * issue hub needs (context, due_at, allowed_transitions, transition_requirements).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useListIssuesApiV1IssuesGet,
  useListIssueWatchersApiV1IssuesIssueIdWatchersGet,
  useAddIssueWatcherApiV1IssuesIssueIdWatchPost,
  useRemoveIssueWatcherApiV1IssuesIssueIdWatchDelete,
  useSpawnInvestigationApiV1IssuesIssueIdInvestigationRunsPost,
} from "./generated/issues/issues";
import type {
  InvestigationRunResponse as GeneratedInvestigationRunResponse,
  IssueResponse as GeneratedIssueResponse,
  IssueListResponse as GeneratedIssueListResponse,
  IssueCreate as GeneratedIssueCreate,
  IssueUpdate as GeneratedIssueUpdate,
} from "./model";
import { customInstance } from "./client";
import { queryKeys } from "./query-keys";

// Re-export types from model
export type {
  WatcherResponse,
  WatcherListResponse,
  InvestigationRunCreate,
  ListIssuesApiV1IssuesGetParams as IssueListParams,
} from "./model";

/** How a run on an issue ended; set from its outcome (spec 0001 §7.11). */
export type RunStatus = "running" | "completed" | "failed";

/**
 * A run on an issue. Beyond the committed schema it carries its number among
 * the issue's runs (by start time), its status and, for a failed run, why.
 */
export type InvestigationRunResponse = GeneratedInvestigationRunResponse & {
  number?: number | null;
  status?: RunStatus | null;
  error?: string | null;
};

export interface InvestigationRunListResponse {
  items: InvestigationRunResponse[];
  total: number;
}

/** Where the problem was seen, collected by the create form. */
export interface IssueContext {
  observed_at?: string;
  column?: string;
  [key: string]: unknown;
}

export type IssueResponse = GeneratedIssueResponse & {
  due_at: string | null;
  context: IssueContext;
  /** Statuses this issue may move to. The UI offers only these. */
  allowed_transitions: string[];
  /** For allowed moves, the fields to send in the same PATCH. */
  transition_requirements: Record<string, string[]>;
};

export type IssueListResponse = Omit<GeneratedIssueListResponse, "items"> & {
  items: IssueResponse[];
};

export type IssueCreate = GeneratedIssueCreate & {
  context?: IssueContext;
};

/** A field sent as null clears it; a missing field is left unchanged. */
export type IssueUpdate = GeneratedIssueUpdate & {
  dataset_id?: string | null;
  due_at?: string | null;
  context?: IssueContext | null;
};

const ISSUES_URL = "/api/v1/issues";

export function getIssue(issueId: string, signal?: AbortSignal) {
  return customInstance<IssueResponse>({
    url: `${ISSUES_URL}/${issueId}`,
    method: "GET",
    signal,
  });
}

export function createIssue(data: IssueCreate) {
  return customInstance<IssueResponse>({
    url: ISSUES_URL,
    method: "POST",
    data,
  });
}

export function updateIssue(issueId: string, data: IssueUpdate) {
  return customInstance<IssueResponse>({
    url: `${ISSUES_URL}/${issueId}`,
    method: "PATCH",
    data,
  });
}

export const useIssues = useListIssuesApiV1IssuesGet;
export const useIssueWatchers =
  useListIssueWatchersApiV1IssuesIssueIdWatchersGet;
export const useWatchIssue = useAddIssueWatcherApiV1IssuesIssueIdWatchPost;
export const useUnwatchIssue =
  useRemoveIssueWatcherApiV1IssuesIssueIdWatchDelete;
export const useSpawnInvestigation =
  useSpawnInvestigationApiV1IssuesIssueIdInvestigationRunsPost;

export function listInvestigationRuns(issueId: string, signal?: AbortSignal) {
  return customInstance<InvestigationRunListResponse>({
    url: `${ISSUES_URL}/${issueId}/investigation-runs`,
    method: "GET",
    signal,
  });
}

/** A run's status. Runs listed without one are running until they complete. */
export function runStatus(run: InvestigationRunResponse): RunStatus {
  if (run.status) return run.status;
  return run.completed_at ? "completed" : "running";
}

/**
 * Each run's number among the issue's runs, by start time. The server sends
 * `number`; for runs without one, count them in start order.
 */
export function runNumbers(
  runs: InvestigationRunResponse[],
): Map<string, number> {
  const ordered = [...runs].sort((a, b) =>
    a.created_at.localeCompare(b.created_at),
  );
  return new Map(ordered.map((run, i) => [run.id, run.number ?? i + 1]));
}

/** The run of an issue with this run id or investigation id. */
export function findRun(
  runs: InvestigationRunResponse[] | undefined,
  {
    runId,
    investigationId,
  }: { runId?: string | null; investigationId?: string | null },
): InvestigationRunResponse | undefined {
  return runs?.find(
    (r) =>
      (!!runId && r.id === runId) ||
      (!!investigationId && r.investigation_id === investigationId),
  );
}

/** How often an issue's runs refresh while one is still running. */
export const RUNS_POLL_MS = 10_000;

/** The issue's runs, refreshed while any is running so failures show. */
export function useIssueInvestigationRuns(issueId: string) {
  return useQuery({
    queryKey: queryKeys.issues.investigationRuns(issueId),
    queryFn: ({ signal }) => listInvestigationRuns(issueId, signal),
    enabled: !!issueId,
    refetchInterval: (query) =>
      query.state.data?.items.some((r) => runStatus(r) === "running")
        ? RUNS_POLL_MS
        : false,
  });
}

export function useIssue(issueId: string) {
  return useQuery({
    queryKey: queryKeys.issues.detail(issueId),
    queryFn: ({ signal }) => getIssue(issueId, signal),
    enabled: !!issueId,
  });
}

export function useCreateIssue() {
  return useMutation({
    mutationFn: ({ data }: { data: IssueCreate }) => createIssue(data),
  });
}

/** PATCH an issue; the response replaces the cached detail. */
export function useUpdateIssue() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ issueId, data }: { issueId: string; data: IssueUpdate }) =>
      updateIssue(issueId, data),
    onSuccess: (issue) => {
      queryClient.setQueryData(queryKeys.issues.detail(issue.id), issue);
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.all });
    },
  });
}

// Helper hook to invalidate issue queries
export function useInvalidateIssues() {
  const queryClient = useQueryClient();

  return {
    invalidateList: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.all }),
    invalidateDetail: (id: string) =>
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.detail(id) }),
    invalidateWatchers: (id: string) =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.issues.watchers(id),
      }),
    invalidateInvestigationRuns: (id: string) =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.issues.investigationRuns(id),
      }),
  };
}

// Status display helpers
export function getStatusVariant(
  status: string,
): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" {
  switch (status) {
    case "open":
      return "default";
    case "triaged":
      return "secondary";
    case "in_progress":
      return "warning";
    case "blocked":
      return "destructive";
    case "resolved":
      return "success";
    case "closed":
      return "outline";
    default:
      return "secondary";
  }
}

export function getStatusLabel(status: string): string {
  switch (status) {
    case "open":
      return "Open";
    case "triaged":
      return "Triaged";
    case "in_progress":
      return "In Progress";
    case "blocked":
      return "Blocked";
    case "resolved":
      return "Resolved";
    case "closed":
      return "Closed";
    default:
      return status;
  }
}

export function getPriorityVariant(
  priority: string | null,
): "default" | "secondary" | "destructive" | "outline" {
  switch (priority) {
    case "P0":
      return "destructive";
    case "P1":
      return "destructive";
    case "P2":
      return "default";
    case "P3":
      return "secondary";
    case "P4":
      return "outline";
    default:
      return "secondary";
  }
}

export function getSeverityVariant(
  severity: string | null,
): "default" | "secondary" | "destructive" | "outline" {
  switch (severity) {
    case "critical":
      return "destructive";
    case "high":
      return "destructive";
    case "medium":
      return "default";
    case "low":
      return "secondary";
    default:
      return "secondary";
  }
}

/** Values the API accepts (IssueCreate/IssueUpdate patterns). */
export const ISSUE_PRIORITIES = ["P0", "P1", "P2", "P3"] as const;
export const ISSUE_SEVERITIES = ["critical", "high", "medium", "low"] as const;

export function getSeverityLabel(severity: string): string {
  return severity.charAt(0).toUpperCase() + severity.slice(1);
}
