/**
 * React hook for managing assistant chat state.
 *
 * Handles session management, message history, and SSE streaming.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { useJwtAuth } from "@/lib/auth/jwt-context";

// Storage key for session persistence
const SESSION_STORAGE_KEY = "dataing_assistant_session_id";

export interface AssistantMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  toolCalls?: { name: string; arguments: Record<string, unknown> }[];
  createdAt: Date;
  isStreaming?: boolean;
}

export interface AssistantSession {
  id: string;
  investigationId: string;
  createdAt: Date;
}

interface UseAssistantOptions {
  onError?: (error: string) => void;
}

interface UseAssistantReturn {
  messages: AssistantMessage[];
  session: AssistantSession | null;
  isLoading: boolean;
  isStreaming: boolean;
  error: string | null;
  sendMessage: (content: string) => Promise<void>;
  createSession: () => Promise<void>;
  clearSession: () => void;
}

export function useAssistant(
  options: UseAssistantOptions = {},
): UseAssistantReturn {
  const { onError } = options;
  const { accessToken } = useJwtAuth();
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [session, setSession] = useState<AssistantSession | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Load session from server
  const loadSession = useCallback(
    async (sessionId: string) => {
      try {
        setIsLoading(true);
        const response = await fetch(`/api/assistant/sessions/${sessionId}`, {
          headers: {
            Authorization: `Bearer ${accessToken}`,
          },
        });

        if (!response.ok) {
          // Session not found or invalid, clear storage
          localStorage.removeItem(SESSION_STORAGE_KEY);
          return;
        }

        const data = await response.json();
        setSession({
          id: data.id,
          investigationId: data.investigation_id,
          createdAt: new Date(data.created_at),
        });

        // Load messages
        setMessages(
          data.messages.map(
            (msg: {
              id: string;
              role: string;
              content: string;
              tool_calls?: {
                name: string;
                arguments: Record<string, unknown>;
              }[];
              created_at: string;
            }) => ({
              id: msg.id,
              role: msg.role as AssistantMessage["role"],
              content: msg.content,
              toolCalls: msg.tool_calls,
              createdAt: new Date(msg.created_at),
            }),
          ),
        );
      } catch (err) {
        console.error("Failed to load session:", err);
        localStorage.removeItem(SESSION_STORAGE_KEY);
      } finally {
        setIsLoading(false);
      }
    },
    [accessToken],
  );

  // Load session from storage on mount
  useEffect(() => {
    const storedSessionId = localStorage.getItem(SESSION_STORAGE_KEY);
    if (storedSessionId && accessToken) {
      loadSession(storedSessionId);
    }
  }, [accessToken, loadSession]);

  // Cleanup EventSource on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  const createSession = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const response = await fetch("/api/assistant/sessions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Failed to create session");
      }

      const data = await response.json();
      const newSession: AssistantSession = {
        id: data.session_id,
        investigationId: data.investigation_id,
        createdAt: new Date(data.created_at),
      };

      setSession(newSession);
      setMessages([]);
      localStorage.setItem(SESSION_STORAGE_KEY, newSession.id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown error";
      setError(message);
      onError?.(message);
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, onError]);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!session) {
        setError("No active session");
        return;
      }

      try {
        setIsStreaming(true);
        setError(null);

        // Add user message immediately
        const userMessage: AssistantMessage = {
          id: `temp-${Date.now()}`,
          role: "user",
          content,
          createdAt: new Date(),
        };
        setMessages((prev) => [...prev, userMessage]);

        // Send message to API
        const response = await fetch(
          `/api/assistant/sessions/${session.id}/messages`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${accessToken}`,
            },
            body: JSON.stringify({ content }),
          },
        );

        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || "Failed to send message");
        }

        // Add assistant message placeholder
        const assistantMessage: AssistantMessage = {
          id: `streaming-${Date.now()}`,
          role: "assistant",
          content: "",
          createdAt: new Date(),
          isStreaming: true,
        };
        setMessages((prev) => [...prev, assistantMessage]);

        // Connect to SSE stream
        const eventSource = new EventSource(
          `/api/assistant/sessions/${session.id}/stream?token=${accessToken}`,
        );
        eventSourceRef.current = eventSource;

        eventSource.addEventListener("text", (event: MessageEvent) => {
          const data = JSON.parse(event.data);
          setMessages((prev) => {
            const updated = [...prev];
            const lastMsg = updated[updated.length - 1];
            if (lastMsg && lastMsg.isStreaming) {
              lastMsg.content += data.text;
            }
            return updated;
          });
        });

        eventSource.addEventListener("tool_call", (event: MessageEvent) => {
          const data = JSON.parse(event.data);
          setMessages((prev) => {
            const updated = [...prev];
            const lastMsg = updated[updated.length - 1];
            if (lastMsg && lastMsg.isStreaming) {
              lastMsg.toolCalls = [
                ...(lastMsg.toolCalls || []),
                { name: data.tool, arguments: data.arguments },
              ];
            }
            return updated;
          });
        });

        eventSource.addEventListener("complete", () => {
          setMessages((prev) => {
            const updated = [...prev];
            const lastMsg = updated[updated.length - 1];
            if (lastMsg) {
              lastMsg.isStreaming = false;
            }
            return updated;
          });
          setIsStreaming(false);
          eventSource.close();
          eventSourceRef.current = null;
        });

        eventSource.addEventListener("error", (event: MessageEvent) => {
          const data = JSON.parse(event.data);
          setError(data.error || "Stream error");
          setIsStreaming(false);
          eventSource.close();
          eventSourceRef.current = null;

          // Remove streaming message
          setMessages((prev) => prev.filter((msg) => !msg.isStreaming));
        });

        eventSource.onerror = () => {
          setError("Connection lost");
          setIsStreaming(false);
          eventSource.close();
          eventSourceRef.current = null;
        };
      } catch (err) {
        const message = err instanceof Error ? err.message : "Unknown error";
        setError(message);
        onError?.(message);
        setIsStreaming(false);

        // Remove the optimistic user message on error
        setMessages((prev) => prev.slice(0, -1));
      }
    },
    [session, accessToken, onError],
  );

  const clearSession = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setSession(null);
    setMessages([]);
    setError(null);
    localStorage.removeItem(SESSION_STORAGE_KEY);
  }, []);

  return {
    messages,
    session,
    isLoading,
    isStreaming,
    error,
    sendMessage,
    createSession,
    clearSession,
  };
}
