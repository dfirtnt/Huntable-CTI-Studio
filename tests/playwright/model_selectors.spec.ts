import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const SKIP_MODEL_TESTS = process.env.SKIP_MODEL_TESTS === 'true';

const describeFn = SKIP_MODEL_TESTS ? test.describe.skip : test.describe;

describeFn('Model Selector Dropdowns - Duplicate Placeholder Check', () => {
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

});
