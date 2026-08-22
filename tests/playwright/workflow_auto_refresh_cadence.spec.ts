import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

/**
 * Regression guard for the /workflow auto-refresh interval.
 *
 * Previously a single `setInterval` computed its period once, at script-load
 * time, from whichever tab was active then, while the callback re-checked the
 * tab on every fire -- so switching tabs changed WHAT was polled but never HOW
 * OFTEN. The fix is a self-rescheduling setTimeout that re-arms immediately on
 * tab switch (window.rearmAutoRefresh, called from switchTab()).
 *
 * Rather than waiting out real 10s/30s intervals (slow, flaky under load),
 * this spies on window.setTimeout calls with the two cadence values the app
 * uses (10000ms for executions, 30000ms otherwise) and asserts that a tab
 * switch immediately re-arms with the matching delay -- proving both that the
 * cadence is tab-aware and that it updates on switch, not just on next fire.
 */
test.describe('Workflow auto-refresh cadence', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      (window as any).__timeoutLog = [];
      const originalSetTimeout = window.setTimeout.bind(window);
      (window as any).setTimeout = ((handler: TimerHandler, delay?: number, ...args: any[]) => {
        if (delay === 10000 || delay === 30000) {
          (window as any).__timeoutLog.push({ delay, at: Date.now() });
        }
        return originalSetTimeout(handler as any, delay, ...args);
      }) as typeof window.setTimeout;
    });

    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
  });

  test('loading on a non-executions tab arms the 30s cadence', async ({ page }) => {
    const log = await page.evaluate(() => (window as any).__timeoutLog);
    expect(log.length).toBeGreaterThan(0);
    expect(log[log.length - 1].delay).toBe(30000);
  });

  test('switching to Executions re-arms the 10s cadence immediately, not on next fire', async ({ page }) => {
    const before = await page.evaluate(() => (window as any).__timeoutLog.length);

    await page.evaluate(() => {
      (window as any).switchTab('executions');
    });
    // rearmAutoRefresh() runs synchronously inside switchTab(); no need to
    // wait out the real interval to observe the new schedule call.
    await page.waitForFunction(
      (prevCount: number) => (window as any).__timeoutLog.length > prevCount,
      before,
      { timeout: 2000 },
    );

    const log = await page.evaluate(() => (window as any).__timeoutLog);
    expect(log[log.length - 1].delay).toBe(10000);
  });

  test('switching from Executions back to SIGMA Queue re-arms the 30s cadence, with no stacked timers', async ({ page }) => {
    await page.evaluate(() => (window as any).switchTab('executions'));
    await page.waitForTimeout(100);
    const afterExecutions = await page.evaluate(() => (window as any).__timeoutLog.length);

    await page.evaluate(() => (window as any).switchTab('queue'));
    await page.waitForFunction(
      (prevCount: number) => (window as any).__timeoutLog.length > prevCount,
      afterExecutions,
      { timeout: 2000 },
    );

    const log = await page.evaluate(() => (window as any).__timeoutLog);
    expect(log[log.length - 1].delay).toBe(30000);

    // Rapid tab switching must re-arm (clearTimeout + setTimeout), not stack a
    // second live interval alongside the first.
    await page.evaluate(() => (window as any).switchTab('executions'));
    await page.evaluate(() => (window as any).switchTab('queue'));
    await page.evaluate(() => (window as any).switchTab('executions'));
    await page.waitForTimeout(1500);

    // Only one real timer should be pending: wait past a single 10s fire plus
    // margin and confirm exactly one executions poll, not two-or-more from a
    // stacked interval.
    let executionsPolls = 0;
    page.on('request', (req) => {
      if (req.url().includes('/api/workflow/executions')) executionsPolls++;
    });
    await page.waitForTimeout(11000);
    expect(executionsPolls).toBeLessThanOrEqual(1);
  });
});
