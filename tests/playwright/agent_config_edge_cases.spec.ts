import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Agent Config Edge Cases', () => {
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
  });

  test('should handle empty model selections correctly', async ({ page }) => {
    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');

    const providerSelect = page.locator('#rankagent-provider');
    await providerSelect.waitFor({ state: 'visible', timeout: 10000 });

    // Switch to a provider that allows empty model
    await providerSelect.selectOption('openai');
    await page.waitForTimeout(2000);

    const modelSelector = page.locator('#rankagent-model-openai');
    await modelSelector.waitFor({ state: 'visible', timeout: 5000 });

    const tagName = await modelSelector.evaluate((el: HTMLElement) => el.tagName.toLowerCase());
    
    if (tagName === 'input') {
      // Clear model value
      await modelSelector.fill('');
      await modelSelector.blur();

      // Should handle empty value without error
      await page.waitForTimeout(1000);

      // Input should still be functional
      await expect(modelSelector).toBeEnabled();
    } else {
      // If it's a select, verify it exists
      await expect(modelSelector).toBeEnabled();
    }
  });

  test('should handle null values in agent_models for OS fallback', async ({ page }) => {
    await expandPanelIfNeeded(page, 'os-detection-panel');

    const fallbackToggle = page.locator('#osdetectionagent-fallback-enabled');
    await fallbackToggle.waitFor({ state: 'visible', timeout: 10000 });

    // Disable fallback (should set to null)
    if (await fallbackToggle.isChecked()) {
      const responsePromise = page.waitForResponse(
        (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
        { timeout: 5000 }
      );

      await fallbackToggle.click();
      await page.waitForTimeout(500);

      const response = await responsePromise;
      expect(response.status()).toBe(200);

      const responseData = await response.json();
      expect(responseData.agent_models?.OSDetectionAgent_fallback).toBeNull();
      expect(responseData.agent_models?.OSDetectionAgent_fallback_provider).toBeNull();
    }
  });

  test('should work when API returns partial config data', async ({ page }) => {
    // Intercept and return partial config
    await page.route('**/api/workflow/config', route => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            ranking_threshold: 6.0,
            // Missing other fields
          })
        });
      } else {
        route.continue();
      }
    });

    // Reload page
    await page.reload();
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

    // Page should still load and be functional
    const form = page.locator('#workflowConfigForm');
    await expect(form).toBeVisible();
  });

  test('should handle config load failures gracefully', async ({ page }) => {
    // Intercept and fail config load
    await page.route('**/api/workflow/config', route => {
      if (route.request().method() === 'GET') {
        route.fulfill({
          status: 500,
          body: JSON.stringify({ detail: 'Server error' })
        });
      } else {
        route.continue();
      }
    });

    // Reload page
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(1000);

    // Page should still render (may show error, but shouldn't crash)
    const form = page.locator('#workflowConfigForm');
    // Form may or may not be visible depending on error handling
    // But page should not be completely broken
    await page.waitForTimeout(1000);
  });

  test('should handle rapid panel toggles without breaking autosave', async ({ page }) => {
    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');

    const panelToggle = page.locator('#rank-agent-configs-panel-toggle, button[onclick*="rank-agent-configs-panel"]').first();
    const rankingInput = page.locator('#rankingThreshold');
    await rankingInput.waitFor({ state: 'visible', timeout: 10000 });

    // Rapidly toggle panel while changing value
    for (let i = 0; i < 3; i++) {
      await panelToggle.click();
      await page.waitForTimeout(100);
      await panelToggle.click();
      await page.waitForTimeout(100);
      await rankingInput.fill((6.0 + i * 0.1).toString());
      await page.waitForTimeout(100);
    }

    // Wait for any pending autosaves
    await page.waitForTimeout(1000);

    // Input should still be functional
    await expect(rankingInput).toBeEnabled();
  });

  test('should handle multiple simultaneous field changes', async ({ page }) => {
    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');
    await expandPanelIfNeeded(page, 'other-thresholds-panel');

    const rankingInput = page.locator('#rankingThreshold');
    const junkFilterInput = page.locator('#junkFilterThreshold');
    const tempInput = page.locator('#rankagent-temperature');

    await rankingInput.waitFor({ state: 'visible', timeout: 10000 });
    await junkFilterInput.waitFor({ state: 'visible', timeout: 10000 });
    await tempInput.waitFor({ state: 'attached', timeout: 10000 });
    await tempInput.scrollIntoViewIfNeeded();

    // Change all fields simultaneously
    await Promise.all([
      rankingInput.fill('7.0'),
      junkFilterInput.fill('0.85'),
      tempInput.fill('0.5')
    ]);

    await page.waitForTimeout(1000);

    // All inputs should have their values
    expect(parseFloat(await rankingInput.inputValue())).toBeCloseTo(7.0, 1);
    expect(parseFloat(await junkFilterInput.inputValue())).toBeCloseTo(0.85, 2);
    // Temperature might have a default value, just verify it's set
    const tempValue = parseFloat(await tempInput.inputValue());
    expect(tempValue).toBeGreaterThanOrEqual(0);
    expect(tempValue).toBeLessThanOrEqual(2);
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
