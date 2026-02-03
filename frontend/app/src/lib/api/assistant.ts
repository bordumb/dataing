/**
 * API client wrapper for Dataing Assistant.
 * Re-exports generated hooks with cleaner names.
 */

import { useQueryClient } from "@tanstack/react-query";
import {
  useCreateSessionApiV1AssistantSessionsPost,
  useListSessionsApiV1AssistantSessionsGet,
  useGetSessionApiV1AssistantSessionsSessionIdGet,
  useDeleteSessionApiV1AssistantSessionsSessionIdDelete,
  useSendMessageApiV1AssistantSessionsSessionIdMessagesPost,
  useExportSessionApiV1AssistantSessionsSessionIdExportPost,
  createSessionApiV1AssistantSessionsPost,
  getSessionApiV1AssistantSessionsSessionIdGet,
  sendMessageApiV1AssistantSessionsSessionIdMessagesPost,
} from "./generated/assistant/assistant";

// Re-export types from model
export type {
  CreateSessionRequest,
  CreateSessionResponse,
  ListSessionsResponse,
  SessionDetailResponse,
  SessionSummary,
  SendMessageRequest,
  SendMessageResponse,
  MessageResponse,
  ExportFormat,
} from "./model";

// Re-export hooks with cleaner names
export const useCreateAssistantSession =
  useCreateSessionApiV1AssistantSessionsPost;
export const useAssistantSessions = useListSessionsApiV1AssistantSessionsGet;
export const useAssistantSession =
  useGetSessionApiV1AssistantSessionsSessionIdGet;
export const useDeleteAssistantSession =
  useDeleteSessionApiV1AssistantSessionsSessionIdDelete;
export const useSendAssistantMessage =
  useSendMessageApiV1AssistantSessionsSessionIdMessagesPost;
export const useExportAssistantSession =
  useExportSessionApiV1AssistantSessionsSessionIdExportPost;

// Non-hook API functions for imperative use
export const assistantApi = {
  createSession: createSessionApiV1AssistantSessionsPost,
  getSession: getSessionApiV1AssistantSessionsSessionIdGet,
  sendMessage: sendMessageApiV1AssistantSessionsSessionIdMessagesPost,
  getStreamUrl: (sessionId: string, token?: string) =>
    `/api/v1/assistant/sessions/${sessionId}/stream${token ? `?token=${token}` : ""}`,
};

// Helper hook to invalidate assistant queries
export function useInvalidateAssistant() {
  const queryClient = useQueryClient();

  return {
    invalidateSessions: () =>
      queryClient.invalidateQueries({
        queryKey: ["/api/v1/assistant/sessions"],
      }),
    invalidateSession: (sessionId: string) =>
      queryClient.invalidateQueries({
        queryKey: [`/api/v1/assistant/sessions/${sessionId}`],
      }),
  };
}
