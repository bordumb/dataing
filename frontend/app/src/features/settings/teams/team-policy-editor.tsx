import * as React from 'react'
import { Plus, Trash2, Loader2, AlertTriangle } from 'lucide-react'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/Badge'
import { EmptyState } from '@/components/shared/empty-state'
import {
  useGetTeamPolicyApiV1TeamsTeamIdPolicyGet,
  useUpdateTeamPolicyApiV1TeamsTeamIdPolicyPut,
  useCreatePolicyOverrideApiV1TeamsTeamIdPolicyOverridesPost,
  useDeletePolicyOverrideApiV1TeamsTeamIdPolicyOverridesOverrideIdDelete,
  useUpdateQueueLimitsApiV1TeamsTeamIdPolicyQueueLimitsPut,
  getGetTeamPolicyApiV1TeamsTeamIdPolicyGetQueryKey,
} from '@/lib/api/generated/teams/teams'
import type { TeamPolicyOverrideResponse } from '@/lib/api/model'

const ALERT_SOURCES = ['monte_carlo', 'great_expectations', 'dbt', 'pagerduty', 'jira', 'custom']
const POLICY_ACTIONS = ['auto', 'review', 'issue_only']
const SEVERITY_LEVELS = ['low', 'medium', 'high', 'critical']

interface TeamPolicyEditorProps {
  teamId: string
  teamName: string
  onClose: () => void
}

