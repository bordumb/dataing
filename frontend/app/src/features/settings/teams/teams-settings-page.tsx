import { PageHeader } from '@/components/shared/page-header'
import { TeamsSettings } from './teams-settings'

export function TeamsSettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Teams"
        description="Manage teams and team membership for your organization."
      />
      <TeamsSettings />
    </div>
  )
}
