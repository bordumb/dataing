/**
 * Auth API client for login, registration, and token management.
 */

import type {
  AuthResponse,
  LoginRequest,
  OrgMembership,
  RefreshRequest,
  RegisterRequest,
} from './types'

// API base URL - empty for same-origin (dev), set VITE_API_URL for production
const API_URL = import.meta.env.VITE_API_URL || ''
const API_BASE = `${API_URL}/api/v1/auth`

class AuthApiError extends Error {
  constructor(
    message: string,
    public statusCode: number
  ) {
    super(message)
    this.name = 'AuthApiError'
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new AuthApiError(
      errorData.detail || `HTTP error ${response.status}`,
      response.status
    )
  }
  return response.json()
}

/**
 * Login with email, password, and organization.
 */
export async function login(request: LoginRequest): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE}/login`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })
  return handleResponse<AuthResponse>(response)
}

/**
 * Register new user and create organization.
 */
export async function register(request: RegisterRequest): Promise<AuthResponse> {
  const response = await fetch(`${API_BASE}/register`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })
  return handleResponse<AuthResponse>(response)
}

/**
 * Refresh access token using refresh token.
 */
export async function refreshToken(
  request: RefreshRequest
): Promise<{ access_token: string; token_type: string }> {
  const response = await fetch(`${API_BASE}/refresh`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(request),
  })
  return handleResponse(response)
}

/**
 * Get current user info (requires valid access token).
 */
export async function getCurrentUser(
  accessToken: string
): Promise<{ user_id: string; org_id: string; role: string; teams: string[] }> {
  const response = await fetch(`${API_BASE}/me`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
  return handleResponse(response)
}

/**
 * Get user's organizations (requires valid access token).
 */
export async function getUserOrgs(accessToken: string): Promise<OrgMembership[]> {
  const response = await fetch(`${API_BASE}/me/orgs`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  })
  return handleResponse(response)
}

export { AuthApiError }