export function TeamPolicyEditor({ teamId, teamName, onClose }: TeamPolicyEditorProps) {
  const queryClient = useQueryClient()
  const [showOverrideDialog, setShowOverrideDialog] = React.useState(false)
  const [newOverride, setNewOverride] = React.useState({
    datasetId: '',
    defaultAction: '',
    autoInvestigateMinSeverity: '',
    reviewRequiredMaxSeverity: '',
  })

  const { data: policyData, isLoading, error } = useGetTeamPolicyApiV1TeamsTeamIdPolicyGet(teamId)

  const updatePolicyMutation = useUpdateTeamPolicyApiV1TeamsTeamIdPolicyPut({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getGetTeamPolicyApiV1TeamsTeamIdPolicyGetQueryKey(teamId),
        })
        toast.success('Policy updated successfully')
      },
      onError: (error: Error) => {
        toast.error(`Failed to update policy: ${error.message || 'Unknown error'}`)
      },
    },
  })

  const createOverrideMutation = useCreatePolicyOverrideApiV1TeamsTeamIdPolicyOverridesPost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getGetTeamPolicyApiV1TeamsTeamIdPolicyGetQueryKey(teamId),
        })
        toast.success('Override created successfully')
        setShowOverrideDialog(false)
        setNewOverride({
          datasetId: '',
          defaultAction: '',
          autoInvestigateMinSeverity: '',
          reviewRequiredMaxSeverity: '',
        })
      },
      onError: (error: Error) => {
        toast.error(`Failed to create override: ${error.message || 'Unknown error'}`)
      },
    },
  })

  const deleteOverrideMutation =
    useDeletePolicyOverrideApiV1TeamsTeamIdPolicyOverridesOverrideIdDelete({
      mutation: {
        onSuccess: () => {
          queryClient.invalidateQueries({
            queryKey: getGetTeamPolicyApiV1TeamsTeamIdPolicyGetQueryKey(teamId),
          })
          toast.success('Override deleted successfully')
        },
        onError: (error: Error) => {
          toast.error(`Failed to delete override: ${error.message || 'Unknown error'}`)
        },
      },
    })

  const updateQueueLimitsMutation = useUpdateQueueLimitsApiV1TeamsTeamIdPolicyQueueLimitsPut({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getGetTeamPolicyApiV1TeamsTeamIdPolicyGetQueryKey(teamId),
        })
        toast.success('Queue limits updated successfully')
      },
      onError: (error: Error) => {
        toast.error(`Failed to update queue limits: ${error.message || 'Unknown error'}`)
      },
    },
  })

  const handleUpdatePolicy = (updates: {
    sources?: string[]
    defaultAction?: string
    autoInvestigateMinSeverity?: string | null
    reviewRequiredMaxSeverity?: string | null
  }) => {
    updatePolicyMutation.mutate({
      teamId,
      data: {
        sources: updates.sources,
        default_action: updates.defaultAction,
        auto_investigate_min_severity: updates.autoInvestigateMinSeverity,
        review_required_max_severity: updates.reviewRequiredMaxSeverity,
      },
    })
  }

  const handleCreateOverride = () => {
    if (!newOverride.datasetId.trim()) {
      toast.error('Dataset ID is required')
      return
    }
    createOverrideMutation.mutate({
      teamId,
      data: {
        dataset_id: newOverride.datasetId.trim(),
        default_action: newOverride.defaultAction || undefined,
        auto_investigate_min_severity: newOverride.autoInvestigateMinSeverity || undefined,
        review_required_max_severity: newOverride.reviewRequiredMaxSeverity || undefined,
      },
    })
  }

  const handleDeleteOverride = (overrideId: string) => {
    deleteOverrideMutation.mutate({ teamId, overrideId })
  }

  const handleUpdateQueueLimits = (updates: {
    rateLimitPerMinute?: number
    burstSize?: number
    maxConcurrent?: number
    batchSize?: number
  }) => {
    updateQueueLimitsMutation.mutate({
      teamId,
      data: {
        rate_limit_per_minute: updates.rateLimitPerMinute,
        burst_size: updates.burstSize,
        max_concurrent: updates.maxConcurrent,
        batch_size: updates.batchSize,
      },
    })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Failed to load policy"
        description="There was an error loading the team policy. Please try again."
      />
    )
  }

  const policy = policyData?.policy
  const overrides = policyData?.overrides ?? []
  const queueLimits = policyData?.queue_limits

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Policy Settings for {teamName}</h2>
          <p className="text-sm text-muted-foreground">
            Configure how alerts are handled for this team
          </p>
        </div>
        <Button variant="outline" onClick={onClose}>
          Close
        </Button>
      </div>

      {/* Default Policy Settings */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Default Policy</CardTitle>
          <CardDescription>
            These settings apply to all alerts unless overridden by dataset-specific rules
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Default Action</Label>
              <Select
                value={policy?.default_action || 'issue_only'}
                onValueChange={(value) => handleUpdatePolicy({ defaultAction: value })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {POLICY_ACTIONS.map((action) => (
                    <SelectItem key={action} value={action}>
                      {action === 'auto'
                        ? 'Auto Investigate'
                        : action === 'review'
                          ? 'Require Review'
                          : 'Issue Only'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Alert Sources</Label>
              <div className="flex flex-wrap gap-2">
                {ALERT_SOURCES.map((source) => {
                  const isSelected = policy?.sources?.includes(source)
                  return (
                    <Badge
                      key={source}
                      variant={isSelected ? 'default' : 'outline'}
                      className="cursor-pointer"
                      onClick={() => {
                        const currentSources = policy?.sources || []
                        const newSources = isSelected
                          ? currentSources.filter((s) => s !== source)
                          : [...currentSources, source]
                        handleUpdatePolicy({ sources: newSources })
                      }}
                    >
                      {source}
                    </Badge>
                  )
                })}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Auto-investigate Min Severity</Label>
              <Select
                value={policy?.auto_investigate_min_severity || ''}
                onValueChange={(value) =>
                  handleUpdatePolicy({ autoInvestigateMinSeverity: value || null })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Not set" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">Not set</SelectItem>
                  {SEVERITY_LEVELS.map((level) => (
                    <SelectItem key={level} value={level}>
                      {level.charAt(0).toUpperCase() + level.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Review Required Max Severity</Label>
              <Select
                value={policy?.review_required_max_severity || ''}
                onValueChange={(value) =>
                  handleUpdatePolicy({ reviewRequiredMaxSeverity: value || null })
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Not set" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">Not set</SelectItem>
                  {SEVERITY_LEVELS.map((level) => (
                    <SelectItem key={level} value={level}>
                      {level.charAt(0).toUpperCase() + level.slice(1)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Dataset Overrides */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Dataset Overrides</CardTitle>
              <CardDescription>
                Override default policy settings for specific datasets
              </CardDescription>
            </div>
            <Button size="sm" onClick={() => setShowOverrideDialog(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Add Override
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {overrides.length === 0 ? (
            <p className="text-sm text-muted-foreground">No dataset overrides configured</p>
          ) : (
            <div className="space-y-3">
              {overrides.map((override: TeamPolicyOverrideResponse) => (
                <div
                  key={override.id}
                  className="flex items-center justify-between rounded-lg border p-3"
                >
                  <div className="space-y-1">
                    <p className="font-medium">{override.dataset_id || `Tag: ${override.tag_id}`}</p>
                    <div className="flex gap-2">
                      {override.default_action && (
                        <Badge variant="secondary">{override.default_action}</Badge>
                      )}
                      {override.auto_investigate_min_severity && (
                        <Badge variant="outline">
                          Auto: {override.auto_investigate_min_severity}+
                        </Badge>
                      )}
                      {override.review_required_max_severity && (
                        <Badge variant="outline">
                          Review: {override.review_required_max_severity}
                        </Badge>
                      )}
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDeleteOverride(override.id)}
                    disabled={deleteOverrideMutation.isPending}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Queue Limits */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Queue & Rate Limits</CardTitle>
          <CardDescription>
            Control investigation throughput and concurrency for this team
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label>Rate Limit (per minute)</Label>
              <Input
                type="number"
                value={queueLimits?.rate_limit_per_minute ?? 60}
                onChange={(e) =>
                  handleUpdateQueueLimits({ rateLimitPerMinute: parseInt(e.target.value) || 60 })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Burst Size</Label>
              <Input
                type="number"
                value={queueLimits?.burst_size ?? 10}
                onChange={(e) =>
                  handleUpdateQueueLimits({ burstSize: parseInt(e.target.value) || 10 })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Max Concurrent</Label>
              <Input
                type="number"
                value={queueLimits?.max_concurrent ?? 5}
                onChange={(e) =>
                  handleUpdateQueueLimits({ maxConcurrent: parseInt(e.target.value) || 5 })
                }
              />
            </div>
            <div className="space-y-2">
              <Label>Batch Size</Label>
              <Input
                type="number"
                value={queueLimits?.batch_size ?? 5}
                onChange={(e) =>
                  handleUpdateQueueLimits({ batchSize: parseInt(e.target.value) || 5 })
                }
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Add Override Dialog */}
      <Dialog open={showOverrideDialog} onOpenChange={setShowOverrideDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add Dataset Override</DialogTitle>
            <DialogDescription>
              Create a policy override for a specific dataset
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="dataset-id">Dataset ID</Label>
              <Input
                id="dataset-id"
                placeholder="e.g., orders, users, transactions"
                value={newOverride.datasetId}
                onChange={(e) => setNewOverride({ ...newOverride, datasetId: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>Override Action</Label>
              <Select
                value={newOverride.defaultAction}
                onValueChange={(value) => setNewOverride({ ...newOverride, defaultAction: value })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Use default" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">Use default</SelectItem>
                  {POLICY_ACTIONS.map((action) => (
                    <SelectItem key={action} value={action}>
                      {action === 'auto'
                        ? 'Auto Investigate'
                        : action === 'review'
                          ? 'Require Review'
                          : 'Issue Only'}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Auto-investigate Min Severity</Label>
                <Select
                  value={newOverride.autoInvestigateMinSeverity}
                  onValueChange={(value) =>
                    setNewOverride({ ...newOverride, autoInvestigateMinSeverity: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Use default" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Use default</SelectItem>
                    {SEVERITY_LEVELS.map((level) => (
                      <SelectItem key={level} value={level}>
                        {level.charAt(0).toUpperCase() + level.slice(1)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Review Required Max Severity</Label>
                <Select
                  value={newOverride.reviewRequiredMaxSeverity}
                  onValueChange={(value) =>
                    setNewOverride({ ...newOverride, reviewRequiredMaxSeverity: value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Use default" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">Use default</SelectItem>
                    {SEVERITY_LEVELS.map((level) => (
                      <SelectItem key={level} value={level}>
                        {level.charAt(0).toUpperCase() + level.slice(1)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowOverrideDialog(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreateOverride} disabled={createOverrideMutation.isPending}>
              {createOverrideMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Create Override
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
