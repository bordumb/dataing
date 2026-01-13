import { useState, useCallback, useEffect } from 'react'

type VoteValue = 1 | -1 | null

interface UseVoteStateReturn {
  getVote: (commentId: string) => VoteValue
  setVote: (commentId: string, vote: VoteValue) => void
}

/**
 * Hook to track user's votes locally with localStorage persistence.
 * This provides optimistic UI while the backend is the source of truth.
 */
export function useVoteState(datasetId: string): UseVoteStateReturn {
  const storageKey = `votes:${datasetId}`

  const [votes, setVotes] = useState<Record<string, VoteValue>>(() => {
    if (typeof window === 'undefined') return {}
    try {
      const stored = localStorage.getItem(storageKey)
      return stored ? JSON.parse(stored) : {}
    } catch {
      return {}
    }
  })

  // Persist to localStorage when votes change
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(votes))
    } catch {
      // Ignore localStorage errors
    }
  }, [votes, storageKey])

  const getVote = useCallback(
    (commentId: string): VoteValue => {
      return votes[commentId] ?? null
    },
    [votes]
  )

  const setVote = useCallback((commentId: string, vote: VoteValue) => {
    setVotes((prev) => ({ ...prev, [commentId]: vote }))
  }, [])

  return { getVote, setVote }
}
