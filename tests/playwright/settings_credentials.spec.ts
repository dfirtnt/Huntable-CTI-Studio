import { test, expect, Page, Request } from '@playwright/test';

/**
 * The Settings credential contract.
 *
 * Two defects motivated these tests, and they compound:
 *
 *   1. The read API returned stored secrets, so full plaintext credentials sat in
 *      the live DOM behind `type="password"`.
 *   2. `saveSettings()` treated an empty field as "delete this", with no way to
 *      distinguish "the user cleared it" from "the GET failed and blanked it".
 *
 * Fixing (1) makes every credential field load empty, which would have made (2)
 * fire on every save. So the contract is asserted together: a secret never
 * reaches the page, and an empty field never deletes anything by itself.
 *
 * Every mutating request is intercepted and fulfilled locally. These tests must
 * not write to the live settings table.
 */

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const SKIP_TESTS = process.env.SKIP_SETTINGS_TESTS === 'true';

// Deliberately not shaped like a real PAT: a synthetic fixture that trips secret
// scanners costs more than it proves. Only its absence from the DOM is asserted.
const LIVE_TOKEN = 'cti-fixture-token-that-must-never-reach-the-browser-0123';

type Recorder = { requests: Request[] };

/**
 * Serve the settings reads this page makes, and swallow every write.
 * `failingKeys` are the GET /api/settings/{key} lookups that should fail.
 */
async function stubSettings(
  page: Page,
  opts: { failingKeys?: string[]; bulkFails?: boolean } = {},
): Promise<Recorder> {
  const failingKeys = opts.failingKeys || [];
  const recorder: Recorder = { requests: [] };

  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (method !== 'GET') {
      recorder.requests.push(request);
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ success: true, updated_keys: [], errors: [] }),
      });
      return;
    }

    if (path === '/api/settings') {
      if (opts.bulkFails) {
        await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
        return;
      }
      await route.fulfill({
        contentType: 'application/json',
        headers: { 'Cache-Control': 'no-store' },
        body: JSON.stringify({
          success: true,
          settings: {
            WORKFLOW_OPENAI_ENABLED: 'true',
            WORKFLOW_OPENAI_API_KEY: null,
            WORKFLOW_ANTHROPIC_API_KEY: null,
            GITHUB_REPO: 'owner/repo',
          },
          sensitive: {
            WORKFLOW_OPENAI_API_KEY: { configured: true, hint: 'sk-live1...(48 chars)' },
            WORKFLOW_ANTHROPIC_API_KEY: { configured: false, hint: null },
          },
        }),
      });
      return;
    }

    const keyMatch = path.match(/^\/api\/settings\/([^/]+)$/);
    if (keyMatch) {
      const key = keyMatch[1];
      if (failingKeys.includes(key)) {
        await route.fulfill({ status: 500, contentType: 'application/json', body: '{}' });
        return;
      }
      const sensitiveKeys = ['GITHUB_TOKEN', 'LANGFUSE_SECRET_KEY'];
      const isSensitive = sensitiveKeys.includes(key);
      await route.fulfill({
        contentType: 'application/json',
        headers: { 'Cache-Control': 'no-store' },
        body: JSON.stringify({
          success: true,
          key,
          value: isSensitive ? null : 'plain-value',
          exists: true,
          sensitive: isSensitive,
          configured: true,
          hint: isSensitive ? 'cti-fixt...(56 chars)' : null,
        }),
      });
      return;
    }

    await route.fallback();
  });

  return recorder;
}

async function openSettings(page: Page, { expandGitHub = false } = {}) {
  await page.goto(`${BASE}/settings`);
  await expect(page.locator('#saveSettings')).toBeVisible();
  await page.waitForFunction(() => document.body.dataset.settingsHydrated === 'true');
  if (expandGitHub) {
    // Section panels start collapsed, so credential controls are in the DOM but
    // not clickable until their card is opened.
    await page.locator('[data-collapsible-panel="githubPRConfig"]').click();
    await expect(page.locator('#githubToken')).toBeVisible();
  }
}

function settingsWrites(recorder: Recorder, key: string) {
  return recorder.requests.filter((r) => {
    const path = new URL(r.url()).pathname;
    if (path === `/api/settings/${key}`) return true;
    if (path === '/api/settings' && r.method() === 'POST') {
      const body = r.postDataJSON();
      return body && body.key === key;
    }
    return false;
  });
}

