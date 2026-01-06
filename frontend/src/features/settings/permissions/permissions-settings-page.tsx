import { PageHeader } from '@/components/shared/page-header'
import { PermissionsSettings } from './permissions-settings'

export function PermissionsSettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Permissions"
        description="Manage access permissions for users and teams."
      />
      <PermissionsSettings />
    </div>
  )
}
