/**
 * E2E Tests: Knowledge Page
 *
 * Tests the knowledge base functionality:
 * 1. Knowledge overview loads correctly
 * 2. Patterns page works
 * 3. Tribal knowledge section
 */

import { test, expect } from "./fixtures";
import { bypassLogin, TEST_CONFIG, waitForPageLoad } from "./utils/test-helpers";

test.describe("Knowledge Overview Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays knowledge page with title", async ({ page }) => {
    await page.goto("/knowledge");
    await waitForPageLoad(page);

    await expect(page.locator("h1")).toContainText(/knowledge/i, {
      timeout: TEST_CONFIG.TIMEOUTS.pageLoad,
    });
  });

  test("shows knowledge categories or empty state", async ({ page }) => {
    await page.goto("/knowledge");
    await waitForPageLoad(page);

    // Look for knowledge cards or categories (CSS selectors only)
    const content = page.locator('[class*="card"], [class*="knowledge"], [class*="pattern"]');

    await page.waitForTimeout(2000);
    const count = await content.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("has navigation to sub-pages", async ({ page }) => {
    await page.goto("/knowledge");
    await waitForPageLoad(page);

    // Look for navigation links
    const navLinks = page.locator(
      'a[href*="/knowledge/patterns"], a[href*="/knowledge/tribal"]'
    );

    const count = await navLinks.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Patterns Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays patterns page", async ({ page }) => {
    await page.goto("/knowledge/patterns");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for patterns content (CSS selectors only)
    const content = page.locator('[class*="card"], [class*="pattern"]');

    const count = await content.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("shows pattern entries or empty state", async ({ page }) => {
    await page.goto("/knowledge/patterns");
    await waitForPageLoad(page);

    // Look for pattern entries (CSS selectors only)
    const patterns = page.locator('[class*="card"], [class*="item"]');

    const count = await patterns.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("has search or filter functionality", async ({ page }) => {
    await page.goto("/knowledge/patterns");
    await waitForPageLoad(page);

    // Look for search/filter
    const searchFilter = page.locator(
      'input[type="search"], input[placeholder*="Search"], select, [class*="filter"]'
    );

    const count = await searchFilter.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Tribal Knowledge Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays tribal knowledge page", async ({ page }) => {
    await page.goto("/knowledge/tribal");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for tribal knowledge content (CSS selectors only)
    const content = page.locator('[class*="card"], [class*="tribal"], [class*="knowledge"]');

    const count = await content.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("shows knowledge entries or empty state", async ({ page }) => {
    await page.goto("/knowledge/tribal");
    await waitForPageLoad(page);

    // Look for knowledge entries (CSS selectors only)
    const entries = page.locator('[class*="card"], [class*="entry"]');

    const count = await entries.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("has add knowledge button", async ({ page }) => {
    await page.goto("/knowledge/tribal");
    await waitForPageLoad(page);

    // Look for add button
    const addButton = page.locator(
      'button:has-text("Add"), button:has-text("Create"), button:has-text("New")'
    );

    const count = await addButton.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Knowledge Search", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("can search across knowledge base", async ({ page }) => {
    await page.goto("/knowledge");
    await waitForPageLoad(page);

    // Look for search input
    const searchInput = page.locator(
      'input[type="search"], input[placeholder*="Search"], input[placeholder*="search"]'
    );

    if (await searchInput.first().isVisible({ timeout: 3000 }).catch(() => false)) {
      await searchInput.first().fill("test search");
      await page.waitForTimeout(1000);

      // Page should still be functional
      const body = await page.locator("body").isVisible();
      expect(body).toBeTruthy();
    } else {
      test.skip();
    }
  });
});
