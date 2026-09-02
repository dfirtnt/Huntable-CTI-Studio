import { test, expect, Page, Request } from '@playwright/test';

/**
 * The Settings save model.
 *
 * /settings expands to ~5,500px behind a single Save button. Three things about
 * that were untrustworthy:
 *
 *   1. No dirty state and no beforeunload guard, so whether anything was pending
 *      was unanswerable without scrolling to the bottom, and navigating away
 *      discarded edits silently.
 *   2. `saveSettings()` runs seven sections with no rollback between them and
 *      reported failure as a bare list of section labels -- never what applied.
 *   3. Buttons that fire the moment they are clicked (Create Backup Now, the
 *      Test connection variants, Restore from Backup) were styled identically to
 *      fields that wait for Save.
 *
 * Every mutating request is intercepted. These tests must not write settings.
 */

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const SKIP_TESTS = process.env.SKIP_SETTINGS_TESTS === 'true';

type Recorder = { requests: Request[] };

/** Serve reads normally; swallow every write, optionally failing named paths. */
async function stubWrites(page: Page, failingPaths: string[] = []): Promise<Recorder> {
  const recorder: Recorder = { requests: [] };

  await page.route('**/api/**', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await route.fallback();
      return;
    }
    recorder.requests.push(request);
    const path = new URL(request.url()).pathname;
    if (failingPaths.some((p) => path.startsWith(p))) {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'stubbed failure' }),
      });
      return;
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ success: true, updated_keys: [], errors: [] }),
    });
  });

  return recorder;
}

async function openSettings(page: Page) {
  await page.goto(`${BASE}/settings`);
  await expect(page.locator('#saveSettings')).toBeVisible();
  await page.waitForFunction(() => document.body.dataset.settingsHydrated === 'true');
}

test.describe('Settings unsaved-change state', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled (SKIP_SETTINGS_TESTS=true).');

  test('[SETTINGS-SAVE-001] a freshly loaded page reports nothing pending', async ({ page }) => {
    await stubWrites(page);
    await openSettings(page);

    await expect(page.locator('#settingsDirtyState')).toHaveText('No unsaved changes');
    await expect(page.locator('#settingsSaveBar')).toHaveAttribute('data-dirty', 'false');
  });

  test('[SETTINGS-SAVE-002] the count tracks edits and clears when they are reverted', async ({ page }) => {
    await stubWrites(page);
    await openSettings(page);

    await page.locator('[data-collapsible-panel="githubPRConfig"]').click();
    const repo = page.locator('#githubRepo');
    const original = await repo.inputValue();

    await repo.fill(`${original}-edited`);
    await expect(page.locator('#settingsDirtyState')).toHaveText('1 unsaved change');
    await expect(page.locator('#settingsSaveBar')).toHaveAttribute('data-dirty', 'true');

    await page.locator('#gitUserName').fill('Someone Else');
    await expect(page.locator('#settingsDirtyState')).toHaveText('2 unsaved changes');

    // Editing back to the original value must clear the flag, not latch it.
    await repo.fill(original);
    await expect(page.locator('#settingsDirtyState')).toHaveText('1 unsaved change');
  });

  test('[SETTINGS-SAVE-003] the save bar stays reachable from the top of the page', async ({ page }) => {
    await stubWrites(page);
    await openSettings(page);

    await page.evaluate(() => window.scrollTo(0, 0));
    // Sticky, not merely present at the bottom of a 5,500px document.
    await expect(page.locator('#saveSettings')).toBeInViewport();
    const position = await page
      .locator('#settingsSaveBar')
      .evaluate((el) => getComputedStyle(el).position);
    expect(position).toBe('sticky');
  });

  test('[SETTINGS-SAVE-004] the unload guard fires only when something is pending', async ({ page }) => {
    await stubWrites(page);
    await openSettings(page);

    const fire = () =>
      page.evaluate(() => {
        const event = new Event('beforeunload', { cancelable: true });
        window.dispatchEvent(event);
        return event.defaultPrevented;
      });

    expect(await fire()).toBe(false);

    await page.locator('[data-collapsible-panel="githubPRConfig"]').click();
    await page.locator('#githubRepo').fill('owner/changed');
    expect(await fire()).toBe(true);
  });
});

