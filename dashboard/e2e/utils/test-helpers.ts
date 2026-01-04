/**
 * Shared E2E Test Utilities
 *
 * Common helper functions for all Playwright tests.
 */

import type { Page } from "@playwright/test";

export const TEST_CONFIG = {
  TIMEOUTS: {
    navigation: 45000,
    pageLoad: 30000,
    shortWait: 5000,
  },
};

/**
 * Helper: Navigate past the SSO login page
 * The demo login page has a "Continue to dashboard" link
 *
 * This function handles multiple scenarios:
 * 1. Login page is shown - click through to dashboard
 * 2. Already logged in - just proceed
 * 3. Navigation is slow - wait patiently
 */
export async function bypassLogin(page: Page): Promise<void> {
  // First, go to the login page
  await page.goto("/login", { waitUntil: "domcontentloaded", timeout: 30000 });

  // Look for the "Continue to dashboard" link
  const continueLink = page.locator('a:has-text("Continue to dashboard")');

  try {
    // Wait for the link to be visible
    await continueLink.waitFor({ state: "visible", timeout: 10000 });

    // Click the link and wait for URL change
    await Promise.all([
      page.waitForURL(/\/(home|dashboard|investigations|datasets|teams)/, {
        timeout: 30000,
        waitUntil: "domcontentloaded",
      }),
      continueLink.click(),
    ]);
  } catch {
    // If the link isn't visible or navigation failed, go directly to home
    await page.goto("/home", { waitUntil: "domcontentloaded", timeout: 30000 });
  }
}

/**
 * Helper: Wait for page content to load
 * More flexible than waiting for specific elements
 */
export async function waitForPageLoad(page: Page): Promise<void> {
  await page.waitForLoadState("domcontentloaded");
  // Give React time to hydrate
  await page.waitForTimeout(500);
}

/**
 * Helper: Check if an element exists without throwing
 */
export async function elementExists(
  page: Page,
  selector: string,
  timeout = 3000
): Promise<boolean> {
  try {
    await page.locator(selector).waitFor({ state: "visible", timeout });
    return true;
  } catch {
    return false;
  }
}
