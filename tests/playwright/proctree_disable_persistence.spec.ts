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

async function reloadWorkflowConfig(page: Page) {
  await page.reload();
  await page.waitForLoadState('networkidle');
  await switchToConfigTab(page);
  await waitForConfigReady(page);
}

async function expandPanel(page: Page, panelId: string) {
  const content = page.locator(`#${panelId}-content`);
  const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
  if (await content.count() === 0 || await header.count() === 0) {
    return;
  }
  const isHidden = await content.evaluate(el => el.classList.contains('hidden')).catch(() => true);
  if (isHidden) {
    await header.click();
    await page.waitForTimeout(300);
  }
}

test.describe('ProcTreeExtract Disable Persistence', () => {
  test('ProcTreeExtract disabled state persists after save + refresh', async ({ page }) => {
    await gotoWorkflowConfig(page);
    
    // Expand Extract Agent panel
    await expandPanel(page, 'extract-agent-panel');
    await page.waitForTimeout(500);
    
    // Expand ProcTreeExtract panel
    await expandPanel(page, 'proctreeextract-agent-panel');
    await page.waitForTimeout(500);
    
    // Wait for toggle to be available
    const toggle = page.locator('#toggle-proctreeextract-enabled');
    await toggle.waitFor({ state: 'attached', timeout: 10000 });
    
    // Get initial state
    const initialState = await toggle.isChecked();
    console.log('Initial ProcTreeExtract state:', initialState ? 'enabled' : 'disabled');
    
    // If already disabled, enable it first so we can test disabling
    if (!initialState) {
      await toggle.click();
      await page.waitForTimeout(300);
      await expect(toggle).toBeChecked();
    }
    
    // Now disable it
    await toggle.click();
    await page.waitForTimeout(300);
    await expect(toggle).not.toBeChecked();
    
    // Verify save button is enabled
    const saveButton = page.locator('#save-config-button');
    await expect(saveButton).toBeEnabled();
    
    // Save configuration
    const [response] = await Promise.all([
      page.waitForResponse(resp => 
        resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
        { timeout: 15000 }  // Increased timeout
      ),
      saveButton.click()
    ]);
    
    expect(response.ok()).toBeTruthy();
    const responseData = await response.json();
    console.log('Save response - agent_prompts.ExtractAgentSettings:', 
      responseData.agent_prompts?.ExtractAgentSettings);
    
    // Verify disabled_agents in response
    const extractSettings = responseData.agent_prompts?.ExtractAgentSettings || {};
    const disabledAgents = extractSettings.disabled_agents || [];
    console.log('Disabled agents in response:', disabledAgents);
    expect(disabledAgents).toContain('ProcTreeExtract');
    
    // Wait for save to complete
    await page.waitForTimeout(2000);
    
    // Reload page
    await reloadWorkflowConfig(page);
    
    // Expand panels again
    await expandPanel(page, 'extract-agent-panel');
    await page.waitForTimeout(500);
    await expandPanel(page, 'proctreeextract-agent-panel');
    await page.waitForTimeout(500);
    
    // Wait for toggle to be available
    await toggle.waitFor({ state: 'attached', timeout: 10000 });
    
    // Verify toggle is still disabled
    const afterReloadState = await toggle.isChecked();
    console.log('After reload ProcTreeExtract state:', afterReloadState ? 'enabled' : 'disabled');
    
    if (afterReloadState !== false) {
      // Debug: Check what the config actually contains
      const configInPage = await page.evaluate(() => {
        return typeof currentConfig !== 'undefined' ? currentConfig : null;
      });
      console.log('Config in page after reload:', JSON.stringify(configInPage?.agent_prompts?.ExtractAgentSettings, null, 2));
      
      const disabledInPage = await page.evaluate(() => {
        return typeof disabledExtractAgents !== 'undefined' ? Array.from(disabledExtractAgents) : [];
      });
      console.log('disabledExtractAgents in page:', disabledInPage);
    }
    
    expect(afterReloadState).toBe(false);
    
    // Restore original state if needed
    if (initialState && !afterReloadState) {
      await toggle.click();
      await page.waitForTimeout(300);
      await expect(saveButton).toBeEnabled();
      await Promise.all([
        page.waitForResponse(resp => 
          resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT'
        ),
        saveButton.click()
      ]);
    }
  });
});
