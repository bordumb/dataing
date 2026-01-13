import * as React from 'react'
import { Shield, Trash2, Loader2, Users, User, Tag, Database } from 'lucide-react'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { EmptyState } from '@/components/shared/empty-state'
import { Badge } from '@/components/ui/Badge'
import {
  useListPermissionsApiV1PermissionsGet,
  useDeletePermissionApiV1PermissionsGrantIdDelete,
  getListPermissionsApiV1PermissionsGetQueryKey,
} from '@/lib/api/generated/permissions/permissions'
import type { PermissionGrantResponse } from '@/lib/api/model'

export function PermissionsSettings() {
  const queryClient = useQueryClient()
  const [grantToDelete, setGrantToDelete] = React.useState<PermissionGrantResponse | null>(null)

  const { data: permissionsData, isLoading, error } = useListPermissionsApiV1PermissionsGet()
  const permissions = permissionsData?.permissions ?? []

  const deleteMutation = useDeletePermissionApiV1PermissionsGrantIdDelete({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListPermissionsApiV1PermissionsGetQueryKey() })
        toast.success('Permission revoked successfully')
        setGrantToDelete(null)
      },
      onError: (error: Error) => {
        toast.error(`Failed to revoke permission: ${error.message || 'Unknown error'}`)
      },
    },
  })

  const handleDelete = () => {
    if (!grantToDelete) return
    deleteMutation.mutate({ grantId: grantToDelete.id })
  }

  const getGranteeIcon = (granteeType: string) => {
    return granteeType === 'user' ? (
      <User className="h-4 w-4 text-muted-foreground" />
    ) : (
      <Users className="h-4 w-4 text-muted-foreground" />
    )
  }

  const getAccessIcon = (accessType: string) => {
    switch (accessType) {
      case 'tag':
        return <Tag className="h-4 w-4 text-muted-foreground" />
      case 'datasource':
        return <Database className="h-4 w-4 text-muted-foreground" />
      default:
        return <Shield className="h-4 w-4 text-muted-foreground" />
    }
  }

  const getPermissionBadgeVariant = (permission: string) => {
    switch (permission) {
      case 'admin':
        return 'destructive'
      case 'write':
        return 'default'
      default:
        return 'secondary'
    }
  }

  const formatGrantDescription = (grant: PermissionGrantResponse) => {
    const granteeType = grant.grantee_type === 'user' ? 'User' : 'Team'
    const granteeId = grant.grantee_id?.slice(0, 8) ?? 'Unknown'

    if (grant.access_type === 'resource') {
      return `${granteeType} ${granteeId} can access investigation ${grant.resource_id?.slice(0, 8)}`
    } else if (grant.access_type === 'tag') {
      return `${granteeType} ${granteeId} can access all investigations with tag`
    } else {
      return `${granteeType} ${granteeId} can access all investigations on datasource`
    }
  }

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-12">
          <EmptyState
            icon={Shield}
            title="Failed to load permissions"
            description="There was an error loading permissions. Please try again."
          />
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Permission Grants</CardTitle>
          <CardDescription>
            View and manage all permission grants. Permissions can be granted directly to
            investigations, via tags, or via datasources.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {permissions.length === 0 ? (
            <EmptyState
              icon={Shield}
              title="No permissions yet"
              description="Permission grants will appear here when you share investigations with users or teams."
            />
          ) : (
            <div className="space-y-4">
              {permissions.map((grant) => (
                <div
                  key={grant.id}
                  className="flex items-center justify-between rounded-lg border p-4"
                >
                  <div className="flex items-center gap-4">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                      {getAccessIcon(grant.access_type)}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        {getGranteeIcon(grant.grantee_type)}
                        <p className="font-medium">
                          {grant.grantee_type === 'user' ? 'User' : 'Team'}
                        </p>
                        <Badge variant={getPermissionBadgeVariant(grant.permission) as 'default'}>
                          {grant.permission}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {formatGrantDescription(grant)}
                      </p>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setGrantToDelete(grant)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!grantToDelete} onOpenChange={() => setGrantToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke Permission</DialogTitle>
            <DialogDescription>
              Are you sure you want to revoke this permission? The user or team will no longer have
              access to the associated resources.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setGrantToDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Revoke Permission
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
