import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Agent Config Commercial Models', () => {
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

    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');
  });

  test('should load commercial model catalog for OpenAI', async ({ page }) => {
    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    await providerSelect.selectOption('openai');
    await page.waitForTimeout(2000); // Wait for model selector to load

    // Check for model selector (could be input or select)
    const modelSelector = page.locator('#rankagent-model-openai');
    await modelSelector.waitFor({ state: 'visible', timeout: 5000 });

    // Verify it exists and is either input or select
    const tagName = await modelSelector.evaluate((el: HTMLElement) => el.tagName.toLowerCase());
    expect(['input', 'select']).toContain(tagName);
  });

  test('should load commercial model catalog for Anthropic', async ({ page }) => {
    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    // First switch to a different provider to ensure clean state
    await providerSelect.selectOption('lmstudio');
    await page.waitForTimeout(1000);
    
    await providerSelect.selectOption('anthropic');
    await page.waitForTimeout(2000); // Wait for model selector to load

    // Check for model selector
    const modelSelector = page.locator('#rankagent-model-anthropic');
    await modelSelector.waitFor({ state: 'visible', timeout: 5000 });

    // Verify it exists and is either input or select
    const tagName = await modelSelector.evaluate((el: HTMLElement) => el.tagName.toLowerCase());
    expect(['input', 'select']).toContain(tagName);
  });

  test('should allow custom model input for commercial providers', async ({ page }) => {
    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    await providerSelect.selectOption('openai');
    await page.waitForTimeout(2000);

    const modelSelector = page.locator('#rankagent-model-openai');
    await modelSelector.waitFor({ state: 'visible', timeout: 5000 });

    const tagName = await modelSelector.evaluate((el: HTMLElement) => el.tagName.toLowerCase());
    
    if (tagName === 'input') {
      const customModel = 'gpt-4-turbo-custom';
      await modelSelector.fill(customModel);
      await modelSelector.blur();

      // Wait for autosave
      await page.waitForResponse(
        (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
        { timeout: 5000 }
      );

      // Verify value was saved
      const savedValue = await modelSelector.inputValue();
      expect(savedValue).toBe(customModel);
    } else if (tagName === 'select') {
      // If it's a select, verify it has options
      const options = await modelSelector.locator('option').count();
      expect(options).toBeGreaterThan(0);
    }
  });

  test('should show model suggestions for commercial providers', async ({ page }) => {
    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    await providerSelect.selectOption('openai');
    await page.waitForTimeout(2000);

    const modelSelector = page.locator('#rankagent-model-openai');
    await modelSelector.waitFor({ state: 'visible', timeout: 5000 });

    const tagName = await modelSelector.evaluate((el: HTMLElement) => el.tagName.toLowerCase());
    
    if (tagName === 'input') {
      // Check if input has placeholder or datalist (suggestions)
      const hasPlaceholder = await modelSelector.getAttribute('placeholder');
      const hasDatalist = await page.locator('datalist').count();

      // At least one of these should indicate suggestions, or it's a select with options
      expect(hasPlaceholder || hasDatalist > 0).toBe(true);
    } else if (tagName === 'select') {
      // Select dropdowns inherently show suggestions via options
      const options = await modelSelector.locator('option').count();
      expect(options).toBeGreaterThan(0);
    }
  });
});

async function expandPanelIfNeeded(page: any, panelId: string) {
  const content = page.locator(`#${panelId}-content`);
  const toggle = page.locator(`#${panelId}-toggle, button[onclick*="${panelId}"]`).first();

  if (await toggle.isVisible({ timeout: 2000 }).catch(() => false)) {
    const isHidden = await content.evaluate((el: HTMLElement) => el.classList.contains('hidden')).catch(() => true);
    if (isHidden) {
      await toggle.click();
      await page.waitForTimeout(300);
    }
  }
}
