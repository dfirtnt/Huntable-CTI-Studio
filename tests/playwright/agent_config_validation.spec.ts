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
    await page.waitForTimeout(2000);

    await expandPanelIfNeeded(page, 'other-thresholds-panel');
    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');
    await expandPanelIfNeeded(page, 'qa-settings-panel');
  });

  test('should validate QA max retries range (1-3)', async ({ page }) => {
    const input = page.locator('#qaMaxRetries');
    const errorElement = page.locator('#qaMaxRetries-error');

    await input.waitFor({ state: 'visible', timeout: 10000 });

    // Test invalid value below range
    await input.fill('0');
    await input.blur();
    await page.waitForTimeout(500);

    const errorText = await errorElement.textContent();
    expect(errorText).toBeTruthy();
    expect(await errorElement.isVisible()).toBe(true);

    // Test invalid value above range
    await input.fill('4');
    await input.blur();
    await page.waitForTimeout(500);

    const errorText2 = await errorElement.textContent();
    expect(errorText2).toBeTruthy();

    // Test valid value
    await input.fill('2');
    await input.blur();
    await page.waitForTimeout(500);

    const isHidden = await errorElement.evaluate((el: HTMLElement) => el.classList.contains('hidden'));
    expect(isHidden).toBe(true);
  });

  test('should clear error messages when valid value is entered', async ({ page }) => {
    const input = page.locator('#qaMaxRetries');
    const errorElement = page.locator('#qaMaxRetries-error');

    await input.waitFor({ state: 'visible', timeout: 10000 });

    // Enter invalid value
    await input.fill('5');
    await input.blur();
    await page.waitForTimeout(500);

    // Error should be visible
    let isHidden = await errorElement.evaluate((el: HTMLElement) => el.classList.contains('hidden'));
    expect(isHidden).toBe(false);

    // Enter valid value
    await input.fill('2');
    await input.blur();
    await page.waitForTimeout(500);

    // Error should be hidden
    isHidden = await errorElement.evaluate((el: HTMLElement) => el.classList.contains('hidden'));
    expect(isHidden).toBe(true);
  });
});

const PANEL_STEP_MAP: Record<string, string[]> = {
  'os-detection-panel': ['s0'], 'other-thresholds-panel': ['s1', 's5'],
  'rank-agent-configs-panel': ['s2'], 'qa-settings-panel': ['s2'],
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
