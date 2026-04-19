import { test, expect, Page } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

async function switchToConfigTab(page: Page) {
  await page.evaluate(() => {
    if (typeof switchTab === 'function') {
      switchTab('config');
    }
  });
  await page.waitForTimeout(1000);
}

async function waitForConfigReady(page: Page) {
  await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
  await page.waitForFunction(() => {
    return typeof currentConfig !== 'undefined' && currentConfig !== null;
  }, { timeout: 10000 });
  await page.waitForTimeout(1000);
}

async function gotoWorkflowConfig(page: Page) {
  await page.goto(`${BASE}/workflow#config`);
  await page.waitForLoadState('networkidle');
  await switchToConfigTab(page);
  await waitForConfigReady(page);
}

const PANEL_STEP_MAP: Record<string, string[]> = {
  'os-detection-panel': ['s0'], 'other-thresholds-panel': ['s1', 's5'],
  'rank-agent-configs-panel': ['s2'], 'qa-settings-panel': ['s2'],
  'extract-agent-panel': ['s3'], 'cmdlineextract-agent-panel': ['s3'],
  'proctreeextract-agent-panel': ['s3'], 'huntqueriesextract-agent-panel': ['s3'],
  'registryextract-agent-panel': ['s3'], 'sigma-agent-panel': ['s4'],
};
async function expandPanel(page: Page, panelId: string) {
  const stepIds = PANEL_STEP_MAP[panelId];
  if (stepIds) {
    await page.evaluate((ids: string[]) => { ids.forEach(id => document.getElementById(id)?.classList.add('open')); }, stepIds);
    await page.waitForTimeout(300);
    return;
  }
  const content = page.locator(`#${panelId}-content`);
  const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
  if (await content.count() === 0 || await header.count() === 0) return;
  const isHidden = await content.evaluate(el => el.classList.contains('hidden')).catch(() => true);
  if (isHidden) { await header.click(); await page.waitForTimeout(300); }
}

async function expandAgentPanels(page: Page) {
  await expandPanel(page, 'qa-settings-panel');
  await expandPanel(page, 'os-detection-panel');
  await expandPanel(page, 'rank-agent-configs-panel');
  await expandPanel(page, 'extract-agent-panel');
  await expandPanel(page, 'cmdlineextract-agent-panel');
  await expandPanel(page, 'proctreeextract-agent-panel');
  await expandPanel(page, 'huntqueriesextract-agent-panel');
  await expandPanel(page, 'sigma-agent-panel');
}

async function ensureQATogglesEnabled(page: Page) {
  await page.evaluate(() => {
    const ids = ['qa-rankagent', 'qa-cmdlineextract', 'qa-proctreeextract', 'qa-huntqueriesextract'];
    ids.forEach(id => {
      const el = document.getElementById(id) as HTMLInputElement | null;
      if (el && !el.checked) {
        el.checked = true;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
  });
  await page.waitForTimeout(500);
}

test.describe('Agent Config Full Coverage (10+ agents)', () => {
  test.beforeEach(async ({ page }) => {
    await gotoWorkflowConfig(page);
    await expandAgentPanels(page);
    await ensureQATogglesEnabled(page);
  });

  test('Enable/disable toggles are visible (10 agents)', async ({ page }) => {
    const toggles = [
      '#rank-agent-enabled',
      '#toggle-cmdlineextract-enabled',
      '#toggle-proctreeextract-enabled',
      '#toggle-huntqueriesextract-enabled',
      '#qa-rankagent',
      '#qa-cmdlineextract',
      '#qa-proctreeextract',
      '#qa-huntqueriesextract',
      '#sigma-fallback-enabled',
      '#osdetectionagent-fallback-enabled'
    ];

    for (const selector of toggles) {
      const toggle = page.locator(selector);
      // Checkboxes are sr-only (visually hidden) — verify they exist in DOM
      await expect(toggle).toBeAttached();
    }
  });

});
