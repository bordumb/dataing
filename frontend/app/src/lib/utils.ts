import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'
import { v5 as uuidv5 } from 'uuid'

// Namespace UUID for generating deterministic feedback target IDs
// This is a fixed UUID that ensures globally unique IDs when combined with local identifiers
const FEEDBACK_NAMESPACE = '6ba7b810-9dad-11d1-80b4-00c04fd430c8' // DNS namespace UUID

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleString()
}

export function formatPercentage(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  return `${mins}m ${secs.toFixed(0)}s`
}

export function formatNumber(num: number): string {
  return new Intl.NumberFormat().format(num)
}

export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 30) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

/**
 * Generate a deterministic UUID v5 from a composite key.
 * Used for creating globally unique IDs for feedback targets that don't have native UUIDs.
 *
 * @param investigationId - The investigation UUID
 * @param targetType - The type of target (hypothesis, query, evidence)
 * @param localId - The local identifier within the investigation (e.g., "hypo-1", "hypo-1-0")
 * @returns A deterministic UUID that's globally unique
 */
export function generateFeedbackTargetId(
  investigationId: string,
  targetType: string,
  localId: string
): string {
  const compositeKey = `${investigationId}:${targetType}:${localId}`
  return uuidv5(compositeKey, FEEDBACK_NAMESPACE)
}
