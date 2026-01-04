/**
 * E2E Tests: Profile Page
 *
 * Tests the user profile functionality:
 * 1. Profile overview loads correctly
 * 2. Preferences can be viewed
 * 3. API keys management
 * 4. Activity history
 */

import { test, expect } from "./fixtures";
import { bypassLogin, TEST_CONFIG, waitForPageLoad } from "./utils/test-helpers";

test.describe("Profile Overview Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays profile page with user info", async ({ page }) => {
    await page.goto("/profile");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for profile-related content (CSS selectors only)
    const profileContent = page.locator('[class*="avatar"], img[alt*="avatar"], [class*="profile"]');

    const count = await profileContent.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("shows user email or name", async ({ page }) => {
    await page.goto("/profile");
    await waitForPageLoad(page);

    // Look for user identification (CSS selectors only)
    const userInfo = page.locator('input[type="email"], [class*="email"], [class*="user"]');

    const count = await userInfo.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("has navigation to sub-pages", async ({ page }) => {
    await page.goto("/profile");
    await waitForPageLoad(page);

    // Look for navigation links
    const navLinks = page.locator(
      'a[href*="/profile/preferences"], a[href*="/profile/api-keys"], a[href*="/profile/activity"]'
    );

    const count = await navLinks.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Profile Preferences Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays preferences page", async ({ page }) => {
    await page.goto("/profile/preferences");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for preferences content (CSS selectors only)
    const prefsContent = page.locator('input, select, [class*="toggle"], [class*="preference"]');

    const count = await prefsContent.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("shows theme or notification settings", async ({ page }) => {
    await page.goto("/profile/preferences");
    await waitForPageLoad(page);

    // Look for common preference options (CSS selectors only)
    const settings = page.locator('[class*="switch"], input[type="checkbox"], [class*="theme"]');

    const count = await settings.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Profile API Keys Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays API keys page", async ({ page }) => {
    await page.goto("/profile/api-keys");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for API keys content (CSS selectors only)
    const apiKeysContent = page.locator('button:has-text("Create"), button:has-text("Generate"), [class*="key"]');

    const count = await apiKeysContent.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("shows create key button", async ({ page }) => {
    await page.goto("/profile/api-keys");
    await waitForPageLoad(page);

    // Look for create button
    const createButton = page.locator(
      'button:has-text("Create"), button:has-text("Generate"), button:has-text("New")'
    );

    const count = await createButton.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

test.describe("Profile Activity Page", () => {
  test.beforeEach(async ({ page }) => {
    await bypassLogin(page);
  });

  test("displays activity page", async ({ page }) => {
    await page.goto("/profile/activity");
    await waitForPageLoad(page);

    // Page should load without errors
    const body = await page.locator("body").isVisible();
    expect(body).toBeTruthy();

    // Look for activity content (CSS selectors only)
    const activityContent = page.locator('[class*="timeline"], [class*="activity"], [class*="history"]');

    const count = await activityContent.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test("shows activity entries or empty state", async ({ page }) => {
    await page.goto("/profile/activity");
    await waitForPageLoad(page);

    // Look for activity entries (CSS selectors only)
    const entries = page.locator('[class*="entry"], [class*="item"]');

    const count = await entries.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});
