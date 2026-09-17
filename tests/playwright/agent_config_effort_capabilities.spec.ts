import { expect, test, type Page } from '@playwright/test';

/**
 * Catalog-driven model parameter compatibility + Effort control on the Agents config page.
 *
 * Capabilities come from GET /api/workflow/provider-options (config/model_capabilities.json
 * for OpenAI/Anthropic, live model/list for Codex). The page must:
 *   - disable, not hide, Temperature / Top_P when the model rejects them, with a visible note;
 *   - re-enable them for sampling models (gpt-4.1, LM Studio);
 *   - render an Effort select listing exactly the model's tiers after "Provider default",
 *     and hide it when the model has no effort control;
 *   - persist a chosen tier through autosave and a hard reload.
 *
 * The page's own DOM helpers are driven directly (setAgentProvider / setAgentModel /
 * updateTemperatureCapabilityUI) so the spec does not depend on which providers the
 * operator has enabled; the live-save test skips when no cloud provider is enabled.
 */

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

async function openConfig(page: Page) {
  await page.goto(`${BASE}/workflow#config`);
  await page.waitForSelector('#workflowConfigForm', { timeout: 15000 });
  await page.waitForFunction(() => (window as any).isInitializing === false, { timeout: 20000 });
  // The capability cache is filled by GET /api/workflow/provider-options, which can land
  // after isInitializing clears. Probe the resolver itself: a catalogued model reporting
  // source "catalog" proves the cache is populated, so the gating assertions below are
  // not racing the fetch.
  await page.waitForFunction(
    () => {
      const w = window as any;
      return (
        typeof w.updateTemperatureCapabilityUI === 'function' &&
        typeof w.resolveModelCapabilities === 'function' &&
        !!document.getElementById('sigmaagent-effort') &&
        w.resolveModelCapabilities('openai', 'gpt-5.6-luna').source === 'catalog'
      );
    },
    { timeout: 25000 }
  );
}

async function gate(page: Page, prefix: string, provider: string, model: string) {
  return page.evaluate(
    ([p, prov, m]) => {
      const w = window as any;
      w.isApplyingStoredConfig = true; // suppress autosave while the spec rearranges controls
      try {
        w.setAgentProvider(p, prov);
        w.setAgentModel(p, m, prov);
        w.updateTemperatureCapabilityUI(p);
      } finally {
        w.isApplyingStoredConfig = false;
      }
      const temp = document.getElementById(`${p}-temperature`) as HTMLInputElement | null;
      const topP = document.getElementById(`${p}-top-p`) as HTMLInputElement | null;
      const note = document.getElementById(`${p}-temperature-reasoning-hint`);
      const effort = document.getElementById(`${p}-effort`) as HTMLSelectElement | null;
      const container = document.getElementById(`${p}-effort-container`);
      return {
        tempDisabled: temp?.disabled ?? null,
        topPDisabled: topP?.disabled ?? null,
        tempVisible: !!temp && temp.offsetParent !== null,
        noteVisible: !!note && !note.classList.contains('hidden'),
        noteText: note?.textContent?.trim() ?? '',
        effortHidden: container ? container.classList.contains('hidden') : null,
        effortOptions: effort ? Array.from(effort.options).map(o => o.value) : null,
        effortSource: effort?.getAttribute('data-capability-source') ?? null,
      };
    },
    [prefix, provider, model] as const
  );
}

