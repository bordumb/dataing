// Storage keys for authentication
const ACCESS_TOKEN_KEY = 'dataing_access_token' // pragma: allowlist secret
const API_KEY_STORAGE_KEY = 'dataing_api_key' // pragma: allowlist secret (legacy)

export interface RequestConfig {
  url: string
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
  params?: Record<string, unknown>
  data?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
}

export const customInstance = async <T>(config: RequestConfig): Promise<T> => {
  const { url, method, params, data, headers, signal } = config

  // Convert params to string, filtering out null/undefined
  const queryString = params
    ? '?' +
      new URLSearchParams(
        Object.entries(params)
          .filter(([, v]) => v != null)
          .map(([k, v]) => [k, String(v)])
      ).toString()
    : ''

  // Get JWT access token (preferred) or fall back to API key (legacy)
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY)
  const apiKey = localStorage.getItem(API_KEY_STORAGE_KEY)

  // Build auth header - prefer JWT, fall back to API key
  const authHeaders: Record<string, string> = {}
  if (accessToken) {
    authHeaders['Authorization'] = `Bearer ${accessToken}`
  } else if (apiKey) {
    authHeaders['X-API-Key'] = apiKey
  }

  // URL already includes /api/v1 prefix from generated code
  const response = await fetch(`${url}${queryString}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders,
      ...headers,
    },
    body: data ? JSON.stringify(data) : undefined,
    signal,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))

    // Check for upgrade-required errors
    if (response.status === 403 && errorData.detail?.error) {
      const detail = errorData.detail
      if (detail.error === 'feature_not_available' || detail.error === 'limit_exceeded') {
        const { setUpgradeError } = await import('./upgrade-error')
        setUpgradeError(detail)
        throw new Error(detail.message)
      }
    }

    // Handle FastAPI validation errors (422) which return { detail: [{loc, msg, type}, ...] }
    if (Array.isArray(errorData.detail)) {
      const messages = errorData.detail
        .map((e: { loc?: string[]; msg?: string }) => {
          const field = e.loc?.slice(1).join('.') || 'field'
          return `${field}: ${e.msg || 'invalid'}`
        })
        .join('; ')
      throw new Error(messages || `HTTP error ${response.status}`)
    }

    throw new Error(errorData.detail?.message || errorData.detail || `HTTP error ${response.status}`)
  }

  return response.json()
}

export default customInstance
