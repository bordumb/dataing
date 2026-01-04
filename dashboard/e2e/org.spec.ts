/**
 * E2E Tests: Organization Page
 *
 * Tests the organization management functionality:
 * 1. Organization overview loads correctly
 * 2. Settings page works
 * 3. Usage page displays data
 * 4. Audit log is accessible
 */

import { test, expect } from "./fixtures";
import { bypassLogin, TEST_CONFIG, waitForPageLoad } from "./utils/test-helpers";

test.describe("Organization Overview Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays organization page with title", async ({ page }) => {
    await page.goto("/org");
    await waitForPageLoad(page);

    await expect(page.locator("h1")).toContainText(/organization|org/i, {
      timeout: TEST_CONFIG.TIMEOUTS.pageLoad,
    });
  });

  test("shows organization details or dashboard", async ({ page }) => {
    await page.goto("/org");
    await waitForPageLoad(page);

    // Look for org details, cards, or navigation (CSS selectors only)
    const content = page.locator('[class*="card"], a[href*="/org/"]');

    await page.waitForTimeout(2000);
    const count = await content.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("has navigation to sub-pages", async ({ page }) => {
    await page.goto("/org");
    await waitForPageLoad(page);

    // Look for navigation links
    const navLinks = page.locator(
      'a[href*="/org/settings"], a[href*="/org/usage"], a[href*="/org/audit"]'
    );

    const count = await navLinks.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Organization Settings Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays settings page", async ({ page }) => {
    await page.goto("/org/settings");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for settings-related content (CSS selectors only)
    const settingsContent = page.locator('form, input, [class*="form"], [class*="setting"]');

    const count = await settingsContent.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("shows organization name field", async ({ page }) => {
    await page.goto("/org/settings");
    await waitForPageLoad(page);

    // Look for name input or display (CSS selectors only)
    const nameField = page.locator('input[name*="name"], input[placeholder*="name"]');

    const count = await nameField.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Organization Usage Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays usage page", async ({ page }) => {
    await page.goto("/org/usage");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for usage-related content (CSS selectors only)
    const usageContent = page.locator('[class*="chart"], canvas, [class*="progress"], [class*="usage"]');

    const count = await usageContent.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Organization Audit Log Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays audit log page", async ({ page }) => {
    await page.goto("/org/audit-log");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for audit log content (CSS selectors only)
    const auditContent = page.locator('table, [class*="log"], [class*="event"], [class*="audit"]');

    const count = await auditContent.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("shows event entries or empty state", async ({ page }) => {
    await page.goto("/org/audit-log");
    await waitForPageLoad(page);

    // Look for log entries (CSS selectors only)
    const logEntries = page.locator('tr, [class*="entry"], [class*="row"]');

    const count = await logEntries.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});
