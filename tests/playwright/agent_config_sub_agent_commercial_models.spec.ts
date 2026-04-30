/**
 * Regression tests for sub-agent and QA agent commercial model inputs.
 *
 * Before the fix, renderSubAgentCommercialInputs had its own inline <select>
 * generation path (catalog-present) that silently dropped onchange, data-config-key,
 * and aria-label attributes. buildCommercialProviderInput was only called as a
 * fallback when the catalog was empty, which is never the case in normal operation.
 *
 * The fix collapses the function to always delegate to buildCommercialProviderInput,
 * matching the main agents (rankagent, extractagent, sigmaagent).
 *
 * Key assertions:
 *   - commercial model inputs for sub-agents have an onchange handler
 *   - provider switching triggers autosave for sub-agents
 */

import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

// Agents covered by renderSubAgentCommercialInputs:
//   isSubAgent: cmdlineextract, proctreeextract, huntqueriesextract, registryextract, servicesextract
//   isQA:       rankqa, cmdlineqa, proctreeqa, huntqueriesqa, registryqa, servicesqa
//
// We test two representative agents:
//   - cmdlineextract  (sub-agent, in extract step s3 / sa-cmdline accordion)
//   - rankqa          (QA agent, in rank agent step s2 / qa-settings panel)

test.describe('Sub-agent commercial model inputs have onchange handler', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await page.evaluate(() => {
      if (typeof (window as any).switchTab === 'function') {
        (window as any).switchTab('config');
      }
    });
    await page.waitForTimeout(1000);
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    // Wait for initialization flag to clear (set false after loadConfig completes)
    await page.waitForFunction(() => (window as any).isInitializing === false, { timeout: 10000 });
  });

  // -------------------------------------------------------------------------
  // cmdlineextract (sub-agent inside Extract Agents accordion)
  // -------------------------------------------------------------------------

  test('cmdlineextract: switching to OpenAI renders model input with onchange', async ({ page }) => {
    // Open extract agents step (s3) and the cmdline sub-accordion
    await page.evaluate(() => {
      document.getElementById('s3')?.classList.add('open');
    });
    await page.waitForTimeout(500);

    await page.evaluate(() => {
      if (typeof (window as any).toggleSA === 'function') {
        (window as any).toggleSA('sa-cmdline');
      } else {
        document.getElementById('sa-cmdline')?.classList.add('open');
      }
    });
    await page.waitForTimeout(800);

    const providerSelect = page.locator('#cmdlineextract-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    await providerSelect.selectOption('openai');
    await page.waitForTimeout(2000);

    const modelInput = page.locator('#cmdlineextract-model-openai');
    await modelInput.waitFor({ state: 'attached', timeout: 8000 });

    // Regression: onchange must be present (it was missing before the fix)
    const onchange = await modelInput.getAttribute('onchange');
    expect(onchange).not.toBeNull();
    expect(onchange).toContain('autoSaveModelChange');
  });

  test('cmdlineextract: switching to Anthropic renders model input with onchange', async ({ page }) => {
    await page.evaluate(() => {
      document.getElementById('s3')?.classList.add('open');
    });
    await page.waitForTimeout(500);

    await page.evaluate(() => {
      if (typeof (window as any).toggleSA === 'function') {
        (window as any).toggleSA('sa-cmdline');
      } else {
        document.getElementById('sa-cmdline')?.classList.add('open');
      }
    });
    await page.waitForTimeout(800);

    const providerSelect = page.locator('#cmdlineextract-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    const hasAnthropic = await providerSelect.locator('option[value="anthropic"]').count() > 0;
    if (!hasAnthropic) {
      test.skip(true, 'Anthropic provider not enabled');
      return;
    }

    await providerSelect.selectOption('anthropic');
    await page.waitForTimeout(2000);

    const modelInput = page.locator('#cmdlineextract-model-anthropic');
    await modelInput.waitFor({ state: 'attached', timeout: 8000 });

    const onchange = await modelInput.getAttribute('onchange');
    expect(onchange).not.toBeNull();
    expect(onchange).toContain('autoSaveModelChange');
  });

  // -------------------------------------------------------------------------
  // rankqa (QA agent inside Rank Agent step s2)
  // -------------------------------------------------------------------------

  test('rankqa: switching to OpenAI renders model input with onchange', async ({ page }) => {
    await page.evaluate(() => {
      document.getElementById('s2')?.classList.add('open');
      // rankqa panel is inside rank-agent-qa-configs which is hidden until QA is enabled
      document.getElementById('rank-agent-qa-configs')?.classList.remove('hidden');
    });
    await page.waitForTimeout(800);

    const providerSelect = page.locator('#rankqa-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    await providerSelect.selectOption('openai');
    await page.waitForTimeout(2000);

    const modelInput = page.locator('#rankqa-model-openai');
    await modelInput.waitFor({ state: 'attached', timeout: 8000 });

    const onchange = await modelInput.getAttribute('onchange');
    expect(onchange).not.toBeNull();
    expect(onchange).toContain('autoSaveModelChange');
  });

  // -------------------------------------------------------------------------
  // Autosave fires when a sub-agent commercial model changes
  // -------------------------------------------------------------------------

  test('cmdlineextract: changing OpenAI model triggers autosave', async ({ page }) => {
    await page.evaluate(() => {
      document.getElementById('s3')?.classList.add('open');
    });
    await page.waitForTimeout(500);

    await page.evaluate(() => {
      if (typeof (window as any).toggleSA === 'function') {
        (window as any).toggleSA('sa-cmdline');
      } else {
        document.getElementById('sa-cmdline')?.classList.add('open');
      }
    });
    await page.waitForTimeout(800);

    const providerSelect = page.locator('#cmdlineextract-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    await providerSelect.selectOption('openai');
    await page.waitForTimeout(2000);

    const modelInput = page.locator('#cmdlineextract-model-openai');
    await modelInput.waitFor({ state: 'attached', timeout: 8000 });

    const tagName = await modelInput.evaluate((el: HTMLElement) => el.tagName.toLowerCase());

    const autosavePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 10000 }
    );

    if (tagName === 'select') {
      // Pick the first non-empty option from the catalog dropdown
      const firstOption = await modelInput.locator('option:not([value=""])').first().getAttribute('value');
      if (firstOption) {
        await modelInput.selectOption(firstOption);
      }
    } else {
      // Text input fallback (no catalog loaded)
      await modelInput.fill('gpt-4o-mini-test');
      await modelInput.blur();
    }

    const response = await autosavePromise;
    expect(response.status()).toBe(200);
  });

  // -------------------------------------------------------------------------
  // Consistency: sub-agent inputs use the same element shape as main agents
  // -------------------------------------------------------------------------

  test('sub-agent commercial inputs are select elements when catalog is loaded', async ({ page }) => {
    await page.evaluate(() => {
      document.getElementById('s3')?.classList.add('open');
    });
    await page.waitForTimeout(500);

    await page.evaluate(() => {
      if (typeof (window as any).toggleSA === 'function') {
        (window as any).toggleSA('sa-cmdline');
      } else {
        document.getElementById('sa-cmdline')?.classList.add('open');
      }
    });
    await page.waitForTimeout(800);

    const providerSelect = page.locator('#cmdlineextract-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    // Check if the catalog has loaded (main rankagent uses same catalog)
    const mainAgentHasSelect = await page.evaluate(() => {
      const el = document.getElementById('rankagent-model-openai');
      return el ? el.tagName.toLowerCase() === 'select' : null;
    });

    if (mainAgentHasSelect === null || !mainAgentHasSelect) {
      test.skip(true, 'Commercial model catalog not loaded in this environment');
      return;
    }

    await providerSelect.selectOption('openai');
    await page.waitForTimeout(2000);

    const modelInput = page.locator('#cmdlineextract-model-openai');
    await modelInput.waitFor({ state: 'attached', timeout: 8000 });

    // When catalog is loaded, both main agents and sub-agents should render <select>
    const tagName = await modelInput.evaluate((el: HTMLElement) => el.tagName.toLowerCase());
    expect(tagName).toBe('select');
  });
});
