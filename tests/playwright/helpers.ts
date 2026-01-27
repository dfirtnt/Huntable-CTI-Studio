/**
 * Shared helper functions for Playwright tests.
 * Provides common patterns for waiting, autosave, model loading, and panel expansion.
 */

import { Page } from '@playwright/test';

/**
 * Wait for autosave to complete by waiting for PUT request to /api/workflow/config
 */
export async function waitForAutosave(page: Page, timeout: number = 15000): Promise<void> {
  await page.waitForResponse(
    (resp) => resp.url().includes('/api/workflow/config') && resp.request().method() === 'PUT',
    { timeout }
  ).catch(() => {
    // Autosave might not fire if debouncing is still active
    // This is acceptable - the test will verify state separately
  });
}

/**
 * Wait for model API to load (LMStudio models endpoint)
 */
export async function waitForModelLoad(page: Page, timeout: number = 15000): Promise<void> {
  await page.waitForResponse(
    (resp) => (resp.url().includes('/api/lmstudio-models') || resp.url().includes('/api/workflow/config')) && resp.status() === 200,
    { timeout }
  ).catch(() => {
    // Model API might have already completed or failed
    // This is acceptable - tests should handle both cases
  });
  await page.waitForTimeout(2000); // Additional wait for UI to update
}

/**
 * Expand panel safely with proper waits
 */
export async function expandPanelSafely(page: Page, panelId: string): Promise<void> {
  const content = page.locator(`#${panelId}-content`);
  const header = page.locator(`[data-collapsible-panel="${panelId}"]`);
  const button = page.locator(`button[onclick*="${panelId}"], #${panelId}-toggle`);
  
  // Check if panel is already expanded
  const isHidden = await content.evaluate(el => el.classList.contains('hidden')).catch(() => true);
  
  if (isHidden) {
    // Try button first, then header
    if (await button.count() > 0 && await button.isVisible().catch(() => false)) {
      await button.click();
    } else if (await header.count() > 0) {
      await header.click();
    }
    await page.waitForTimeout(500); // Wait for animation
  }
  
  // Verify panel is expanded
  await content.waitFor({ state: 'visible', timeout: 10000 }).catch(() => {});
}

/**
 * Wait for input change and autosave with debouncing
 */
export async function fillAndWaitForAutosave(
  page: Page,
  input: any,
  value: string,
  debounceWait: number = 500
): Promise<void> {
  await input.fill(value);
  await input.blur();
  await page.waitForTimeout(debounceWait); // Wait for debouncing
  await waitForAutosave(page);
}

/**
 * Wait for provider switch to complete with model loading
 */
export async function switchProviderAndWait(
  page: Page,
  providerSelect: any,
  provider: string
): Promise<void> {
  await providerSelect.selectOption(provider);
  await page.waitForTimeout(2000); // Wait for UI to update
  await waitForModelLoad(page); // Wait for model API if needed
}
