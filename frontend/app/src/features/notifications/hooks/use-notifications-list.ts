/**
 * Hook for fetching notifications list from API.
 */

import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '@/lib/api/query-keys'
import { useJwtAuth } from '@/lib/auth/jwt-context'
import type { NotificationData } from '../components/notification-card'

interface NotificationListResponse {
  items: NotificationData[]
  next_cursor: string | null
  has_more: boolean
}

interface UseNotificationsListOptions {
  unreadOnly?: boolean
  limit?: number
}

/**
 * Hook to fetch paginated notifications list.
 */
export function useNotificationsList(options: UseNotificationsListOptions = {}) {
  const { accessToken, isAuthenticated } = useJwtAuth()
  const { unreadOnly = false, limit = 50 } = options

  return useQuery<NotificationListResponse>({
    queryKey: queryKeys.notifications.list({ unread_only: unreadOnly }),
    queryFn: async () => {
      const params = new URLSearchParams({
        limit: limit.toString(),
      })
      if (unreadOnly) {
        params.set('unread_only', 'true')
      }

      const res = await fetch(`/api/v1/notifications?${params}`, {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      })

      if (!res.ok) {
        throw new Error('Failed to fetch notifications')
      }

      return res.json()
    },
    enabled: !!accessToken && isAuthenticated,
    staleTime: 30000, // 30 seconds
  })
}

/**
 * Hook to fetch unread count.
 */
export function useUnreadCount() {
  const { accessToken, isAuthenticated } = useJwtAuth()

  return useQuery<{ count: number }>({
    queryKey: queryKeys.notifications.unreadCount,
    queryFn: async () => {
      const res = await fetch('/api/v1/notifications/unread-count', {
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      })

      if (!res.ok) {
        throw new Error('Failed to fetch unread count')
      }

      return res.json()
    },
    enabled: !!accessToken && isAuthenticated,
    staleTime: 30000, // 30 seconds
  })
}
