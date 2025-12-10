import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

test.describe('Model Selector Dropdowns - Duplicate Placeholder Check', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow`);
    await page.waitForLoadState('networkidle');
    
    // Switch to config tab
    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(2000);
    
    // Wait for config to load
    await page.waitForSelector('#workflowConfigForm, #configDisplay', { timeout: 10000 });
    await page.waitForTimeout(2000); // Wait for models to load
  });

  /**
   * Helper function to check for duplicate placeholder options in a select element
   * Returns true if exactly one placeholder (value="") exists, false otherwise
   */
  async function checkNoDuplicatePlaceholders(page: any, selector: string, selectorName: string): Promise<boolean> {
    const select = page.locator(selector);
    
    // Wait for select to exist
    try {
      await select.waitFor({ state: 'attached', timeout: 10000 });
    } catch (e) {
      console.log(`⚠️ ${selectorName} (${selector}) not found, skipping`);
      return true; // Skip if not found
    }
    
    // Get all options
    const options = await select.locator('option').all();
    
    // Count placeholder options (value="")
    const placeholderOptions = [];
    for (const opt of options) {
      const value = await opt.getAttribute('value');
      if (value === '' || value === null) {
        const text = await opt.textContent();
        placeholderOptions.push(text?.trim() || '');
      }
    }
    
    // Should have exactly one placeholder
    if (placeholderOptions.length === 0) {
      console.log(`❌ ${selectorName}: No placeholder option found`);
      return false;
    }
    
    if (placeholderOptions.length > 1) {
      console.log(`❌ ${selectorName}: Found ${placeholderOptions.length} placeholder options:`, placeholderOptions);
      return false;
    }
    
    console.log(`✅ ${selectorName}: Single placeholder found: "${placeholderOptions[0]}"`);
    return true;
  }

  /**
   * Helper function to check for duplicate model entries (e.g., "Mistral7" and "Mistral7:2")
   * Returns true if no duplicates found, false otherwise
   */
  async function checkNoDuplicateModels(page: any, selector: string, selectorName: string): Promise<boolean> {
    const select = page.locator(selector);
    
    // Wait for select to exist
    try {
      await select.waitFor({ state: 'attached', timeout: 10000 });
    } catch (e) {
      console.log(`⚠️ ${selectorName} (${selector}) not found, skipping`);
      return true; // Skip if not found
    }
    
    // Get all options (excluding placeholder)
    const options = await select.locator('option').all();
    const modelNames: string[] = [];
    
    for (const opt of options) {
      const value = await opt.getAttribute('value');
      if (value && value !== '') {
        const text = await opt.textContent();
        if (text) {
          // Remove "(not in LM Studio)" suffix if present
          const cleanText = text.trim().replace(/\s*\(not in LM Studio\)$/, '');
          modelNames.push(cleanText);
        }
      }
    }
    
    // Check for duplicates by base model name (remove :2, :3 suffixes)
    const baseModelNames = new Map<string, number>();
    const duplicates: string[] = [];
    
    for (const modelName of modelNames) {
      // Extract base model name (remove :2, :3, etc. suffixes)
      const baseName = modelName.replace(/:\d+$/, '');
      const count = baseModelNames.get(baseName) || 0;
      baseModelNames.set(baseName, count + 1);
      
      if (count > 0) {
        duplicates.push(modelName);
      }
    }
    
    if (duplicates.length > 0) {
      console.log(`❌ ${selectorName}: Found duplicate models:`, duplicates);
      console.log(`   All models:`, modelNames);
      return false;
    }
    
    console.log(`✅ ${selectorName}: No duplicate models found (${modelNames.length} unique models)`);
    return true;
  }

  test('Rank Agent model selector should have single placeholder', async ({ page }) => {
    // Expand Rank Agent panel if needed
    const rankPanelToggle = page.locator('#rank-agent-configs-panel-toggle');
    if (await rankPanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#rank-agent-configs-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await rankPanelToggle.click();
        await page.waitForTimeout(500);
      }
    }
    
    const hasSinglePlaceholder = await checkNoDuplicatePlaceholders(
      page,
      '#rankagent-model-2',
      'Rank Agent Model Selector'
    );
    
    expect(hasSinglePlaceholder).toBe(true);
  });

  test('Rank Agent model selector should have no duplicate models', async ({ page }) => {
    // Expand Rank Agent panel if needed
    const rankPanelToggle = page.locator('#rank-agent-configs-panel-toggle');
    if (await rankPanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#rank-agent-configs-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await rankPanelToggle.click();
        await page.waitForTimeout(500);
      }
    }
    
    const noDuplicates = await checkNoDuplicateModels(
      page,
      '#rankagent-model-2',
      'Rank Agent Model Selector'
    );
    
    expect(noDuplicates).toBe(true);
  });

  test('Rank Agent commercial providers show curated dropdowns', async ({ page }) => {
    const rankPanelToggle = page.locator('#rank-agent-configs-panel-toggle');
    if (await rankPanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#rank-agent-configs-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await rankPanelToggle.click();
        await page.waitForTimeout(500);
      }
    }

    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible' });

    await providerSelect.selectOption('openai');
    const openaiSelect = page.locator('#rankagent-model-openai');
    await expect(openaiSelect).toBeVisible();
    const openaiOptions = await openaiSelect.locator('option').allTextContents();
    expect(openaiOptions[0].trim()).toBe('Select an OpenAI model');
    expect(openaiOptions.some(text => text.includes('gpt-4.1'))).toBeTruthy();
    expect(openaiOptions.some(text => text.includes('gpt-4o'))).toBeTruthy();

    await providerSelect.selectOption('anthropic');
    const anthropicSelect = page.locator('#rankagent-model-anthropic');
    await expect(anthropicSelect).toBeVisible();
    const anthropicOptions = await anthropicSelect.locator('option').allTextContents();
    expect(anthropicOptions[0].trim()).toBe('Select a Claude model');
    expect(anthropicOptions.some(text => text.toLowerCase().includes('claude-3.7'))).toBeTruthy();
  });

  test('Anthropic dropdown excludes non-Claude saved models', async ({ page }) => {
    const rankPanelToggle = page.locator('#rank-agent-configs-panel-toggle');
    if (await rankPanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#rank-agent-configs-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await rankPanelToggle.click();
        await page.waitForTimeout(500);
      }
    }

    // Inject a saved config with a non-Claude anthropic model
    await page.evaluate(() => {
      if (typeof renderAgentModels !== 'function') return;
      if (!window.agentModels) {
        window.agentModels = {};
      }
      window.agentModels['RankAgent'] = 'nvidia-nemotron-nano-12b-v2';
      window.agentModels['RankAgent_provider'] = 'anthropic';
      renderAgentModels([]);
    });

    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible' });
    await providerSelect.selectOption('anthropic');

    const anthropicSelect = page.locator('#rankagent-model-anthropic');
    await expect(anthropicSelect).toBeVisible();
    const options = await anthropicSelect.locator('option').allTextContents();
    expect(options.some(text => text.includes('nvidia'))).toBeFalsy();
  });

  test('Rank QA model selector should have single placeholder', async ({ page }) => {
    // Expand Rank Agent panel if needed
    const rankPanelToggle = page.locator('#rank-agent-configs-panel-toggle');
    if (await rankPanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#rank-agent-configs-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await rankPanelToggle.click();
        await page.waitForTimeout(500);
      }
    }
    
    const hasSinglePlaceholder = await checkNoDuplicatePlaceholders(
      page,
      '#rankqa-model',
      'Rank QA Model Selector'
    );
    
    expect(hasSinglePlaceholder).toBe(true);
  });

  test('CmdLine QA model selector should have single placeholder', async ({ page }) => {
    // Expand Extract Agent panel and CmdlineExtract sub-agent panel
    const extractPanelToggle = page.locator('#extract-agent-panel-toggle');
    if (await extractPanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#extract-agent-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await extractPanelToggle.click();
        await page.waitForTimeout(500);
      }
    }
    
    // Expand CmdlineExtract sub-agent panel
    const cmdlinePanelToggle = page.locator('#cmdlineextract-agent-panel-toggle');
    if (await cmdlinePanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#cmdlineextract-agent-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await cmdlinePanelToggle.click();
        await page.waitForTimeout(500);
      }
    }
    
    const hasSinglePlaceholder = await checkNoDuplicatePlaceholders(
      page,
      '#cmdlineqa-model',
      'CmdLine QA Model Selector'
    );
    
    expect(hasSinglePlaceholder).toBe(true);
  });

  test('Sig QA model selector should have single placeholder', async ({ page }) => {
    // Expand Extract Agent panel and SigExtract sub-agent panel
    const extractPanelToggle = page.locator('#extract-agent-panel-toggle');
    if (await extractPanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#extract-agent-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await extractPanelToggle.click();
        await page.waitForTimeout(500);
      }
    }
    
    // Expand SigExtract sub-agent panel
    const sigPanelToggle = page.locator('#sigextract-agent-panel-toggle');
    if (await sigPanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#sigextract-agent-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await sigPanelToggle.click();
        await page.waitForTimeout(500);
      }
    }
    
    const hasSinglePlaceholder = await checkNoDuplicatePlaceholders(
      page,
      '#sigqa-model',
      'Sig QA Model Selector'
    );
    
    expect(hasSinglePlaceholder).toBe(true);
  });

  test('EventCode QA model selector should have single placeholder', async ({ page }) => {
    // Expand Extract Agent panel and EventCodeExtract sub-agent panel
    const extractPanelToggle = page.locator('#extract-agent-panel-toggle');
    if (await extractPanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#extract-agent-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await extractPanelToggle.click();
        await page.waitForTimeout(500);
      }
    }
    
    // Expand EventCodeExtract sub-agent panel
    const eventcodePanelToggle = page.locator('#eventcodeextract-agent-panel-toggle');
    if (await eventcodePanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#eventcodeextract-agent-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await eventcodePanelToggle.click();
        await page.waitForTimeout(500);
      }
    }
    
    const hasSinglePlaceholder = await checkNoDuplicatePlaceholders(
      page,
      '#eventcodeqa-model',
      'EventCode QA Model Selector'
    );
    
    expect(hasSinglePlaceholder).toBe(true);
  });

  test('ProcTree QA model selector should have single placeholder', async ({ page }) => {
    // Expand Extract Agent panel and ProcTreeExtract sub-agent panel
    const extractPanelToggle = page.locator('#extract-agent-panel-toggle');
    if (await extractPanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#extract-agent-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await extractPanelToggle.click();
        await page.waitForTimeout(500);
      }
    }
    
    // Expand ProcTreeExtract sub-agent panel
    const proctreePanelToggle = page.locator('#proctreeextract-agent-panel-toggle');
    if (await proctreePanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#proctreeextract-agent-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await proctreePanelToggle.click();
        await page.waitForTimeout(500);
      }
    }
    
    const hasSinglePlaceholder = await checkNoDuplicatePlaceholders(
      page,
      '#proctreeqa-model',
      'ProcTree QA Model Selector'
    );
    
    expect(hasSinglePlaceholder).toBe(true);
  });

  test('Reg QA model selector should have single placeholder', async ({ page }) => {
    // Expand Extract Agent panel and RegExtract sub-agent panel
    const extractPanelToggle = page.locator('#extract-agent-panel-toggle');
    if (await extractPanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#extract-agent-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await extractPanelToggle.click();
        await page.waitForTimeout(500);
      }
    }
    
    // Expand RegExtract sub-agent panel
    const regPanelToggle = page.locator('#regextract-agent-panel-toggle');
    if (await regPanelToggle.isVisible({ timeout: 2000 }).catch(() => false)) {
      const panelContent = page.locator('#regextract-agent-panel-content');
      const isHidden = await panelContent.evaluate(el => el.classList.contains('hidden')).catch(() => true);
      if (isHidden) {
        await regPanelToggle.click();
        await page.waitForTimeout(500);
      }
    }
    
    const hasSinglePlaceholder = await checkNoDuplicatePlaceholders(
      page,
      '#regqa-model',
      'Reg QA Model Selector'
    );
    
    expect(hasSinglePlaceholder).toBe(true);
  });
});
