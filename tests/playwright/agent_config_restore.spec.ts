import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

// Map legacy panel IDs to step-section IDs and their model containers.
const PANEL_INFO: Record<string, { step: string; container: string; label: string }> = {
  'rank-agent-configs-panel': { step: 's2', container: '#rank-agent-model-container', label: 'Rank Agent' },
  'extract-agent-panel': { step: 's3', container: '#extract-agent-model-container', label: 'Extract Agent' },
  'os-detection-panel': { step: 's0', container: '#os-detection-model-container', label: 'OS Detection' },
  'sigma-agent-panel': { step: 's4', container: '#sigma-agent-model-container', label: 'SIGMA Generator Agent' },
};

test.describe('Agent Config Restore After Collapse', () => {
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
  });

  test('should render Rank Agent config content after restore when panel was collapsed', async ({ page }) => {
    const info = PANEL_INFO['rank-agent-configs-panel'];
    const section = page.locator(`#${info.step}`);
    const container = page.locator(info.container);

    // Open step section
    await page.evaluate((id) => document.getElementById(id)?.classList.add('open'), info.step);
    await page.waitForTimeout(300);

    // Manually trigger loadAgentModels to populate containers
    await page.evaluate(async () => {
      if (typeof loadAgentModels === 'function') {
        await loadAgentModels();
      }
    });
    await page.waitForTimeout(2000);

    const containerExists = await container.count() > 0;
    expect(containerExists).toBe(true);

    // Close the step section
    await page.evaluate((id) => document.getElementById(id)?.classList.remove('open'), info.step);
    await page.waitForTimeout(300);
    await expect(section).not.toHaveClass(/open/);

    // Verify container still exists in DOM even when hidden
    const containerWhenHidden = await container.evaluate(el => el !== null);
    expect(containerWhenHidden).toBe(true);

    // Trigger a config reload (simulating what happens after save)
    await page.evaluate(async () => {
      if (typeof loadAgentModels === 'function') {
        await loadAgentModels();
      }
    });
    await page.waitForTimeout(2000);

    // Re-open the step section
    await page.evaluate((id) => document.getElementById(id)?.classList.add('open'), info.step);
    await page.waitForTimeout(500);

    // Verify content is accessible after expanding
    await expect(section).toHaveClass(/open/);

    await page.waitForTimeout(500);
    const containerAfterRestore = page.locator(info.container);
    const containerContent = await containerAfterRestore.evaluate(el => el.innerHTML);
    expect(containerContent.length).toBeGreaterThan(0);
    const containerAfterRestoreExists = await containerAfterRestore.count() > 0;
    expect(containerAfterRestoreExists).toBe(true);
  });

  test.skip('should render Extract Agent config content after restore when panel was collapsed', async ({ page }) => {
    const info = PANEL_INFO['extract-agent-panel'];
    await page.evaluate((id) => document.getElementById(id)?.classList.add('open'), info.step);
    await page.waitForSelector(info.container, { state: 'attached', timeout: 10000 });
    await page.waitForTimeout(3000);

    const container = page.locator(info.container);
    const containerContent = await container.evaluate(el => el.innerHTML);
    expect(containerContent.length).toBeGreaterThan(0);
    expect(containerContent).toContain('Extract Agent Model');

    await page.evaluate((id) => document.getElementById(id)?.classList.remove('open'), info.step);
    await page.waitForTimeout(300);

    await page.evaluate(async () => {
      if (typeof loadAgentModels === 'function') await loadAgentModels();
    });
    await page.waitForTimeout(2000);

    await page.evaluate((id) => document.getElementById(id)?.classList.add('open'), info.step);
    await page.waitForTimeout(500);

    const containerAfterRestore = page.locator(info.container);
    const contentAfterRestore = await containerAfterRestore.evaluate(el => el.innerHTML);
    expect(contentAfterRestore.length).toBeGreaterThan(0);
    expect(contentAfterRestore).toContain('Extract Agent Model');
  });

  test.skip('should render OS Detection Agent config content after restore when panel was collapsed', async ({ page }) => {
    const info = PANEL_INFO['os-detection-panel'];
    await page.evaluate((id) => document.getElementById(id)?.classList.add('open'), info.step);
    await page.waitForSelector(info.container, { state: 'attached', timeout: 10000 });
    await page.waitForTimeout(3000);

    const container = page.locator(info.container);
    const containerContent = await container.evaluate(el => el.innerHTML);
    expect(containerContent.length).toBeGreaterThan(0);
    expect(containerContent).toContain('OS Detection Agent Model');

    await page.evaluate((id) => document.getElementById(id)?.classList.remove('open'), info.step);
    await page.waitForTimeout(300);

    await page.evaluate(async () => {
      if (typeof loadAgentModels === 'function') await loadAgentModels();
    });
    await page.waitForTimeout(2000);

    await page.evaluate((id) => document.getElementById(id)?.classList.add('open'), info.step);
    await page.waitForTimeout(500);

    const containerAfterRestore = page.locator(info.container);
    const contentAfterRestore = await containerAfterRestore.evaluate(el => el.innerHTML);
    expect(contentAfterRestore.length).toBeGreaterThan(0);
    expect(contentAfterRestore).toContain('OS Detection Agent Model');
  });

  test('should render Sigma Agent config content after restore when panel was collapsed', async ({ page }) => {
    const info = PANEL_INFO['sigma-agent-panel'];
    await page.evaluate((id) => document.getElementById(id)?.classList.add('open'), info.step);
    await page.waitForSelector(info.container, { state: 'attached', timeout: 5000 });
    await page.waitForTimeout(2000);

    const container = page.locator(info.container);
    const containerContent = await container.evaluate(el => el.innerHTML);
    expect(containerContent.length).toBeGreaterThan(0);
    expect(containerContent).toContain('SIGMA Generator Agent Model');

    await page.evaluate((id) => document.getElementById(id)?.classList.remove('open'), info.step);
    await page.waitForTimeout(300);

    await page.evaluate(async () => {
      if (typeof loadAgentModels === 'function') await loadAgentModels();
    });
    await page.waitForTimeout(2000);

    await page.evaluate((id) => document.getElementById(id)?.classList.add('open'), info.step);
    await page.waitForTimeout(500);

    const section = page.locator(`#${info.step}`);
    await expect(section).toHaveClass(/open/);
    const containerAfterRestore = page.locator(info.container);
    const contentAfterRestore = await containerAfterRestore.evaluate(el => el.innerHTML);
    expect(contentAfterRestore.length).toBeGreaterThan(0);
    expect(contentAfterRestore).toContain('SIGMA Generator Agent Model');
  });
});
