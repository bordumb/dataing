import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import customInstance from './client'
import { queryKeys } from './query-keys'

// Re-export generated types for convenience
export type { SchemaCommentResponse, SchemaCommentCreate, SchemaCommentUpdate } from './model'

// Import types for internal use
import type {
  SchemaCommentResponse,
  SchemaCommentCreate,
  SchemaCommentUpdate,
} from './model'

async function listSchemaComments(
  datasetId: string,
  fieldName?: string
): Promise<SchemaCommentResponse[]> {
  const params = fieldName ? `?field_name=${encodeURIComponent(fieldName)}` : ''
  return customInstance<SchemaCommentResponse[]>({
    url: `/api/v1/datasets/${datasetId}/schema-comments${params}`,
    method: 'GET',
  })
}

async function createSchemaComment(
  datasetId: string,
  data: SchemaCommentCreate
): Promise<SchemaCommentResponse> {
  return customInstance<SchemaCommentResponse>({
    url: `/api/v1/datasets/${datasetId}/schema-comments`,
    method: 'POST',
    data,
  })
}

async function updateSchemaComment(
  datasetId: string,
  commentId: string,
  data: SchemaCommentUpdate
): Promise<SchemaCommentResponse> {
  return customInstance<SchemaCommentResponse>({
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
