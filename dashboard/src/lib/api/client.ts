import { getApiBaseUrl, API_CONFIG } from "./config";

// Use centralized API configuration
const BASE_URL = getApiBaseUrl();

class ApiClient {
  private async getHeaders() {
    // Enterprise Requirement: Forward Auth Token
    // Only get session on client-side
    let authToken = "";
    if (typeof window !== 'undefined') {
      try {
        const { getSession } = await import("next-auth/react");
        const session = await getSession();
        authToken = session?.accessToken ? `Bearer ${session.accessToken}` : "";
      } catch (error) {
        // Session not available, continue without auth
      }
    }

    return {
      "Content-Type": "application/json",
      "Authorization": authToken,
    };
  }

  async fetch<T>(endpoint: string, config?: RequestInit): Promise<T> {
    const headers = await this.getHeaders();
    const response = await fetch(`${BASE_URL}${endpoint}`, {
      ...config,
      headers: { ...headers, ...config?.headers },
    });

    if (!response.ok) {
      // Enterprise Requirement: Standardized Error Logging
      console.error(`[API Error] ${config?.method || 'GET'} ${endpoint}: ${response.status}`);
      throw new Error(`API Error: ${response.statusText}`);
    }

    // Handle 204 No Content
    if (response.status === 204) return {} as T;

    return response.json();
  }

  get<T>(path: string, tags?: string[]) {
    return this.fetch<T>(path, {
      method: "GET",
      next: { tags } // Enable granular caching
    });
  }

  post<T>(path: string, body: any) {
    return this.fetch<T>(path, {
      method: "POST",
      body: JSON.stringify(body)
    });
  }

  put<T>(path: string, body: any) {
    return this.fetch<T>(path, {
      method: "PUT",
      body: JSON.stringify(body)
    });
  }

  patch<T>(path: string, body: any) {
    return this.fetch<T>(path, {
      method: "PATCH",
      body: JSON.stringify(body)
    });
  }

  delete<T>(path: string) {
    return this.fetch<T>(path, {
      method: "DELETE"
    });
  }
}

export const api = new ApiClient();

// Legacy exports for backward compatibility
export const API_BASE_URL = BASE_URL;
export const USE_MOCKS = process.env.NEXT_PUBLIC_USE_MOCKS !== "false";

// Legacy apiFetch for gradual migration
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  return api.fetch<T>(path, init);
}
