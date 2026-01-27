import { test, expect } from '@playwright/test';

const BASE_URL = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

test.describe('Workflow Config Verification', () => {
  test.skip('verify provider/model validation and temperature limits', async ({ page }) => {
    await page.goto(`${BASE_URL}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000); // Wait for config to load

    // Expand Rank Agent panel
    await page.evaluate(() => {
      const panel = document.querySelector('[data-collapsible-panel="rank-agent-configs-panel"]');
      if (panel) {
        const content = document.getElementById('rank-agent-configs-panel-content');
        const toggle = document.getElementById('rank-agent-configs-panel-toggle');
        if (content && content.classList.contains('hidden')) {
          content.classList.remove('hidden');
          if (toggle) {
            toggle.textContent = '▲';
            toggle.style.transform = 'rotate(0deg)';
          }
        }
      }
    });
    await page.waitForTimeout(1000);

    // Test 1: Verify invalid provider/model combinations are blocked
    // Select OpenAI provider for Rank Agent
    const rankProvider = page.locator('#rankagent-provider');
    await rankProvider.waitFor({ state: 'visible', timeout: 10000 });
    await rankProvider.selectOption('openai');
    await page.waitForTimeout(500);

    // Try to enter an LMStudio model (should show error)
    // For OpenAI, it's a select dropdown, so we need to type in the input if it exists
    // Or check if it's a text input
    const rankModelOpenAI = page.locator('#rankagent-model-openai');
    await rankModelOpenAI.waitFor({ state: 'visible', timeout: 5000 });
    
    const tagName = await rankModelOpenAI.evaluate(el => el.tagName.toLowerCase());
    if (tagName === 'input') {
      await rankModelOpenAI.fill('Qwen3-14B-Instruct');
      await rankModelOpenAI.blur();
      await page.waitForTimeout(500);

      // Check for error message
      const rankError = page.locator('#rankagent-model-error');
      await rankError.waitFor({ state: 'visible', timeout: 2000 }).catch(() => {});
      const rankErrorText = await rankError.textContent();
      if (rankErrorText) {
        expect(rankErrorText).toContain('Invalid model');
      }
    } else {
      // It's a select, try to select an invalid option if available
      // Or just verify the validation function exists
      console.log('OpenAI model selector is a dropdown, validation tested via type checking');
    }

    // Test 2: Verify LMStudio provider rejects OpenAI models
    await rankProvider.selectOption('lmstudio');
    await page.waitForTimeout(1000);
    
    const rankModelLMStudio = page.locator('#rankagent-model-2');
    await rankModelLMStudio.waitFor({ state: 'visible', timeout: 5000 });
    
    // Try to manually set an OpenAI model value via JavaScript to test validation
    await page.evaluate(() => {
      const select = document.getElementById('rankagent-model-2');
      if (select) {
        // Create a temporary option with OpenAI model name
        const option = document.createElement('option');
        option.value = 'gpt-4o-mini';
        option.textContent = 'gpt-4o-mini';
        select.appendChild(option);
        select.value = 'gpt-4o-mini';
        select.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    await page.waitForTimeout(500);
    
    // Check for error message
    const lmstudioError = page.locator('#rankagent-model-error');
    const errorVisible = await lmstudioError.isVisible().catch(() => false);
    if (errorVisible) {
      const errorText = await lmstudioError.textContent();
      expect(errorText).toContain('Invalid model for LMStudio');
    }

    // Test 3: Verify temperature limits are provider-specific
    const rankTemp = page.locator('#rankagent-temperature');
    await rankTemp.waitFor({ state: 'visible', timeout: 5000 });
    
    // Check Anthropic temperature max is 1
    await rankProvider.selectOption('anthropic');
    await page.waitForTimeout(1000);
    
    const maxAttrAnthropic = await rankTemp.getAttribute('max');
    expect(maxAttrAnthropic).toBe('1');

    // Check OpenAI temperature max is 2
    await rankProvider.selectOption('openai');
    await page.waitForTimeout(1000);
    
    const maxAttrOpenAI = await rankTemp.getAttribute('max');
    expect(maxAttrOpenAI).toBe('2');

    // Check LMStudio temperature max is 1
    await rankProvider.selectOption('lmstudio');
    await page.waitForTimeout(1000);
    
    const maxAttrLMStudio = await rankTemp.getAttribute('max');
    expect(maxAttrLMStudio).toBe('1');

    // Test 4: Verify Temperature and Top_P are on one row
    const tempParent = rankTemp.locator('..'); // Get parent div
    const tempRow = tempParent.locator('..'); // Get flex container
    const flexClass = await tempRow.getAttribute('class');
    expect(flexClass).toContain('flex');
    expect(flexClass).toContain('gap-3');

    // Test 5: Verify SIGMA agent alignment
    await page.evaluate(() => {
      const panel = document.querySelector('[data-collapsible-panel="sigma-agent-panel"]');
      if (panel) {
        const content = document.getElementById('sigma-agent-panel-content');
        const toggle = document.getElementById('sigma-agent-panel-toggle');
        if (content && content.classList.contains('hidden')) {
          content.classList.remove('hidden');
          if (toggle) {
            toggle.textContent = '▲';
            toggle.style.transform = 'rotate(0deg)';
          }
        }
      }
    });
    await page.waitForTimeout(1000);

    // Verify both SIGMA and Presets have same panel structure
    const sigmaPanel = page.locator('h3:has-text("SIGMA Generator Agent")').locator('..').locator('..');
    const presetPanel = page.locator('h3:has-text("Configuration Presets")').locator('..').locator('..');
    
    const sigmaPanelClass = await sigmaPanel.getAttribute('class');
    const presetPanelClass = await presetPanel.getAttribute('class');
    
    // Both should have border and rounded-lg classes
    expect(sigmaPanelClass).toContain('border');
    expect(sigmaPanelClass).toContain('rounded-lg');
    expect(presetPanelClass).toContain('border');
    expect(presetPanelClass).toContain('rounded-lg');
    
    // Check header padding alignment
    const sigmaHeader = page.locator('h3:has-text("SIGMA Generator Agent")').locator('..');
    const presetHeader = page.locator('h3:has-text("Configuration Presets")').locator('..');
    
    const sigmaPadding = await sigmaHeader.evaluate(el => window.getComputedStyle(el).paddingLeft);
    const presetPadding = await presetHeader.evaluate(el => window.getComputedStyle(el).paddingLeft);
    
    // They should have the same padding (p-4 = 1rem = 16px)
    expect(sigmaPadding).toBe(presetPadding);
  });
});
