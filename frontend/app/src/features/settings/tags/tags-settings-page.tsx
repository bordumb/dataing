import { PageHeader } from '@/components/shared/page-header'
import { TagsSettings } from './tags-settings'

export function TagsSettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Tags"
        description="Create and manage tags to organize and control access to investigations."
      />
      <TagsSettings />
    </div>
  )
}
