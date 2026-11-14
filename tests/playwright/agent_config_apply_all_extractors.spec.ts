/**
 * "Apply model to all extractors" button on the agents config page.
 *
 * The button copies the Extract Agent provider + model onto every extractor
 * sub-agent. autosave is stubbed so the live workflow config is never written.
 */

import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';
const MARKER_MODEL = 'bulk-apply-test-model';
const SUB_AGENTS = [
  'CmdlineExtract', 'ProcTreeExtract', 'HuntQueriesExtract', 'RegistryExtract',
  'ServicesExtract', 'ScheduledTasksExtract', 'NetworkIndicatorExtract',
];

test.describe('Apply model to all extractors', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await page.evaluate(() => {
      if (typeof (window as any).switchTab === 'function') (window as any).switchTab('config');
    });
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    await page.waitForFunction(() => (window as any).isInitializing === false, { timeout: 10000 });
    // Never persist test changes to the live config.
    await page.evaluate(() => {
      (window as any).autoSaveModelChange = () => Promise.resolve();
    });
  });

  test('copies Extract Agent provider and model onto all extractor sub-agents', async ({ page }) => {
    const result = await page.evaluate(({ marker, SUB_AGENTS }) => {
      const w = window as any;
      const provider = w.getAgentProvider('extractagent');
      w.setAgentModel('extractagent', marker, provider);
      document.getElementById('apply-extract-model-to-all-btn')!.click();
      return {
        provider,
        agents: SUB_AGENTS.map((a: string) => {
          const p = a.toLowerCase();
          return { name: a, provider: w.getAgentProvider(p), model: w.getAgentModel(p) };
        }),
        status: document.getElementById('apply-extract-model-to-all-status')!.textContent,
      };
    }, { marker: MARKER_MODEL, SUB_AGENTS });

    expect(result.agents.length).toBe(7);
    for (const a of result.agents) {
      expect(a.provider, `${a.name} provider`).toBe(result.provider);
      expect(a.model, `${a.name} model`).toBe(MARKER_MODEL);
    }
    expect(result.status).toContain('7 of 7');
  });

  test('does nothing when the Extract Agent model is empty', async ({ page }) => {
    const result = await page.evaluate((SUB_AGENTS) => {
      const w = window as any;
      const provider = w.getAgentProvider('extractagent');
      w.setAgentModel('extractagent', '', provider);
      const before = SUB_AGENTS.map((a: string) => w.getAgentModel(a.toLowerCase()));
      document.getElementById('apply-extract-model-to-all-btn')!.click();
      const after = SUB_AGENTS.map((a: string) => w.getAgentModel(a.toLowerCase()));
      return {
        before,
        after,
        status: document.getElementById('apply-extract-model-to-all-status')!.textContent,
      };
    }, SUB_AGENTS);

    expect(result.after).toEqual(result.before);
    expect(result.status).toContain('Choose an Extract Agent model');
  });
});
