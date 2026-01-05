/**
 * Auth types for JWT-based authentication.
 */

export interface User {
  id: string
  email: string
  name: string | null
}

export interface Organization {
  id: string
  name: string
  slug: string
  plan: string
}

export type OrgRole = 'viewer' | 'member' | 'admin' | 'owner'

export interface AuthTokens {
  accessToken: string
  refreshToken: string
  tokenType: string
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
  org: Organization
  role: OrgRole
}

export interface LoginRequest {
  email: string
  password: string
  org_id: string
}

export interface RegisterRequest {
  email: string
  password: string
  name: string
  org_name: string
  org_slug?: string
}

export interface RefreshRequest {
  refresh_token: string
  org_id: string
}

export interface AuthState {
  isAuthenticated: boolean
  isLoading: boolean
  user: User | null
  org: Organization | null
  role: OrgRole | null
  accessToken: string | null
}

/**
 * Decoded JWT payload structure.
 */
export interface JwtPayload {
  sub: string // user_id
  org_id: string
  role: OrgRole
  teams: string[]
  exp: number
  iat: number
}
