/**
 * NotificationProvider context for global unread count with SSE subscription.
 *
 * Provides real-time notification updates via Server-Sent Events and
 * manages the global unread count displayed in the sidebar badge.
 */

import * as React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useJwtAuth } from "@/lib/auth/jwt-context";
import { queryKeys } from "@/lib/api/query-keys";

interface NotificationContextValue {
  unreadCount: number;
  isConnected: boolean;
}

const NotificationContext =
  React.createContext<NotificationContextValue | null>(null);

/**
 * Hook to access notification context.
 */
export function useNotifications() {
  const ctx = React.useContext(NotificationContext);
  if (!ctx) {
    throw new Error(
      "useNotifications must be used within NotificationProvider",
    );
  }
  return ctx;
}

/**
 * NotificationProvider component.
 *
 * Manages SSE connection for real-time notifications and provides
 * unread count to the rest of the app.
 */
export function NotificationProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const { accessToken, org, isAuthenticated } = useJwtAuth();
  const queryClient = useQueryClient();
  const [isConnected, setIsConnected] = React.useState(false);
  const [unreadCount, setUnreadCount] = React.useState(0);
  const seenIds = React.useRef(new Set<string>());
  const eventSourceRef = React.useRef<EventSource | null>(null);
  const retryTimeoutRef = React.useRef<number | null>(null);

  // Fetch initial unread count
  React.useEffect(() => {
    if (!accessToken || !isAuthenticated) {
      setUnreadCount(0);
      return;
    }

    async function fetchUnreadCount() {
      try {
        const response = await fetch("/api/v1/notifications/unread-count", {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (response.ok) {
          const data = await response.json();
          setUnreadCount(data.count ?? 0);
        }
      } catch (error) {
        console.error("Failed to fetch unread count:", error);
      }
    }

    fetchUnreadCount();

    // Poll every 30s as fallback
    const intervalId = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(intervalId);
  }, [accessToken, isAuthenticated]);

  // SSE subscription - reconnects on org change
  React.useEffect(() => {
    if (!accessToken || !isAuthenticated) {
      // Clean up any existing connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      setIsConnected(false);
      return;
    }

    let retryCount = 0;

    function connect() {
      // Close existing connection
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      // Clear any pending retry
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }

      const es = new EventSource(
        `/api/v1/notifications/stream?token=${accessToken}`,
      );
      eventSourceRef.current = es;

      es.onopen = () => {
        setIsConnected(true);
        retryCount = 0;
      };

      es.addEventListener("notification", (event: MessageEvent) => {
        try {
          const notification = JSON.parse(event.data);
          // Dedupe via event ID
          const eventId = event.lastEventId || notification.id;
          if (eventId && !seenIds.current.has(eventId)) {
            seenIds.current.add(eventId);
            // Increment unread count
            setUnreadCount((prev) => prev + 1);
            // Invalidate notification queries so lists refresh
            queryClient.invalidateQueries({
              queryKey: queryKeys.notifications.all,
            });
            // Show toast for new notification
            const severity = notification.severity as
              | "info"
              | "success"
              | "warning"
              | "error";
            if (severity === "error") {
              toast.error(notification.title, {
                description: notification.body,
              });
            } else if (severity === "warning") {
              toast.warning(notification.title, {
                description: notification.body,
              });
            } else if (severity === "success") {
              toast.success(notification.title, {
                description: notification.body,
              });
            } else {
              toast.info(notification.title, {
                description: notification.body,
              });
            }
          }
        } catch (error) {
          console.error("Failed to parse notification:", error);
        }
      });

      es.addEventListener("heartbeat", () => {
        // Heartbeat received, connection is healthy
        setIsConnected(true);
      });

      es.onerror = () => {
        setIsConnected(false);
        es.close();
        eventSourceRef.current = null;

        // Exponential backoff with jitter (max 30s)
        const delay = Math.min(
          1000 * Math.pow(2, retryCount) + Math.random() * 1000,
          30000,
        );
        retryCount++;
        retryTimeoutRef.current = window.setTimeout(connect, delay);
      };
    }

    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }
    };
  }, [accessToken, org?.id, isAuthenticated, queryClient]); // Reconnect on org change

  // Reset seen IDs when org changes
  React.useEffect(() => {
    seenIds.current.clear();
  }, [org?.id]);

  const value = React.useMemo(
    () => ({
      unreadCount,
      isConnected,
    }),
    [unreadCount, isConnected],
  );

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  );
}

/**
 * Hook to invalidate notification queries when marking notifications as read.
 */
export function useMarkNotificationRead() {
  const queryClient = useQueryClient();

  return React.useCallback(() => {
    // Invalidate queries to refetch fresh data
    queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all });
    queryClient.invalidateQueries({
      queryKey: queryKeys.notifications.unreadCount,
    });
  }, [queryClient]);
}
