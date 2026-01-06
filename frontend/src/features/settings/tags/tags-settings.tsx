import * as React from 'react'
import { Plus, Tag, Trash2, Loader2 } from 'lucide-react'
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
import {
  useListTagsApiV1TagsGet,
  useCreateTagApiV1TagsPost,
  useDeleteTagApiV1TagsTagIdDelete,
  getListTagsApiV1TagsGetQueryKey,
} from '@/lib/api/generated/tags/tags'
import type { TagResponse } from '@/lib/api/model'

const DEFAULT_COLORS = [
  '#6366f1', // Indigo
  '#8b5cf6', // Violet
  '#d946ef', // Fuchsia
  '#ec4899', // Pink
  '#f43f5e', // Rose
  '#ef4444', // Red
  '#f97316', // Orange
  '#eab308', // Yellow
  '#22c55e', // Green
  '#14b8a6', // Teal
  '#0ea5e9', // Sky
  '#3b82f6', // Blue
]

export function TagsSettings() {
  const queryClient = useQueryClient()
  const [showCreateDialog, setShowCreateDialog] = React.useState(false)
  const [newTagName, setNewTagName] = React.useState('')
  const [newTagColor, setNewTagColor] = React.useState(DEFAULT_COLORS[0])
  const [tagToDelete, setTagToDelete] = React.useState<TagResponse | null>(null)

  const { data: tagsData, isLoading, error } = useListTagsApiV1TagsGet()
  const tags = tagsData?.tags ?? []

  const createMutation = useCreateTagApiV1TagsPost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListTagsApiV1TagsGetQueryKey() })
        toast.success('Tag created successfully')
        closeCreateDialog()
      },
      onError: (error) => {
        toast.error(`Failed to create tag: ${error.message}`)
      },
    },
  })

  const deleteMutation = useDeleteTagApiV1TagsTagIdDelete({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListTagsApiV1TagsGetQueryKey() })
        toast.success('Tag deleted successfully')
        setTagToDelete(null)
      },
      onError: (error) => {
        toast.error(`Failed to delete tag: ${error.message}`)
      },
    },
  })

  const closeCreateDialog = () => {
    setShowCreateDialog(false)
    setNewTagName('')
    setNewTagColor(DEFAULT_COLORS[0])
  }

  const handleCreate = () => {
    if (!newTagName.trim()) {
      toast.error('Tag name is required')
      return
    }
    createMutation.mutate({ data: { name: newTagName.trim(), color: newTagColor } })
  }

  const handleDelete = () => {
    if (!tagToDelete) return
    deleteMutation.mutate({ tagId: tagToDelete.id })
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
            icon={<Tag className="h-12 w-12" />}
            title="Failed to load tags"
            description="There was an error loading your tags. Please try again."
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
              <CardTitle>Tags</CardTitle>
              <CardDescription>
                Create tags to categorize investigations and control access with tag-based
                permissions.
              </CardDescription>
            </div>
            <Button onClick={() => setShowCreateDialog(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Create Tag
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {tags.length === 0 ? (
            <EmptyState
              icon={<Tag className="h-12 w-12" />}
              title="No tags yet"
              description="Create your first tag to start organizing investigations."
              action={
                <Button onClick={() => setShowCreateDialog(true)}>
                  <Plus className="mr-2 h-4 w-4" />
                  Create Tag
                </Button>
              }
            />
          ) : (
            <div className="flex flex-wrap gap-3">
              {tags.map((tag) => (
                <div
                  key={tag.id}
                  className="group flex items-center gap-2 rounded-lg border px-3 py-2"
                >
                  <div
                    className="h-3 w-3 rounded-full"
                    style={{ backgroundColor: tag.color }}
                  />
                  <span className="font-medium">{tag.name}</span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 opacity-0 transition-opacity group-hover:opacity-100"
                    onClick={() => setTagToDelete(tag)}
                  >
                    <Trash2 className="h-3 w-3 text-destructive" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create Tag Dialog */}
      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Create Tag</DialogTitle>
            <DialogDescription>
              Create a new tag to categorize investigations.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="tag-name">Tag Name</Label>
              <Input
                id="tag-name"
                placeholder="finance"
                value={newTagName}
                onChange={(e) => setNewTagName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              />
            </div>
            <div className="space-y-2">
              <Label>Color</Label>
              <div className="flex flex-wrap gap-2">
                {DEFAULT_COLORS.map((color) => (
                  <button
                    key={color}
                    type="button"
                    className={`h-8 w-8 rounded-full ring-offset-2 transition-all ${
                      newTagColor === color ? 'ring-2 ring-primary' : ''
                    }`}
                    style={{ backgroundColor: color }}
                    onClick={() => setNewTagColor(color)}
                  />
                ))}
              </div>
            </div>
            <div className="flex items-center gap-2 rounded-lg border p-3">
              <div className="h-3 w-3 rounded-full" style={{ backgroundColor: newTagColor }} />
              <span className="font-medium">{newTagName || 'Preview'}</span>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeCreateDialog}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={createMutation.isPending}>
              {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create Tag
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!tagToDelete} onOpenChange={() => setTagToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Tag</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete "{tagToDelete?.name}"? This action cannot be undone.
              The tag will be removed from all investigations and permission grants.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTagToDelete(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Delete Tag
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
