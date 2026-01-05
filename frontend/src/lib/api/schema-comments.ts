import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import customInstance from './client'
import { queryKeys } from './query-keys'

export interface SchemaComment {
  id: string
  dataset_id: string
  field_name: string
  parent_id: string | null
  content: string
  author_id: string | null
  author_name: string | null
  upvotes: number
  downvotes: number
  created_at: string
  updated_at: string
}

export interface SchemaCommentCreate {
  field_name: string
  content: string
  parent_id?: string
}

export interface SchemaCommentUpdate {
  content: string
}

async function listSchemaComments(
  datasetId: string,
  fieldName?: string
): Promise<SchemaComment[]> {
  const params = fieldName ? `?field_name=${encodeURIComponent(fieldName)}` : ''
  return customInstance<SchemaComment[]>({
    url: `/api/v1/datasets/${datasetId}/schema-comments${params}`,
    method: 'GET',
  })
}

async function createSchemaComment(
  datasetId: string,
  data: SchemaCommentCreate
): Promise<SchemaComment> {
  return customInstance<SchemaComment>({
    url: `/api/v1/datasets/${datasetId}/schema-comments`,
    method: 'POST',
    data,
  })
}

async function updateSchemaComment(
  datasetId: string,
  commentId: string,
  data: SchemaCommentUpdate
): Promise<SchemaComment> {
  return customInstance<SchemaComment>({
    url: `/api/v1/datasets/${datasetId}/schema-comments/${commentId}`,
    method: 'PATCH',
    data,
  })
}

async function deleteSchemaComment(datasetId: string, commentId: string): Promise<void> {
  return customInstance<void>({
    url: `/api/v1/datasets/${datasetId}/schema-comments/${commentId}`,
    method: 'DELETE',
  })
}

export function useSchemaComments(datasetId: string, fieldName?: string) {
  return useQuery({
    queryKey: queryKeys.schemaComments.list(datasetId, fieldName),
    queryFn: () => listSchemaComments(datasetId, fieldName),
    enabled: !!datasetId,
  })
}

export function useCreateSchemaComment(datasetId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data: SchemaCommentCreate) => createSchemaComment(datasetId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.schemaComments.all(datasetId) })
    },
  })
}

export function useUpdateSchemaComment(datasetId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ commentId, data }: { commentId: string; data: SchemaCommentUpdate }) =>
      updateSchemaComment(datasetId, commentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.schemaComments.all(datasetId) })
    },
  })
}

export function useDeleteSchemaComment(datasetId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (commentId: string) => deleteSchemaComment(datasetId, commentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.schemaComments.all(datasetId) })
    },
  })
}
