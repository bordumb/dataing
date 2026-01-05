'use client'

import { useState } from 'react'
import { CommentItem } from './comment-item'
import { CommentEditor } from './comment-editor'
import type { SchemaCommentResponse, KnowledgeCommentResponse } from '@/lib/api/model'

type Comment = SchemaCommentResponse | KnowledgeCommentResponse

interface CommentThreadProps {
  comments: Comment[]
  onReply: (parentId: string, content: string) => void
  onVote: (commentId: string, vote: 1 | -1) => void
  onRemoveVote: (commentId: string) => void
  onDelete?: (commentId: string) => void
  isSubmitting?: boolean
  getVote: (commentId: string) => 1 | -1 | null
}

export function CommentThread({
  comments,
  onReply,
  onVote,
  onRemoveVote,
  onDelete,
  isSubmitting,
  getVote,
}: CommentThreadProps) {
  const [replyingTo, setReplyingTo] = useState<string | null>(null)

  // Build thread structure from flat list
  const rootComments = comments.filter((c) => !c.parent_id)
  const childComments = comments.filter((c) => c.parent_id)

  const getReplies = (parentId: string) =>
    childComments.filter((c) => c.parent_id === parentId)

  const renderComment = (comment: Comment, isNested = false) => (
    <div key={comment.id} className="space-y-2">
      <CommentItem
        comment={comment}
        isNested={isNested}
        onReply={() => setReplyingTo(comment.id)}
        onVote={(vote) => onVote(comment.id, vote)}
        onRemoveVote={() => onRemoveVote(comment.id)}
        onDelete={onDelete ? () => onDelete(comment.id) : undefined}
        userVote={getVote(comment.id)}
      />

      {replyingTo === comment.id && (
        <div className={isNested ? 'ml-6 pl-4' : 'ml-6'}>
          <CommentEditor
            placeholder="Write a reply..."
            submitLabel="Reply"
            onSubmit={(content) => {
              onReply(comment.id, content)
              setReplyingTo(null)
            }}
            onCancel={() => setReplyingTo(null)}
            isSubmitting={isSubmitting}
          />
        </div>
      )}

      {getReplies(comment.id).map((reply) => renderComment(reply, true))}
    </div>
  )

  return (
    <div className="space-y-4">
      {rootComments.map((comment) => renderComment(comment))}
    </div>
  )
}
