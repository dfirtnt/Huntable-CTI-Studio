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
