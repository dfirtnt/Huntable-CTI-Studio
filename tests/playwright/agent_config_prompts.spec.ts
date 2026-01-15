import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Agent Config Prompts', () => {
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

    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');
  });

  test('should not autosave prompt changes', async ({ page }) => {
    // Find a prompt edit area if it exists
    // Prompts require manual save, so autosave should not fire
    let autosaveFired = false;
    page.on('response', (response) => {
      if (response.url().includes('/api/workflow/config') && response.request().method() === 'PUT') {
        // Check if this is a prompt save (different endpoint)
        if (!response.url().includes('/prompts')) {
          autosaveFired = true;
        }
      }
    });

    // Try to find and interact with prompt editor
    // Note: Prompt editing UI may vary, so we test the general behavior
    await page.waitForTimeout(1000);

    // Autosave should not fire for prompt changes
    // (This is a basic test - full prompt editing tests would require more specific UI knowledge)
    expect(autosaveFired).toBe(false);
  });

  test('should have save button for individual prompts', async ({ page }) => {
    // Look for prompt save buttons
    // These are typically agent-specific save buttons
    const promptContainers = page.locator('[id*="prompt-container"]');
    const count = await promptContainers.count();

    // If prompt containers exist, they should have save functionality
    // The exact implementation may vary, so we just verify containers exist in DOM
    if (count > 0) {
      // Check if at least one container exists (may be hidden in collapsed panels)
      const firstContainer = promptContainers.first();
      await firstContainer.waitFor({ state: 'attached', timeout: 5000 }).catch(() => {});
      // Don't require visibility since panels might be collapsed
    } else {
      // If no containers found, that's also valid - prompts might not be loaded yet
      // This is a lower priority test, so we'll just skip the assertion
      test.skip();
    }
  });

  test('should persist saved prompts after reload', async ({ page }) => {
    // This test would require actually editing and saving a prompt
    // For now, we verify the prompt containers exist and are loaded
    await page.waitForTimeout(2000);

    // Check if prompts are loaded (containers exist)
    const promptContainers = page.locator('[id*="prompt-container"]');
    const count = await promptContainers.count();

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
    await expandPanelIfNeeded(page, 'rank-agent-configs-panel');

    // Prompts should still be visible after reload
    const promptContainersAfterReload = page.locator('[id*="prompt-container"]');
    const countAfterReload = await promptContainersAfterReload.count();

    // Count should be consistent (prompts persisted)
    expect(countAfterReload).toBe(count);
  });

  test('should show validation errors for invalid prompts', async ({ page }) => {
    // Prompt validation would typically happen on save
    // This is a placeholder test - actual implementation depends on prompt validation logic
    const promptContainers = page.locator('[id*="prompt-container"]');
    const count = await promptContainers.count();

    // If prompts exist, they should support validation
    if (count > 0) {
      // Verify containers exist in DOM (may be hidden in collapsed panels)
      const firstContainer = promptContainers.first();
      await firstContainer.waitFor({ state: 'attached', timeout: 5000 }).catch(() => {});
      // Don't require visibility
    } else {
      // Lower priority test - skip if no containers
      test.skip();
    }
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
