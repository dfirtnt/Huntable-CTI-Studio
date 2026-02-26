import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

async function switchToConfigTab(page: any) {
  await page.evaluate(() => {
    if (typeof (window as any).switchTab === 'function') {
      (window as any).switchTab('config');
    }
  });
  await page.waitForTimeout(1000);
}

async function waitForConfigReady(page: any) {
  await page.waitForSelector('#workflowConfigForm', { timeout: 15000 });
  await page.waitForFunction(() => typeof (window as any).currentConfig !== 'undefined', { timeout: 15000 });
  await page.waitForTimeout(1000);
}

async function expandPanel(page: any, panelId: string) {
  await page.evaluate((id: string) => {
    const content = document.getElementById(`${id}-content`);
    if (!content) return;
    if (content.classList.contains('hidden') && typeof (window as any).toggleCollapsible === 'function') {
      (window as any).toggleCollapsible(id);
    }
  }, panelId);
  await page.waitForTimeout(150);
}

test.describe('Workflow Config Binding Audit', () => {
  test('visible mutable controls have labels and bindings; prompt panels render consistently', async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await switchToConfigTab(page);
    await waitForConfigReady(page);

    const panels = [
      'other-thresholds-panel',
      'qa-settings-panel',
      'os-detection-panel',
      'rank-agent-configs-panel',
      'extract-agent-panel',
      'cmdlineextract-agent-panel',
      'proctreeextract-agent-panel',
      'huntqueriesextract-agent-panel',
      'sigma-agent-panel'
    ];
    for (const panel of panels) {
      await expandPanel(page, panel);
    }

    // Enable conditional sections so their controls are present in the DOM for the audit.
    await page.evaluate(() => {
      const toggleIds = [
        'qa-rankagent',
        'qa-cmdlineextract',
        'qa-proctreeextract',
        'qa-huntqueriesextract',
        'osdetectionagent-fallback-enabled'
      ];
      for (const id of toggleIds) {
        const el = document.getElementById(id) as HTMLInputElement | null;
        if (el && !el.checked) {
          el.checked = true;
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }
      }
      if (typeof (window as any).normalizeWorkflowConfigControlBindings === 'function') {
        (window as any).normalizeWorkflowConfigControlBindings();
      }
    });
    await page.waitForTimeout(500);

    const audit = await page.evaluate(() => {
      const fn = (window as any).getWorkflowConfigBindingAudit;
      return typeof fn === 'function' ? fn() : { error: 'audit helper missing' };
    });

    expect(audit.error ?? null).toBeNull();
    expect(audit.counts.missingLabels).toBe(0);
    expect(audit.counts.missingBindings).toBe(0);

    const rankProvider = audit.controls.find((c: any) => c.id === 'rankagent-provider');
    expect(rankProvider?.name).toBe('agent_models[RankAgent_provider]');
    expect(rankProvider?.persistKey).toBe('RankAgent_provider');
    expect(rankProvider?.ariaLabel).toContain('Rank Agent');

    const osFallbackProvider = audit.controls.find((c: any) => c.id === 'osdetectionagent-fallback-provider');
    expect(osFallbackProvider?.name).toBe('agent_models[OSDetectionAgent_fallback_provider]');
    expect(osFallbackProvider?.persistKey).toBe('OSDetectionAgent_fallback_provider');

    const cmdlineToggle = audit.controls.find((c: any) => c.id === 'toggle-cmdlineextract-enabled');
    expect(cmdlineToggle?.persistKey).toBe('agent_prompts.ExtractAgentSettings.disabled_agents');
    expect(cmdlineToggle?.bindingKind).toBe('inverse-disabled-list');

    const promptHeaders = audit.promptPanelHeaders as string[];
    expect(promptHeaders.some(h => h.includes('OSDetectionAgent Prompt'))).toBe(true);
    expect(promptHeaders.some(h => h.includes('RankAgent Prompt'))).toBe(true);
    expect(promptHeaders.some(h => h.includes('SigmaAgent Prompt'))).toBe(true);

    const commercialParity = await page.evaluate(() => {
      const readOptions = (id: string) => {
        const el = document.getElementById(id) as HTMLSelectElement | null;
        if (!el || el.tagName !== 'SELECT') return null;
        return Array.from(el.options).map(o => o.value);
      };
      return {
        procTreeExtractOpenAI: readOptions('proctreeextract-model-openai'),
        huntQueriesExtractOpenAI: readOptions('huntqueriesextract-model-openai'),
        procTreeQAOpenAI: readOptions('proctreeqa-model-openai'),
        huntQueriesQAOpenAI: readOptions('huntqueriesqa-model-openai'),
        procTreeExtractAnthropic: readOptions('proctreeextract-model-anthropic'),
        huntQueriesExtractAnthropic: readOptions('huntqueriesextract-model-anthropic'),
        procTreeQAAnthropic: readOptions('proctreeqa-model-anthropic'),
        huntQueriesQAAnthropic: readOptions('huntqueriesqa-model-anthropic')
      };
    });

    expect(commercialParity.procTreeExtractOpenAI).toEqual(commercialParity.huntQueriesExtractOpenAI);
    expect(commercialParity.procTreeQAOpenAI).toEqual(commercialParity.huntQueriesQAOpenAI);
    expect(commercialParity.procTreeExtractAnthropic).toEqual(commercialParity.huntQueriesExtractAnthropic);
    expect(commercialParity.procTreeQAAnthropic).toEqual(commercialParity.huntQueriesQAAnthropic);
  });
});
