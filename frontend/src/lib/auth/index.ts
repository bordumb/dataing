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
  OrgRole,
  RefreshRequest,
  RegisterRequest,
  User,
} from './types'

// API
export { login, register, refreshToken, getCurrentUser, AuthApiError } from './api'

// Legacy API key auth (for backwards compatibility during migration)
export { AuthProvider, RequireAuth, useAuth } from './context'

// JWT auth
export { JwtAuthProvider, RequireJwtAuth, useJwtAuth } from './jwt-context'
