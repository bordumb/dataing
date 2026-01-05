import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import customInstance from './client'
import { queryKeys } from './query-keys'

export type TargetType = 'hypothesis' | 'query' | 'evidence' | 'synthesis' | 'investigation'

export interface FeedbackCreate {
  target_type: TargetType
  target_id: string
  investigation_id: string
  rating: 1 | -1
  reason?: string
  comment?: string
}

export interface FeedbackResponse {
  id: string
  created_at: string
}

export interface FeedbackItem {
  id: string
  target_type: string
  target_id: string
  rating: number
  reason: string | null
  comment: string | null
  created_at: string
}

async function submitFeedback(data: FeedbackCreate): Promise<FeedbackResponse> {
  return customInstance<FeedbackResponse>({
    url: '/api/v1/feedback/',
    method: 'POST',
    data,
  })
}

async function getInvestigationFeedback(investigationId: string): Promise<FeedbackItem[]> {
  return customInstance<FeedbackItem[]>({
    url: `/api/v1/feedback/investigations/${investigationId}`,
    method: 'GET',
  })
}

export function useInvestigationFeedback(investigationId: string) {
  return useQuery({
    queryKey: queryKeys.feedback.investigation(investigationId),
    queryFn: () => getInvestigationFeedback(investigationId),
    enabled: !!investigationId,
  })
}

export function useSubmitFeedback(investigationId: string) {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: submitFeedback,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.feedback.investigation(investigationId) })
    },
  })
}
