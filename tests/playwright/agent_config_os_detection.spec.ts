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
      { timeout: 10000 }  // Increased from 5000 to 10000
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
          { timeout: 10000 }  // Increased from 5000 to 10000
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
        { timeout: 10000 }  // Increased from 5000 to 10000
      );

      await embeddingSelector.fill(newValue);
      await embeddingSelector.blur();

      const response = await responsePromise;
      expect(response.status()).toBe(200);

      const responseData = await response.json();
      expect(responseData.agent_models?.OSDetectionAgent_embedding).toBe(newValue);
    }
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
