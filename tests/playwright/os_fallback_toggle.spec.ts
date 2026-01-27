import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

test.describe('OS Detection Fallback Toggle', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to workflow config page
    await page.goto(`${BASE}/workflow`);
    await page.waitForLoadState('networkidle');
    
    // Switch to config tab
    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(1000);
    
    // Wait for the page to fully load
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    await page.waitForTimeout(2000); // Wait for config to load
    
    // Wait for OS Detection model container to exist (it's rendered dynamically, may be hidden)
    await page.waitForSelector('#os-detection-model-container', { timeout: 10000, state: 'attached' });
    await page.waitForTimeout(2000); // Wait for models to load and render
    
    // Expand OS Detection panel if it's collapsed
    const osPanelToggle = page.locator('[data-collapsible-panel="os-detection-panel"]');
    const osPanelContent = page.locator('#os-detection-panel-content');
    if (await osPanelContent.isHidden()) {
      await osPanelToggle.click();
      await page.waitForTimeout(500);
    }
  });

  test.skip('toggle should stay disabled after unchecking and saving', async ({ page }) => {
    // Check for console errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.log('Console error:', msg.text());
      }
    });
    
    // Wait for models API to complete
    await page.waitForResponse(response => 
      response.url().includes('/api/lmstudio-models') && response.status() === 200
    ).catch(() => console.log('Models API may have failed or already completed'));
    
    // Wait a bit for rendering
    await page.waitForTimeout(3000);
    
    // Check if container exists and try to trigger rendering manually if needed
    const containerExists = await page.locator('#os-detection-model-container').count() > 0;
    if (containerExists) {
      // Try to trigger loadAgentModels manually
      await page.evaluate(() => {
        if (typeof loadAgentModels === 'function') {
          loadAgentModels();
        }
      });
      await page.waitForTimeout(2000);
    }
    
    // Wait for toggle to exist (with longer timeout)
    await page.waitForFunction(() => {
      const toggle = document.getElementById('osdetectionagent-fallback-enabled');
      return toggle !== null;
    }, { timeout: 15000 });
    
    // Find the OS Detection fallback toggle (it has sr-only class so check for existence)
    const fallbackToggle = page.locator('#osdetectionagent-fallback-enabled');
    const fallbackContainer = page.locator('#osdetectionagent-fallback-container');
    
    // Wait for toggle to exist in DOM (it's rendered in the OS Detection container)
    await expect(fallbackToggle).toBeAttached({ timeout: 10000 });
    await page.waitForTimeout(1000); // Wait for page to fully initialize
    
    // Check initial state - toggle might be checked or unchecked
    const initialChecked = await fallbackToggle.isChecked();
    console.log('Initial toggle state:', initialChecked);
    
    // If toggle is checked, uncheck it using JavaScript
    if (initialChecked) {
      // Use JavaScript to uncheck the toggle and trigger the change event
      await page.evaluate(() => {
        const toggle = document.getElementById('osdetectionagent-fallback-enabled');
        if (toggle) {
          toggle.checked = false;
          toggle.dispatchEvent(new Event('change', { bubbles: true }));
          // Also call the toggle function if it exists
          if (typeof toggleFallbackModel === 'function') {
            toggleFallbackModel();
          }
        }
      });
      await page.waitForTimeout(1000); // Wait for UI update
      
      // Verify container is hidden
      await expect(fallbackContainer).toBeHidden();
      
      // Verify toggle is unchecked
      await expect(fallbackToggle).not.toBeChecked();
    }
    
    // Save the configuration
    const saveButton = page.locator('#save-config-button');
    await expect(saveButton).toBeEnabled();
    
    // Wait for save to complete by waiting for button text to change or response
    await Promise.all([
      saveButton.click(),
      page.waitForResponse(response => 
        response.url().includes('/api/workflow/config') && response.request().method() === 'PUT',
        { timeout: 15000 }  // Increased timeout
      ).catch(() => null)
    ]);
    
    // Wait for save to complete (look for success indicator)
    await page.waitForTimeout(3000);
    
    // Reload the page
    await page.reload();
    await page.waitForLoadState('networkidle');
    
    // Switch to config tab again after reload
    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(1000);
    
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    
    // Wait for toggle to exist again after reload
    await expect(fallbackToggle).toBeAttached({ timeout: 10000 });
    await page.waitForTimeout(3000); // Give time for state to restore
    
    // Verify toggle is still unchecked after reload
    await expect(fallbackToggle).not.toBeChecked();
    
    // Verify container is still hidden
    await expect(fallbackContainer).toBeHidden();
  });

  test.skip('toggle should stay enabled after checking and saving', async ({ page }) => {
    // Wait for models to load and OS Detection container to be populated
    await page.waitForFunction(() => {
      const toggle = document.getElementById('osdetectionagent-fallback-enabled');
      return toggle !== null;
    }, { timeout: 30000 });
    
    // Find the OS Detection fallback toggle (it has sr-only class so check for existence)
    const fallbackToggle = page.locator('#osdetectionagent-fallback-enabled');
    const fallbackContainer = page.locator('#osdetectionagent-fallback-container');
    
    // Wait for toggle to exist in DOM (it's rendered in the OS Detection container)
    await expect(fallbackToggle).toBeAttached({ timeout: 10000 });
    await page.waitForTimeout(1000); // Wait for page to fully initialize
    
    // Uncheck first to ensure clean state using JavaScript
    if (await fallbackToggle.isChecked()) {
      await page.evaluate(() => {
        const toggle = document.getElementById('osdetectionagent-fallback-enabled');
        if (toggle) {
          toggle.checked = false;
          toggle.dispatchEvent(new Event('change', { bubbles: true }));
          if (typeof toggleFallbackModel === 'function') {
            toggleFallbackModel();
          }
        }
      });
      await page.waitForTimeout(500);
    }
    
    // Now check it using JavaScript
    await page.evaluate(() => {
      const toggle = document.getElementById('osdetectionagent-fallback-enabled');
      if (toggle) {
        toggle.checked = true;
        toggle.dispatchEvent(new Event('change', { bubbles: true }));
        if (typeof toggleFallbackModel === 'function') {
          toggleFallbackModel();
        }
      }
    });
    await page.waitForTimeout(500);
    
    // Verify container is visible
    await expect(fallbackContainer).toBeVisible();
    
    // Verify toggle is checked
    await expect(fallbackToggle).toBeChecked();
    
    // Save the configuration
    const saveButton = page.locator('#save-config-button');
    await expect(saveButton).toBeEnabled();
    
    // Wait for save to complete by waiting for button text to change or response
    await Promise.all([
      saveButton.click(),
      page.waitForResponse(response => 
        response.url().includes('/api/workflow/config') && response.request().method() === 'PUT',
        { timeout: 15000 }  // Increased timeout
      ).catch(() => null)
    ]);
    
    // Wait for save to complete
    await page.waitForTimeout(3000);
    
    // Reload the page
    await page.reload();
    await page.waitForLoadState('networkidle');
    
    // Switch to config tab again after reload
    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(1000);
    
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    
    // Wait for toggle to exist again after reload
    await expect(fallbackToggle).toBeAttached({ timeout: 10000 });
    await page.waitForTimeout(3000); // Give time for state to restore
    
    // Verify toggle is still checked after reload
    await expect(fallbackToggle).toBeChecked();
    
    // Verify container is still visible
    await expect(fallbackContainer).toBeVisible();
  });
});

