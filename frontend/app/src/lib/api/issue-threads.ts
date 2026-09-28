/**
 * Issue threads: the shared thread and scratch chats on an issue.
 *
 * Hand-written against routes/issue_threads.py (spec 0001 §7.1). The committed
 * openapi.json predates these routes, so they are not in the orval output.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";

import { customInstance } from "./client";
import { queryKeys } from "./query-keys";

// ============================================================================
// Types
// ============================================================================

export type ThreadKind = "shared" | "scratch";

export interface IssueThread {
  id: string;
  issue_id: string;
  kind: ThreadKind;
  owner_user_id: string | null;
  title: string | null;
  created_at: string;
}

export interface IssueThreadList {
  items: IssueThread[];
}

export type MessageAuthorKind = "user" | "agent" | "system";

export type MessageKind =
  | "comment"
  | "agent_reply"
  | "brief"
  | "steer"
  | "investigation"
  | "event"
  | "published";

export type MessageStatus =
  | "queued"
  | "streaming"
  | "complete"
  | "error"
  | "cancelled";

export interface ToolCall {
  id: string;
  tool: string;
  input: Record<string, unknown>;
  status: "ok" | "error";
  summary: string;
  query_result_id: string | null;
  error_code: string | null;
}

export interface SteerProposal {
  run_id: string | null;
  kind: string;
  text: string;
  hypothesis_id: string | null;
}

/** Payload of an agent_reply; other kinds carry their own shapes. */
export interface AgentReplyPayload {
  tool_calls?: ToolCall[];
  proposals?: SteerProposal[];
  usage?: Record<string, unknown>;
  error?: string;
}

export interface ThreadMessage {
  id: string;
  thread_id: string;
  seq: number;
  rev: number;
  author_kind: MessageAuthorKind;
  author_user_id: string | null;
  requested_by_user_id: string | null;
  request_message_id: string | null;
  kind: MessageKind;
  body_md: string;
  payload: Record<string, unknown>;
  status: MessageStatus;
  asks_agent: boolean;
  reply_to_id: string | null;
  created_at: string;
  updated_at: string;
  edited_at: string | null;
  deleted_at: string | null;
}

export interface ThreadMessageList {
  items: ThreadMessage[];
}

export interface QueryResultColumn {
  name: string;
  [key: string]: unknown;
}

export interface QueryResult {
  id: string;
  message_id: string;
  tool_call_id: string;
  sql: string;
  dialect: string;
  columns: QueryResultColumn[];
  rows: Record<string, unknown>[];
  row_count: number;
  truncated: boolean;
  duration_ms: number;
  error: string | null;
  created_at: string;
}

export interface PublishBody {
  message_ids: string[];
  note?: string | null;
}

export interface PostMessageBody {
  body_md: string;
  ask_agent?: boolean;
  reply_to_id?: string | null;
}

// ============================================================================
// Requests
// ============================================================================

const MESSAGE_PAGE_SIZE = 500;

const threadsUrl = (issueId: string) => `/api/v1/issues/${issueId}/threads`;
const messagesUrl = (issueId: string, threadId: string) =>
  `${threadsUrl(issueId)}/${threadId}/messages`;

export function listThreads(issueId: string, signal?: AbortSignal) {
  return customInstance<IssueThreadList>({
    url: threadsUrl(issueId),
    method: "GET",
    signal,
  });
}

/** Every message in a thread, oldest first, following seq pages. */
export async function listAllMessages(
  issueId: string,
  threadId: string,
  signal?: AbortSignal,
): Promise<ThreadMessage[]> {
  const items: ThreadMessage[] = [];
  let afterSeq = 0;
  for (;;) {
    const page = await customInstance<ThreadMessageList>({
      url: messagesUrl(issueId, threadId),
      method: "GET",
      params: { after_seq: afterSeq, limit: MESSAGE_PAGE_SIZE },
      signal,
    });
    items.push(...page.items);
    if (page.items.length < MESSAGE_PAGE_SIZE) return items;
    afterSeq = page.items[page.items.length - 1].seq;
  }
}

export function postMessage(
  issueId: string,
  threadId: string,
  body: PostMessageBody,
) {
  return customInstance<ThreadMessage>({
    url: messagesUrl(issueId, threadId),
    method: "POST",
    data: body,
  });
}

