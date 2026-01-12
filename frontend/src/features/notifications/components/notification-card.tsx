/**
 * NotificationCard component for displaying individual notifications.
 *
 * Supports polymorphic rendering based on notification type.
 */

import { Link } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { CheckCircle, XCircle, AlertTriangle, Info } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface NotificationData {
  id: string
  type: string
  title: string
  body: string | null
  resource_kind: string | null
  resource_id: string | null
  severity: 'info' | 'success' | 'warning' | 'error'
  created_at: string
  read_at: string | null
}

interface NotificationCardProps {
  notification: NotificationData
  onMarkRead: (id: string) => void
}

const severityIcons = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
}

const severityColors = {
  success: 'text-green-500',
  error: 'text-red-500',
  warning: 'text-yellow-500',
  info: 'text-blue-500',
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffMins < 60) {
    return `${diffMins} minute${diffMins !== 1 ? 's' : ''} ago`
  } else if (diffHours < 24) {
    return `${diffHours} hour${diffHours !== 1 ? 's' : ''} ago`
  } else if (diffDays < 7) {
    return `${diffDays} day${diffDays !== 1 ? 's' : ''} ago`
  } else {
    return date.toLocaleDateString()
  }
}

export function NotificationCard({ notification, onMarkRead }: NotificationCardProps) {
  const isUnread = !notification.read_at
  const Icon = severityIcons[notification.severity] || Info
  const iconColor = severityColors[notification.severity] || 'text-blue-500'

  // Build link to resource
  const resourceLink =
    notification.resource_kind === 'investigation' && notification.resource_id
      ? `/investigations/${notification.resource_id}`
      : null

  const handleClick = () => {
    if (isUnread) {
      onMarkRead(notification.id)
    }
  }

  // Polymorphic rendering for approval_required type
  if (notification.type === 'approval_required') {
    return (
      <Card className={cn('p-4', isUnread && 'border-l-4 border-l-primary')}>
        <div className="flex items-start gap-3">
          <AlertTriangle className="size-5 mt-0.5 text-yellow-500" />
          <div className="flex-1 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <h4 className="font-semibold">{notification.title}</h4>
              <Badge variant="destructive">Action Required</Badge>
            </div>
            {notification.body && (
              <p className="text-sm text-muted-foreground">{notification.body}</p>
            )}
            <div className="flex gap-2 mt-3">
              {resourceLink && (
                <Button size="sm" asChild>
                  <Link to={resourceLink} onClick={handleClick}>
                    Review
                  </Link>
                </Button>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {formatTimestamp(notification.created_at)}
            </p>
          </div>
        </div>
      </Card>
    )
  }

  // Default card for investigation_completed/failed
  const cardContent = (
    <Card
      className={cn(
        'p-4 transition-colors',
        isUnread && 'border-l-4 border-l-primary',
        resourceLink && 'cursor-pointer hover:bg-accent'
      )}
      onClick={handleClick}
    >
      <div className="flex items-start gap-3">
        <Icon className={cn('size-5 mt-0.5', iconColor)} />
        <div className="flex-1 space-y-1">
          <div className="flex items-center justify-between gap-2">
            <h4 className="font-medium">{notification.title}</h4>
            {isUnread && (
              <Badge variant="default" className="text-xs">
                New
              </Badge>
            )}
          </div>
          {notification.body && (
            <p className="text-sm text-muted-foreground">{notification.body}</p>
          )}
          <p className="text-xs text-muted-foreground">{formatTimestamp(notification.created_at)}</p>
        </div>
      </div>
    </Card>
  )

  return resourceLink ? (
    <Link to={resourceLink} onClick={handleClick} className="block">
      {cardContent}
    </Link>
  ) : (
    cardContent
  )
}
