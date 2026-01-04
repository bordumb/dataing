/**
 * Custom Playwright Fixtures
 *
 * Extends the base Playwright test with API mocking capabilities.
 * Uses HAR recording/replay for scalable, low-maintenance mocking.
 *
 * Usage:
 *   import { test, expect } from './fixtures';
 *
 * Environment Variables:
 *   RECORD_HAR=true  - Record new API responses
 *   MOCK_API=true    - Use mocked API responses
 */

import { test as base, expect } from "@playwright/test";
import { startRecording, useMockedResponses, hasRecordedResponses } from "./utils/api-mocking";

// Extend base test with mocking capabilities
export const test = base.extend({
  // Auto-setup HAR recording or playback based on environment
  context: async ({ context }, use) => {
    const shouldRecord = process.env.RECORD_HAR === "true";
    const shouldMock = process.env.MOCK_API === "true";

    if (shouldRecord) {
      console.log("HAR Recording Mode: Recording API responses...");
      await startRecording(context);
    } else if (shouldMock) {
      if (hasRecordedResponses()) {
        console.log("Mock Mode: Using recorded API responses...");
        await useMockedResponses(context);
      } else {
        console.warn("Mock Mode: No HAR file found, falling back to live API");
      }
    }

    await use(context);
  },
});

export { expect };

// Re-export mocking utilities for custom use cases
export {
  mockApiEndpoint,
  mockApiError,
  mockEmptyResponse,
  mockSlowResponse,
} from "./utils/api-mocking";
