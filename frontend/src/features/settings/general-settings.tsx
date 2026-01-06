import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/lib/auth/context'

export function GeneralSettings() {
  // Use API key auth context (tenant) instead of JWT auth (org)
  const { tenant } = useAuth()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Organization</CardTitle>
        <CardDescription>
          Manage your organization settings and preferences.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-2">
          <Label htmlFor="org-name">Organization Name</Label>
          <Input
            id="org-name"
            defaultValue={tenant?.name ?? ''}
            placeholder="Your organization"
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="org-slug">Organization Slug</Label>
          <Input
            id="org-slug"
            defaultValue={tenant?.slug ?? ''}
            placeholder="your-org"
            disabled
          />
          <p className="text-sm text-muted-foreground">
            Used in URLs and API calls
          </p>
        </div>
        <Button>Save Changes</Button>
      </CardContent>
    </Card>
  )
}
