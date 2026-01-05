import { createContext, useContext, useMemo, ReactNode } from 'react'
import {
  useInvestigationFeedback,
  useSubmitInvestigationFeedback,
  FeedbackCreate,
  TargetType,
} from '@/lib/api/investigation-feedback'

interface InvestigationFeedbackData {
  rating: 1 | -1
  reason?: string
  comment?: string
}

interface InvestigationFeedbackState {
  ratings: Record<string, InvestigationFeedbackData>
  isLoading: boolean
  submitFeedback: (params: Omit<FeedbackCreate, 'investigation_id'>) => Promise<void>
  getRating: (targetType: TargetType, targetId: string) => InvestigationFeedbackData | null
}

const InvestigationFeedbackContext = createContext<InvestigationFeedbackState | null>(null)

interface InvestigationFeedbackProviderProps {
  investigationId: string
  children: ReactNode
}

export function InvestigationFeedbackProvider({
  investigationId,
  children,
}: InvestigationFeedbackProviderProps) {
  const { data: feedbackItems, isLoading } = useInvestigationFeedback(investigationId)
  const submitMutation = useSubmitInvestigationFeedback(investigationId)

  const ratings = useMemo(() => {
    if (!feedbackItems) return {}
    return feedbackItems.reduce(
      (acc, item) => {
        const key = `${item.target_type}:${item.target_id}`
        acc[key] = {
          rating: item.rating as 1 | -1,
          reason: item.reason ?? undefined,
          comment: item.comment ?? undefined,
        }
        return acc
      },
      {} as Record<string, InvestigationFeedbackData>
    )
  }, [feedbackItems])

  const submitFeedback = async (params: Omit<FeedbackCreate, 'investigation_id'>) => {
    await submitMutation.mutateAsync({
      ...params,
      investigation_id: investigationId,
    })
  }

  const getRating = (targetType: TargetType, targetId: string) => {
    const key = `${targetType}:${targetId}`
    return ratings[key] ?? null
  }

  return (
    <InvestigationFeedbackContext.Provider
      value={{ ratings, isLoading, submitFeedback, getRating }}
    >
      {children}
    </InvestigationFeedbackContext.Provider>
  )
}

export function useInvestigationFeedbackContext() {
  const context = useContext(InvestigationFeedbackContext)
  if (!context) {
    throw new Error(
      'useInvestigationFeedbackContext must be used within InvestigationFeedbackProvider'
    )
  }
  return context
}
