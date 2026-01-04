import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  listInvestigationsApiV1InvestigationsGet,
  createInvestigationApiV1InvestigationsPost,
  getInvestigationApiV1InvestigationsInvestigationIdGet,
} from './generated/investigations/investigations'
import type { CreateInvestigationRequest } from './model'
import { queryKeys } from './query-keys'

// Re-export the request type
export type { CreateInvestigationRequest }

// Define proper response types (backend OpenAPI doesn't fully specify these)
export interface InvestigationResponse {
  investigation_id: string
  status: string
  created_at: string
}

export interface InvestigationEvent {
  type: string
  timestamp: string
  data: Record<string, unknown>
}

export interface Evidence {
  hypothesis_id: string
  query: string
  result_summary: string
  row_count: number
  supports_hypothesis: boolean | null
  confidence: number
  interpretation: string
}

export interface InvestigationFinding {
  investigation_id: string
  status: string
  root_cause: string | null
  confidence: number
  evidence: Evidence[]
  recommendations: string[]
  duration_seconds: number
}

export interface InvestigationStatusResponse {
  investigation_id: string
  status: string
  events: InvestigationEvent[]
  finding: InvestigationFinding | null
  error?: string
}

export interface InvestigationListItem {
  investigation_id: string
  status: string
  created_at: string
  dataset_id: string
}

export function useInvestigations() {
  return useQuery({
    queryKey: queryKeys.investigations.all,
    queryFn: async (): Promise<InvestigationListItem[]> => {
      try {
        const response = await listInvestigationsApiV1InvestigationsGet()
        return (Array.isArray(response) ? response : []) as unknown as InvestigationListItem[]
      } catch {
        return []
      }
    },
  })
}

export function useInvestigation(id: string) {
  return useQuery({
    queryKey: queryKeys.investigations.detail(id),
    queryFn: async (): Promise<InvestigationStatusResponse> => {
      const response = await getInvestigationApiV1InvestigationsInvestigationIdGet(id)
      return response as unknown as InvestigationStatusResponse
    },
    enabled: !!id,
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.status === 'completed' || data?.status === 'failed') {
        return false
      }
      return 2000
    },
  })
}

export function useCreateInvestigation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (data: CreateInvestigationRequest): Promise<InvestigationResponse> => {
      const response = await createInvestigationApiV1InvestigationsPost(data)
      return response as InvestigationResponse
    },
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.investigations.all,
      })
    },
  })
}
