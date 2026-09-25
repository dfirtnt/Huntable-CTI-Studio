import { test, expect, Page } from '@playwright/test';

/**
 * Loading the config tab must not write the config back.
 *
 * `agentic_workflow_config` had grown to 8,152 rows with exactly one active,
 * because opening /workflow#config and touching nothing saved a new version.
 * Three independent causes fed it:
 *
 *   1. `OSDetectionAgent_selected_os` is an array rebuilt on every read, and the
 *      dirty check compared it with `!==`, so it always reported changed.
 *   2. `SigmaEmbeddingModel` is stored by the server but has no config panel, so
 *      form state read it as undefined and it always differed.
 *   3. `applyAgentConfigs()` writes stored values into the form, and
 *      `setAgentProvider()` dispatches a real 'change' to rebuild dependent UI --
 *      which reached the user-edit handler and scheduled a save.
 *
 * This spec asserts the observable contract rather than any one cause: an
 * untouched load issues no write, and a real edit still does. It only reads, so
 * it is safe to run against the live config.
 */

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

async function loadConfigTab(page: Page): Promise<string[]> {
  const configWrites: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/workflow/config') && request.method() !== 'GET') {
      configWrites.push(`${request.method()} ${url.pathname}`);
    }
  });

  await page.goto(`${BASE}/workflow#config`);
  await expect(page.locator('#config-content')).toBeAttached();
  // The page loads config, prompts, the model catalog and LM Studio models before
  // it settles; autosave is debounced behind that, so give it room to misbehave.
  await page.waitForFunction(() => typeof (window as any).checkForUnsavedChanges === 'function');
  await page.waitForTimeout(6000);
  return configWrites;
}

test.describe('Workflow config does not save itself on load', () => {
  test('[WF-CFG-PHANTOM-001] an untouched load issues no config write', async ({ page }) => {
    const configWrites = await loadConfigTab(page);
    expect(configWrites).toEqual([]);
  });

  test('[WF-CFG-PHANTOM-002] the page does not consider itself dirty on load', async ({ page }) => {
    await loadConfigTab(page);

    const dirty = await page.evaluate(() => (window as any).checkForUnsavedChanges());
    expect(dirty).toBe(false);

    const saveButton = page.locator('#save-config-button');
    if (await saveButton.count()) {
      await expect(saveButton).toBeDisabled();
    }
  });

  test('[WF-CFG-PHANTOM-003] a real edit still triggers a save carrying every stored key', async ({ page, request }) => {
    // Read what the server holds through the API rather than page internals, so
    // this asserts the contract and not a particular global.
    const stored = await (await request.get(`${BASE}/api/workflow/config`)).json();
    const storedKeys = Object.keys(stored.agent_models || {}).sort();
    expect(storedKeys.length).toBeGreaterThan(0);

    await loadConfigTab(page);

    // Intercept the write so the assertion never mutates the live config.
    const captured = await page.evaluate(async () => {
      let body: any = null;
      const realFetch = window.fetch;
      window.fetch = function (url: any, opts: any) {
        const method = (opts && opts.method) || 'GET';
        if (String(url).includes('/api/workflow/config') && method === 'PUT') {
          body = JSON.parse(opts.body || '{}');
          // Echo the request back; the page only needs a well-shaped 200.
          return Promise.resolve(
            new Response(opts.body, { status: 200, headers: { 'Content-Type': 'application/json' } }),
          );
        }
        return realFetch.apply(this, arguments as any);
      };

      const temp = document.getElementById('cmdlineextract-temperature') as HTMLInputElement | null;
      const original = temp ? temp.value : null;
      if (temp) {
        temp.value = (parseFloat(temp.value || '0') + 0.1).toFixed(1);
        temp.dispatchEvent(new Event('change', { bubbles: true }));
      }
      await new Promise((r) => setTimeout(r, 3000));
      if (temp && original !== null) {
        temp.value = original;
        temp.dispatchEvent(new Event('input', { bubbles: true }));
      }
      window.fetch = realFetch;

      return {
        sawWrite: body !== null,
        sentKeys: Object.keys((body && body.agent_models) || {}).sort(),
      };
    });

    expect(captured.sawWrite).toBe(true);
    // The payload must stand on its own rather than relying on the backend's
    // agent_models merge to restore whatever the page failed to send.
    for (const key of storedKeys) {
      expect(captured.sentKeys).toContain(key);
    }
  });
});