export function editMessage(
  issueId: string,
  threadId: string,
  messageId: string,
  bodyMd: string,
) {
  return customInstance<ThreadMessage>({
    url: `${messagesUrl(issueId, threadId)}/${messageId}`,
    method: "PATCH",
    data: { body_md: bodyMd },
  });
}

export function deleteMessage(
  issueId: string,
  threadId: string,
  messageId: string,
) {
  return customInstance<void>({
    url: `${messagesUrl(issueId, threadId)}/${messageId}`,
    method: "DELETE",
  });
}

export function cancelAnswer(
  issueId: string,
  threadId: string,
  messageId: string,
) {
  return customInstance<ThreadMessage>({
    url: `${messagesUrl(issueId, threadId)}/${messageId}/cancel`,
    method: "POST",
  });
}

export function getQueryResult(
  issueId: string,
  threadId: string,
  resultId: string,
  signal?: AbortSignal,
) {
  return customInstance<QueryResult>({
    url: `${threadsUrl(issueId)}/${threadId}/query-results/${resultId}`,
    method: "GET",
    signal,
  });
}

/** Create a private scratch chat on the issue. */
export function createScratchThread(issueId: string, title: string | null) {
  return customInstance<IssueThread>({
    url: threadsUrl(issueId),
    method: "POST",
    data: { title },
  });
}

/**
 * Rename one of the caller's scratch chats.
 *
 * Needs PATCH /issues/{issue_id}/threads/{thread_id} on the server, which
 * routes/issue_threads.py doesn't have yet; until it does this fails with 405.
 */
export function renameThread(issueId: string, threadId: string, title: string) {
  return customInstance<IssueThread>({
    url: `${threadsUrl(issueId)}/${threadId}`,
    method: "PATCH",
    data: { title },
  });
}

/** Delete one of the caller's scratch chats. */
export function deleteThread(issueId: string, threadId: string) {
  return customInstance<void>({
    url: `${threadsUrl(issueId)}/${threadId}`,
    method: "DELETE",
  });
}

/**
 * Copy selected scratch-chat messages into one `published` message in the
 * shared thread, with their query snapshots.
 */
export function publishFromScratch(
  issueId: string,
  threadId: string,
  body: PublishBody,
) {
  return customInstance<ThreadMessage>({
    url: `${threadsUrl(issueId)}/${threadId}/publish`,
    method: "POST",
    data: body,
  });
}

/**
 * Ask the agent to draft an investigation brief from a thread. The draft
 * streams into the returned `brief` message; its payload.brief holds the
 * draft once the message is complete.
 */
export function requestBriefDraft(issueId: string, threadId: string) {
  return customInstance<ThreadMessage>({
    url: `${threadsUrl(issueId)}/${threadId}/brief-drafts`,
    method: "POST",
  });
}

/** SSE URL for a thread. EventSource can't send headers, so the JWT rides along. */
export function threadStreamUrl(
  issueId: string,
  threadId: string,
  afterRev: number,
  token: string | null,
): string {
  const base = import.meta.env.VITE_API_URL || "";
  const params = new URLSearchParams({ after: String(afterRev) });
  if (token) params.set("token", token);
  return `${base}${threadsUrl(issueId)}/${threadId}/stream?${params}`;
}

// ============================================================================
// Cache merging
// ============================================================================

/**
 * Merge incoming message versions into a list, keeping the highest rev per id
 * and ordering by seq. Stream events, refetches and mutation responses can
 * arrive in any order; an older rev never overwrites a newer one.
 */
export function mergeMessages(
  current: ThreadMessage[],
  incoming: ThreadMessage[],
): ThreadMessage[] {
  if (incoming.length === 0) return current;
  const byId = new Map(current.map((m) => [m.id, m]));
  let changed = false;
  for (const message of incoming) {
    const existing = byId.get(message.id);
    if (existing && existing.rev >= message.rev) continue;
    byId.set(message.id, message);
    changed = true;
  }
  if (!changed) return current;
  return [...byId.values()].sort((a, b) => a.seq - b.seq);
}

export function maxRev(messages: ThreadMessage[] | undefined): number {
  return (messages ?? []).reduce((max, m) => Math.max(max, m.rev), 0);
}

/** Merge message versions into the cached thread. */
export function mergeIntoCache(
  queryClient: QueryClient,
  issueId: string,
  threadId: string,
  incoming: ThreadMessage[],
): void {
  queryClient.setQueryData<ThreadMessage[]>(
    queryKeys.issueThreads.messages(issueId, threadId),
    (current) => mergeMessages(current ?? [], incoming),
  );
}

