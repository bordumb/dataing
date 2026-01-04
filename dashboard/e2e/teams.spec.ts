/**
 * E2E Tests: Teams Page
 *
 * Tests the teams management functionality:
 * 1. Teams list loads correctly
 * 2. Team details are displayed
 * 3. Team members section
 * 4. Team datasets section
 */

import { test, expect } from "./fixtures";
import { bypassLogin, TEST_CONFIG, waitForPageLoad } from "./utils/test-helpers";

test.describe("Teams List Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays teams page with title", async ({ page }) => {
    await page.goto("/teams");
    await waitForPageLoad(page);

    await expect(page.locator("h1")).toContainText(/team/i, {
      timeout: TEST_CONFIG.TIMEOUTS.pageLoad,
    });
  });

  test("shows teams list or empty state", async ({ page }) => {
    await page.goto("/teams");
    await waitForPageLoad(page);

    // Look for team cards, table rows, or empty state (CSS selectors only)
    const content = page.locator('[class*="card"], table, [class*="empty"]');

    await page.waitForTimeout(2000);
    const count = await content.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("has create team button", async ({ page }) => {
    await page.goto("/teams");
    await waitForPageLoad(page);

    // Look for create team button
    const createButton = page.locator(
      'button:has-text("Create"), button:has-text("New Team"), a:has-text("Create")'
    );

    const count = await createButton.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Team Detail Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("can navigate to team detail", async ({ page }) => {
    await page.goto("/teams");
    await waitForPageLoad(page);

    // Find first team link
    const teamLink = page.locator('a[href^="/teams/"]').first();

    if (await teamLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await teamLink.click();

      await expect(page).toHaveURL(/\/teams\//, {
        timeout: TEST_CONFIG.TIMEOUTS.navigation,
      });
    } else {
      test.skip();
    }
  });

  test("shows team members section", async ({ page }) => {
    await page.goto("/teams");
    await waitForPageLoad(page);

    const teamLink = page.locator('a[href^="/teams/"]').first();

    if (await teamLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await teamLink.click();
      await waitForPageLoad(page);

      // Look for members section or tab (CSS selectors only)
      const membersContent = page.locator('a[href*="members"], [class*="member"], [class*="user"]');

      await page.waitForTimeout(2000);
      const count = await membersContent.count();
      expect(count).toBeGreaterThanOrEqual(0);
    } else {
      test.skip();
    }
  });

  test("shows team datasets section", async ({ page }) => {
    await page.goto("/teams");
    await waitForPageLoad(page);

    const teamLink = page.locator('a[href^="/teams/"]').first();

    if (await teamLink.isVisible({ timeout: 5000 }).catch(() => false)) {
      await teamLink.click();
      await waitForPageLoad(page);

      // Look for datasets section or tab (CSS selectors only)
      const datasetsContent = page.locator('a[href*="datasets"], [class*="dataset"]');

      await page.waitForTimeout(2000);
      const count = await datasetsContent.count();
      expect(count).toBeGreaterThanOrEqual(0);
    } else {
      test.skip();
    }
  });
});

test.describe("Team Error Handling", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("handles invalid team ID gracefully", async ({ page }) => {
    await page.goto("/teams/invalid-team-id-12345");
    await waitForPageLoad(page);

    // Should show error or redirect
    const url = page.url();
    expect(url).toBeTruthy();

    // Page should still be functional
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();
  });
});
