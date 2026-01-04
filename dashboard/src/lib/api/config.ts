/**
 * Unified API URL Configuration.
 *
 * This module consolidates API URL handling to prevent drift between
 * server-side (API_INTERNAL_URL) and client-side (NEXT_PUBLIC_API_URL)
 * configurations.
 *
 * ARCHITECTURE:
 * - Server-side requests (SSR, API routes): Use internal Docker network URL
 * - Client-side requests (browser): Use public-facing URL
 *
 * The configuration validates that both URLs are properly set and
 * warns on potential misconfigurations.
 */

/**
 * API Configuration interface.
 */
export interface ApiConfig {
  /** Base URL for API requests */
  baseUrl: string;
  /** Whether running on server or client */
  isServer: boolean;
  /** Internal URL for server-side requests */
  internalUrl: string;
  /** Public URL for client-side requests */
  publicUrl: string;
  /** Timeout for API requests in milliseconds */
  timeout: number;
  /** Whether to enable request/response logging */
  debug: boolean;
}

/**
 * Default configuration values.
 */
const DEFAULTS = {
  INTERNAL_URL: "http://api:8000",
  PUBLIC_URL: "http://localhost:8000",
  TIMEOUT: 30000,
  DEBUG: false,
} as const;

/**
 * Get the current environment.
 */
function isServerSide(): boolean {
  return typeof window === "undefined";
}

/**
 * Validate URL format.
 */
function isValidUrl(url: string): boolean {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
}

/**
 * Get API configuration with validation.
 *
 * @returns Validated API configuration object.
 * @throws Error if configuration is invalid.
 */
export function getApiConfig(): ApiConfig {
  const isServer = isServerSide();

  // Get URLs from environment
  const internalUrl =
    process.env.API_INTERNAL_URL || DEFAULTS.INTERNAL_URL;
  const publicUrl =
    process.env.NEXT_PUBLIC_API_URL || DEFAULTS.PUBLIC_URL;

  // Validate URLs
  if (!isValidUrl(internalUrl)) {
    console.error(
      `[API Config] Invalid API_INTERNAL_URL: ${internalUrl}`
    );
  }
  if (!isValidUrl(publicUrl)) {
    console.error(
      `[API Config] Invalid NEXT_PUBLIC_API_URL: ${publicUrl}`
    );
  }

  // Warn on potential misconfigurations
  if (isServer && internalUrl === DEFAULTS.INTERNAL_URL) {
    console.debug(
      "[API Config] Using default internal URL. Set API_INTERNAL_URL for production."
    );
  }

  // Select appropriate URL based on environment
  const baseUrl = isServer ? internalUrl : publicUrl;

  // Get optional settings
  const timeout = parseInt(
    process.env.NEXT_PUBLIC_API_TIMEOUT || String(DEFAULTS.TIMEOUT),
    10
  );
  const debug =
    process.env.NEXT_PUBLIC_API_DEBUG === "true" || DEFAULTS.DEBUG;

  return {
    baseUrl,
    isServer,
    internalUrl,
    publicUrl,
    timeout,
    debug,
  };
}

/**
 * Get the API base URL for the current environment.
 *
 * This is the primary function to use when constructing API URLs.
 * It automatically selects the correct URL based on whether the
 * code is running on the server or client.
 *
 * @returns The appropriate API base URL.
 *
 * @example
 * ```ts
 * const url = `${getApiBaseUrl()}/api/v1/investigations`;
 * const response = await fetch(url);
 * ```
 */
export function getApiBaseUrl(): string {
  const config = getApiConfig();
  return config.baseUrl;
}

/**
 * Construct a full API URL with path.
 *
 * @param path - The API path (e.g., "/api/v1/investigations").
 * @returns Full URL with base and path combined.
 *
 * @example
 * ```ts
 * const url = buildApiUrl("/api/v1/investigations");
 * // Server: "http://api:8000/api/v1/investigations"
 * // Client: "http://localhost:8000/api/v1/investigations"
 * ```
 */
export function buildApiUrl(path: string): string {
  const baseUrl = getApiBaseUrl();
  // Ensure path starts with /
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  // Remove trailing slash from baseUrl if present
  const normalizedBase = baseUrl.endsWith("/")
    ? baseUrl.slice(0, -1)
    : baseUrl;
  return `${normalizedBase}${normalizedPath}`;
}

/**
 * Configuration validation for deployment checks.
 *
 * Call this during application startup to verify configuration.
 *
 * @returns Validation result with any warnings or errors.
 */
export function validateApiConfig(): {
  valid: boolean;
  warnings: string[];
  errors: string[];
} {
  const warnings: string[] = [];
  const errors: string[] = [];

  const internalUrl = process.env.API_INTERNAL_URL;
  const publicUrl = process.env.NEXT_PUBLIC_API_URL;

  // Check if URLs are set
  if (!internalUrl) {
    warnings.push(
      "API_INTERNAL_URL not set. Using default: " + DEFAULTS.INTERNAL_URL
    );
  }
  if (!publicUrl) {
    warnings.push(
      "NEXT_PUBLIC_API_URL not set. Using default: " + DEFAULTS.PUBLIC_URL
    );
  }

  // Validate URL formats
  if (internalUrl && !isValidUrl(internalUrl)) {
    errors.push(`Invalid API_INTERNAL_URL format: ${internalUrl}`);
  }
  if (publicUrl && !isValidUrl(publicUrl)) {
    errors.push(`Invalid NEXT_PUBLIC_API_URL format: ${publicUrl}`);
  }

  // Check for common misconfigurations
  if (internalUrl && publicUrl) {
    // Warn if internal URL is same as public (might work locally but not in Docker)
    if (internalUrl === publicUrl && internalUrl.includes("localhost")) {
      warnings.push(
        "API_INTERNAL_URL and NEXT_PUBLIC_API_URL are both localhost. " +
          "This works locally but will fail in Docker/production."
      );
    }

    // Warn if internal URL contains localhost (won't work in Docker)
    if (
      internalUrl.includes("localhost") &&
      process.env.NODE_ENV === "production"
    ) {
      warnings.push(
        "API_INTERNAL_URL contains 'localhost' in production. " +
          "Use Docker service name (e.g., 'http://api:8000')."
      );
    }
  }

  return {
    valid: errors.length === 0,
    warnings,
    errors,
  };
}

/**
 * Log configuration on startup (for debugging).
 */
export function logApiConfig(): void {
  const config = getApiConfig();
  const validation = validateApiConfig();

  console.log("[API Config] Configuration:");
  console.log(`  Base URL: ${config.baseUrl}`);
  console.log(`  Is Server: ${config.isServer}`);
  console.log(`  Internal URL: ${config.internalUrl}`);
  console.log(`  Public URL: ${config.publicUrl}`);
  console.log(`  Timeout: ${config.timeout}ms`);

  if (validation.warnings.length > 0) {
    console.warn("[API Config] Warnings:");
    validation.warnings.forEach((w) => console.warn(`  - ${w}`));
  }

  if (validation.errors.length > 0) {
    console.error("[API Config] Errors:");
    validation.errors.forEach((e) => console.error(`  - ${e}`));
  }
}

// Export a singleton config for convenience
export const API_CONFIG = getApiConfig();

// Legacy export for backward compatibility
export const API_BASE_URL = getApiBaseUrl();