test.describe('Settings per-section save reporting', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled.');

  test('[SETTINGS-SAVE-010] a partial failure names what applied and what did not', async ({ page }) => {
    // Fail one section; the rest still write, because there is no rollback.
    const recorder = await stubWrites(page, ['/api/scheduled-jobs']);
    await openSettings(page);

    await page.locator('#saveSettings').click();
    const report = page.locator('#settingsSaveReport');
    await expect(report).toBeVisible();

    // The old toast said only "Failed to save: scheduled jobs" and never stated
    // that the other six sections had already been written.
    await expect(report.locator('li .is-failed')).toHaveCount(1);
    expect(await report.locator('li .is-applied').count()).toBeGreaterThan(0);
    await expect(report).toContainText('scheduled jobs');

    expect(recorder.requests.length).toBeGreaterThan(0);
  });

  test('[SETTINGS-SAVE-011] a clean save reports every section as applied', async ({ page }) => {
    await stubWrites(page);
    await openSettings(page);

    await page.locator('#saveSettings').click();
    const report = page.locator('#settingsSaveReport');
    await expect(report).toBeVisible();

    await expect(report.locator('li .is-failed')).toHaveCount(0);
    expect(await report.locator('li .is-applied').count()).toBeGreaterThan(0);
  });

  test('[SETTINGS-SAVE-012] the report outlives the toast', async ({ page }) => {
    await stubWrites(page, ['/api/scheduled-jobs']);
    await openSettings(page);

    await page.locator('#saveSettings').click();
    await expect(page.locator('#settingsSaveReport')).toBeVisible();

    // Toasts self-remove after 5s; a partial-save summary must not.
    await page.waitForTimeout(6000);
    await expect(page.locator('#settingsSaveReport')).toBeVisible();
    await expect(page.locator('#settingsSaveReport')).toContainText('scheduled jobs');
  });

  test('[SETTINGS-SAVE-013] section detail renders as text, never as markup', async ({ page }) => {
    await stubWrites(page);
    await openSettings(page);

    const injected = await page.evaluate(() => {
      const w = window as any;
      w.renderSaveReport([{ label: 'x', status: 'failed', detail: '<' + 'img src=q onerror=void(0)' + '>' }]);
      const host = document.getElementById('settingsSaveReport')!;
      return { images: host.querySelectorAll('img').length, text: host.querySelector('li')!.textContent };
    });

    expect(injected.images).toBe(0);
    expect(injected.text).toContain('img src=q');
  });
});

test.describe('Settings immediate-effect controls', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled.');

  test('[SETTINGS-SAVE-020] act-now buttons are marked and Save is not', async ({ page }) => {
    await stubWrites(page);
    await openSettings(page);

    // Save is the deferred control; marking it would invert the convention.
    await expect(page.locator('#saveSettings')).not.toHaveClass(/settings-btn-immediate/);

    for (const id of [
      'createBackupBtn',
      'applyBackupCronBtn',
      'disableBackupCronBtn',
      'refreshScheduledJobsBtn',
      'exportAnnotationsBtn',
      'restoreBackupBtn',
      'testGitHubConnection',
      'testLangfuseConnection',
    ]) {
      await expect(page.locator(`#${id}`)).toHaveClass(/settings-btn-immediate/);
    }
  });

  test('[SETTINGS-SAVE-021] the marker is a visible treatment, not a bare class', async ({ page }) => {
    await stubWrites(page);
    await openSettings(page);

    const style = await page.locator('#createBackupBtn').evaluate((el) => {
      const cs = getComputedStyle(el);
      return { border: cs.borderTopColor, shadow: cs.boxShadow };
    });

    // An unset CSS variable would leave these transparent/none and the marker invisible.
    expect(style.border).not.toBe('rgba(0, 0, 0, 0)');
    expect(style.shadow).not.toBe('none');
    expect(style.shadow).toContain('inset');
  });

  test('[SETTINGS-SAVE-022] a legend explains the marker', async ({ page }) => {
    await stubWrites(page);
    await openSettings(page);

    const legend = page.locator('.settings-immediate-legend');
    await expect(legend).toBeVisible();
    await expect(legend).toContainText('act immediately');
    await expect(legend.locator('.settings-immediate-swatch')).toHaveCount(1);
  });
});
