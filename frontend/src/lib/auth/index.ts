/**
 * Auth module exports.
 */

// Types
export type {
  AuthResponse,
  AuthState,
  AuthTokens,
  JwtPayload,
  LoginRequest,
  Organization,
  OrgMembership,
  OrgRole,
  RefreshRequest,
  RegisterRequest,
  User,
} from './types'

// API
export { login, register, refreshToken, getCurrentUser, getUserOrgs, AuthApiError } from './api'

// Legacy API key auth (for backwards compatibility during migration)
export { AuthProvider, RequireAuth, useAuth } from './context'

// JWT auth
export { JwtAuthProvider, RequireJwtAuth, useJwtAuth } from './jwt-context'

// Demo role toggle
export { DemoRoleToggle } from './demo-role-toggle'

// Role utilities
export { useRole } from './use-role'
export { RoleGuard, ExactRoleGuard } from './role-guard'

// Org selector
export { OrgSelector } from './org-selector'
