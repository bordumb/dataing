import type { UpgradeError } from '@/components/shared/upgrade-required-modal'

type UpgradeErrorListener = (error: UpgradeError | null) => void

let currentError: UpgradeError | null = null
const listeners: Set<UpgradeErrorListener> = new Set()

export function setUpgradeError(error: UpgradeError | null) {
  currentError = error
  listeners.forEach((listener) => listener(error))
}

export function subscribeToUpgradeError(listener: UpgradeErrorListener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function getUpgradeError() {
  return currentError
}
