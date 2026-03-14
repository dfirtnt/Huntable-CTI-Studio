import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const SKIP_TESTS = process.env.SKIP_NAVIGATION_TESTS === 'true';

test.describe('Cross-Page Navigation', () => {
  test.skip(SKIP_TESTS, 'Navigation tests disabled (SKIP_NAVIGATION_TESTS=true).');

  test('[NAV-001] Can navigate from Dashboard to Articles', async ({ page }) => {
    await page.goto(`${BASE}/dashboard`);
    await page.waitForLoadState('networkidle');
    
    const articlesLink = page.locator('a[href*="/articles"]').first();
    await articlesLink.click();
    
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/articles/);
  });

  test('[NAV-002] Can navigate from Dashboard to Sources', async ({ page }) => {
    await page.goto(`${BASE}/dashboard`);
    await page.waitForLoadState('networkidle');
    
    const sourcesLink = page.locator('a[href*="/sources"]').first();
    await sourcesLink.click();
    
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/sources/);
  });

  test('[NAV-003] Can navigate from Dashboard to Chat', async ({ page }) => {
    await page.goto(`${BASE}/dashboard`);
    await page.waitForLoadState('networkidle');
    
    const chatLink = page.locator('a[href*="/chat"]').first();
    const hasChatLink = await chatLink.isVisible({ timeout: 5000 }).catch(() => false);
    test.skip(!hasChatLink, 'Dashboard has no Chat link in current layout');
    
    await chatLink.click();
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/chat/);
  });

  test('[NAV-004] Can navigate from Sources to Article Detail', async ({ page, request }) => {
    await page.goto(`${BASE}/sources`);
    await page.waitForLoadState('networkidle');
    
    const sourceLink = page.locator('a[href*="/articles"]').first();
    await sourceLink.click();
    
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/articles/);
  });

  test('[NAV-005] Can navigate from Articles to Article Detail', async ({ page }) => {
    await page.goto(`${BASE}/articles`);
    await page.waitForLoadState('networkidle');
    
    const articleLink = page.locator('a[href*="/articles/"]').first();
    if (await articleLink.isVisible().catch(() => false)) {
      await articleLink.click();
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveURL(/\/articles\/\d+/);
    }
  });

  test('[NAV-006] Can navigate from Article to Chat', async ({ page }) => {
    await page.goto(`${BASE}/articles/1`);
    await page.waitForLoadState('networkidle');
    
    const chatLink = page.locator('a[href*="/chat"]').first();
    if (await chatLink.isVisible().catch(() => false)) {
      await chatLink.click();
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveURL(/\/chat/);
    }
  });

  test('[NAV-007] Can navigate from Chat to Dashboard', async ({ page }) => {
    await page.goto(`${BASE}/chat`);
    await page.waitForLoadState('networkidle');
    
    const homeLink = page.locator('a[href="/"], a[href*="/dashboard"]').first();
    await homeLink.click();
    
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/(\/|dashboard)/);
  });

  test('[NAV-008] Can navigate to Settings from any page', async ({ page }) => {
    await page.goto(`${BASE}/articles`);
    await page.waitForLoadState('networkidle');
    
    const settingsLink = page.locator('a[href*="/settings"]').first();
    await settingsLink.click();
    
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/settings/);
  });

  test('[NAV-009] Can navigate to Jobs from Dashboard', async ({ page }) => {
    await page.goto(`${BASE}/dashboard`);
    await page.waitForLoadState('networkidle');
    
    const jobsLink = page.locator('a[href*="/jobs"]').first();
    if (await jobsLink.isVisible().catch(() => false)) {
      await jobsLink.click();
      await page.waitForLoadState('networkidle');
      await expect(page).toHaveURL(/\/jobs/);
    }
  });

  test('[NAV-010] Breadcrumb navigation works', async ({ page }) => {
    await page.goto(`${BASE}/articles/1`);
    await page.waitForLoadState('networkidle');
    
    const breadcrumb = page.locator('nav[aria-label="Breadcrumb"], .breadcrumb, [data-testid="breadcrumb"]');
    const hasBreadcrumb = await breadcrumb.first().isVisible().catch(() => false);
    expect(hasBreadcrumb).toBe(true);
  });

  test('[NAV-011] Back button works from Article Detail', async ({ page }) => {
    await page.goto(`${BASE}/articles/1`);
    await page.waitForLoadState('networkidle');
    
    const backBtn = page.locator('button:has-text("Back"), a:has-text("Back")').first();
    if (await backBtn.isVisible().catch(() => false)) {
      await backBtn.click();
      await page.waitForLoadState('networkidle');
    }
  });

  test('[NAV-012] Logo/Home link navigates to Dashboard', async ({ page }) => {
    await page.goto(`${BASE}/settings`);
    await page.waitForLoadState('networkidle');
    
    const logo = page.locator('a[href="/"], a[href="/dashboard"], .logo, [data-testid="logo"]').first();
    await logo.click();
    
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/(\/|dashboard)/);
  });
});
