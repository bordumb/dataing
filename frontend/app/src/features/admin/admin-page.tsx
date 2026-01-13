import { PageHeader } from '@/components/shared/page-header'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { TeamsSettings } from '@/features/settings/teams/teams-settings'
import { TagsSettings } from '@/features/settings/tags/tags-settings'
import { PermissionsSettings } from '@/features/settings/permissions/permissions-settings'
import { SSOSettings } from '@/features/settings/sso/sso-settings'
import { AuditLogSettings } from '@/features/settings/audit'

export function AdminPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Admin"
        description="Manage teams, tags, permissions, single sign-on, and audit logging."
      />
      <Tabs defaultValue="teams" className="space-y-6">
        <TabsList>
          <TabsTrigger value="teams">Teams</TabsTrigger>
          <TabsTrigger value="tags">Tags</TabsTrigger>
          <TabsTrigger value="permissions">Permissions</TabsTrigger>
          <TabsTrigger value="sso">Single Sign-On</TabsTrigger>
          <TabsTrigger value="audit">Audit Log</TabsTrigger>
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
        <TabsContent value="audit">
          <AuditLogSettings />
        </TabsContent>
      </Tabs>
    </div>
  )
}
