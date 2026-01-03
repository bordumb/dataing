import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import customInstance from './client'
import type {
  CreateInvestigationRequest,
  InvestigationResponse,
  InvestigationStatusResponse,
  InvestigationListItem,
} from './types'

const INVESTIGATIONS_KEY = 'investigations'

export function useInvestigations() {
  return useQuery({
    queryKey: [INVESTIGATIONS_KEY],
    queryFn: async () => {
      try {
        const response = await customInstance<InvestigationListItem[]>({
          url: '/investigations',
          method: 'GET',
        })
        // Ensure we always return an array
        return Array.isArray(response) ? response : []
      } catch {
        // Return empty array if API is unavailable
        return []
      }
    },
  })
}

export function useInvestigation(id: string) {
  return useQuery({
    queryKey: [INVESTIGATIONS_KEY, id],
    queryFn: () =>
      customInstance<InvestigationStatusResponse>({
        url: `/investigations/${id}`,
        method: 'GET',
      }),
    refetchInterval: (query) => {
      const data = query.state.data
      if (data?.status === 'completed' || data?.status === 'failed') {
        return false
      }
      return 2000 // Poll every 2 seconds while in progress
    },
  })
}

export function useCreateInvestigation() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (data: CreateInvestigationRequest) =>
      customInstance<InvestigationResponse>({
        url: '/investigations',
        method: 'POST',
        data,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [INVESTIGATIONS_KEY] })
    },
  })
}
