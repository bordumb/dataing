/**
 * Playwright configuration for E2E tests.
 *
 * @see https://playwright.dev/docs/test-configuration
 */

import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true, // Run tests in parallel within files too
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 8, // Use 8 parallel workers
  reporter: process.env.CI ? "github" : "html",
  timeout: 60000, // 60 seconds per test
  expect: {
    timeout: 15000, // 15 seconds for assertions
  },
  use: {
    baseURL: process.env.TEST_BASE_URL || "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    actionTimeout: 30000, // 30 seconds for actions
    navigationTimeout: 45000, // 45 seconds for navigation
  },

  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],

  // Run local dev server before tests if not in CI
  webServer: process.env.CI
    ? undefined
    : {
        command: "pnpm dev",
        url: "http://localhost:3000",
        reuseExistingServer: !process.env.CI,
        timeout: 120 * 1000,
      },
});
