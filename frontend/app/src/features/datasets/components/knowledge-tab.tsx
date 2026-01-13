import { useMemo } from 'react'
import { Brain, MessageSquare } from 'lucide-react'
import { CommentThread } from './comment-thread'
import { CommentEditor } from './comment-editor'
import {
  useKnowledgeComments,
  useCreateKnowledgeComment,
} from '@/lib/api/knowledge-comments'
import { useVoteOnComment, useRemoveVote } from '@/lib/api/comment-votes'
import { useVoteState } from '@/lib/hooks/useVoteState'
import type { KnowledgeCommentResponse } from '@/lib/api/model'

interface KnowledgeTabProps {
  datasetId: string
}

export function KnowledgeTab({ datasetId }: KnowledgeTabProps) {
  const { data: comments = [], isLoading, isError } = useKnowledgeComments(datasetId)
  const createComment = useCreateKnowledgeComment(datasetId)
  const voteOnComment = useVoteOnComment(datasetId, 'knowledge')
  const removeVoteMutation = useRemoveVote(datasetId, 'knowledge')
  const { getVote, setVote } = useVoteState(datasetId)

  // Sort comments: (upvotes - downvotes) descending, then created_at descending
  const sortedComments = useMemo(() => {
    return [...comments].sort((a, b) => {
      const scoreA = a.upvotes - a.downvotes
      const scoreB = b.upvotes - b.downvotes
      if (scoreB !== scoreA) {
        return scoreB - scoreA
      }
      // Secondary sort by created_at descending
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })
  }, [comments])

  // Group comments: root threads (parent_id = null) and replies (parent_id != null)
  const rootComments = useMemo(
    () => sortedComments.filter((c: KnowledgeCommentResponse) => !c.parent_id),
    [sortedComments]
  )

  const handleCreateComment = (content: string, parentId?: string) => {
    createComment.mutate({
      content,
      parent_id: parentId,
    })
  }

  const handleVote = (commentId: string, vote: 1 | -1) => {
    setVote(commentId, vote)
    voteOnComment.mutate({ commentId, vote: { vote } })
  }

  const handleRemoveVote = (commentId: string) => {
    setVote(commentId, null)
    removeVoteMutation.mutate(commentId)
  }

  const rootCount = rootComments.length
  const totalCount = comments.length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Brain className="h-5 w-5 text-muted-foreground" />
          <h2 className="text-lg font-semibold">Dataset Knowledge</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Share insights, documentation, and discussions about this dataset. Help your team
          understand how to use this data effectively.
        </p>
      </div>

      {/* New comment editor */}
      <div className="space-y-2">
        <h4 className="text-sm font-medium text-muted-foreground">Start a discussion</h4>
        <CommentEditor
          placeholder="Share knowledge about this dataset... (Markdown supported)"
          submitLabel="Post"
          onSubmit={(content) => handleCreateComment(content)}
          isSubmitting={createComment.isPending}
        />
      </div>

      {/* Comments list */}
      <div className="space-y-2">
        <h4 className="text-sm font-medium text-muted-foreground">
          {rootCount > 0
            ? `${rootCount} discussion${rootCount === 1 ? '' : 's'} (${totalCount} comment${totalCount === 1 ? '' : 's'} total)`
            : 'No discussions yet'}
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
            <p>No knowledge shared yet.</p>
            <p className="text-sm">
              Be the first to document insights about this dataset!
            </p>
          </div>
        ) : (
          <CommentThread
            comments={sortedComments}
            onReply={(parentId, content) => handleCreateComment(content, parentId)}
            onVote={handleVote}
            onRemoveVote={handleRemoveVote}
            isSubmitting={createComment.isPending}
            getVote={getVote}
          />
        )}
      </div>
    </div>
  )
}
