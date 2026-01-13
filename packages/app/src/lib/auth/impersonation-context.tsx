/**
 * CRITICAL: DO NOT REMOVE THIS FILE
 *
 * Context provider for admin user impersonation in demo mode.
 * Allows admins to switch between user accounts to test multi-user features.
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react'

export interface DemoUser {
  id: string
  email: string
  name: string
  role: 'admin' | 'member' | 'viewer'
}

// Demo users - must match seed.py UUIDs
export const DEMO_USERS: DemoUser[] = [
  {
    id: '00000000-0000-0000-0000-000000000012',
    email: 'kimitaka@demo.dataing.io',
    name: 'Kimitaka',
    role: 'admin',
  },
  {
    id: '00000000-0000-0000-0000-000000000010',
    email: 'bob@demo.dataing.io',
    name: 'Bob',
    role: 'member',
  },
  {
    id: '00000000-0000-0000-0000-000000000011',
    email: 'alice@demo.dataing.io',
    name: 'Alice',
    role: 'member',
  },
]

interface ImpersonationContextValue {
  /** Currently impersonated user (or real user if not impersonating) */
  currentUser: DemoUser
  /** The real admin user doing the impersonation */
  realUser: DemoUser
  /** Whether impersonation is active (currentUser !== realUser) */
  isImpersonating: boolean
  /** Switch to impersonate a different user */
  impersonate: (userId: string) => void
  /** Stop impersonating and return to real user */
  stopImpersonating: () => void
  /** Whether the real user is an admin (can impersonate) */
  canImpersonate: boolean
  /** All available demo users */
  availableUsers: DemoUser[]
}

const ImpersonationContext = createContext<ImpersonationContextValue | null>(null)

const STORAGE_KEY = 'dataing_impersonated_user_id'

interface ImpersonationProviderProps {
  children: ReactNode
}

/**
 * Provider for user impersonation state.
 *
 * CRITICAL: DO NOT REMOVE - Required for multi-user demo testing.
 */
export function ImpersonationProvider({ children }: ImpersonationProviderProps) {
  // In demo mode, default to Kimitaka (admin)
  const realUser = DEMO_USERS[0] // Kimitaka - admin

  // Load saved impersonation from localStorage
  const [currentUserId, setCurrentUserId] = useState<string>(() => {
    if (typeof window === 'undefined') return realUser.id
    const saved = localStorage.getItem(STORAGE_KEY)
    return saved || realUser.id
  })

  const currentUser =
    DEMO_USERS.find((u) => u.id === currentUserId) || realUser

  const isImpersonating = currentUserId !== realUser.id
  const canImpersonate = realUser.role === 'admin'

  const impersonate = useCallback((userId: string) => {
    const user = DEMO_USERS.find((u) => u.id === userId)
    if (user) {
      setCurrentUserId(userId)
      localStorage.setItem(STORAGE_KEY, userId)
    }
  }, [])

  const stopImpersonating = useCallback(() => {
    setCurrentUserId(realUser.id)
    localStorage.removeItem(STORAGE_KEY)
  }, [realUser.id])

  // Sync with localStorage changes (for multi-tab support)
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) {
        setCurrentUserId(e.newValue || realUser.id)
      }
    }
    window.addEventListener('storage', handleStorageChange)
    return () => window.removeEventListener('storage', handleStorageChange)
  }, [realUser.id])

  return (
    <ImpersonationContext.Provider
      value={{
        currentUser,
        realUser,
        isImpersonating,
        impersonate,
        stopImpersonating,
        canImpersonate,
        availableUsers: DEMO_USERS,
      }}
    >
      {children}
    </ImpersonationContext.Provider>
  )
}

/**
 * Hook to access impersonation context.
 *
 * @throws Error if used outside of ImpersonationProvider
 */
export function useImpersonation(): ImpersonationContextValue {
  const context = useContext(ImpersonationContext)
  if (!context) {
    throw new Error('useImpersonation must be used within an ImpersonationProvider')
  }
  return context
}
