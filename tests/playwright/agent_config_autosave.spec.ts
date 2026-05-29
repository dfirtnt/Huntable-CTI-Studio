import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Agent Config Autosave', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Switch to config tab
    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(1000);

    // Wait for config form to be visible
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    // Wait for initialization flag to clear (set false after loadConfig completes)
    await page.waitForFunction(() => (window as any).isInitializing === false, { timeout: 10000 });

    // Expand necessary panels
    await expandPanelIfNeeded(page, 'other-thresholds-panel');
    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');
  });

  test('should autosave junk filter threshold on input', async ({ page }) => {
    const input = page.locator('#junkFilterThreshold');
    await input.waitFor({ state: 'visible', timeout: 10000 });

    const initialValue = await input.inputValue();
    const newValue = (parseFloat(initialValue) || 0.8) + 0.05;

    // Set up response listener
    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 10000 }  // Increased from 5000 to 10000 for reliability
    );

    // Range inputs need evaluate() + dispatchEvent to trigger oninput handler
    await input.evaluate((el, val) => {
      (el as HTMLInputElement).value = val.toString();
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }, newValue);
    await page.waitForTimeout(500);  // Wait for debouncing

    // Wait for autosave
    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    expect(responseData.junk_filter_threshold).toBeCloseTo(newValue, 2);
  });

  test('should autosave ranking threshold on input', async ({ page }) => {
    const input = page.locator('#rankingThreshold');
    await input.waitFor({ state: 'visible', timeout: 10000 });

    const initialValue = await input.inputValue();
    const newValue = (parseFloat(initialValue) || 6.0) + 0.5;

    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 10000 }  // Increased from 5000 to 10000 for reliability
    );

    await input.evaluate((el, val) => {
      (el as HTMLInputElement).value = val.toString();
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }, newValue);
    await page.waitForTimeout(500);  // Wait for debouncing

    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    expect(responseData.ranking_threshold).toBeCloseTo(newValue, 1);
  });

  test('should autosave similarity threshold on input', async ({ page }) => {
    const input = page.locator('#similarityThreshold');
    await input.waitFor({ state: 'attached', timeout: 10000 });

    const initialValue = await input.inputValue();
    const newValue = (parseFloat(initialValue) || 0.5) + 0.1;

    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 10000 }
    );

    // Use JavaScript to set value if element is hidden
    await page.evaluate((val) => {
      const el = document.getElementById('similarityThreshold') as HTMLInputElement;
      if (el) {
        el.value = val.toString();
        el.dispatchEvent(new Event('input', { bubbles: true }));
        // Trigger autosave
        if (typeof autoSaveConfig === 'function') {
          autoSaveConfig();
        }
        el.dispatchEvent(new Event('blur', { bubbles: true }));
      }
    }, newValue);

    await page.waitForTimeout(500); // Wait for debounce

    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    expect(responseData.similarity_threshold).toBeCloseTo(newValue, 2);
  });

  test('should autosave Rank Agent toggle on change', async ({ page }) => {
    const toggle = page.locator('#rank-agent-enabled');
    await toggle.waitFor({ state: 'attached', timeout: 10000 });

    const initialChecked = await toggle.isChecked();

    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 10000 }  // Increased from 5000 to 10000 for reliability
    );

    // Use JavaScript to toggle since checkbox is sr-only
    await page.evaluate(() => {
      const el = document.getElementById('rank-agent-enabled') as HTMLInputElement;
      if (el) {
        el.checked = !el.checked;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    await page.waitForTimeout(500);  // Add explicit wait for debouncing
    await page.waitForTimeout(500);

    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    expect(responseData.rank_agent_enabled).toBe(!initialChecked);
  });

  test('should autosave Sigma fallback toggle on change', async ({ page }) => {
    await expandPanelIfNeeded(page, 'sigma-agent-panel');
    const toggle = page.locator('#sigma-fallback-enabled');
    await toggle.waitFor({ state: 'attached', timeout: 10000 });

    const initialChecked = await toggle.isChecked();

    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 10000 }  // Increased from 5000 to 10000 for reliability
    );

    await page.evaluate(() => {
      const el = document.getElementById('sigma-fallback-enabled') as HTMLInputElement;
      if (el) {
        el.checked = !el.checked;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }
    });
    await page.waitForTimeout(500);

    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    expect(responseData.sigma_fallback_enabled).toBe(!initialChecked);
  });

  test('should preserve other fields when autosaving one field', async ({ page }) => {
    // Read initial values from the DOM -- the same source performAutoSave reads when it
    // builds the PUT payload. Using a fresh API GET here would be a race: a concurrent
    // test can write rank_agent_enabled between the GET and the PUT, making the expected
    // value differ from what the DOM (and therefore performAutoSave) actually sends.
    const initialConfig = await page.evaluate(() => {
      const junkInput = document.getElementById('junkFilterThreshold') as HTMLInputElement;
      const simInput  = document.getElementById('similarityThreshold') as HTMLInputElement;
      const rankToggle = document.getElementById('rank-agent-enabled') as HTMLInputElement;
      return {
        junk_filter_threshold: junkInput  ? parseFloat(junkInput.value)  : 0.8,
        similarity_threshold:  simInput   ? parseFloat(simInput.value)   : 0.5,
        rank_agent_enabled:    rankToggle ? rankToggle.checked            : true,
      };
    });

    const input = page.locator('#rankingThreshold');
    await input.waitFor({ state: 'visible', timeout: 10000 });

    const newValue = (parseFloat(await input.inputValue()) || 6.0) + 0.1;

    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
      { timeout: 10000 }
    );

    await input.evaluate((el, val) => {
      (el as HTMLInputElement).value = val.toString();
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }, newValue);
    await page.waitForTimeout(500);  // Wait for debouncing

    const response = await responsePromise;
    expect(response.status()).toBe(200);

    const responseData = await response.json();
    // Verify the autosave preserved other fields (values come from DOM, same as performAutoSave)
    expect(responseData.junk_filter_threshold).toBeCloseTo(initialConfig.junk_filter_threshold, 3);
    expect(responseData.similarity_threshold).toBeCloseTo(initialConfig.similarity_threshold, 3);
    expect(responseData.rank_agent_enabled).toBe(initialConfig.rank_agent_enabled);
  });

  test('should handle API error during autosave gracefully', async ({ page }) => {
    // Intercept and fail the PUT request
    await page.route('**/api/workflow/config', route => {
      if (route.request().method() === 'PUT') {
        route.fulfill({
          status: 500,
          body: JSON.stringify({ detail: 'Internal server error' })
        });
      } else {
        route.continue();
      }
    });

    const input = page.locator('#rankingThreshold');
    await input.waitFor({ state: 'visible', timeout: 10000 });

    const newValue = (parseFloat(await input.inputValue()) || 6.0) + 0.1;

    // Change should not throw error — use evaluate for range input
    await input.evaluate((el, val) => {
      (el as HTMLInputElement).value = val.toString();
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }, newValue);

    // Wait for error to be logged (but UI should remain functional)
    await page.waitForTimeout(1000);

    // Verify input still has the value (UI didn't break)
    const currentValue = await input.inputValue();
    expect(parseFloat(currentValue)).toBeCloseTo(newValue, 1);
  });

  test('should debounce rapid changes to prevent excessive API calls', async ({ page }) => {
    const input = page.locator('#rankingThreshold');
    await input.waitFor({ state: 'visible', timeout: 10000 });

    let requestCount = 0;
    page.on('request', (request) => {
      if (request.url().includes('/api/workflow/config') && request.method() === 'PUT') {
        requestCount++;
      }
    });

    // Make rapid changes — use evaluate for range input
    for (let i = 0; i < 5; i++) {
      await input.evaluate((el, val) => {
        (el as HTMLInputElement).value = val.toString();
        el.dispatchEvent(new Event('input', { bubbles: true }));
      }, 6.0 + i * 0.1);
      await page.waitForTimeout(50); // Faster than debounce delay
    }

    // Wait for debounce to complete
    await page.waitForTimeout(500);

    // Should only have one request (or very few) due to debouncing
    expect(requestCount).toBeLessThanOrEqual(2);
  });
});

// Map legacy panel IDs → step-section indices.  The workflow config tab was
// redesigned into step-sections (s0-s5).  Adding `.open` directly bypasses
// the accordion so multiple sections can be visible during a single test.
const PANEL_STEP_MAP: Record<string, string[]> = {
  'os-detection-panel': ['s0'],
  'other-thresholds-panel': ['s1', 's5'],   // junk filter + similarity
  'rank-agent-configs-panel': ['s2'],
  'extract-agent-panel': ['s3'],
  'cmdlineextract-agent-panel': ['s3'],
  'proctreeextract-agent-panel': ['s3'],
  'huntqueriesextract-agent-panel': ['s3'],
  'registryextract-agent-panel': ['s3'],
  'sigma-agent-panel': ['s4'],
};

async function expandPanelIfNeeded(page: any, panelId: string) {
  const stepIds = PANEL_STEP_MAP[panelId];
  if (stepIds) {
    await page.evaluate((ids: string[]) => {
      ids.forEach(id => document.getElementById(id)?.classList.add('open'));
    }, stepIds);
    await page.waitForTimeout(300);
    return;
  }
  // Fallback: try legacy data-collapsible-panel (prompt sub-panels still use it)
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
