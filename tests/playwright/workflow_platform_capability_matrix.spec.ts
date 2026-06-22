/**
 * Workflow Config -- read-only Platform Capability Matrix (spec §7).
 *
 * Phase one shows a read-only matrix of which extractors are platform-aware vs
 * Windows-only. This spec asserts the matrix renders in the Workflow Config tab
 * and reflects the phase-one capability intent (§4): shared extractors are
 * platform-aware; Registry/Services/ScheduledTasks are Windows-only.
 *
 * In goal-mode the matrix counts as delivered only when this spec prints green
 * (the evaluator cannot see a browser) -- spec §0.1/§7.
 */

import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

test.describe('Workflow Config - Platform Capability Matrix', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.evaluate(() => {
      if (typeof (window as any).switchTab === 'function') (window as any).switchTab('config');
    });
    // The matrix is server-rendered into the config tab; make sure step 0 is open.
    await page.evaluate(() => document.getElementById('s0')?.classList.add('open'));
    await page.waitForSelector('#platform-capability-matrix', { timeout: 15000 });
  });

  test('renders the read-only capability matrix', async ({ page }) => {
    const matrix = page.locator('#platform-capability-matrix');
    await expect(matrix).toBeVisible();
    await expect(matrix).toContainText('Platform Capability Matrix');
    await expect(matrix).toContainText('Read-only');
    // Column headers for the controlled platform vocabulary.
    await expect(matrix).toContainText('Windows');
    await expect(matrix).toContainText('Linux');
    await expect(matrix).toContainText('macOS');
  });

  test('marks Windows-only extractors as skipped on non-Windows platforms', async ({ page }) => {
    const matrix = page.locator('#platform-capability-matrix');
    // RegistryExtract is Windows-only in phase one (spec §4).
    const registryRow = matrix.locator('tr', { hasText: 'RegistryExtract' });
    await expect(registryRow).toContainText('Supported'); // Windows
    await expect(registryRow).toContainText('Skipped'); // Linux/macOS/cross
    for (const extractor of ['ServicesExtract', 'ScheduledTasksExtract']) {
      await expect(matrix.locator('tr', { hasText: extractor })).toContainText('Skipped');
    }
  });

  test('marks shared extractors as platform-aware', async ({ page }) => {
    const matrix = page.locator('#platform-capability-matrix');
    for (const extractor of ['CmdlineExtract', 'ProcTreeExtract']) {
      const row = matrix.locator('tr', { hasText: extractor });
      // Supported on Windows, Linux and macOS columns.
      const supportedCount = await row.locator('td', { hasText: /^Supported$/ }).count();
      expect(supportedCount).toBeGreaterThanOrEqual(3);
    }
  });
});
