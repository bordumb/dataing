import * as React from 'react'
import { Plus, Trash2, Globe } from 'lucide-react'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/label'
import { Checkbox } from '@/components/ui/checkbox'
import { EmptyState } from '@/components/shared/empty-state'

interface Webhook {
  id: string
  url: string
  events: string[]
  active: boolean
}

const EVENT_TYPES = [
  { id: 'investigation.started', label: 'Investigation Started' },
  { id: 'investigation.completed', label: 'Investigation Completed' },
  { id: 'investigation.failed', label: 'Investigation Failed' },
  { id: 'approval.required', label: 'Approval Required' },
]

export function WebhookSettings() {
  const [webhooks, setWebhooks] = React.useState<Webhook[]>([])
  const [showForm, setShowForm] = React.useState(false)
  const [newWebhook, setNewWebhook] = React.useState({
    url: '',
    events: [] as string[],
  })

  const addWebhook = () => {
    if (newWebhook.url && newWebhook.events.length > 0) {
      setWebhooks([
        ...webhooks,
        {
          id: Date.now().toString(),
          url: newWebhook.url,
          events: newWebhook.events,
          active: true,
        },
      ])
      setNewWebhook({ url: '', events: [] })
      setShowForm(false)
    }
  }

  const toggleEvent = (eventId: string) => {
    setNewWebhook((prev) => ({
      ...prev,
      events: prev.events.includes(eventId)
        ? prev.events.filter((e) => e !== eventId)
        : [...prev.events, eventId],
    }))
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Webhooks</CardTitle>
        <CardDescription>
          Configure webhook endpoints to receive real-time notifications.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {webhooks.length === 0 && !showForm ? (
          <EmptyState
            icon={Globe}
            title="No webhooks configured"
            description="Add a webhook to receive notifications when events occur."
            action={
              <Button onClick={() => setShowForm(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Add Webhook
              </Button>
            }
          />
        ) : (
          <>
            {webhooks.map((webhook) => (
              <div
                key={webhook.id}
                className="flex items-center justify-between p-4 border rounded-lg"
              >
                <div>
                  <p className="font-medium">{webhook.url}</p>
                  <p className="text-sm text-muted-foreground">
                    Events: {webhook.events.join(', ')}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() =>
                    setWebhooks(webhooks.filter((w) => w.id !== webhook.id))
                  }
                >
                  <Trash2 className="h-4 w-4 text-destructive" />
                </Button>
              </div>
            ))}

            {showForm && (
              <div className="space-y-4 p-4 border rounded-lg">
                <div className="grid gap-2">
                  <Label htmlFor="webhook-url">Webhook URL</Label>
                  <Input
                    id="webhook-url"
                    type="url"
                    value={newWebhook.url}
                    onChange={(e) =>
                      setNewWebhook({ ...newWebhook, url: e.target.value })
                    }
                    placeholder="https://your-server.com/webhook"
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Events</Label>
                  <div className="space-y-2">
                    {EVENT_TYPES.map((event) => (
                      <div key={event.id} className="flex items-center space-x-2">
                        <Checkbox
                          id={event.id}
                          checked={newWebhook.events.includes(event.id)}
                          onCheckedChange={() => toggleEvent(event.id)}
                        />
                        <Label htmlFor={event.id} className="font-normal">
                          {event.label}
                        </Label>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="flex gap-2">
                  <Button onClick={addWebhook}>Add Webhook</Button>
                  <Button variant="outline" onClick={() => setShowForm(false)}>
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            {!showForm && webhooks.length > 0 && (
              <Button onClick={() => setShowForm(true)}>
                <Plus className="mr-2 h-4 w-4" />
                Add Another Webhook
              </Button>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}
