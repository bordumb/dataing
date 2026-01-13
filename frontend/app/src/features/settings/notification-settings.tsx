import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/Button'

const NOTIFICATION_SETTINGS = [
  {
    id: 'investigation_complete',
    label: 'Investigation Complete',
    description: 'Get notified when an investigation finishes.',
  },
  {
    id: 'approval_required',
    label: 'Approval Required',
    description: 'Get notified when human-in-the-loop approval is needed.',
  },
  {
    id: 'error_alerts',
    label: 'Error Alerts',
    description: 'Get notified when investigations fail or encounter errors.',
  },
  {
    id: 'weekly_digest',
    label: 'Weekly Digest',
    description: 'Receive a weekly summary of investigation activity.',
  },
]

export function NotificationSettings() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Email Notifications</CardTitle>
        <CardDescription>
          Choose which email notifications you want to receive.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {NOTIFICATION_SETTINGS.map((setting) => (
          <div key={setting.id} className="flex items-start space-x-3">
            <Checkbox id={setting.id} defaultChecked />
            <div className="grid gap-1.5 leading-none">
              <Label htmlFor={setting.id} className="font-medium">
                {setting.label}
              </Label>
              <p className="text-sm text-muted-foreground">
                {setting.description}
              </p>
            </div>
          </div>
        ))}
        <Button className="mt-4">Save Preferences</Button>
      </CardContent>
    </Card>
  )
}
