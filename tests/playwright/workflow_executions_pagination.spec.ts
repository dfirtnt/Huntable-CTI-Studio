import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

test.describe('Workflow executions pagination', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#executions`);
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('#tab-content-executions:not(.hidden)', { timeout: 10000 }).catch(async () => {
      await page.locator('#tab-executions, button:has-text("Executions")').first().click();
      await page.waitForTimeout(500);
    });
  });

  test('Executions API is called with page and limit params', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (r) =>
        r.url().includes('/api/workflow/executions') &&
        r.url().includes('page=') &&
        r.url().includes('limit=') &&
        r.request().method() === 'GET',
      { timeout: 10000 }
    );
    await page.locator('button:has-text("Refresh")').first().click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    const url = new URL(response.url());
    expect(url.searchParams.get('page')).toBeTruthy();
    expect(url.searchParams.get('limit')).toBeTruthy();
  });

  test('Pagination footer shows when more than 50 executions', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/workflow/executions') && r.request().method() === 'GET',
      { timeout: 10000 }
    );
    await page.locator('button:has-text("Refresh")').first().click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    const data = await response.json();
    const total = data?.total ?? 0;
    await page.waitForTimeout(500);
    const paginationEl = page.locator('#executionPagination');
    const pageInfo = page.locator('#executionPageInfo');
    if (total > 50) {
      await expect(paginationEl).toBeVisible();
      await expect(pageInfo).toContainText('Page');
      await expect(page.locator('#executionPrevBtn')).toBeVisible();
      await expect(page.locator('#executionNextBtn')).toBeVisible();
    }
  });

  test('Page info displays total and page numbers', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/workflow/executions') && r.request().method() === 'GET',
      { timeout: 10000 }
    );
    await page.locator('button:has-text("Refresh")').first().click();
    await responsePromise;
    await page.waitForTimeout(500);
    const pageInfo = page.locator('#executionPageInfo');
    const text = await pageInfo.textContent();
    expect(text).toMatch(/Page \d+ of \d+/);
    expect(text).toMatch(/\(\d+ total\)/);
  });
});
