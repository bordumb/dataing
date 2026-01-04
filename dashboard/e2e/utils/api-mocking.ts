/**
 * API Mocking Utilities for E2E Tests
 *
 * Uses Playwright's HAR recording/replay for scalable API mocking.
 * When the API changes, just re-record the HAR file.
 *
 * Usage:
 *   # Record new HAR file (requires running API)
 *   pnpm test:e2e:record
 *
 *   # Run tests with mocked API (no API needed)
 *   pnpm test:e2e:mock
 */

import { type Page, type BrowserContext } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";

// Path to HAR file
const HAR_DIR = path.join(__dirname, "..", "fixtures");
const HAR_FILE = path.join(HAR_DIR, "api-responses.har");

/**
 * Check if HAR file exists
 */
export function hasRecordedResponses(): boolean {
  return fs.existsSync(HAR_FILE);
}

/**
 * Start recording API responses to HAR file
 * Call this at the start of a test run to record fresh responses
 */
export async function startRecording(context: BrowserContext): Promise<void> {
  // Ensure fixtures directory exists
  if (!fs.existsSync(HAR_DIR)) {
    fs.mkdirSync(HAR_DIR, { recursive: true });
  }

  await context.routeFromHAR(HAR_FILE, {
    update: true, // Record mode
    updateContent: "embed", // Embed response bodies in HAR
    updateMode: "full", // Record all requests
  });
}

/**
 * Use recorded HAR responses (mock mode)
 * API requests will be served from the HAR file
 */
export async function useMockedResponses(context: BrowserContext): Promise<void> {
  if (!hasRecordedResponses()) {
    console.warn(
      "No HAR file found. Run with --update-har flag first to record API responses."
    );
    return;
  }

  await context.routeFromHAR(HAR_FILE, {
    update: false, // Replay mode
    notFound: "fallback", // Fall back to network for unrecorded requests
  });
}

/**
 * Mock specific API endpoints with custom responses
 * Use this for edge cases or error scenarios
 */
export async function mockApiEndpoint(
  page: Page,
  urlPattern: string | RegExp,
  response: {
    status?: number;
    body?: unknown;
    headers?: Record<string, string>;
  }
): Promise<void> {
  await page.route(urlPattern, async (route) => {
    await route.fulfill({
      status: response.status ?? 200,
      contentType: "application/json",
      headers: response.headers,
      body: JSON.stringify(response.body ?? {}),
    });
  });
}

/**
 * Mock API to return an error
 */
export async function mockApiError(
  page: Page,
  urlPattern: string | RegExp,
  statusCode: number = 500,
  message: string = "Internal Server Error"
): Promise<void> {
  await mockApiEndpoint(page, urlPattern, {
    status: statusCode,
    body: { error: message, detail: message },
  });
}

/**
 * Mock API to return empty data
 */
export async function mockEmptyResponse(
  page: Page,
  urlPattern: string | RegExp
): Promise<void> {
  await mockApiEndpoint(page, urlPattern, {
    status: 200,
    body: { data: [], items: [], total: 0 },
  });
}

/**
 * Mock slow API response (for testing loading states)
 */
export async function mockSlowResponse(
  page: Page,
  urlPattern: string | RegExp,
  delayMs: number = 3000
): Promise<void> {
  await page.route(urlPattern, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    await route.continue();
  });
}
