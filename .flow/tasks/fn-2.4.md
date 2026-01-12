# fn-2.4 Frontend: Interactive cards + optimistic updates

## Description

Refactor notifications page with interactive cards, optimistic mark-as-read, and toast integration.

### Remove Mock Data

Delete `MOCK_NOTIFICATIONS` from `frontend/src/features/notifications/notifications-page.tsx`.

### Notification Cards

Create `frontend/src/features/notifications/components/notification-card.tsx`:

```typescript
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Link } from 'react-router-dom'
import { cn } from '@/lib/utils'

interface NotificationCardProps {
  notification: {
    id: string
    type: string
    title: string
    body: string | null
    resource_kind: string | null
    resource_id: string | null
    severity: 'info' | 'warning' | 'error'
    created_at: string
    read_at: string | null
  }
  onMarkRead: (id: string) => void
}

export function NotificationCard({ notification, onMarkRead }: NotificationCardProps) {
  const isUnread = !notification.read_at

  // Build link to resource
  const resourceLink = notification.resource_kind === 'investigation' && notification.resource_id
    ? `/investigations/${notification.resource_id}`
    : null

  const handleClick = () => {
    if (isUnread) onMarkRead(notification.id)
  }

  // Polymorphic rendering based on type
  if (notification.type === 'approval_required') {
    return (
      <Card className={cn("p-4", isUnread && "border-l-4 border-l-primary")}>
        <div className="flex justify-between">
          <h4 className="font-semibold">{notification.title}</h4>
          <Badge variant="destructive">Action Required</Badge>
        </div>
        <p className="text-sm text-muted-foreground mt-1">{notification.body}</p>
        <div className="flex gap-2 mt-3">
          <Button size="sm">Approve</Button>
          <Button size="sm" variant="outline">Review</Button>
        </div>
      </Card>
    )
  }

  // Default card for investigation_completed/failed
  const content = (
    <Card
      className={cn(
        "p-4 cursor-pointer hover:bg-accent transition-colors",
        isUnread && "border-l-4 border-l-primary"
      )}
      onClick={handleClick}
    >
      <div className="flex justify-between items-start">
        <div>
          <h4 className="font-medium">{notification.title}</h4>
          {notification.body && (
            <p className="text-sm text-muted-foreground mt-1">{notification.body}</p>
          )}
        </div>
        {notification.severity === 'error' && (
          <Badge variant="destructive">Error</Badge>
        )}
      </div>
      <p className="text-xs text-muted-foreground mt-2">
        {new Date(notification.created_at).toLocaleString()}
      </p>
    </Card>
  )

  return resourceLink ? (
    <Link to={resourceLink} onClick={handleClick}>{content}</Link>
  ) : content
}
```

### Optimistic Mark-as-Read Hook

Create `frontend/src/features/notifications/hooks/use-mark-read.ts`:

```typescript
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { queryKeys } from '@/lib/api/query-keys'

export function useMarkAsRead() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (id: string) => {
      const res = await fetch(`/api/v1/notifications/${id}/read`, { method: 'PUT' })
      if (!res.ok) throw new Error('Failed to mark as read')
    },

    onMutate: async (id) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({ queryKey: queryKeys.notifications.all })

      // Snapshot current state
      const previousList = queryClient.getQueryData(queryKeys.notifications.list())
      const previousCount = queryClient.getQueryData(queryKeys.notifications.unreadCount)

      // Optimistically update list
      queryClient.setQueryData(queryKeys.notifications.list(), (old: any) => ({
        ...old,
        items: old?.items?.map((n: any) =>
          n.id === id ? { ...n, read_at: new Date().toISOString() } : n
        ),
      }))

      // Optimistically decrement count
      queryClient.setQueryData(queryKeys.notifications.unreadCount, (old: any) => ({
        count: Math.max(0, (old?.count ?? 1) - 1),
      }))

      return { previousList, previousCount }
    },

    onError: (err, id, context) => {
      // Rollback on error
      if (context?.previousList) {
        queryClient.setQueryData(queryKeys.notifications.list(), context.previousList)
      }
      if (context?.previousCount) {
        queryClient.setQueryData(queryKeys.notifications.unreadCount, context.previousCount)
      }
      toast.error('Failed to mark as read')
    },

    onSettled: () => {
      // Sync with server
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all })
    },
  })
}

export function useMarkAllAsRead() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/v1/notifications/read-all', { method: 'POST' })
      if (!res.ok) throw new Error('Failed to mark all as read')
    },

    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: queryKeys.notifications.all })
      const previousList = queryClient.getQueryData(queryKeys.notifications.list())
      const previousCount = queryClient.getQueryData(queryKeys.notifications.unreadCount)

      // Mark all as read
      queryClient.setQueryData(queryKeys.notifications.list(), (old: any) => ({
        ...old,
        items: old?.items?.map((n: any) => ({ ...n, read_at: new Date().toISOString() })),
      }))
      queryClient.setQueryData(queryKeys.notifications.unreadCount, { count: 0 })

      return { previousList, previousCount }
    },

    onError: (err, vars, context) => {
      if (context?.previousList) {
        queryClient.setQueryData(queryKeys.notifications.list(), context.previousList)
      }
      if (context?.previousCount) {
        queryClient.setQueryData(queryKeys.notifications.unreadCount, context.previousCount)
      }
      toast.error('Failed to mark all as read')
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all })
    },
  })
}
```

