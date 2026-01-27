/**
 * Modal stack and Enter key behaviour:
 * - ESC/cancel/click-away with multiple modals returns to previous modal
 * - Enter key triggers primary/enter button when modal has one
 */
import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const TEST_ARTICLE_ID = process.env.TEST_ARTICLE_ID || '68';

test.describe('Modal stack and Enter key', () => {
  test('ESC with nested modals closes only topmost and restores previous', async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const hasPush = await page.evaluate(() => typeof (window as any).pushModal === 'function');
    expect(hasPush).toBe(true);

    await page.evaluate(() => (window as any).pushModal('configPresetListModal', true));
    await expect(page.locator('#configPresetListModal')).toBeVisible({ timeout: 5000 });

    await page.evaluate(() => (window as any).pushModal('configVersionListModal', true));
    await expect(page.locator('#configVersionListModal')).toBeVisible({ timeout: 5000 });

    const stackBefore = await page.evaluate(() =>
      (window as any).ModalManager ? (window as any).ModalManager.getStack() : []
    );
    expect(stackBefore.length).toBeGreaterThanOrEqual(2);

    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);

    await expect(page.locator('#configVersionListModal')).not.toBeVisible({ timeout: 3000 });
    await expect(page.locator('#configPresetListModal')).toBeVisible({ timeout: 2000 });

    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    await expect(page.locator('#configPresetListModal')).not.toBeVisible({ timeout: 3000 });
  });

  test('Cancel button with nested modals closes topmost and restores previous', async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await page.evaluate(() => (window as any).pushModal('configPresetListModal', true));
    await expect(page.locator('#configPresetListModal')).toBeVisible({ timeout: 5000 });

    await page.evaluate(() => (window as any).pushModal('configVersionListModal', true));
    await expect(page.locator('#configVersionListModal')).toBeVisible({ timeout: 5000 });

    await page.locator('#configVersionListModal button:has-text("Close")').click();
    await page.waitForTimeout(500);

    await expect(page.locator('#configVersionListModal')).not.toBeVisible({ timeout: 3000 });
    await expect(page.locator('#configPresetListModal')).toBeVisible({ timeout: 2000 });

    await page.locator('#configPresetListModal button:has-text("Close")').click();
    await page.waitForTimeout(500);
    await expect(page.locator('#configPresetListModal')).not.toBeVisible({ timeout: 3000 });
  });

  test('Click backdrop with nested modals closes topmost and restores previous', async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await page.evaluate(() => (window as any).pushModal('configPresetListModal', true));
    await expect(page.locator('#configPresetListModal')).toBeVisible({ timeout: 5000 });

    await page.evaluate(() => (window as any).pushModal('configVersionListModal', true));
    await expect(page.locator('#configVersionListModal')).toBeVisible({ timeout: 5000 });

    const top = page.locator('#configVersionListModal');
    await top.click({ position: { x: 5, y: 5 } });
    await page.waitForTimeout(600);

    await expect(page.locator('#configVersionListModal')).not.toBeVisible({ timeout: 3000 });
    await expect(page.locator('#configPresetListModal')).toBeVisible({ timeout: 2000 });

    await page.locator('#configPresetListModal').click({ position: { x: 5, y: 5 } });
    await page.waitForTimeout(600);
    await expect(page.locator('#configPresetListModal')).not.toBeVisible({ timeout: 3000 });
  });

  test('Enter key triggers primary/enter button in modal', async ({ page }) => {
    await page.goto(`${BASE}/workflow#executions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await page.evaluate(() => {
      if (typeof (window as any).showTriggerWorkflowModal === 'function') {
        (window as any).showTriggerWorkflowModal();
      }
    });
    await expect(page.locator('#triggerWorkflowModal')).toBeVisible({ timeout: 5000 });

    await page.locator('#triggerArticleId').fill(TEST_ARTICLE_ID);
    await page.waitForTimeout(200);

    await page.keyboard.press('Enter');
    await page.waitForTimeout(2000);

    const modalClosed = await page.locator('#triggerWorkflowModal').isHidden().catch(() => false);
    const hasTriggerMsg = await page.locator('#triggerWorkflowMessage').isVisible().catch(() => false);
    expect(modalClosed || hasTriggerMsg).toBe(true);
  });
});