test.describe('Settings credential contract', () => {
  test.skip(SKIP_TESTS, 'Settings tests disabled (SKIP_SETTINGS_TESTS=true).');

  test('[SETTINGS-CRED-001] a failed credential load blocks the save instead of deleting', async ({ page }) => {
    const recorder = await stubSettings(page, { failingKeys: ['GITHUB_TOKEN'] });
    await openSettings(page);

    // The field reports that it could not load, rather than looking merely empty.
    await expect(page.locator('#githubTokenCredentialState')).toContainText('Could not load');
    await expect(page.locator('#githubToken')).toHaveAttribute('aria-invalid', 'true');

    await page.locator('#saveSettings').click();
    await page.waitForTimeout(750);

    // The stored token is untouched: no DELETE, and no POST writing an empty value.
    expect(settingsWrites(recorder, 'GITHUB_TOKEN')).toHaveLength(0);
  });

  test('[SETTINGS-CRED-002] an untouched configured secret is left alone on save', async ({ page }) => {
    const recorder = await stubSettings(page);
    await openSettings(page);

    // Loaded successfully, configured, and deliberately empty -- that is the
    // normal state now that the value is never returned.
    await expect(page.locator('#githubToken')).toHaveValue('');
    await expect(page.locator('#githubTokenCredentialState')).toContainText('Configured');

    await page.locator('#saveSettings').click();
    await page.waitForTimeout(750);

    expect(settingsWrites(recorder, 'GITHUB_TOKEN')).toHaveLength(0);
  });

  test('[SETTINGS-CRED-003] a typed credential is written', async ({ page }) => {
    const recorder = await stubSettings(page);
    await openSettings(page, { expandGitHub: true });

    await page.locator('#githubToken').fill('ghp_brandNewTokenTypedByTheOperator');
    await page.locator('#saveSettings').click();
    await page.waitForTimeout(750);

    const writes = settingsWrites(recorder, 'GITHUB_TOKEN');
    expect(writes).toHaveLength(1);
    expect(writes[0].method()).toBe('POST');
    expect(writes[0].postDataJSON().value).toBe('ghp_brandNewTokenTypedByTheOperator');
  });

  test('[SETTINGS-CRED-004] deleting a credential requires the explicit Clear action', async ({ page }) => {
    const recorder = await stubSettings(page);
    await openSettings(page, { expandGitHub: true });

    await page.locator('#githubTokenClearCredential').click();
    // ModalManager.confirm is not a native dialog -- drive the rendered modal.
    await page.locator('[id^="_confirm_"] .confirm-btn').click();
    await expect(page.locator('#githubTokenCredentialState')).toContainText('removed when you save');

    await page.locator('#saveSettings').click();
    await page.waitForTimeout(750);

    const writes = settingsWrites(recorder, 'GITHUB_TOKEN');
    expect(writes).toHaveLength(1);
    expect(writes[0].method()).toBe('DELETE');
  });

  test('[SETTINGS-CRED-005] a failed bulk read blocks the provider keys, not blanks them', async ({ page }) => {
    const recorder = await stubSettings(page, { bulkFails: true });
    await openSettings(page);

    await page.locator('#saveSettings').click();
    await page.waitForTimeout(750);

    const bulk = recorder.requests.filter((r) => new URL(r.url()).pathname === '/api/settings/bulk');
    expect(bulk.length).toBeGreaterThan(0);
    for (const request of bulk) {
      const payload = request.postDataJSON().settings || {};
      // Absent is correct. Present-and-empty would overwrite the stored key.
      expect(payload).not.toHaveProperty('WORKFLOW_OPENAI_API_KEY');
      expect(payload).not.toHaveProperty('WORKFLOW_ANTHROPIC_API_KEY');
    }
  });

  test('[SETTINGS-CRED-006] no credential value reaches the DOM', async ({ page }) => {
    await stubSettings(page);
    await openSettings(page);

    const html = await page.content();
    expect(html).not.toContain(LIVE_TOKEN);

    for (const id of ['githubToken', 'langfuseSecretKey', 'workflowOpenaiApiKey', 'workflowAnthropicApiKey']) {
      await expect(page.locator(`#${id}`)).toHaveValue('');
    }
  });

  test('[SETTINGS-CRED-007] a configured secret says so and offers a replace affordance', async ({ page }) => {
    await stubSettings(page);
    await openSettings(page, { expandGitHub: true });

    await expect(page.locator('#githubToken')).toHaveAttribute(
      'placeholder',
      'Configured -- enter a new value to replace',
    );
    await expect(page.locator('#githubTokenClearCredential')).toBeVisible();
  });
});
