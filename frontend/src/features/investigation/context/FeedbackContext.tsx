import { createContext, useContext, useMemo, ReactNode } from 'react'
import {
  useInvestigationFeedback,
  useSubmitFeedback,
  FeedbackCreate,
  TargetType,
} from '@/lib/api/feedback'

interface FeedbackData {
  rating: 1 | -1
  reason?: string
  comment?: string
}

interface FeedbackState {
  ratings: Record<string, FeedbackData>
  isLoading: boolean
  submitFeedback: (params: Omit<FeedbackCreate, 'investigation_id'>) => Promise<void>
  getRating: (targetType: TargetType, targetId: string) => FeedbackData | null
}

const FeedbackContext = createContext<FeedbackState | null>(null)

interface FeedbackProviderProps {
  investigationId: string
  children: ReactNode
}

export function FeedbackProvider({ investigationId, children }: FeedbackProviderProps) {
  const { data: feedbackItems, isLoading } = useInvestigationFeedback(investigationId)
  const submitMutation = useSubmitFeedback(investigationId)

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
      {} as Record<string, FeedbackData>
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
    <FeedbackContext.Provider value={{ ratings, isLoading, submitFeedback, getRating }}>
      {children}
    </FeedbackContext.Provider>
  )
}

export function useFeedback() {
  const context = useContext(FeedbackContext)
  if (!context) {
    throw new Error('useFeedback must be used within FeedbackProvider')
  }
  return context
}
