const API_BASE = '/api/v1'
const API_KEY_STORAGE_KEY = 'datadr_api_key' // pragma: allowlist secret

export interface RequestConfig {
  url: string
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
  params?: Record<string, string>
  data?: unknown
  headers?: Record<string, string>
}

export const customInstance = async <T>(config: RequestConfig): Promise<T> => {
  const { url, method, params, data, headers } = config

  const queryString = params
    ? '?' + new URLSearchParams(params).toString()
    : ''

  // Get API key from storage
  const apiKey = localStorage.getItem(API_KEY_STORAGE_KEY)

  const response = await fetch(`${API_BASE}${url}${queryString}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(apiKey ? { 'X-API-Key': apiKey } : {}),
      ...headers,
    },
    body: data ? JSON.stringify(data) : undefined,
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `HTTP error ${response.status}`)
  }

  return response.json()
}

export default customInstance
