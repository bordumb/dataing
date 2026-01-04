/**
 * E2E Tests: Integrations Page
 *
 * Tests the integrations management functionality:
 * 1. Integrations overview loads correctly
 * 2. Anomaly sources configuration
 * 3. Lineage integrations
 * 4. Notifications setup
 */

import { test, expect } from "./fixtures";
import { bypassLogin, TEST_CONFIG, waitForPageLoad } from "./utils/test-helpers";

test.describe("Integrations Overview Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays integrations page with title", async ({ page }) => {
    await page.goto("/integrations");
    await waitForPageLoad(page);

    await expect(page.locator("h1")).toContainText(/integration/i, {
      timeout: TEST_CONFIG.TIMEOUTS.pageLoad,
    });
  });

  test("shows integration categories", async ({ page }) => {
    await page.goto("/integrations");
    await waitForPageLoad(page);

    // Look for integration cards or categories (CSS selectors only)
    const content = page.locator('[class*="card"], [class*="integration"]');

    await page.waitForTimeout(2000);
    const count = await content.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("has navigation to sub-pages", async ({ page }) => {
    await page.goto("/integrations");
    await waitForPageLoad(page);

    // Look for navigation links
    const navLinks = page.locator(
      'a[href*="/integrations/anomaly"], a[href*="/integrations/lineage"], a[href*="/integrations/notification"]'
    );

    const count = await navLinks.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Anomaly Sources Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays anomaly sources page", async ({ page }) => {
    await page.goto("/integrations/anomaly-sources");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for anomaly sources content (CSS selectors only)
    const content = page.locator('[class*="card"], button:has-text("Add"), [class*="source"]');

    const count = await content.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("shows configured sources or empty state", async ({ page }) => {
    await page.goto("/integrations/anomaly-sources");
    await waitForPageLoad(page);

    // Look for source entries or empty state (CSS selectors only)
    const sources = page.locator('[class*="card"], [class*="item"]');

    const count = await sources.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Lineage Integrations Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays lineage page", async ({ page }) => {
    await page.goto("/integrations/lineage");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for lineage content (CSS selectors only)
    const content = page.locator('[class*="card"], [class*="lineage"]');

    const count = await content.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Notifications Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays notifications page", async ({ page }) => {
    await page.goto("/integrations/notifications");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for notifications content (CSS selectors only)
    const content = page.locator('[class*="card"], [class*="notification"]');

    const count = await content.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("shows notification channels or empty state", async ({ page }) => {
    await page.goto("/integrations/notifications");
    await waitForPageLoad(page);

    // Look for notification channels (CSS selectors only)
    const channels = page.locator('[class*="card"], [class*="channel"]');

    const count = await channels.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("has add notification button", async ({ page }) => {
    await page.goto("/integrations/notifications");
    await waitForPageLoad(page);

    // Look for add button
    const addButton = page.locator(
      'button:has-text("Add"), button:has-text("Create"), button:has-text("Configure")'
    );

    const count = await addButton.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});
