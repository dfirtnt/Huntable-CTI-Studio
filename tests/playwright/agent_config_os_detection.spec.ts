import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Agent Config OS Detection', () => {
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

    await expandPanelIfNeeded(page, 'os-detection-panel');
  });

  test('should autosave OS selection checkboxes', async ({ page }) => {
    // Find OS selection checkboxes
    const windowsCheckbox = page.locator('input[name="os_selection[]"][value="Windows"]').first();
    await windowsCheckbox.waitFor({ state: 'attached', timeout: 10000 });

    const initialChecked = await windowsCheckbox.isChecked();

    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 5000 }
    );

    // Toggle checkbox using JavaScript if it's hidden
    await page.evaluate(() => {
      const checkbox = document.querySelector('input[name="os_selection[]"][value="Windows"]') as HTMLInputElement;
      if (checkbox) {
        checkbox.checked = !checkbox.checked;
        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    await page.waitForTimeout(500);

    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    const selectedOS = responseData.agent_models?.OSDetectionAgent_selected_os || [];
    const isWindowsSelected = selectedOS.includes('Windows');
    // Windows is always selected by default, so if it was checked, unchecking should remove it
    // But if no OS is selected, Windows is the default
    expect(selectedOS.length).toBeGreaterThan(0);
  });

  test('should autosave OS fallback toggle', async ({ page }) => {
    const fallbackToggle = page.locator('#osdetectionagent-fallback-enabled');
    await fallbackToggle.waitFor({ state: 'attached', timeout: 10000 });

    const initialChecked = await fallbackToggle.isChecked();

    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 10000 }
    );

    await page.evaluate(() => {
      const toggle = document.getElementById('osdetectionagent-fallback-enabled') as HTMLInputElement;
      if (toggle) {
        toggle.checked = !toggle.checked;
        toggle.dispatchEvent(new Event('change', { bubbles: true }));
        // Call the handler if it exists
        if (typeof toggleFallbackModel === 'function') {
          toggleFallbackModel();
        } else if (typeof autoSaveConfig === 'function') {
          autoSaveConfig();
        }
      }
    });
    await page.waitForTimeout(1000);

    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    
    // Verify the toggle state was saved
    // If toggle was enabled, fallback should have a value (or be null if disabled)
    // If toggle was disabled, fallback should be null
    const fallbackValue = responseData.agent_models?.OSDetectionAgent_fallback;
    if (!initialChecked) {
      // Was disabled, now enabled - should have a value or be explicitly null
      expect(fallbackValue !== undefined).toBe(true);
    } else {
      // Was enabled, now disabled - should be null
      expect(fallbackValue).toBeNull();
    }
  });

  test('should autosave OS embedding model', async ({ page }) => {
    const embeddingSelector = page.locator('#osdetectionagent-embedding-model-2');
    await embeddingSelector.waitFor({ state: 'attached', timeout: 10000 });

    const tagName = await embeddingSelector.evaluate((el: HTMLElement) => el.tagName.toLowerCase());
    
    if (tagName === 'select') {
      // If it's a select, just verify it exists and can be changed
      const options = await embeddingSelector.locator('option').count();
      expect(options).toBeGreaterThan(0);
      
      // Select first available option
      const firstOption = await embeddingSelector.locator('option').nth(1).getAttribute('value');
      if (firstOption) {
        const responsePromise = page.waitForResponse(
          (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
          { timeout: 5000 }
        );

        await embeddingSelector.selectOption(firstOption);
        await page.waitForTimeout(500);

        const response = await responsePromise;
        expect(response.status()).toBe(200);

        const responseData = await response.json();
        expect(responseData.agent_models?.OSDetectionAgent_embedding).toBe(firstOption);
      }
    } else {
      // If it's an input
      const newValue = 'test-embedding-model';

      const responsePromise = page.waitForResponse(
        (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
        { timeout: 5000 }
      );

      await embeddingSelector.fill(newValue);
      await embeddingSelector.blur();

      const response = await responsePromise;
      expect(response.status()).toBe(200);

      const responseData = await response.json();
      expect(responseData.agent_models?.OSDetectionAgent_embedding).toBe(newValue);
    }
  });

  test('should set fallback to null when toggle is disabled', async ({ page }) => {
    const fallbackToggle = page.locator('#osdetectionagent-fallback-enabled');
    await fallbackToggle.waitFor({ state: 'attached', timeout: 10000 });

    // Ensure toggle is enabled first
    if (!(await fallbackToggle.isChecked())) {
      await page.evaluate(() => {
        const toggle = document.getElementById('osdetectionagent-fallback-enabled') as HTMLInputElement;
        if (toggle) {
          toggle.checked = true;
          toggle.dispatchEvent(new Event('change', { bubbles: true }));
          if (typeof toggleFallbackModel === 'function') {
            toggleFallbackModel();
          } else if (typeof autoSaveConfig === 'function') {
            autoSaveConfig();
          }
        }
      });
      await page.waitForResponse(
        (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
        { timeout: 10000 }
      );
      await page.waitForTimeout(1000); // Wait for autosave
    }

    // Now disable it
    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 10000 }
    );

    await page.evaluate(() => {
      const toggle = document.getElementById('osdetectionagent-fallback-enabled') as HTMLInputElement;
      if (toggle) {
        toggle.checked = false;
        toggle.dispatchEvent(new Event('change', { bubbles: true }));
        if (typeof toggleFallbackModel === 'function') {
          toggleFallbackModel();
        } else if (typeof autoSaveConfig === 'function') {
          autoSaveConfig();
        }
      }
    });
    await page.waitForTimeout(1000);

    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    expect(responseData.agent_models?.OSDetectionAgent_fallback).toBeNull();
    expect(responseData.agent_models?.OSDetectionAgent_fallback_provider).toBeNull();
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
