/**
 * Hooks for marking notifications as read with optimistic updates.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { queryKeys } from "@/lib/api/query-keys";
import { useJwtAuth } from "@/lib/auth/jwt-context";
import type { NotificationData } from "../components/notification-card";

interface NotificationListData {
  items: NotificationData[];
  next_cursor: string | null;
  has_more: boolean;
}

interface UnreadCountData {
  count: number;
}

/**
 * Hook for marking a single notification as read with optimistic update.
 */
export function useMarkAsRead() {
  const queryClient = useQueryClient();
  const { accessToken } = useJwtAuth();

  return useMutation({
    mutationFn: async (id: string) => {
      const res = await fetch(`/api/v1/notifications/${id}/read`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });
      if (!res.ok) throw new Error("Failed to mark as read");
    },

    onMutate: async (id) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({
        queryKey: queryKeys.notifications.all,
      });

      // Snapshot current state
      const previousList = queryClient.getQueryData<NotificationListData>(
        queryKeys.notifications.list(),
      );
      const previousCount = queryClient.getQueryData<UnreadCountData>(
        queryKeys.notifications.unreadCount,
      );

      // Optimistically update list
      queryClient.setQueryData<NotificationListData>(
        queryKeys.notifications.list(),
        (old) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.map((n) =>
              n.id === id ? { ...n, read_at: new Date().toISOString() } : n,
            ),
          };
        },
      );

      // Optimistically decrement count
      queryClient.setQueryData<UnreadCountData>(
        queryKeys.notifications.unreadCount,
        (old) => ({
          count: Math.max(0, (old?.count ?? 1) - 1),
        }),
      );

      return { previousList, previousCount };
    },

    onError: (_err, _id, context) => {
      // Rollback on error
      if (context?.previousList) {
        queryClient.setQueryData(
          queryKeys.notifications.list(),
          context.previousList,
        );
      }
      if (context?.previousCount) {
        queryClient.setQueryData(
          queryKeys.notifications.unreadCount,
          context.previousCount,
        );
      }
      toast.error("Failed to mark notification as read");
    },

    onSettled: () => {
      // Sync with server
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all });
    },
  });
}

/**
 * Hook for marking all notifications as read with optimistic update.
 */
export function useMarkAllAsRead() {
  const queryClient = useQueryClient();
  const { accessToken } = useJwtAuth();

  return useMutation({
    mutationFn: async () => {
      const res = await fetch("/api/v1/notifications/read-all", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });
      if (!res.ok) throw new Error("Failed to mark all as read");
    },

    onMutate: async () => {
      await queryClient.cancelQueries({
        queryKey: queryKeys.notifications.all,
      });

      const previousList = queryClient.getQueryData<NotificationListData>(
        queryKeys.notifications.list(),
      );
      const previousCount = queryClient.getQueryData<UnreadCountData>(
        queryKeys.notifications.unreadCount,
      );

      // Mark all as read
      queryClient.setQueryData<NotificationListData>(
        queryKeys.notifications.list(),
        (old) => {
          if (!old) return old;
          return {
            ...old,
            items: old.items.map((n) => ({
              ...n,
              read_at: n.read_at || new Date().toISOString(),
            })),
          };
        },
      );
      queryClient.setQueryData<UnreadCountData>(
        queryKeys.notifications.unreadCount,
        { count: 0 },
      );

      return { previousList, previousCount };
    },

    onError: (_err, _vars, context) => {
      if (context?.previousList) {
        queryClient.setQueryData(
          queryKeys.notifications.list(),
          context.previousList,
        );
      }
      if (context?.previousCount) {
        queryClient.setQueryData(
          queryKeys.notifications.unreadCount,
          context.previousCount,
        );
      }
      toast.error("Failed to mark all as read");
    },

    onSuccess: () => {
      toast.success("All notifications marked as read");
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all });
    },
  });
}
