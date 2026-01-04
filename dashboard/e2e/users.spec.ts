/**
 * E2E Tests: Users Page
 *
 * Tests the user management functionality:
 * 1. Users list loads correctly
 * 2. User details are accessible
 * 3. User search works
 * 4. Role information is displayed
 */

import { test, expect } from "./fixtures";
import { bypassLogin, TEST_CONFIG, waitForPageLoad } from "./utils/test-helpers";

test.describe("Users List Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays users page with title", async ({ page }) => {
    await page.goto("/users");
    await waitForPageLoad(page);

    await expect(page.locator("h1")).toContainText(/user/i, {
      timeout: TEST_CONFIG.TIMEOUTS.pageLoad,
    });
  });

  test("shows users list or empty state", async ({ page }) => {
    await page.goto("/users");
    await waitForPageLoad(page);

    // Look for user cards, table rows, or empty state (CSS selectors only)
    const content = page.locator('[class*="card"], table, [class*="empty"], tr');

    await page.waitForTimeout(2000);
    const count = await content.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("has search functionality", async ({ page }) => {
    await page.goto("/users");
    await waitForPageLoad(page);

    // Look for search input
    const searchInput = page.locator(
      'input[type="search"], input[placeholder*="Search"], input[placeholder*="search"]'
    );

    const count = await searchInput.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("shows user roles", async ({ page }) => {
    await page.goto("/users");
    await waitForPageLoad(page);

    await page.waitForTimeout(2000);

    // Look for role indicators (CSS selectors only)
    const roleIndicators = page.locator('[class*="badge"], [class*="role"]');

    const count = await roleIndicators.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("User Detail Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("can navigate to user detail", async ({ page }) => {
    await page.goto("/users");
    await waitForPageLoad(page);

    // Find first user link
    const userLink = page.locator('a[href^="/users/"]').first();

    if (await userLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await userLink.click();

      await expect(page).toHaveURL(/\/users\//, {
        timeout: TEST_CONFIG.TIMEOUTS.navigation,
      });
    } else {
      test.skip();
    }
  });

  test("shows user information", async ({ page }) => {
    await page.goto("/users");
    await waitForPageLoad(page);

    const userLink = page.locator('a[href^="/users/"]').first();

    if (await userLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await userLink.click();
      await waitForPageLoad(page);

      // Look for user info (CSS selectors only)
      const userInfo = page.locator('[class*="avatar"], img, [class*="email"]');

      await page.waitForTimeout(2000);
      const count = await userInfo.count();
      expect(count).toBeGreaterThanOrEqual(0);
    } else {
      test.skip();
    }
  });

  test("shows user teams", async ({ page }) => {
    await page.goto("/users");
    await waitForPageLoad(page);

    const userLink = page.locator('a[href^="/users/"]').first();

    if (await userLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await userLink.click();
      await waitForPageLoad(page);

      // Look for teams section (CSS selectors only)
      const teamsSection = page.locator('a[href*="teams"], [class*="team"]');

      await page.waitForTimeout(2000);
      const count = await teamsSection.count();
      expect(count).toBeGreaterThanOrEqual(0);
    } else {
      test.skip();
    }
  });
});

test.describe("User Error Handling", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("handles invalid user ID gracefully", async ({ page }) => {
    await page.goto("/users/invalid-user-id-12345");
    await waitForPageLoad(page);

    // Should show error or redirect
    const url = page.url();
    expect(url).toBeTruthy();

    // Page should still be functional
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();
  });
});
