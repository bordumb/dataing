const API_KEY_STORAGE_KEY = 'dataing_api_key' // pragma: allowlist secret

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

  // Get API key from storage
  const apiKey = localStorage.getItem(API_KEY_STORAGE_KEY)

  // URL already includes /api/v1 prefix from generated code
  const response = await fetch(`${url}${queryString}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(apiKey ? { 'X-API-Key': apiKey } : {}),
      ...headers,
    },
    body: data ? JSON.stringify(data) : undefined,
    signal,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP error ${response.status}`)
  }

  return response.json()
}

export default customInstance