// ============================================================================
// Hooks
// ============================================================================

export function useIssueThreads(issueId: string) {
  return useQuery({
    queryKey: queryKeys.issueThreads.list(issueId),
    queryFn: ({ signal }) => listThreads(issueId, signal),
    enabled: !!issueId,
  });
}

/**
 * A thread's messages. The stream keeps this cache current; a refetch merges
 * by rev so it never rolls back a newer streamed version.
 */
export function useThreadMessages(issueId: string, threadId: string | null) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: queryKeys.issueThreads.messages(issueId, threadId ?? ""),
    queryFn: async ({ signal }) => {
      const fresh = await listAllMessages(issueId, threadId!, signal);
      const cached = queryClient.getQueryData<ThreadMessage[]>(
        queryKeys.issueThreads.messages(issueId, threadId!),
      );
      return mergeMessages(cached ?? [], fresh);
    },
    enabled: !!issueId && !!threadId,
  });
}

export function useQueryResult(
  issueId: string,
  threadId: string,
  resultId: string | null,
) {
  return useQuery({
    queryKey: queryKeys.issueThreads.queryResult(
      issueId,
      threadId,
      resultId ?? "",
    ),
    queryFn: ({ signal }) =>
      getQueryResult(issueId, threadId, resultId!, signal),
    enabled: !!resultId,
    // Snapshots never change once written.
    staleTime: Infinity,
  });
}

export function usePostMessage(issueId: string, threadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PostMessageBody) => postMessage(issueId, threadId, body),
    onSuccess: (message) =>
      mergeIntoCache(queryClient, issueId, threadId, [message]),
  });
}

export function useCreateScratchThread(issueId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (title: string | null) => createScratchThread(issueId, title),
    onSuccess: (thread) =>
      queryClient.setQueryData<IssueThreadList>(
        queryKeys.issueThreads.list(issueId),
        (current) => ({ items: [...(current?.items ?? []), thread] }),
      ),
  });
}

export function useRenameThread(issueId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ threadId, title }: { threadId: string; title: string }) =>
      renameThread(issueId, threadId, title),
    onSuccess: (thread) =>
      queryClient.setQueryData<IssueThreadList>(
        queryKeys.issueThreads.list(issueId),
        (current) =>
          current && {
            items: current.items.map((t) => (t.id === thread.id ? thread : t)),
          },
      ),
  });
}

export function useDeleteThread(issueId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (threadId: string) => deleteThread(issueId, threadId),
    onSuccess: (_void, threadId) => {
      queryClient.setQueryData<IssueThreadList>(
        queryKeys.issueThreads.list(issueId),
        (current) =>
          current && {
            items: current.items.filter((t) => t.id !== threadId),
          },
      );
      queryClient.removeQueries({
        queryKey: queryKeys.issueThreads.messages(issueId, threadId),
      });
    },
  });
}

export function usePublishFromScratch(issueId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ threadId, body }: { threadId: string; body: PublishBody }) =>
      publishFromScratch(issueId, threadId, body),
    // The published message lands in the shared thread.
    onSuccess: (message) =>
      mergeIntoCache(queryClient, issueId, message.thread_id, [message]),
  });
}

export function useRequestBriefDraft(issueId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (threadId: string) => requestBriefDraft(issueId, threadId),
    onSuccess: (message) =>
      mergeIntoCache(queryClient, issueId, message.thread_id, [message]),
  });
}

export function useEditMessage(issueId: string, threadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      messageId,
      bodyMd,
    }: {
      messageId: string;
      bodyMd: string;
    }) => editMessage(issueId, threadId, messageId, bodyMd),
    onSuccess: (message) =>
      mergeIntoCache(queryClient, issueId, threadId, [message]),
  });
}

export function useDeleteMessage(issueId: string, threadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) =>
      deleteMessage(issueId, threadId, messageId),
    // The stream delivers the tombstone; refetch in case it is disconnected.
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: queryKeys.issueThreads.messages(issueId, threadId),
      }),
  });
}

export function useCancelAnswer(issueId: string, threadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (messageId: string) =>
      cancelAnswer(issueId, threadId, messageId),
    onSuccess: (message) =>
      mergeIntoCache(queryClient, issueId, threadId, [message]),
  });
}
