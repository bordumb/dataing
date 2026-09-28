import { apiErrorMessage } from "./error-message";

// API base URL - empty for same-origin (dev), set VITE_API_URL for production
const API_BASE_URL = import.meta.env.VITE_API_URL || "";

// Storage keys for authentication
const ACCESS_TOKEN_KEY = "dataing_access_token"; // pragma: allowlist secret
const API_KEY_STORAGE_KEY = "dataing_api_key"; // pragma: allowlist secret (legacy)

export interface RequestConfig {
  url: string;
  method: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  params?: Record<string, unknown>;
  data?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
  /** "blob" returns the body as a Blob, for downloads. Defaults to JSON. */
  responseType?: "json" | "blob";
}

/**
 * A failed API response. The message is readable (apiErrorMessage); `code` is
 * the machine-readable `detail.error` when the server sends one, such as
 * "ambiguous_datasource".
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;
  readonly code: string | null;

  constructor(message: string, status: number, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    const code = (detail as { error?: unknown } | null | undefined)?.error;
    this.code = typeof code === "string" ? code : null;
  }
}

export const customInstance = async <T>(config: RequestConfig): Promise<T> => {
  const { url, method, params, data, headers, signal, responseType } = config;

  // Convert params to string, filtering out null/undefined
  const queryString = params
    ? "?" +
      new URLSearchParams(
        Object.entries(params)
          .filter(([, v]) => v != null)
          .map(([k, v]) => [k, String(v)]),
      ).toString()
    : "";

  // Get JWT access token (preferred) or fall back to API key (legacy)
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
  const apiKey = localStorage.getItem(API_KEY_STORAGE_KEY);

  // Build auth header - prefer JWT, fall back to API key
  const authHeaders: Record<string, string> = {};
  if (accessToken) {
    authHeaders["Authorization"] = `Bearer ${accessToken}`;
  } else if (apiKey) {
    authHeaders["X-API-Key"] = apiKey;
  }

  // URL already includes /api/v1 prefix from generated code
  const response = await fetch(`${API_BASE_URL}${url}${queryString}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      ...headers,
    },
    body: data ? JSON.stringify(data) : undefined,
    signal,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));

    // Check for upgrade-required errors
    if (response.status === 403 && errorData.detail?.error) {
      const detail = errorData.detail;
      if (
        detail.error === "feature_not_available" ||
        detail.error === "limit_exceeded"
      ) {
        const { setUpgradeError } = await import("./upgrade-error");
        setUpgradeError(detail);
        throw new Error(detail.message);
      }
    }

    throw new ApiError(
      apiErrorMessage(errorData, response.status),
      response.status,
      errorData?.detail,
    );
  }

  // No Content (e.g. DELETE): there is no body to parse.
  if (response.status === 204) {
    return undefined as T;
  }

  if (responseType === "blob") {
    return (await response.blob()) as T;
  }

  return response.json();
};

export default customInstance;
