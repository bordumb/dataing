# fn-2.3 Frontend: NotificationProvider + sidebar badge

## Description

Create NotificationProvider context for global unread count with SSE subscription and org-switch handling.

### NotificationProvider

Create `frontend/src/lib/notifications/context.tsx`:

```typescript
import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useJwtAuth } from '@/lib/auth/jwt-context'
import { queryKeys } from '@/lib/api/query-keys'

interface NotificationContextValue {
  unreadCount: number
  isConnected: boolean
}

const NotificationContext = createContext<NotificationContextValue | null>(null)

export function NotificationProvider({ children }: { children: React.ReactNode }) {
  const { accessToken, org } = useJwtAuth()
  const queryClient = useQueryClient()
  const [isConnected, setIsConnected] = useState(false)
  const seenIds = useRef(new Set<string>())
  const eventSourceRef = useRef<EventSource | null>(null)

  // Fetch unread count (fallback polling)
  const { data } = useQuery({
    queryKey: queryKeys.notifications.unreadCount,
    queryFn: () => fetch('/api/v1/notifications/unread-count', {
      headers: { Authorization: `Bearer ${accessToken}` }
    }).then(r => r.json()),
    enabled: !!accessToken,
    refetchInterval: 30000,
  })

  // SSE subscription - reconnects on org change
  useEffect(() => {
    if (!accessToken) return

    let retryCount = 0
    let timeoutId: number

    function connect() {
      // Close existing connection
      eventSourceRef.current?.close()

      const es = new EventSource(`/api/v1/notifications/stream?token=${accessToken}`)
      eventSourceRef.current = es

      es.onopen = () => {
        setIsConnected(true)
        retryCount = 0
      }

      es.addEventListener('notification', (event) => {
        const notification = JSON.parse(event.data)
        // Dedupe via event ID
        if (!seenIds.current.has(event.lastEventId)) {
          seenIds.current.add(event.lastEventId)
          queryClient.invalidateQueries({ queryKey: queryKeys.notifications.all })
          // Toast logic in separate hook
        }
      })

      es.onerror = () => {
        setIsConnected(false)
        es.close()
        // Exponential backoff with jitter
        const delay = Math.min(1000 * Math.pow(2, retryCount) + Math.random() * 1000, 30000)
        retryCount++
        timeoutId = window.setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      eventSourceRef.current?.close()
      clearTimeout(timeoutId)
    }
  }, [accessToken, org?.id, queryClient])  // Reconnect on org change

  const value = useMemo(() => ({
    unreadCount: data?.count ?? 0,
    isConnected,
  }), [data, isConnected])

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  )
}

export function useNotifications() {
  const ctx = useContext(NotificationContext)
  if (!ctx) throw new Error('useNotifications must be used within NotificationProvider')
  return ctx
}
```

### Query Keys

Add to `frontend/src/lib/api/query-keys.ts`:

```typescript
notifications: {
  all: ['notifications'] as const,
  list: (filters?: { unread_only?: boolean }) => ['notifications', 'list', filters] as const,
  unreadCount: ['notifications', 'unreadCount'] as const,
}
```

### Sidebar Badge

Update `frontend/src/components/layout/app-sidebar.tsx`:

```typescript
import { useNotifications } from '@/lib/notifications/context'
import { Badge } from '@/components/ui/badge'

// In the notifications nav item:
const { unreadCount } = useNotifications()

<SidebarMenuButton asChild>
  <Link to="/notifications">
    <Bell className="size-4" />
    <span>Notifications</span>
    {unreadCount > 0 && (
      <Badge variant="destructive" className="ml-auto">
        {unreadCount > 99 ? '99+' : unreadCount}
      </Badge>
    )}
  </Link>
</SidebarMenuButton>
```

### App.tsx Integration

Add provider under auth:

```typescript
// In frontend/src/App.tsx
<JwtAuthProvider>
  <NotificationProvider>
    {/* rest of app */}
  </NotificationProvider>
</JwtAuthProvider>
```

### Files to Create/Modify

- Create: `frontend/src/lib/notifications/context.tsx`
- Create: `frontend/src/lib/notifications/index.ts`
- Modify: `frontend/src/App.tsx` (wrap with NotificationProvider)
- Modify: `frontend/src/components/layout/app-sidebar.tsx` (add badge)
- Modify: `frontend/src/lib/api/query-keys.ts` (add notification keys)

## Acceptance

- [ ] NotificationProvider wraps app under JwtAuthProvider
- [ ] `useNotifications()` hook returns `{ unreadCount, isConnected }`
- [ ] Sidebar shows red badge when unreadCount > 0
- [ ] Badge shows "99+" for counts > 99
- [ ] Badge disappears when count is 0
- [ ] Badge updates in real-time when new notification arrives via SSE
- [ ] Badge updates after marking notifications as read
- [ ] SSE reconnects with exponential backoff on disconnect
- [ ] SSE reconnects when user switches org
- [ ] No console errors when auth is not present

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
