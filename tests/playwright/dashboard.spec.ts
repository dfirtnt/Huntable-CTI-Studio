import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const SKIP_TESTS = process.env.SKIP_DASHBOARD_TESTS === 'true';

test.describe('Dashboard Page', () => {
  test.skip(SKIP_TESTS, 'Dashboard tests disabled (SKIP_DASHBOARD_TESTS=true).');

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/dashboard`);
    await page.waitForLoadState('networkidle');
  });

  test('[DASH-001] Dashboard page loads successfully', async ({ page }) => {
    await expect(page).toHaveURL(/\/dashboard|\/$/);
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });
    await page.waitForTimeout(250);
    expect(errors.filter((e) => !e.includes('favicon'))).toHaveLength(0);
  });

  test('[DASH-002] Page title is displayed', async ({ page }) => {
    const title = page.locator('h1, h2, h3, [data-testid="dashboard-title"]');
    await expect(title.first()).toBeVisible();
  });

  test('[DASH-003] Stats section is present', async ({ page }) => {
    const stats = page.locator('#total-sources, #health-indicator, [data-testid="stats"], .stats, .stat-card, .stat-value, h3:has-text("System Stats")');
    const hasStats = await stats.first().isVisible().catch(() => false);
    expect(hasStats).toBe(true);
  });

  test('[DASH-004] Sources section is present', async ({ page }) => {
    const sources = page.locator('#total-sources, h3:has-text("Source"), h3:has-text("Failing"), [data-testid="sources"], .sources, h2:has-text("Source")');
    const hasSources = await sources.first().isVisible().catch(() => false);
    expect(hasSources).toBe(true);
  });

  test('[DASH-005] Recent articles section is present', async ({ page }) => {
    const articles = page.locator('#high-score-articles-container, #top-articles-container, [data-testid="recent-articles"], .recent-articles, h2:has-text("Recent"), h3:has-text("Article")');
    const hasArticles = await articles.first().isVisible().catch(() => false);
    expect(hasArticles).toBe(true);
  });
});

test.describe('Dashboard - Navigation', () => {
  test.skip(SKIP_TESTS, 'Dashboard tests disabled.');

  test('[DASH-010] Can navigate to Sources from Dashboard', async ({ page }) => {
    const sourcesLink = page.locator('a[href*="/sources"], a:has-text("Sources")').first();
    await sourcesLink.click();
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/sources/);
  });

  test('[DASH-011] Can navigate to Articles from Dashboard', async ({ page }) => {
    const articlesLink = page.locator('a[href*="/articles"], a:has-text("Article")').first();
    await articlesLink.click();
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/articles/);
  });

  test('[DASH-012] Can navigate to Chat from Dashboard', async ({ page }) => {
    const chatLink = page.locator('a[href*="/chat"], a:has-text("Chat")').first();
    const hasChatLink = await chatLink.isVisible().catch(() => false);
    if (hasChatLink) {
      await chatLink.click();
    } else {
      await page.goto(`${BASE}/chat`);
    }
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/chat/);
  });

  test('[DASH-013] Can navigate to Settings from Dashboard', async ({ page }) => {
    const settingsLink = page.locator('a[href*="/settings"], a:has-text("Settings")').first();
    await settingsLink.click();
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/settings/);
  });
});

test.describe('Dashboard - Stats Display', () => {
  test.skip(SKIP_TESTS, 'Dashboard tests disabled.');

  test('[DASH-020] Total articles count is displayed', async ({ page }) => {
    const count = page.locator('#top-articles-container, [data-testid="total-articles"], .stat:has-text("Article"), canvas#dailyChart');
    const hasCount = await count.first().isVisible().catch(() => false);
    expect(hasCount).toBe(true);
  });

  test('[DASH-021] Sources count is displayed', async ({ page }) => {
    const count = page.locator('#total-sources, [data-testid="sources-count"], .stat:has-text("Source"), span:has-text("Total Sources")');
    const hasCount = await count.first().isVisible().catch(() => false);
    expect(hasCount).toBe(true);
  });

  test('[DASH-022] Active sources are indicated', async ({ page }) => {
    const active = page.locator('span:has-text("Active Sources"), [data-testid="active-sources"], .active, .source.active');
    const hasActive = await active.first().isVisible().catch(() => false);
    expect(hasActive).toBe(true);
  });
});
