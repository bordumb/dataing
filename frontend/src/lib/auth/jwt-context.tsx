/**
 * JWT-based authentication context.
 *
 * Provides login, logout, registration, and automatic token refresh.
 */

import * as React from 'react'
import { useNavigate, useLocation } from 'react-router-dom'

import * as authApi from './api'
import type {
  AuthState,
  JwtPayload,
  LoginRequest,
  Organization,
  OrgRole,
  RegisterRequest,
  User,
} from './types'

// Storage keys
const ACCESS_TOKEN_KEY = 'dataing_access_token' // pragma: allowlist secret
const REFRESH_TOKEN_KEY = 'dataing_refresh_token' // pragma: allowlist secret
const USER_KEY = 'dataing_user'
const ORG_KEY = 'dataing_org'
const ROLE_KEY = 'dataing_role'

interface JwtAuthContextType extends AuthState {
  login: (request: LoginRequest) => Promise<void>
  register: (request: RegisterRequest) => Promise<void>
  logout: () => void
  switchOrg: (orgId: string, orgName?: string, orgSlug?: string) => Promise<void>
  // Demo role override for testing
  demoRole: OrgRole | null
  setDemoRole: (role: OrgRole | null) => void
  effectiveRole: OrgRole | null // demoRole if set, otherwise real role
}

const JwtAuthContext = React.createContext<JwtAuthContextType | null>(null)

/**
 * Hook to access JWT auth context.
 */
export function useJwtAuth() {
  const context = React.useContext(JwtAuthContext)
  if (!context) {
    throw new Error('useJwtAuth must be used within a JwtAuthProvider')
  }
  return context
}

/**
 * Decode JWT payload (without verification - server does that).
 */
function decodeJwt(token: string): JwtPayload | null {
  try {
    const base64Url = token.split('.')[1]
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    )
    return JSON.parse(jsonPayload)
  } catch {
    return null
  }
}

/**
 * Check if token is expired (with 60s buffer).
 */
function isTokenExpired(token: string): boolean {
  const payload = decodeJwt(token)
  if (!payload) return true
  return Date.now() >= (payload.exp - 60) * 1000
}

/**
 * JWT auth provider component.
 */
export function JwtAuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = React.useState<AuthState>({
    isAuthenticated: false,
    isLoading: true,
    user: null,
    org: null,
    role: null,
    accessToken: null,
  })

  // Demo role override for testing different permission levels
  const [demoRole, setDemoRole] = React.useState<OrgRole | null>(null)

  // Effective role: demo override takes precedence
  const effectiveRole = demoRole ?? state.role

  const clearStorage = React.useCallback(() => {
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    localStorage.removeItem(ORG_KEY)
    localStorage.removeItem(ROLE_KEY)
  }, [])

  // Load stored auth on mount
  React.useEffect(() => {
    const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY)
    const userJson = localStorage.getItem(USER_KEY)
    const orgJson = localStorage.getItem(ORG_KEY)
    const role = localStorage.getItem(ROLE_KEY) as OrgRole | null

    if (accessToken && !isTokenExpired(accessToken) && userJson && orgJson) {
      try {
        const user = JSON.parse(userJson) as User
        const org = JSON.parse(orgJson) as Organization
        setState({
          isAuthenticated: true,
          isLoading: false,
          user,
          org,
          role,
          accessToken,
        })
      } catch {
        // Invalid stored data, clear and start fresh
        clearStorage()
        setState((s) => ({ ...s, isLoading: false }))
      }
    } else {
      // Try to refresh if we have a refresh token
      const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
      const orgId = orgJson ? JSON.parse(orgJson).id : null

      if (refreshToken && orgId) {
        authApi
          .refreshToken({ refresh_token: refreshToken, org_id: orgId })
          .then((response) => {
            localStorage.setItem(ACCESS_TOKEN_KEY, response.access_token)
            setState((s) => ({
              ...s,
              isAuthenticated: true,
              isLoading: false,
              accessToken: response.access_token,
            }))
          })
          .catch(() => {
            clearStorage()
            setState((s) => ({ ...s, isLoading: false }))
          })
      } else {
        setState((s) => ({ ...s, isLoading: false }))
      }
    }
  }, [clearStorage])

  const saveAuth = React.useCallback(
    (
      accessToken: string,
      refreshToken: string,
      user: User,
      org: Organization,
      role: OrgRole
    ) => {
      localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
      localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
      localStorage.setItem(USER_KEY, JSON.stringify(user))
      localStorage.setItem(ORG_KEY, JSON.stringify(org))
      localStorage.setItem(ROLE_KEY, role)
    },
    []
  )

  const login = React.useCallback(
    async (request: LoginRequest) => {
      const response = await authApi.login(request)
      saveAuth(
        response.access_token,
        response.refresh_token,
        response.user,
        response.org,
        response.role
      )
      setState({
        isAuthenticated: true,
        isLoading: false,
        user: response.user,
        org: response.org,
        role: response.role,
        accessToken: response.access_token,
      })
    },
    [saveAuth]
  )

  const register = React.useCallback(
    async (request: RegisterRequest) => {
      const response = await authApi.register(request)
      saveAuth(
        response.access_token,
        response.refresh_token,
        response.user,
        response.org,
        response.role
      )
      setState({
        isAuthenticated: true,
        isLoading: false,
        user: response.user,
        org: response.org,
        role: response.role,
        accessToken: response.access_token,
      })
    },
    [saveAuth]
  )

  const logout = React.useCallback(() => {
    clearStorage()
    setState({
      isAuthenticated: false,
      isLoading: false,
      user: null,
      org: null,
      role: null,
      accessToken: null,
    })
  }, [clearStorage])

  const switchOrg = React.useCallback(
    async (orgId: string, orgName?: string, orgSlug?: string) => {
      const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
      if (!refreshToken) {
        throw new Error('No refresh token available')
      }

      const response = await authApi.refreshToken({
        refresh_token: refreshToken,
        org_id: orgId,
      })

      // Decode the new token to get updated role
      const payload = decodeJwt(response.access_token)
      const newRole = payload?.role as OrgRole | null

      // Build new org object
      const newOrg: Organization = {
        id: orgId,
        name: orgName ?? 'Organization',
        slug: orgSlug ?? orgId,
        plan: 'pro',
      }

      // Update localStorage
      localStorage.setItem(ACCESS_TOKEN_KEY, response.access_token)
      localStorage.setItem(ORG_KEY, JSON.stringify(newOrg))
      if (newRole) {
        localStorage.setItem(ROLE_KEY, newRole)
      }

      // Update state
      setState((s) => ({
        ...s,
        accessToken: response.access_token,
        org: newOrg,
        role: newRole,
      }))
    },
    []
  )

  const value = React.useMemo(
    () => ({
      ...state,
      login,
      register,
      logout,
      switchOrg,
      demoRole,
      setDemoRole,
      effectiveRole,
    }),
    [state, login, register, logout, switchOrg, demoRole, effectiveRole]
  )

  return (
    <JwtAuthContext.Provider value={value}>{children}</JwtAuthContext.Provider>
  )
}

/**
 * Require JWT authentication - redirects to login if not authenticated.
 */
export function RequireJwtAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useJwtAuth()
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
