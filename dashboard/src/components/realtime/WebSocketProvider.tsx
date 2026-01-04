"use client";

/**
 * WebSocket Provider for real-time updates.
 *
 * Provides a shared WebSocket connection to all components in the tree.
 * Components can subscribe to specific channels for filtered updates.
 */

import { createContext, useContext, useMemo, type ReactNode } from "react";
import {
  useWebSocket,
  type WebSocketMessage,
  type WebSocketStatus,
} from "@/lib/hooks/useWebSocket";

interface WebSocketContextValue {
  status: WebSocketStatus;
  messages: WebSocketMessage[];
  send: (payload: unknown) => void;
  subscribe: (channel: string) => void;
  unsubscribe: (channel: string) => void;
  isConnected: boolean;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

const DEFAULT_WS_URL =
  process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";

interface WebSocketProviderProps {
  children: ReactNode;
  url?: string;
  autoConnect?: boolean;
}

export function WebSocketProvider({
  children,
  url = DEFAULT_WS_URL,
  autoConnect = true,
}: WebSocketProviderProps) {
  const {
    status,
    messages,
    send,
    subscribe,
    unsubscribe,
    isConnected,
  } = useWebSocket({
    url,
    autoConnect,
  });

  const value = useMemo<WebSocketContextValue>(
    () => ({
      status,
      messages,
      send,
      subscribe,
      unsubscribe,
      isConnected,
    }),
    [status, messages, send, subscribe, unsubscribe, isConnected]
  );

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
}

/**
 * Hook to access the WebSocket context.
 *
 * Returns a fallback object if used outside of WebSocketProvider,
 * allowing components to gracefully degrade.
 */
export function useWebSocketContext(): WebSocketContextValue {
  const context = useContext(WebSocketContext);

  if (!context) {
    // Return a no-op fallback for use outside provider
    return {
      status: "idle",
      messages: [],
      send: () => undefined,
      subscribe: () => undefined,
      unsubscribe: () => undefined,
      isConnected: false,
    };
  }

  return context;
}

export default WebSocketProvider;
