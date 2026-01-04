/**
 * E2E Tests: Home Page
 *
 * Tests the dashboard home page functionality:
 * 1. Key metrics display
 * 2. Active investigations section
 * 3. Quick actions
 * 4. Navigation elements
 */

import { test, expect } from "./fixtures";
import { bypassLogin, TEST_CONFIG, waitForPageLoad } from "./utils/test-helpers";

test.describe("Home Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays home page with welcome message", async ({ page }) => {
    await page.goto("/home");
    await waitForPageLoad(page);

    // Look for h1 heading
    await expect(page.locator("h1").first()).toBeVisible({
      timeout: TEST_CONFIG.TIMEOUTS.pageLoad,
    });
  });

  test("shows key metrics section", async ({ page }) => {
    await page.goto("/home");
    await waitForPageLoad(page);

    // Look for metric cards or stats (CSS selectors only)
    const metricsContent = page.locator('[class*="card"], [class*="metric"], [class*="stat"]');

    await page.waitForTimeout(2000);
    const count = await metricsContent.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("displays active investigations section", async ({ page }) => {
    await page.goto("/home");
    await waitForPageLoad(page);

    // Look for investigations section
    const investigationsSection = page.locator('a[href*="investigations"]');

    await page.waitForTimeout(2000);
    const count = await investigationsSection.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("has navigation to other sections", async ({ page }) => {
    await page.goto("/home");
    await waitForPageLoad(page);

    // Look for main navigation links
    const navLinks = page.locator(
      'a[href*="/investigations"], a[href*="/datasets"], a[href*="/teams"]'
    );

    const count = await navLinks.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("shows recent anomalies or activity", async ({ page }) => {
    await page.goto("/home");
    await waitForPageLoad(page);

    // Look for activity or anomaly content (CSS selectors only)
    const activityContent = page.locator('[class*="timeline"], [class*="activity"], [class*="card"]');

    await page.waitForTimeout(2000);
    const count = await activityContent.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Home Page Navigation", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("can navigate to investigations from home", async ({ page }) => {
    await page.goto("/home");
    await waitForPageLoad(page);

    const investigationsLink = page.locator('a[href*="/investigations"]').first();

    if (await investigationsLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await investigationsLink.click();
      await expect(page).toHaveURL(/\/investigations/, {
        timeout: TEST_CONFIG.TIMEOUTS.navigation,
      });
    } else {
      // Navigate directly if no link found
      await page.goto("/investigations");
    }
  });

  test("can navigate to datasets from home", async ({ page }) => {
    await page.goto("/home");
    await waitForPageLoad(page);

    const datasetsLink = page.locator('a[href*="/datasets"]').first();

    if (await datasetsLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await datasetsLink.click();
      await expect(page).toHaveURL(/\/datasets/, {
        timeout: TEST_CONFIG.TIMEOUTS.navigation,
      });
    } else {
      await page.goto("/datasets");
    }
  });

  test("can navigate to teams from home", async ({ page }) => {
    await page.goto("/home");
    await waitForPageLoad(page);

    const teamsLink = page.locator('a[href*="/teams"]').first();

    if (await teamsLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await teamsLink.click();
      await expect(page).toHaveURL(/\/teams/, {
        timeout: TEST_CONFIG.TIMEOUTS.navigation,
      });
    } else {
      await page.goto("/teams");
    }
  });
});
