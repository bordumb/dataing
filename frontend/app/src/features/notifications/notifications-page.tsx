/**
 * Notifications page displaying real-time notifications with mark-as-read functionality.
 */

import { Bell, Check } from 'lucide-react'
import { PageHeader } from '@/components/shared/page-header'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { NotificationCard } from './components/notification-card'
import { useNotificationsList, useUnreadCount } from './hooks/use-notifications-list'
import { useMarkAsRead, useMarkAllAsRead } from './hooks/use-mark-read'

function NotificationSkeleton() {
  return (
    <div className="p-4 border rounded-lg space-y-3">
      <div className="flex items-start gap-3">
        <Skeleton className="size-5 rounded-full" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3 w-2/3" />
          <Skeleton className="h-3 w-1/4" />
        </div>
      </div>
    </div>
  )
}

export function NotificationsPage() {
  const { data, isLoading, error } = useNotificationsList()
  const { data: unreadData } = useUnreadCount()
  const markAsRead = useMarkAsRead()
  const markAllAsRead = useMarkAllAsRead()

  const allNotifications = data?.items ?? []
  const unreadNotifications = allNotifications.filter((n) => !n.read_at)
  const unreadCount = unreadData?.count ?? unreadNotifications.length

  const handleMarkAsRead = (id: string) => {
    markAsRead.mutate(id)
  }

  const handleMarkAllAsRead = () => {
    markAllAsRead.mutate()
  }

  if (error) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Notifications"
          description="Stay updated on investigation progress and system alerts."
        />
        <Card>
          <CardContent className="py-8">
            <p className="text-sm text-muted-foreground text-center">
              Failed to load notifications. Please try again.
            </p>
          </CardContent>
        </Card>
      </div>
    )
  }

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
          <Button
            variant="outline"
            size="sm"
            onClick={handleMarkAllAsRead}
            disabled={markAllAsRead.isPending}
          >
            <Check className="size-4 mr-2" />
            {markAllAsRead.isPending ? 'Marking...' : 'Mark all as read'}
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
              {isLoading ? (
                <>
                  <NotificationSkeleton />
                  <NotificationSkeleton />
                  <NotificationSkeleton />
                </>
              ) : allNotifications.length > 0 ? (
                allNotifications.map((notification) => (
                  <NotificationCard
                    key={notification.id}
                    notification={notification}
                    onMarkRead={handleMarkAsRead}
                  />
                ))
              ) : (
                <p className="text-sm text-muted-foreground text-center py-8">
                  No notifications yet.
                </p>
              )}
            </TabsContent>

            <TabsContent value="unread" className="space-y-3">
              {isLoading ? (
                <>
                  <NotificationSkeleton />
                  <NotificationSkeleton />
                </>
              ) : unreadNotifications.length > 0 ? (
                unreadNotifications.map((notification) => (
                  <NotificationCard
                    key={notification.id}
                    notification={notification}
                    onMarkRead={handleMarkAsRead}
                  />
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
