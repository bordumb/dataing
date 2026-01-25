/**
 * API client wrapper for Issues.
 * Re-exports generated hooks with cleaner names.
 */

import { useQueryClient } from "@tanstack/react-query";
import {
  useListIssuesApiV1IssuesGet,
  useGetIssueApiV1IssuesIssueIdGet,
  useCreateIssueApiV1IssuesPost,
  useUpdateIssueApiV1IssuesIssueIdPatch,
  useListIssueCommentsApiV1IssuesIssueIdCommentsGet,
  useCreateIssueCommentApiV1IssuesIssueIdCommentsPost,
  useListIssueWatchersApiV1IssuesIssueIdWatchersGet,
  useAddIssueWatcherApiV1IssuesIssueIdWatchPost,
  useRemoveIssueWatcherApiV1IssuesIssueIdWatchDelete,
  useListInvestigationRunsApiV1IssuesIssueIdInvestigationRunsGet,
  useSpawnInvestigationApiV1IssuesIssueIdInvestigationRunsPost,
} from "./generated/issues/issues";
import { queryKeys } from "./query-keys";

// Re-export types from model
export type {
  IssueResponse,
  IssueListResponse,
  IssueCreate,
  IssueUpdate,
  IssueCommentResponse,
  IssueCommentListResponse,
  IssueCommentCreate,
  WatcherResponse,
  WatcherListResponse,
  InvestigationRunResponse,
  InvestigationRunListResponse,
  InvestigationRunCreate,
  ListIssuesApiV1IssuesGetParams as IssueListParams,
} from "./model";

// Re-export hooks with cleaner names
export const useIssues = useListIssuesApiV1IssuesGet;
export const useIssue = useGetIssueApiV1IssuesIssueIdGet;
export const useCreateIssue = useCreateIssueApiV1IssuesPost;
export const useUpdateIssue = useUpdateIssueApiV1IssuesIssueIdPatch;
export const useIssueComments =
  useListIssueCommentsApiV1IssuesIssueIdCommentsGet;
export const useCreateIssueComment =
  useCreateIssueCommentApiV1IssuesIssueIdCommentsPost;
export const useIssueWatchers =
  useListIssueWatchersApiV1IssuesIssueIdWatchersGet;
export const useWatchIssue = useAddIssueWatcherApiV1IssuesIssueIdWatchPost;
export const useUnwatchIssue =
  useRemoveIssueWatcherApiV1IssuesIssueIdWatchDelete;
export const useIssueInvestigationRuns =
  useListInvestigationRunsApiV1IssuesIssueIdInvestigationRunsGet;
export const useSpawnInvestigation =
  useSpawnInvestigationApiV1IssuesIssueIdInvestigationRunsPost;

// Helper hook to invalidate issue queries
export function useInvalidateIssues() {
  const queryClient = useQueryClient();

  return {
    invalidateList: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.all }),
    invalidateDetail: (id: string) =>
      queryClient.invalidateQueries({ queryKey: queryKeys.issues.detail(id) }),
    invalidateComments: (id: string) =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.issues.comments(id),
      }),
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
