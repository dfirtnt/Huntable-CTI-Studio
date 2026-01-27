import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Agent Config Provider Switching', () => {
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

    // Expand Rank Agent panel
    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');
    
    // Wait for model container to load
    await page.waitForTimeout(2000);
  });

  test('should autosave when switching from LMStudio to OpenAI', async ({ page }) => {
    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    // Get initial provider
    const initialProvider = await providerSelect.inputValue();

    // Switch to OpenAI
    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 5000 }
    );

    await providerSelect.selectOption('openai');
    await page.waitForTimeout(500);

    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    expect(responseData.agent_models?.RankAgent_provider).toBe('openai');
  });

  test('should autosave when switching from OpenAI to Anthropic', async ({ page }) => {
    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    // Skip if anthropic is not available (e.g. no API key in settings)
    const hasAnthropic = await providerSelect.locator('option[value="anthropic"]').count() > 0;
    if (!hasAnthropic) {
      test.skip(true, 'Anthropic provider not available (requires API key in Settings)');
      return;
    }

    // Switch to OpenAI first and wait for any autosave
    await providerSelect.selectOption('openai');
    await page.waitForTimeout(2000); // Wait for UI to update

    // Then switch to Anthropic
    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 15000 }
    );

    await providerSelect.selectOption('anthropic');
    await page.waitForTimeout(2000);

    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    expect(responseData.agent_models?.RankAgent_provider).toBe('anthropic');
  });

  test('should repopulate LMStudio models when switching to LMStudio', async ({ page }) => {
    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    // Get initial provider
    const initialProvider = await providerSelect.inputValue();
    
    // Switch away from LMStudio first if needed
    if (initialProvider === 'lmstudio') {
      await providerSelect.selectOption('openai');
      await page.waitForTimeout(2000);
    }

    // Switch back to LMStudio
    await providerSelect.selectOption('lmstudio');
    await page.waitForTimeout(5000); // Wait longer for model list to load via API

    // LM Studio model select uses id rankagent-model-2 (not rankagent-model-lmstudio)
    const modelSelect = page.locator('#rankagent-model-2');
    // Wait for it to be attached first, then visible
    await modelSelect.waitFor({ state: 'attached', timeout: 10000 });
    await page.waitForTimeout(2000); // Additional wait for visibility
    
    // Verify it exists and is a select element
    const exists = await modelSelect.count() > 0;
    expect(exists).toBe(true);
    
    if (exists) {
      const tagName = await modelSelect.evaluate((el: HTMLElement) => el.tagName.toLowerCase());
      expect(tagName).toBe('select');
    }
  });

  test('should show commercial model inputs when switching to OpenAI', async ({ page }) => {
    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    await providerSelect.selectOption('openai');
    await page.waitForTimeout(2000);

    // Check for OpenAI model selector (could be input or select)
    const modelSelector = page.locator('#rankagent-model-openai');
    await modelSelector.waitFor({ state: 'visible', timeout: 5000 });

    const tagName = await modelSelector.evaluate((el: HTMLElement) => el.tagName.toLowerCase());
    expect(['input', 'select']).toContain(tagName);
  });

  test('should show commercial model inputs when switching to Anthropic', async ({ page }) => {
    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    const hasAnthropic = await providerSelect.locator('option[value="anthropic"]').count() > 0;
    if (!hasAnthropic) {
      test.skip(true, 'Anthropic provider not available (requires API key in Settings)');
      return;
    }

    await providerSelect.selectOption('lmstudio');
    await page.waitForTimeout(2000);

    await providerSelect.selectOption('anthropic');
    await page.waitForTimeout(5000);

    const modelSelector = page.locator('#rankagent-model-anthropic');
    await modelSelector.waitFor({ state: 'attached', timeout: 10000 });
    await page.waitForTimeout(2000); // Additional wait for visibility
    
    // Check if it exists (might be hidden initially)
    const exists = await modelSelector.count() > 0;
    expect(exists).toBe(true);
    
    if (exists) {
      const tagName = await modelSelector.evaluate((el: HTMLElement) => el.tagName.toLowerCase());
      expect(['input', 'select']).toContain(tagName);
    }
  });

  test('should preserve model value across provider switches', async ({ page }) => {
    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    // Set a model for OpenAI
    await providerSelect.selectOption('openai');
    await page.waitForTimeout(2000);

    const modelSelector = page.locator('#rankagent-model-openai');
    await modelSelector.waitFor({ state: 'visible', timeout: 5000 });
    
    const tagName = await modelSelector.evaluate((el: HTMLElement) => el.tagName.toLowerCase());
    
    if (tagName === 'input') {
      const testModel = 'gpt-4-turbo';
      await modelSelector.fill(testModel);
      await page.waitForTimeout(1000);

      // Switch to Anthropic and back
      await providerSelect.selectOption('anthropic');
      await page.waitForTimeout(1000);
      await providerSelect.selectOption('openai');
      await page.waitForTimeout(2000);

      // Model value should be preserved
      const preservedValue = await modelSelector.inputValue();
      expect(preservedValue).toBe(testModel);
    } else {
      // If it's a select, just verify it exists and has options
      const options = await modelSelector.locator('option').count();
      expect(options).toBeGreaterThan(0);
    }
  });

  test('should only show valid models for selected provider', async ({ page }) => {
    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    // Test LMStudio
    await providerSelect.selectOption('lmstudio');
    // Wait for loadLMStudioModels API call
    await page.waitForResponse(
      (resp) => resp.url().includes('/api/lmstudio-models') || resp.url().includes('/api/workflow/config'),
      { timeout: 15000 }
    ).catch(() => {});
    await page.waitForTimeout(3000);

    const lmModelSelect = page.locator('#rankagent-model-2');
    await lmModelSelect.waitFor({ state: 'attached', timeout: 15000 });
    await page.waitForTimeout(2000);
    const lmExists = await lmModelSelect.count() > 0;
    expect(lmExists).toBe(true);

    // Test OpenAI
    await providerSelect.selectOption('openai');
    await page.waitForTimeout(3000);

    const openaiModelSelector = page.locator('#rankagent-model-openai');
    await openaiModelSelector.waitFor({ state: 'attached', timeout: 15000 });
    await page.waitForTimeout(2000);
    const openaiExists = await openaiModelSelector.count() > 0;
    expect(openaiExists).toBe(true);

    // LM Studio model selector (#rankagent-model-2) should be hidden when provider is openai
    const lmVisible = await lmModelSelect.isVisible().catch(() => false);
    expect(lmVisible).toBe(false);
  });

  test('should update UI correctly when switching providers', async ({ page }) => {
    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    await providerSelect.selectOption('openai');
    await page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 15000 }
    ).catch(() => {});
    await page.waitForTimeout(3000);

    const openaiModelInput = page.locator('#rankagent-model-openai');
    await openaiModelInput.waitFor({ state: 'attached', timeout: 15000 });
    await page.waitForTimeout(2000);
    const openaiExists = await openaiModelInput.count() > 0;
    expect(openaiExists).toBe(true);

    await providerSelect.selectOption('lmstudio');
    await page.waitForResponse(
      (resp) => resp.url().includes('/api/lmstudio-models') || (resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT'),
      { timeout: 15000 }
    ).catch(() => {});
    await page.waitForTimeout(5000);

    const lmModelSelect = page.locator('#rankagent-model-2');
    await lmModelSelect.waitFor({ state: 'attached', timeout: 15000 });
    await page.waitForTimeout(2000);
    const lmExists = await lmModelSelect.count() > 0;
    expect(lmExists).toBe(true);
    
    const openaiVisible = await openaiModelInput.isVisible().catch(() => false);
    expect(openaiVisible).toBe(false);
  });
});

async function expandPanelIfNeeded(page: any, panelId: string) {
  const content = page.locator(`#${panelId}-content`);
  const header = page.locator(`[data-collapsible-panel="${panelId}"]`);

  if (await header.isVisible({ timeout: 2000 }).catch(() => false)) {
    const isHidden = await content.evaluate((el: HTMLElement) => el.classList.contains('hidden')).catch(() => true);
    if (isHidden) {
      await header.click();
      await page.waitForTimeout(300);
    }
  }
}
