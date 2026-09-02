import { test, expect } from '@playwright/test';

/**
 * copyArticleContent() (articles.html) previously called
 * navigator.clipboard.writeText() with no fallback and no cause-specific error
 * message. That works on 127.0.0.1 (a secure context in a normal browser) but
 * silently fails for anyone reaching the dev server over plain http:// on a
 * LAN address, where `navigator.clipboard` is unavailable -- with no hint why.
 *
 * These tests force the non-secure-context branch via an init script (rather
 * than relying on the environment actually being insecure) so the fallback
 * path is exercised deterministically regardless of how the suite is run.
 */

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

test.describe('Articles list - copy content clipboard fallback', () => {
  test.beforeEach(async ({ page }) => {
    // Force the non-secure-context branch before any page script runs.
    await page.addInitScript(() => {
      Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    });
  });

  test('falls back to execCommand and succeeds when the async Clipboard API is unavailable', async ({ page }) => {
    await page.goto(`${BASE}/articles`);
    await page.waitForLoadState('domcontentloaded');

    const execCommandCalls: string[] = [];
    await page.exposeFunction('__recordExecCommand', (cmd: string) => execCommandCalls.push(cmd));
    await page.evaluate(() => {
      const w = window as any;
      document.execCommand = ((cmd: string) => {
        (w as any).__recordExecCommand(cmd);
        return true;
      }) as any;
    });

    const copyButton = page.locator('[aria-label^="Copy content of article"]').first();
    await copyButton.waitFor({ state: 'attached' });
    await copyButton.click();

    await expect(page.getByText('Article content copied to clipboard!')).toBeVisible({ timeout: 5000 });
    expect(execCommandCalls).toContain('copy');

    // The fallback textarea must not leak into the DOM after use.
    expect(await page.locator('textarea').count()).toBe(0);
  });

  test('reports the actual cause when the fallback itself is unavailable', async ({ page }) => {
    await page.goto(`${BASE}/articles`);
    await page.waitForLoadState('domcontentloaded');

    await page.evaluate(() => {
      document.execCommand = (() => false) as any;
    });

    const copyButton = page.locator('[aria-label^="Copy content of article"]').first();
    await copyButton.waitFor({ state: 'attached' });
    await copyButton.click();

    await expect(page.getByText(/Clipboard access is unavailable/i)).toBeVisible({ timeout: 5000 });
    // Must not fall back to the old opaque, cause-less message.
    await expect(page.getByText('Failed to copy article content', { exact: true })).not.toBeVisible();
  });
});
