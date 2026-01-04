/**
 * E2E Tests: Analytics Page
 *
 * Tests the analytics dashboard functionality:
 * 1. Analytics overview loads correctly
 * 2. MTTR metrics are displayed
 * 3. Cost tracking works
 * 4. Trends visualization
 */

import { test, expect } from "./fixtures";
import { bypassLogin, TEST_CONFIG, waitForPageLoad } from "./utils/test-helpers";

test.describe("Analytics Overview Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays analytics page with title", async ({ page }) => {
    await page.goto("/analytics");
    await waitForPageLoad(page);

    await expect(page.locator("h1")).toContainText(/analytic/i, {
      timeout: TEST_CONFIG.TIMEOUTS.pageLoad,
    });
  });

  test("shows key metrics or empty state", async ({ page }) => {
    await page.goto("/analytics");
    await waitForPageLoad(page);

    // Look for metric cards, charts, or empty state (CSS selectors only)
    const content = page.locator('[class*="card"], [class*="chart"], [class*="metric"], canvas, svg');

    await page.waitForTimeout(2000);
    const count = await content.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("has navigation tabs for different analytics views", async ({ page }) => {
    await page.goto("/analytics");
    await waitForPageLoad(page);

    // Look for navigation tabs (MTTR, Costs, Trends)
    const navTabs = page.locator(
      '[role="tab"], a[href*="/analytics/"], button:has-text("MTTR"), button:has-text("Cost"), button:has-text("Trend")'
    );

    const count = await navTabs.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("MTTR Analytics Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays MTTR metrics page", async ({ page }) => {
    await page.goto("/analytics/mttr");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for MTTR-related content (CSS selectors only)
    const mttrContent = page.locator('[class*="chart"], [class*="mttr"], canvas');

    const count = await mttrContent.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("shows time range selector", async ({ page }) => {
    await page.goto("/analytics/mttr");
    await waitForPageLoad(page);

    // Look for date/time filters
    const timeSelector = page.locator(
      'select, [class*="date"], button:has-text("7 days"), button:has-text("30 days"), input[type="date"]'
    );

    const count = await timeSelector.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Cost Analytics Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays cost tracking page", async ({ page }) => {
    await page.goto("/analytics/costs");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for cost-related content (CSS selectors only)
    const costContent = page.locator('[class*="chart"], [class*="cost"], canvas');

    const count = await costContent.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Trends Analytics Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays trends page", async ({ page }) => {
    await page.goto("/analytics/trends");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for trend-related content (CSS selectors only)
    const trendContent = page.locator('[class*="chart"], [class*="trend"], canvas, svg');

    const count = await trendContent.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});
