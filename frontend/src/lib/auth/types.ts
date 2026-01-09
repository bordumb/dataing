/**
 * CRITICAL: DO NOT REMOVE THIS FILE
 *
 * Defines the role types used for RBAC and the demo role toggle,
 * plus auth-related types.
 */

export type OrgRole = 'viewer' | 'member' | 'admin' | 'owner'

export interface User {
  id: string
  email: string
  name: string | null
  org_id: string
  role: OrgRole
  created_at: string
}

export interface Organization {
  id: string
  name: string
  slug: string
  plan?: string
}

export interface OrgMembership {
  org_id: string
  org_name: string
  org_slug: string
  role: OrgRole
}

export interface LoginRequest {
  email: string
  password: string
  org_id?: string
}

export interface RegisterRequest {
  email: string
  password: string
  name: string
  org_name: string
}

export interface RefreshRequest {
  refresh_token: string
  org_id?: string
}

export interface AuthResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
  org: Organization
  role: OrgRole
}

export interface JwtPayload {
  sub: string
  org_id: string
  role: OrgRole
  exp: number
  iat: number
}

export interface AuthState {
  isAuthenticated: boolean
  isLoading: boolean
  user: User | null
  org: Organization | null
  role: OrgRole | null
  accessToken: string | null
}