### Toast Integration

Add to NotificationProvider SSE handler or separate hook:

```typescript
// Rate-limited toast logic
const toastTimestamps = useRef<number[]>([])
const MAX_TOASTS_PER_10S = 3

function showRateLimitedToast(notification: Notification) {
  const now = Date.now()
  // Remove timestamps older than 10s
  toastTimestamps.current = toastTimestamps.current.filter(t => now - t < 10000)

  if (toastTimestamps.current.length < MAX_TOASTS_PER_10S) {
    toastTimestamps.current.push(now)
    toast(notification.title, { description: notification.body })
  } else if (toastTimestamps.current.length === MAX_TOASTS_PER_10S) {
    toast.info('Multiple notifications received')
  }
}
```

### Files to Create/Modify

- Create: `frontend/src/features/notifications/components/notification-card.tsx`
- Create: `frontend/src/features/notifications/hooks/use-mark-read.ts`
- Create: `frontend/src/features/notifications/hooks/use-notifications-list.ts`
- Rewrite: `frontend/src/features/notifications/notifications-page.tsx`
- Modify: `frontend/src/lib/notifications/context.tsx` (add toast integration)

## Acceptance

- [ ] Notifications page fetches from `/api/v1/notifications`
- [ ] No MOCK_NOTIFICATIONS in codebase
- [ ] Cards render differently based on notification type
- [ ] `approval_required` cards show action buttons
- [ ] `investigation_completed/failed` cards link to investigation
- [ ] Unread notifications have visual indicator (left border)
- [ ] Clicking notification marks as read immediately (optimistic)
- [ ] If mark-as-read fails, UI reverts and shows error toast
- [ ] "Mark all as read" button works and updates badge
- [ ] Empty state shows "You're all caught up" message
- [ ] Loading state shows skeleton cards
- [ ] New notifications appear at top when SSE pushes
- [ ] Toast rate limiting: max 3 per 10s, then summary

## Done summary
## Summary

Implemented interactive notification cards with optimistic mark-as-read updates.

### Changes Made

1. **NotificationCard** (`frontend/src/features/notifications/components/notification-card.tsx`):
   - Polymorphic rendering based on notification type
   - Special handling for `approval_required` type with action buttons
   - Severity-based icons and colors
   - Relative timestamp display
   - Click to mark as read + navigate

2. **useMarkAsRead hooks** (`frontend/src/features/notifications/hooks/use-mark-read.ts`):
   - `useMarkAsRead` - marks single notification with optimistic update
   - `useMarkAllAsRead` - marks all notifications with optimistic update
   - Both include rollback on error and cache invalidation

3. **useNotificationsList hooks** (`frontend/src/features/notifications/hooks/use-notifications-list.ts`):
   - `useNotificationsList` - fetches paginated notifications
   - `useUnreadCount` - fetches unread count

4. **NotificationsPage** (`frontend/src/features/notifications/notifications-page.tsx`):
   - Removed MOCK_NOTIFICATIONS
   - Uses real API hooks
   - Loading skeleton states
   - Error handling
   - Tabs for All/Unread filtering

5. **NotificationProvider toast integration** (`frontend/src/lib/notifications/context.tsx`):
   - Shows toast on new SSE notifications
   - Severity-based toast types (error, warning, success, info)

### Verification

- ESLint: passed
- TypeScript: passed
## Evidence
- Commits:
- Tests: eslint_passed, typescript_passed
- PRs:
