import { test, expect } from '@playwright/test';

/**
 * ml_hunt_comparison.html had 11 of 12 fetch() call sites that went straight
 * from `await fetch(...)` to `await resp.json()` with no `resp.ok` check. A
 * FastAPI error body (`{"detail": ...}`) has no `success` key, so every
 * 4xx/5xx fell into the same branch as a legitimate empty result -- an
 * outage looked identical to "nothing here yet", and a "Refresh Status"
 * during a backend outage looked like a successful refresh.
 *
 * Each API route is intercepted independently so a genuine empty (200, zero
 * rows) result is proven to still render as "no data" -- the fix must not
 * turn every empty result into a false error.
 */

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

test.describe('Model Performance page - HTTP error handling', () => {
  test('a 500 on /api/model/versions shows an error distinct from the empty state', async ({ page }) => {
    await page.route('**/api/model/versions**', (route) =>
      route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'boom' }) })
    );

    await page.goto(`${BASE}/ml-model-performance`);
    await page.waitForLoadState('domcontentloaded');
    await page.locator('button[title="Refresh"]').click();

    const listEl = page.locator('#modelVersionHistoryList');
    await expect(listEl).toContainText(/Failed to load version history/i);
    await expect(listEl.locator('.text-red-400')).toBeVisible();
    await expect(listEl).not.toContainText('No model versions recorded yet.');
  });

  test('a genuine empty result (200, zero versions) still renders the plain empty state', async ({ page }) => {
    await page.route('**/api/model/versions**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, versions: [], total_versions: 0, total_pages: 1 }),
      })
    );

    await page.goto(`${BASE}/ml-model-performance`);
    await page.waitForLoadState('domcontentloaded');
    await page.locator('button[title="Refresh"]').click();

    const listEl = page.locator('#modelVersionHistoryList');
    await expect(listEl).toContainText('No model versions recorded yet.');
    await expect(listEl.locator('.text-red-400')).toHaveCount(0);
  });

  test('an outage across every /api/ endpoint surfaces a failure instead of leaving stale tiles unmarked', async ({
    page,
  }) => {
    await page.goto(`${BASE}/ml-model-performance`);
    await page.waitForLoadState('domcontentloaded');
    // Let the real initial load populate the KPI tiles first.
    await expect(page.locator('#totalModelVersions')).not.toHaveText('-', { timeout: 10000 });

    await page.route('**/api/**', (route) =>
      route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'down' }) })
    );

    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await page.evaluate(() => (window as any).loadInitialData());

    await expect(page.getByText('Failed to load initial data')).toBeVisible({ timeout: 5000 });
    expect(consoleErrors.some((e) => e.includes('Error loading initial data'))).toBe(true);
  });

  test('a 422 rollback validation error renders the message, not [object Object]', async ({ page }) => {
    await page.route('**/api/model/rollback/**', (route) =>
      route.fulfill({
        status: 422,
        contentType: 'application/json',
        body: JSON.stringify({ detail: [{ msg: 'version_id must be a positive integer', type: 'int_parsing' }] }),
      })
    );

    await page.goto(`${BASE}/ml-model-performance`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => {
      (window as any).confirmRollback(999999, '999999');
    });
    await page.evaluate(() => (window as any).executeRollback());

    const progressText = page.locator('#rollbackProgressText');
    await expect(progressText).toContainText('version_id must be a positive integer', { timeout: 5000 });
    await expect(progressText).not.toContainText('[object Object]');
  });
});
