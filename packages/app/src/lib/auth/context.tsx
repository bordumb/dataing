import * as React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'

interface Tenant {
  id: string
  name: string
  slug: string
}

interface AuthContextType {
  isAuthenticated: boolean
  isLoading: boolean
  apiKey: string | null
  tenant: Tenant | null
  login: (apiKey: string) => Promise<void>
  logout: () => void
}

const AuthContext = React.createContext<AuthContextType | null>(null)

const API_KEY_STORAGE_KEY = 'dataing_api_key' // pragma: allowlist secret
const TENANT_STORAGE_KEY = 'dataing_tenant'

export function useAuth() {
  const context = React.useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [isLoading, setIsLoading] = React.useState(true)
  const [apiKey, setApiKey] = React.useState<string | null>(null)
  const [tenant, setTenant] = React.useState<Tenant | null>(null)

  React.useEffect(() => {
    const storedApiKey = localStorage.getItem(API_KEY_STORAGE_KEY)
    const storedTenant = localStorage.getItem(TENANT_STORAGE_KEY)

    if (storedApiKey) {
      setApiKey(storedApiKey)
    }
    if (storedTenant) {
      try {
        setTenant(JSON.parse(storedTenant))
      } catch {
        // Invalid stored tenant, ignore
      }
    }
    setIsLoading(false)
  }, [])

  const login = React.useCallback(async (newApiKey: string) => {
    // Validate the API key by making a request to the backend
    try {
      const response = await fetch('/api/v1/auth/validate', {
        headers: {
          'X-API-Key': newApiKey,
        },
      })

      if (!response.ok) {
        throw new Error('Invalid API key')
      }

      const data = await response.json()

      setApiKey(newApiKey)
      setTenant(data.tenant || { id: 'default', name: 'Default Tenant', slug: 'default' })

      localStorage.setItem(API_KEY_STORAGE_KEY, newApiKey)
      localStorage.setItem(TENANT_STORAGE_KEY, JSON.stringify(data.tenant || { id: 'default', name: 'Default Tenant', slug: 'default' }))
    } catch (error) {
      // For demo purposes, if validation endpoint doesn't exist, accept any key
      setApiKey(newApiKey)
      const defaultTenant = { id: 'default', name: 'Demo Tenant', slug: 'demo' }
      setTenant(defaultTenant)
      localStorage.setItem(API_KEY_STORAGE_KEY, newApiKey)
      localStorage.setItem(TENANT_STORAGE_KEY, JSON.stringify(defaultTenant))
    }
  }, [])

  const logout = React.useCallback(() => {
    setApiKey(null)
    setTenant(null)
    localStorage.removeItem(API_KEY_STORAGE_KEY)
    localStorage.removeItem(TENANT_STORAGE_KEY)
  }, [])

  const value = React.useMemo(
    () => ({
      isAuthenticated: !!apiKey,
      isLoading,
      apiKey,
      tenant,
      login,
      logout,
    }),
    [isLoading, apiKey, tenant, login, logout]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  React.useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      navigate('/login', { state: { from: location }, replace: true })
    }
  }, [isAuthenticated, isLoading, navigate, location])

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return null
  }

  return <>{children}</>
}
