import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

/**
 * Regression tests for two Diags page ("System Diagnostics & Health",
 * src/web/templates/diags.html) fixes shipped together in a72c3a31:
 *
 * 1. DOM-XSS: updateOverallHealthStatus() interpolated `data.error` directly
 *    into `content.innerHTML` (line ~624), unlike every sibling health-card
 *    updater which already used escapeHtml()/textContent. A health endpoint
 *    (or a caught fetch error whose message reflects response content)
 *    returning an `error` string containing markup would execute it. Fixed
 *    by wrapping the interpolation in escapeHtml().
 *
 * 2. Batch overlay/button: "Run All Health Checks" issues five sequential
 *    health-check calls, each of which independently showed/hid the single
 *    #loadingOverlay and never disabled the trigger button -- so the overlay
 *    could flicker between checks and a second click mid-run could start an
 *    overlapping batch. Fixed by having the click handler own the overlay
 *    for the whole batch (each update*Health() call takes a suppressOverlay
 *    flag) and disable/re-enable the button around the run.
 */
const XSS_PAYLOAD = '<img src=x onerror="window.__diags_xss_fired=true">';

test.describe('Diags health check regression', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/diags`);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#runAllHealthChecks')).toBeVisible();
  });

  test('[DIAGS-XSS-001] overall health status escapes error markup instead of executing it', async ({ page }) => {
    await page.route('**/api/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'error', error: XSS_PAYLOAD, timestamp: new Date().toISOString() }),
      });
    });
    // Sibling checks aren't under test here; stub them healthy so the batch
    // completes quickly and doesn't depend on live worker/DB/service state.
    await page.route('**/api/health/**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'healthy' }) });
    });

    await page.locator('#runAllHealthChecks').click();
    await expect(page.locator('#loadingOverlay')).toBeHidden({ timeout: 10000 });

    const content = page.locator('#overallHealthStatus');
    await expect(content).toContainText('img src=x onerror=');

    const result = await content.evaluate((el) => ({
      imgCount: el.querySelectorAll('img').length,
      hasOnError: Array.from(el.querySelectorAll('*')).some((node) => node.hasAttribute('onerror')),
    }));
    expect(result.imgCount).toBe(0);
    expect(result.hasOnError).toBe(false);

    const xssFired = await page.evaluate(() => (window as any).__diags_xss_fired === true);
    expect(xssFired).toBe(false);
  });

  test('[DIAGS-BATCH-001] batch run shows a single overlay and disables the trigger button', async ({ page }) => {
    await page.route('**/api/health**', async (route) => {
      // Hold each response open briefly so the mid-run state is observable.
      await new Promise((resolve) => setTimeout(resolve, 200));
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'healthy', timestamp: new Date().toISOString() }) });
    });

    const button = page.locator('#runAllHealthChecks');
    const overlay = page.locator('#loadingOverlay');

    await expect(overlay).toBeHidden();
    await button.click();

    await expect(overlay).toBeVisible();
    await expect(button).toBeDisabled();
    // The overlay is a single singleton element -- assert only one is ever
    // shown, and that a second click while running doesn't re-open it.
    await expect(page.locator('#loadingOverlay')).toHaveCount(1);
    await button.click({ force: true }); // no-op while disabled

    await expect(overlay).toBeHidden({ timeout: 10000 });
    await expect(button).toBeEnabled();
  });

  test('[DIAGS-FOCUS-001] batch run sets aria-busy, traps focus in the overlay, and restores it on completion', async ({ page }) => {
    await page.route('**/api/health**', async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 200));
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'healthy', timestamp: new Date().toISOString() }) });
    });

    const button = page.locator('#runAllHealthChecks');
    const overlay = page.locator('#loadingOverlay');

    await button.click();
    await expect(button).toHaveAttribute('aria-busy', 'true');
    await expect(overlay).toBeFocused();

    // Tab must not escape the overlay while it's open (it has no focusable
    // descendants, so the trap keeps focus pinned on the overlay itself).
    await page.keyboard.press('Tab');
    await expect(overlay).toBeFocused();

    await expect(overlay).toBeHidden({ timeout: 10000 });
    await expect(button).not.toHaveAttribute('aria-busy', 'true');
    await expect(button).toBeFocused();
  });

  test('[DIAGS-FRESH-001] each health card shows its own checked-at time after a run', async ({ page }) => {
    await page.route('**/api/health**', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'healthy', timestamp: new Date().toISOString() }) });
    });

    const checkedAtIds = [
      'overallHealthCheckedAt',
      'databaseHealthCheckedAt',
      'deduplicationHealthCheckedAt',
      'servicesHealthCheckedAt',
      'celeryHealthCheckedAt',
    ];
    for (const id of checkedAtIds) {
      await expect(page.locator(`#${id}`)).toHaveText('');
    }

    await page.locator('#runAllHealthChecks').click();
    await expect(page.locator('#loadingOverlay')).toBeHidden({ timeout: 10000 });

    for (const id of checkedAtIds) {
      await expect(page.locator(`#${id}`)).toContainText('checked');
    }

    // The toolbar clock is scoped to job data, not the health cards, and says so.
    await expect(page.locator('.last-updated')).toContainText('Job data last updated');
  });

  test('[DIAGS-TESSERACT-001] a degraded service moves the card red without hiding the per-service breakdown', async ({ page }) => {
    // Regression for the "false TESSERACT missing alarm" fix: the top-level
    // services status used to be hardcoded "healthy", so a real failure never
    // reddened the card (issue 3) -- and once fixed naively, the per-service
    // list rendering was gated on that same "healthy" status, so a real
    // failure hid every service's detail behind a bare "Unknown error"
    // instead of showing which service failed and why.
    await page.route('**/api/health**', async (route) => {
      const url = route.request().url();
      if (url.endsWith('/api/health/services')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            status: 'unhealthy',
            timestamp: new Date().toISOString(),
            services: {
              redis: { status: 'healthy', info: {} },
              tesseract: { status: 'missing', version: null, message: 'Tesseract binary not found' },
            },
          }),
        });
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'healthy', timestamp: new Date().toISOString() }) });
    });

    await page.locator('#runAllHealthChecks').click();
    await expect(page.locator('#loadingOverlay')).toBeHidden({ timeout: 10000 });

    await expect(page.locator('#cardServices')).toHaveClass(/health-bad/);
    const content = page.locator('#servicesHealthContent');
    await expect(content).toContainText('REDIS');
    await expect(content).toContainText('TESSERACT');
    await expect(content).toContainText('Tesseract binary not found');
    await expect(content).not.toContainText('Unknown error');
  });

  test('[DIAGS-TESSERACT-002] tesseract not applicable in the web process renders a neutral icon and a healthy card', async ({ page }) => {
    // Live, unmocked: this dev/test web container never has pytesseract
    // installed (it's an optional worker-only extra), so this exercises the
    // real by-design "not_applicable" path end to end.
    await page.locator('#runAllHealthChecks').click();
    await expect(page.locator('#loadingOverlay')).toBeHidden({ timeout: 10000 });

    const content = page.locator('#servicesHealthContent');
    await expect(content).toContainText('TESSERACT');
    await expect(content).toContainText('not_applicable');
    await expect(content).not.toContainText('ModuleNotFoundError');
    await expect(content).not.toContainText('Traceback');
    await expect(page.locator('#cardServices')).toHaveClass(/health-ok/);
  });
});
