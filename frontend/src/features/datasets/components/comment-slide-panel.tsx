import { MessageSquare } from 'lucide-react'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { CommentThread } from './comment-thread'
import { CommentEditor } from './comment-editor'
import {
  useSchemaComments,
  useCreateSchemaComment,
} from '@/lib/api/schema-comments'
import { useVoteOnComment, useRemoveVote } from '@/lib/api/comment-votes'

interface CommentSlidePanelProps {
  datasetId: string
  fieldName: string
  isOpen: boolean
  onClose: () => void
}

export function CommentSlidePanel({
  datasetId,
  fieldName,
  isOpen,
  onClose,
}: CommentSlidePanelProps) {
  const { data: comments = [], isLoading, isError } = useSchemaComments(datasetId, fieldName)
  const createComment = useCreateSchemaComment(datasetId)
  const voteOnComment = useVoteOnComment(datasetId, 'schema')
  const removeVote = useRemoveVote(datasetId, 'schema')

  const handleCreateComment = (content: string, parentId?: string) => {
    createComment.mutate({
      field_name: fieldName,
      content,
      parent_id: parentId,
    })
  }

  const handleVote = (commentId: string, vote: 1 | -1) => {
    voteOnComment.mutate({ commentId, vote: { vote } })
  }

  const handleRemoveVote = (commentId: string) => {
    removeVote.mutate(commentId)
  }

  return (
    <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <SheetContent side="right" className="w-[450px] sm:max-w-[450px] flex flex-col">
        <SheetHeader className="border-b pb-4">
          <SheetTitle className="flex items-center gap-2">
            <MessageSquare className="h-5 w-5" />
            Comments
          </SheetTitle>
          <SheetDescription>
            Discussion for field: <span className="font-mono font-medium">{fieldName}</span>
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto py-4 space-y-6">
          {/* New comment editor at the top */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-muted-foreground">Add a comment</h4>
            <CommentEditor
              placeholder="Share your knowledge about this field..."
              submitLabel="Post Comment"
              onSubmit={(content) => handleCreateComment(content)}
              isSubmitting={createComment.isPending}
            />
          </div>

          {/* Comments list */}
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-muted-foreground">
              {comments.length > 0
                ? `${comments.length} comment${comments.length === 1 ? '' : 's'}`
                : 'No comments yet'}
            </h4>

            {isLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary" />
              </div>
            ) : isError ? (
              <div className="text-center text-destructive py-8">
                Failed to load comments. Please try again.
              </div>
            ) : comments.length === 0 ? (
              <div className="text-center text-muted-foreground py-8 bg-muted/50 rounded-lg">
                <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>No comments yet.</p>
                <p className="text-sm">Be the first to share knowledge about this field!</p>
              </div>
            ) : (
              <CommentThread
                comments={comments}
                onReply={(parentId, content) => handleCreateComment(content, parentId)}
                onVote={handleVote}
                onRemoveVote={handleRemoveVote}
                isSubmitting={createComment.isPending}
              />
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
