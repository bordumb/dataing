import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { GeneralSettings } from './general-settings'
import { WebhookSettings } from './webhook-settings'
import { NotificationSettings } from './notification-settings'
import { ApiKeySettings } from './api-key-settings'
import { PageHeader } from '@/components/shared/page-header'

export function SettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Manage your account and integration settings."
      />

      <Tabs defaultValue="general" className="space-y-4">
        <TabsList>
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="webhooks">Webhooks</TabsTrigger>
          <TabsTrigger value="notifications">Notifications</TabsTrigger>
          <TabsTrigger value="api-keys">API Keys</TabsTrigger>
        </TabsList>

        <TabsContent value="general" className="space-y-4">
          <GeneralSettings />
        </TabsContent>

        <TabsContent value="webhooks" className="space-y-4">
          <WebhookSettings />
        </TabsContent>

        <TabsContent value="notifications" className="space-y-4">
          <NotificationSettings />
        </TabsContent>

        <TabsContent value="api-keys" className="space-y-4">
          <ApiKeySettings />
        </TabsContent>
      </Tabs>
    </div>
  )
}
