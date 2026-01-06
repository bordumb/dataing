import { PageHeader } from '@/components/shared/page-header'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TeamsSettings } from '@/features/settings/teams/teams-settings'
import { TagsSettings } from '@/features/settings/tags/tags-settings'
import { PermissionsSettings } from '@/features/settings/permissions/permissions-settings'
import { SSOSettings } from '@/features/settings/sso/sso-settings'

export function AdminPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Admin"
        description="Manage teams, tags, permissions, and single sign-on configuration."
      />
      <Tabs defaultValue="teams" className="space-y-6">
        <TabsList>
          <TabsTrigger value="teams">Teams</TabsTrigger>
          <TabsTrigger value="tags">Tags</TabsTrigger>
          <TabsTrigger value="permissions">Permissions</TabsTrigger>
          <TabsTrigger value="sso">Single Sign-On</TabsTrigger>
        </TabsList>
        <TabsContent value="teams">
          <TeamsSettings />
        </TabsContent>
        <TabsContent value="tags">
          <TagsSettings />
        </TabsContent>
        <TabsContent value="permissions">
          <PermissionsSettings />
        </TabsContent>
        <TabsContent value="sso">
          <SSOSettings />
        </TabsContent>
      </Tabs>
    </div>
  )
}
