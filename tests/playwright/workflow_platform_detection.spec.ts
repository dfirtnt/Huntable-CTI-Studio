/**
 * Workflow Config -- Platform Detection (renamed/retargeted from
 * agent_config_os_detection.spec.ts per spec §7).
 *
 * Phase one renames the "OS Detection" workflow concept to "Platform Detection"
 * (it no longer hard-gates non-Windows articles; it routes by capability). This
 * read-only spec verifies the rename is reflected in the Workflow Config UI. It
 * lives in the `workflow` Playwright project so `run_tests.py ui --area workflow`
 * (spec §0.3) runs it, and it does not mutate config so it is not excluded from
 * the default UI run.
 */

import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

test.describe('Workflow Config - Platform Detection', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.evaluate(() => {
      if (typeof (window as any).switchTab === 'function') (window as any).switchTab('config');
    });
    await page.evaluate(() => document.getElementById('s0')?.classList.add('open'));
    await page.waitForSelector('#s0', { timeout: 15000 });
  });

  test('step 0 is titled Platform Detection (not OS Detection)', async ({ page }) => {
    const section = page.locator('#s0');
    await expect(section.locator('.section-title')).toHaveText('Platform Detection');
    await expect(section.locator('.section-title')).not.toHaveText(/OS Detection/);
  });

  test('pipeline rail labels step 0 as Platform Detection', async ({ page }) => {
    const railLabel = page.locator('.rail-item.c0 .rail-label');
    await expect(railLabel).toHaveText('Platform Detection');
  });
});