test.describe('Agent config: capability-gated sampling controls and Effort select', () => {
  test('[AGENT-CONFIG-EFFORT-001] OpenAI reasoning model disables Temperature/Top_P with a note and lists its tiers', async ({ page }) => {
    await openConfig(page);
    const state = await gate(page, 'sigmaagent', 'openai', 'gpt-5.6-luna');
    expect(state.tempDisabled).toBe(true);
    expect(state.topPDisabled).toBe(true);
    expect(state.noteVisible).toBe(true);
    expect(state.noteText).toBe('Not supported by this model');
    expect(state.effortHidden).toBe(false);
    // "Provider default" first, then exactly the catalog tiers (verified 2026-09-04).
    expect(state.effortOptions).toEqual(['', 'none', 'low', 'medium', 'high', 'xhigh', 'max']);
    expect(state.effortSource).toBe('catalog');
  });

  test('[AGENT-CONFIG-EFFORT-002] gpt-4.1 re-enables the sliders and shows no Effort control', async ({ page }) => {
    await openConfig(page);
    await gate(page, 'sigmaagent', 'openai', 'gpt-5.6-luna');
    const state = await gate(page, 'sigmaagent', 'openai', 'gpt-4.1');
    expect(state.tempDisabled).toBe(false);
    expect(state.topPDisabled).toBe(false);
    expect(state.noteVisible).toBe(false);
    expect(state.effortHidden).toBe(true);
    expect(state.effortOptions).toEqual(['']);
  });

  test('[AGENT-CONFIG-EFFORT-003] Anthropic Opus 4.7 lists xhigh and rejects sampling; Sonnet 4.6 keeps sampling and omits xhigh', async ({ page }) => {
    await openConfig(page);
    const opus = await gate(page, 'cmdlineextract', 'anthropic', 'claude-opus-4-7');
    expect(opus.tempDisabled).toBe(true);
    expect(opus.effortOptions).toEqual(['', 'low', 'medium', 'high', 'xhigh', 'max']);

    const sonnet = await gate(page, 'cmdlineextract', 'anthropic', 'claude-sonnet-4-6');
    expect(sonnet.tempDisabled).toBe(false);
    expect(sonnet.noteVisible).toBe(false);
    expect(sonnet.effortOptions).toEqual(['', 'low', 'medium', 'high', 'max']);
  });

  test('[AGENT-CONFIG-EFFORT-004] Codex tiers come from the live model list and sampling is always disabled', async ({ page }) => {
    await openConfig(page);
    const codexModels: string[] = await page.evaluate(async () => {
      const r = await fetch('/api/workflow/provider-options');
      const d = await r.json();
      const c = d.providers?.codex;
      return c && c.enabled && Array.isArray(c.models) ? c.models : [];
    });
    test.skip(codexModels.length === 0, 'Codex subscription is not enabled/connected on this deployment');
    const state = await gate(page, 'rankagent', 'codex', codexModels[0]);
    expect(state.tempDisabled).toBe(true);
    expect(state.topPDisabled).toBe(true);
    expect(state.noteVisible).toBe(true);
    expect(state.effortSource).toBe('live');
    expect(state.effortHidden).toBe(false);
    expect((state.effortOptions ?? []).length).toBeGreaterThan(1);
  });

  test('[AGENT-CONFIG-EFFORT-005] LM Studio keeps the sliders enabled with no Effort control', async ({ page }) => {
    await openConfig(page);
    const state = await gate(page, 'proctreeextract', 'lmstudio', 'qwen/qwen3-4b');
    expect(state.tempDisabled).toBe(false);
    expect(state.topPDisabled).toBe(false);
    expect(state.noteVisible).toBe(false);
    expect(state.effortHidden).toBe(true);
  });

  test('[AGENT-CONFIG-EFFORT-006] a chosen tier autosaves, survives a hard reload, and clears back to provider default', async ({ page }) => {
    await openConfig(page);
    const stored = await page.evaluate(async () => {
      const cfg = await (await fetch('/api/workflow/config')).json();
      const provider = (cfg.agent_models?.SigmaAgent_provider || '').toLowerCase();
      const model = cfg.agent_models?.SigmaAgent || '';
      const opts = await (await fetch('/api/workflow/provider-options')).json();
      const caps = opts.providers?.[provider]?.model_capabilities?.[model];
      return { provider, model, levels: caps?.effort_levels ?? [], effort: cfg.agent_models?.SigmaAgent_effort ?? '' };
    });
    test.skip(stored.levels.length === 0, `SigmaAgent model ${stored.provider}/${stored.model} has no effort tiers on this deployment`);
    const target = stored.levels.find((l: string) => l !== stored.effort) as string;

    // The SIGMA panel may be collapsed, so drive the select through the DOM the same way
    // the slider specs drive range inputs, rather than requiring visibility.
    const select = page.locator('#sigmaagent-effort');
    await expect(select).toHaveCount(1);
    const saved = page.waitForResponse(r => r.url().includes('/api/workflow/config') && r.request().method() === 'PUT', { timeout: 15000 });
    await select.evaluate((el, v) => {
      (el as HTMLSelectElement).value = v as string;
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }, target);
    expect((await saved).status()).toBe(200);
    await page.waitForFunction(
      async (t) => (await (await fetch('/api/workflow/config')).json()).agent_models?.SigmaAgent_effort === t,
      target,
      { timeout: 15000 }
    );

    await page.reload();
    await openConfig(page);
    await expect(page.locator('#sigmaagent-effort')).toHaveValue(target);

    // Restore: the blank option must clear the override (the key disappears), not store "".
    const cleared = page.waitForResponse(r => r.url().includes('/api/workflow/config') && r.request().method() === 'PUT', { timeout: 15000 });
    await page.locator('#sigmaagent-effort').evaluate((el, v) => {
      (el as HTMLSelectElement).value = v as string;
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }, stored.effort || '');
    expect((await cleared).status()).toBe(200);
    await page.waitForFunction(
      async (prev) => {
        const am = (await (await fetch('/api/workflow/config')).json()).agent_models || {};
        return prev ? am.SigmaAgent_effort === prev : !('SigmaAgent_effort' in am);
      },
      stored.effort,
      { timeout: 15000 }
    );
  });
});
