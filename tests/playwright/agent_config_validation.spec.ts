import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Agent Config Validation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(1000);

    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    // Wait for initialization flag to clear (set false after loadConfig completes)
    await page.waitForFunction(() => (window as any).isInitializing === false, { timeout: 10000 });

    await expandPanelIfNeeded(page, 'other-thresholds-panel');
    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');
  });
});

// Regression guard: validateProviderModelCombination() previously fired its
// async /api/validate-model POST as a side effect from every bulk/load-time
// pass over all ~30 agents (applyProviderSelections, syncProviderVisibilityAndInputs,
// refreshAllProviderBlocks, autosave's pre-save validation loops), not just from
// a real user-driven change. A fix added an opt-in `skipAsync` option to those
// bulk call sites; this test pins the observable behavior (request counts) so a
// future edit that drops the option is caught here rather than as log noise.
test.describe('Agent Config Validation - validate-model request volume', () => {
  test('loading the config page issues zero /api/validate-model requests', async ({ page }) => {
    const validateModelRequests: string[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/validate-model')) {
        validateModelRequests.push(req.url());
      }
    });

    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    await page.waitForFunction(() => (window as any).isInitializing === false, { timeout: 10000 });
    // Bulk sync/refresh passes run synchronously off the same load event; give
    // any stray async validation call a moment to have fired if it were going to.
    await page.waitForTimeout(1000);

    expect(validateModelRequests).toHaveLength(0);
  });

  test('an explicit single-agent validation call still triggers exactly one request', async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    await page.waitForFunction(() => (window as any).isInitializing === false, { timeout: 10000 });

    const validateModelRequests: string[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/api/validate-model')) {
        validateModelRequests.push(req.url());
      }
    });

    // Mirrors the real call path a genuine provider/model change takes
    // (onAgentProviderChange / validateAgentModelOnChange), which pass no
    // skipAsync option and so must keep firing the async check.
    await page.evaluate(() => {
      (window as any).validateProviderModelCombination('rankagent', 'openai', 'gpt-4o');
    });
    await page.waitForTimeout(1000);

    expect(validateModelRequests).toHaveLength(1);
  });
});

const PANEL_STEP_MAP: Record<string, string[]> = {
  'os-detection-panel': ['s0'], 'other-thresholds-panel': ['s1', 's5'],
  'rank-agent-configs-panel': ['s2'],
  'extract-agent-panel': ['s3'], 'cmdlineextract-agent-panel': ['s3'],
  'proctreeextract-agent-panel': ['s3'], 'huntqueriesextract-agent-panel': ['s3'],
  'registryextract-agent-panel': ['s3'], 'sigma-agent-panel': ['s4'],
};
async function expandPanelIfNeeded(page: any, panelId: string) {
  const stepIds = PANEL_STEP_MAP[panelId];
  if (stepIds) {
    await page.evaluate((ids: string[]) => { ids.forEach(id => document.getElementById(id)?.classList.add('open')); }, stepIds);
    await page.waitForTimeout(300);
    return;
  }
  const content = page.locator(`#${panelId}-content`);
  const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
  if (await header.isVisible({ timeout: 2000 }).catch(() => false)) {
    const isHidden = await content.evaluate((el: HTMLElement) => el.classList.contains('hidden')).catch(() => true);
    if (isHidden) { await header.click(); await page.waitForTimeout(300); }
  }
}
