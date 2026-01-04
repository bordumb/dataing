"use client";

/**
 * Enhanced WebSocket hook with subscription management.
 *
 * Features:
 * - Automatic reconnection with exponential backoff
 * - Channel subscription/unsubscription
 * - Message type filtering
 * - Connection state machine
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "next-auth/react";

export type WebSocketStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "error";

export interface WebSocketMessage {
  type: string;
  channel?: string;
  event_type?: string;
  payload?: Record<string, unknown>;
  timestamp?: string;
  [key: string]: unknown;
}

export interface UseWebSocketOptions {
  url?: string;
  autoConnect?: boolean;
  reconnectAttempts?: number;
  reconnectInterval?: number;
  onMessage?: (message: WebSocketMessage) => void;
  onStatusChange?: (status: WebSocketStatus) => void;
}

export interface UseWebSocketReturn {
  status: WebSocketStatus;
  messages: WebSocketMessage[];
  subscribe: (channel: string) => void;
  unsubscribe: (channel: string) => void;
  send: (data: unknown) => void;
  connect: () => void;
  disconnect: () => void;
  isConnected: boolean;
}

const DEFAULT_WS_URL =
  process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";
const MAX_RECONNECT_ATTEMPTS = 5;
const BASE_RECONNECT_INTERVAL = 1000;
const MAX_MESSAGES = 100;

export function useWebSocket(
  options: UseWebSocketOptions = {}
): UseWebSocketReturn {
  const {
    url = DEFAULT_WS_URL,
    autoConnect = true,
    reconnectAttempts = MAX_RECONNECT_ATTEMPTS,
    reconnectInterval = BASE_RECONNECT_INTERVAL,
    onMessage,
    onStatusChange,
  } = options;

  const { data: session } = useSession();
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const subscribedChannelsRef = useRef<Set<string>>(new Set());
  const pendingSubscriptionsRef = useRef<Set<string>>(new Set());

  const [status, setStatus] = useState<WebSocketStatus>("idle");
  const [messages, setMessages] = useState<WebSocketMessage[]>([]);

  const updateStatus = useCallback(
    (newStatus: WebSocketStatus) => {
      setStatus(newStatus);
      onStatusChange?.(newStatus);
    },
    [onStatusChange]
  );

  const connect = useCallback(() => {
    // In development without auth, allow connection anyway
    const token = session?.accessToken || "dev-token";

    if (socketRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    updateStatus("connecting");

    try {
      const wsUrl = new URL(url);
      wsUrl.searchParams.set("token", token);

      const socket = new WebSocket(wsUrl.toString());
      socketRef.current = socket;

      socket.onopen = () => {
        console.log("WebSocket connected");
        updateStatus("connected");
        reconnectCountRef.current = 0;

        // Subscribe to pending channels
        pendingSubscriptionsRef.current.forEach((channel) => {
          socket.send(JSON.stringify({ type: "subscribe", channel }));
        });
        pendingSubscriptionsRef.current.clear();

        // Resubscribe to previous channels
        subscribedChannelsRef.current.forEach((channel) => {
          socket.send(JSON.stringify({ type: "subscribe", channel }));
        });
      };

      socket.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);

          // Handle acknowledgments
          if (message.type === "ack") {
            console.debug(
              `WebSocket ack: ${message.action} ${message.channel}`
            );
            if (message.action === "subscribe" && message.success && message.channel) {
              subscribedChannelsRef.current.add(message.channel as string);
            }
            return;
          }

          // Handle heartbeats silently
          if (message.type === "heartbeat") {
            return;
          }

          // Store message and notify
          setMessages((prev) => [...prev.slice(-MAX_MESSAGES + 1), message]);
          onMessage?.(message);
        } catch (e) {
          console.error("WebSocket message parse error:", e);
        }
      };

      socket.onerror = (error) => {
        console.error("WebSocket error:", error);
        updateStatus("error");
      };

      socket.onclose = (event) => {
        console.log(`WebSocket closed: ${event.code} ${event.reason}`);
        socketRef.current = null;

        // Attempt reconnection for non-intentional closes
        if (
          event.code !== 1000 &&
          reconnectCountRef.current < reconnectAttempts
        ) {
          updateStatus("reconnecting");
          const delay =
            reconnectInterval * Math.pow(2, reconnectCountRef.current);
          reconnectCountRef.current++;

          reconnectTimeoutRef.current = setTimeout(() => {
            console.log(
              `WebSocket reconnecting (attempt ${reconnectCountRef.current})`
            );
            connect();
          }, delay);
        } else {
          updateStatus("idle");
        }
      };
    } catch (e) {
      console.error("WebSocket connection error:", e);
      updateStatus("error");
    }
  }, [
    url,
    session?.accessToken,
    reconnectAttempts,
    reconnectInterval,
    updateStatus,
    onMessage,
  ]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (socketRef.current) {
      socketRef.current.close(1000, "Client disconnect");
      socketRef.current = null;
    }

    updateStatus("idle");
  }, [updateStatus]);

  const subscribe = useCallback((channel: string) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: "subscribe", channel }));
    } else {
      // Queue for when connected
      pendingSubscriptionsRef.current.add(channel);
    }
  }, []);

  const unsubscribe = useCallback((channel: string) => {
    subscribedChannelsRef.current.delete(channel);
    pendingSubscriptionsRef.current.delete(channel);

    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type: "unsubscribe", channel }));
    }
  }, []);

  const send = useCallback((data: unknown) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(data));
    } else {
      console.warn("WebSocket: Cannot send, not connected");
    }
  }, []);

  // Auto-connect on mount
  useEffect(() => {
    if (autoConnect) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  return {
    status,
    messages,
    subscribe,
    unsubscribe,
    send,
    connect,
    disconnect,
    isConnected: status === "connected",
  };
}

// Legacy export for backward compatibility
export default useWebSocket;
