import { Bell, Check, AlertTriangle, Info, CheckCircle, XCircle } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

// Mock notifications data - in production this would come from API
const MOCK_NOTIFICATIONS = [
  {
    id: '1',
    type: 'success' as const,
    title: 'Investigation Complete',
    message: 'Investigation "NULL spike in user_id" completed with root cause identified.',
    timestamp: '2 hours ago',
    read: false,
    link: '/investigations/1',
  },
  {
    id: '2',
    type: 'warning' as const,
    title: 'Approval Required',
    message: 'Human-in-the-loop approval needed for "Volume drop in EU events".',
    timestamp: '4 hours ago',
    read: false,
    link: '/investigations/2',
  },
  {
    id: '3',
    type: 'error' as const,
    title: 'Investigation Failed',
    message: 'Investigation "Schema drift in prices" failed: Unable to connect to data source.',
    timestamp: '1 day ago',
    read: true,
    link: '/investigations/3',
  },
  {
    id: '4',
    type: 'info' as const,
    title: 'New Data Source Connected',
    message: 'PostgreSQL data source "analytics_db" was successfully connected.',
    timestamp: '2 days ago',
    read: true,
    link: '/datasources',
  },
  {
    id: '5',
    type: 'success' as const,
    title: 'Weekly Digest',
    message: 'Your weekly investigation summary is ready. 12 investigations completed, 2 pending.',
    timestamp: '3 days ago',
    read: true,
  },
]

const typeIcons = {
  success: CheckCircle,
  warning: AlertTriangle,
  error: XCircle,
  info: Info,
}

const typeColors = {
  success: 'text-green-500',
  warning: 'text-yellow-500',
  error: 'text-red-500',
  info: 'text-blue-500',
}

interface Notification {
  id: string
  type: 'success' | 'warning' | 'error' | 'info'
  title: string
  message: string
  timestamp: string
  read: boolean
  link?: string
}

function NotificationItem({ notification }: { notification: Notification }) {
  const Icon = typeIcons[notification.type]
  const colorClass = typeColors[notification.type]

  return (
    <div
      className={`flex items-start gap-4 p-4 rounded-lg border ${
        notification.read ? 'bg-background' : 'bg-muted/50'
      }`}
    >
      <Icon className={`size-5 mt-0.5 ${colorClass}`} />
      <div className="flex-1 space-y-1">
        <div className="flex items-center gap-2">
          <span className="font-medium">{notification.title}</span>
          {!notification.read && (
            <Badge variant="default" className="text-xs">
              New
            </Badge>
          )}
        </div>
        <p className="text-sm text-muted-foreground">{notification.message}</p>
        <span className="text-xs text-muted-foreground">{notification.timestamp}</span>
      </div>
      {notification.link && (
        <Button variant="ghost" size="sm" asChild>
          <a href={notification.link}>View</a>
        </Button>
      )}
    </div>
  )
}

export function NotificationsPage() {
  const unreadCount = MOCK_NOTIFICATIONS.filter((n) => !n.read).length
  const allNotifications = MOCK_NOTIFICATIONS
  const unreadNotifications = MOCK_NOTIFICATIONS.filter((n) => !n.read)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Notifications"
        description="Stay updated on investigation progress and system alerts."
      />

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bell className="size-5" />
          <span className="text-sm text-muted-foreground">
            {unreadCount} unread notification{unreadCount !== 1 ? 's' : ''}
          </span>
        </div>
        {unreadCount > 0 && (
          <Button variant="outline" size="sm">
            <Check className="size-4 mr-2" />
            Mark all as read
          </Button>
        )}
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="all">
            <TabsList className="mb-4">
              <TabsTrigger value="all">All ({allNotifications.length})</TabsTrigger>
              <TabsTrigger value="unread">Unread ({unreadNotifications.length})</TabsTrigger>
            </TabsList>

            <TabsContent value="all" className="space-y-3">
              {allNotifications.length > 0 ? (
                allNotifications.map((notification) => (
                  <NotificationItem key={notification.id} notification={notification} />
                ))
              ) : (
                <p className="text-sm text-muted-foreground text-center py-8">
                  No notifications yet.
                </p>
              )}
            </TabsContent>

            <TabsContent value="unread" className="space-y-3">
              {unreadNotifications.length > 0 ? (
                unreadNotifications.map((notification) => (
                  <NotificationItem key={notification.id} notification={notification} />
                ))
              ) : (
                <p className="text-sm text-muted-foreground text-center py-8">
                  All caught up! No unread notifications.
                </p>
              )}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  )
}
