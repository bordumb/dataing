import * as React from 'react'
import { Plus, Users, Lock, Trash2, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/label'
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
  useListTeamsApiV1TeamsGet,
  useCreateTeamApiV1TeamsPost,
  useDeleteTeamApiV1TeamsTeamIdDelete,
  getListTeamsApiV1TeamsGetQueryKey,
} from '@/lib/api/generated/teams/teams'
import type { TeamResponse } from '@/lib/api/model'

export function TeamsSettings() {
  const queryClient = useQueryClient()
  const [showCreateDialog, setShowCreateDialog] = React.useState(false)
  const [newTeamName, setNewTeamName] = React.useState('')
  const [teamToDelete, setTeamToDelete] = React.useState<TeamResponse | null>(null)

  const { data: teamsData, isLoading, error } = useListTeamsApiV1TeamsGet()
  const teams = teamsData?.teams ?? []

  const createMutation = useCreateTeamApiV1TeamsPost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListTeamsApiV1TeamsGetQueryKey() })
        toast.success('Team created successfully')
        closeCreateDialog()
      },
      onError: (error: Error) => {
        toast.error(`Failed to create team: ${error.message || 'Unknown error'}`)
      },
    },
  })

  const deleteMutation = useDeleteTeamApiV1TeamsTeamIdDelete({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListTeamsApiV1TeamsGetQueryKey() })
        toast.success('Team deleted successfully')
        setTeamToDelete(null)
      },
      onError: (error: Error) => {
        toast.error(`Failed to delete team: ${error.message || 'Unknown error'}`)
      },
    },
  })

  const closeCreateDialog = () => {
    setShowCreateDialog(false)
    setNewTeamName('')
  }

  const handleCreate = () => {
    if (!newTeamName.trim()) {
      toast.error('Team name is required')
      return
    }
    createMutation.mutate({ data: { name: newTeamName.trim() } })
  }

  const handleDelete = () => {
    if (!teamToDelete) return
    deleteMutation.mutate({ teamId: teamToDelete.id })
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
            icon={Users}
            title="Failed to load teams"
            description="There was an error loading your teams. Please try again."
          />
        </CardContent>
      </Card>
    )
  }

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Teams</CardTitle>
              <CardDescription>
                Create and manage teams to organize users and control access.
              </CardDescription>
            </div>
            <Button onClick={() => setShowCreateDialog(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Create Team
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {teams.length === 0 ? (
            <EmptyState
              icon={Users}
              title="No teams yet"
              description="Create your first team to start organizing users."
              action={
                <Button onClick={() => setShowCreateDialog(true)}>
                  <Plus className="mr-2 h-4 w-4" />
                  Create Team
                </Button>
              }
            />
          ) : (
            <div className="space-y-4">
              {teams.map((team) => (
                <div
                  key={team.id}
                  className="flex items-center justify-between rounded-lg border p-4"
                >
                  <div className="flex items-center gap-4">
                    <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10">
                      <Users className="h-5 w-5 text-primary" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <p className="font-medium">{team.name}</p>
                        {team.is_scim_managed && (
                          <Badge variant="secondary" className="gap-1">
                            <Lock className="h-3 w-3" />
                            SCIM Managed
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {team.member_count ?? 0} member{(team.member_count ?? 0) !== 1 ? 's' : ''}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {!team.is_scim_managed && (
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setTeamToDelete(team)}
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create Team Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Team</DialogTitle>
            <DialogDescription>
              Create a new team to organize users and control access to resources.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="team-name">Team Name</Label>
              <Input
                id="team-name"
                placeholder="Engineering"
                value={newTeamName}
                onChange={(e) => setNewTeamName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeCreateDialog}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={createMutation.isPending}>
              {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create Team
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!teamToDelete} onOpenChange={() => setTeamToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Team</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{teamToDelete?.name}"? This action cannot be undone.
              All permission grants to this team will also be removed.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTeamToDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Delete Team
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
