import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Agent Config Error Handling', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(1000);

    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    await page.waitForTimeout(2000);

    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');
  });

  test('should handle API failure during autosave gracefully', async ({ page }) => {
    // Intercept and fail the PUT request
    await page.route('**/api/workflow/config', route => {
      if (route.request().method() === 'PUT') {
        route.fulfill({
          status: 500,
          body: JSON.stringify({ detail: 'Internal server error' })
        });
      } else {
        route.continue();
      }
    });

    const input = page.locator('#rankingThreshold');
    await input.waitFor({ state: 'visible', timeout: 10000 });

    const newValue = '7.0';

    // Change should not throw error or break UI
    await input.fill(newValue);
    await input.blur();

    // Wait for error to be logged (but UI should remain functional)
    await page.waitForTimeout(1000);

    // Verify input still has the value (UI didn't break)
    const currentValue = await input.inputValue();
    expect(parseFloat(currentValue)).toBeCloseTo(7.0, 1);

    // Verify form is still functional
    await expect(input).toBeEnabled();
  });

  test('should handle network errors gracefully', async ({ page }) => {
    // Intercept and fail with network error
    await page.route('**/api/workflow/config', route => {
      if (route.request().method() === 'PUT') {
        route.abort('failed');
      } else {
        route.continue();
      }
    });

    const input = page.locator('#rankingThreshold');
    await input.waitFor({ state: 'visible', timeout: 10000 });

    const newValue = '7.5';

    // Change should not break UI
    await input.fill(newValue);
    await input.blur();

    await page.waitForTimeout(1000);

    // UI should remain functional
    const currentValue = await input.inputValue();
    expect(parseFloat(currentValue)).toBeCloseTo(7.5, 1);
    await expect(input).toBeEnabled();
  });

  test('should handle invalid API responses', async ({ page }) => {
    // Intercept and return malformed response
    await page.route('**/api/workflow/config', route => {
      if (route.request().method() === 'PUT') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: 'invalid json{'
        });
      } else {
        route.continue();
      }
    });

    const input = page.locator('#rankingThreshold');
    await input.waitFor({ state: 'visible', timeout: 10000 });

    const newValue = '8.0';

    // Change should not break UI
    await input.fill(newValue);
    await input.blur();

    await page.waitForTimeout(1000);

    // UI should remain functional
    const currentValue = await input.inputValue();
    expect(parseFloat(currentValue)).toBeCloseTo(8.0, 1);
  });

  test('should handle concurrent autosave requests correctly', async ({ page }) => {
    const rankingInput = page.locator('#rankingThreshold');
    const junkFilterInput = page.locator('#junkFilterThreshold');

    await rankingInput.waitFor({ state: 'visible', timeout: 10000 });
    await expandPanelIfNeeded(page, 'other-thresholds-panel');
    await junkFilterInput.waitFor({ state: 'visible', timeout: 10000 });

    let requestCount = 0;
    page.on('request', (request) => {
      if (request.url().includes('/api/workflow/config') && request.method() === 'PUT') {
        requestCount++;
      }
    });

    // Make rapid changes to different fields
    await rankingInput.fill('7.0');
    await page.waitForTimeout(100);
    await junkFilterInput.fill('0.85');
    await page.waitForTimeout(100);

    // Wait for debounce to complete
    await page.waitForTimeout(1000);

    // Should handle concurrent requests (may be debounced into one or a few)
    expect(requestCount).toBeGreaterThan(0);
    expect(requestCount).toBeLessThanOrEqual(3); // Debouncing should limit requests
  });

  test('should not break UI when autosave fails multiple times', async ({ page }) => {
    // Intercept and fail multiple times
    await page.route('**/api/workflow/config', route => {
      if (route.request().method() === 'PUT') {
        route.fulfill({
          status: 500,
          body: JSON.stringify({ detail: 'Server error' })
        });
      } else {
        route.continue();
      }
    });

    const input = page.locator('#rankingThreshold');
    await input.waitFor({ state: 'visible', timeout: 10000 });

    // Make multiple changes
    for (let i = 0; i < 3; i++) {
      await input.fill((6.0 + i * 0.5).toString());
      await input.blur();
      await page.waitForTimeout(500);
    }

    // UI should still be functional
    await expect(input).toBeEnabled();
    const currentValue = await input.inputValue();
    expect(parseFloat(currentValue)).toBeGreaterThan(0);
  });
});

async function expandPanelIfNeeded(page: any, panelId: string) {
  const content = page.locator(`#${panelId}-content`);
  const toggle = page.locator(`#${panelId}-toggle, button[onclick*="${panelId}"]`).first();

  if (await toggle.isVisible({ timeout: 2000 }).catch(() => false)) {
    const isHidden = await content.evaluate((el: HTMLElement) => el.classList.contains('hidden')).catch(() => true);
    if (isHidden) {
      await toggle.click();
      await page.waitForTimeout(300);
    }
  }
}
