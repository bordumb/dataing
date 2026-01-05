import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import customInstance from './client'
import { queryKeys } from './query-keys'

export interface KnowledgeComment {
  id: string
  dataset_id: string
  parent_id: string | null
  content: string
  author_id: string | null
  author_name: string | null
  upvotes: number
  downvotes: number
  created_at: string
  updated_at: string
}

export interface KnowledgeCommentCreate {
  content: string
  parent_id?: string
}

export interface KnowledgeCommentUpdate {
  content: string
}

async function listKnowledgeComments(datasetId: string): Promise<KnowledgeComment[]> {
  return customInstance<KnowledgeComment[]>({
    url: `/api/v1/datasets/${datasetId}/knowledge-comments`,
    method: 'GET',
  })
}

async function createKnowledgeComment(
  datasetId: string,
  data: KnowledgeCommentCreate
): Promise<KnowledgeComment> {
  return customInstance<KnowledgeComment>({
    url: `/api/v1/datasets/${datasetId}/knowledge-comments`,
    method: 'POST',
    data,
  })
}

async function updateKnowledgeComment(
  datasetId: string,
  commentId: string,
  data: KnowledgeCommentUpdate
): Promise<KnowledgeComment> {
  return customInstance<KnowledgeComment>({
    url: `/api/v1/datasets/${datasetId}/knowledge-comments/${commentId}`,
    method: 'PATCH',
    data,
  })
}

async function deleteKnowledgeComment(datasetId: string, commentId: string): Promise<void> {
  return customInstance<void>({
    url: `/api/v1/datasets/${datasetId}/knowledge-comments/${commentId}`,
    method: 'DELETE',
  })
}

export function useKnowledgeComments(datasetId: string) {
  return useQuery({
    queryKey: queryKeys.knowledgeComments.list(datasetId),
    queryFn: () => listKnowledgeComments(datasetId),
    enabled: !!datasetId,
  })
}

export function useCreateKnowledgeComment(datasetId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: KnowledgeCommentCreate) => createKnowledgeComment(datasetId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledgeComments.all(datasetId) })
    },
  })
}

export function useUpdateKnowledgeComment(datasetId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ commentId, data }: { commentId: string; data: KnowledgeCommentUpdate }) =>
      updateKnowledgeComment(datasetId, commentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledgeComments.all(datasetId) })
    },
  })
}

export function useDeleteKnowledgeComment(datasetId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (commentId: string) => deleteKnowledgeComment(datasetId, commentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.knowledgeComments.all(datasetId) })
    },
  })
}
