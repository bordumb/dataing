import { useMutation, useQueryClient } from '@tanstack/react-query'
import customInstance from './client'
import { queryKeys } from './query-keys'

export type CommentType = 'schema' | 'knowledge'

export interface VoteCreate {
  vote: 1 | -1
}

async function voteOnComment(
  commentType: CommentType,
  commentId: string,
  vote: VoteCreate
): Promise<void> {
  return customInstance<void>({
    url: `/api/v1/comments/${commentType}/${commentId}/vote`,
    method: 'POST',
    data: vote,
  })
}

async function removeVote(commentType: CommentType, commentId: string): Promise<void> {
  return customInstance<void>({
    url: `/api/v1/comments/${commentType}/${commentId}/vote`,
    method: 'DELETE',
  })
}

export function useVoteOnComment(datasetId: string, commentType: CommentType) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ commentId, vote }: { commentId: string; vote: VoteCreate }) =>
      voteOnComment(commentType, commentId, vote),
    onSuccess: () => {
      // Invalidate the appropriate comments query
      if (commentType === 'schema') {
        queryClient.invalidateQueries({ queryKey: queryKeys.schemaComments.all(datasetId) })
      } else {
        queryClient.invalidateQueries({ queryKey: queryKeys.knowledgeComments.all(datasetId) })
      }
    },
  })
}

export function useRemoveVote(datasetId: string, commentType: CommentType) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (commentId: string) => removeVote(commentType, commentId),
    onSuccess: () => {
      if (commentType === 'schema') {
        queryClient.invalidateQueries({ queryKey: queryKeys.schemaComments.all(datasetId) })
      } else {
        queryClient.invalidateQueries({ queryKey: queryKeys.knowledgeComments.all(datasetId) })
      }
    },
  })
}
