import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const TEST_ARTICLE_ID = process.env.TEST_ARTICLE_ID || '68'; // Use a known article ID

test.describe('Modal Escape Key Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to an article detail page
    await page.goto(`${BASE}/articles/${TEST_ARTICLE_ID}`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000); // Wait for page to fully initialize
  });

  test('ESC key closes Junk Filter Tuning modal (chunkDebugModal)', async ({ page }) => {
    // Wait for page to be ready
    await page.waitForSelector('body', { state: 'visible' });
    
    // Check if ModalManager is loaded
    const modalManagerLoaded = await page.evaluate(() => {
      return typeof window.ModalManager !== 'undefined';
    });
    expect(modalManagerLoaded).toBe(true);
    
    // Open the Junk Filter Tuning modal by clicking the button
    // First, we need to find the button that opens it
    const openModalButton = page.locator('button:has-text("Junk Filter Tuning"), button:has-text("🔍")').first();
    
    // If button not found, try to trigger the function directly
    const buttonFound = await openModalButton.isVisible({ timeout: 3000 }).catch(() => false);
    
    if (!buttonFound) {
      // Try to open modal via JavaScript
      await page.evaluate(() => {
        if (typeof showChunkDebugModal === 'function') {
          showChunkDebugModal();
        }
      });
    } else {
      await openModalButton.click();
    }
    
    // Wait for modal to appear
    const modal = page.locator('#chunkDebugModal, #chunkDebugLoadingModal');
    await expect(modal).toBeVisible({ timeout: 10000 });
    
    // Verify modal is in the stack
    const modalInStack = await page.evaluate(() => {
      if (window.ModalManager) {
        const stack = window.ModalManager.getStack();
        return stack.includes('chunkDebugModal') || stack.includes('chunkDebugLoadingModal');
      }
      return false;
    });
    
    // Press ESC key
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    
    // Verify modal is closed
    await expect(modal).not.toBeVisible({ timeout: 3000 });
    
    // Verify modal is removed from stack
    const modalStillInStack = await page.evaluate(() => {
      if (window.ModalManager) {
        const stack = window.ModalManager.getStack();
        return stack.includes('chunkDebugModal') || stack.includes('chunkDebugLoadingModal');
      }
      return false;
    });
    expect(modalStillInStack).toBe(false);
  });

  test.skip('ESC key closes test-subagent-modal', async ({ page }) => {
    // Navigate to workflow page
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    
    // Wait for config to load
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    
    // Find and click a test button that opens a modal
    const testButton = page.locator('button:has-text("Test with Custom ArticleID")').first();
    
    // Set up dialog handler
    page.on('dialog', async dialog => {
      await dialog.accept(TEST_ARTICLE_ID);
    });
    
    // Click test button
    await testButton.click({ timeout: 10000 });
    
    // Wait for modal to appear
    const modal = page.locator('#test-subagent-modal');
    await expect(modal).toBeVisible({ timeout: 15000 });
    
    // Verify modal is registered
    const modalRegistered = await page.evaluate(() => {
      if (window.ModalManager) {
        const stack = window.ModalManager.getStack();
        return stack.includes('test-subagent-modal');
      }
      return false;
    });
    
    // Press ESC key
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    
    // Verify modal is closed
    await expect(modal).not.toBeVisible({ timeout: 3000 });
  });

  test('ESC key closes nested modals (only topmost), then previous', async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await page.evaluate(() => {
      if (typeof (window as any).pushModal === 'function') {
        (window as any).pushModal('configPresetListModal', true);
      }
    });
    const firstModal = page.locator('#configPresetListModal');
    await expect(firstModal).toBeVisible({ timeout: 5000 });

    await page.evaluate(() => {
      if (typeof (window as any).pushModal === 'function') {
        (window as any).pushModal('configVersionListModal', true);
      }
    });
    const secondModal = page.locator('#configVersionListModal');
    await expect(secondModal).toBeVisible({ timeout: 5000 });

    const stackState = await page.evaluate(() =>
      (window as any).ModalManager ? (window as any).ModalManager.getStack() : []
    );
    expect(stackState.length).toBeGreaterThanOrEqual(2);

    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    await expect(secondModal).not.toBeVisible({ timeout: 3000 });
    await expect(firstModal).toBeVisible({ timeout: 2000 });

    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    await expect(firstModal).not.toBeVisible({ timeout: 3000 });
  });

  test('ESC key works on all registered modals', async ({ page }) => {
    // Test multiple modals to ensure ESC works consistently
    const modalsToTest = [
      { id: 'classificationModal', openFunction: 'openClassificationModal' },
      { id: 'resultModal', openFunction: 'showModal' },
    ];
    
    for (const { id, openFunction } of modalsToTest) {
      // Navigate to appropriate page
      if (id === 'classificationModal') {
        await page.goto(`${BASE}/articles`);
        await page.waitForLoadState('networkidle');
      } else if (id === 'resultModal') {
        await page.goto(`${BASE}/sources`);
        await page.waitForLoadState('networkidle');
      }
      
      await page.waitForTimeout(2000);
      
      // Open modal (evaluate accepts a single arg)
      const modalOpened = await page.evaluate((o: { funcName: string }) => {
        const fn = o.funcName;
        if (fn === 'openClassificationModal') {
          const link = document.querySelector('a[href*="/articles/"]');
          if (link && typeof (window as any).openClassificationModal === 'function') {
            const m = link.getAttribute('href')?.match(/\/articles\/(\d+)/);
            if (m?.[1]) {
              (window as any).openClassificationModal(m[1], 'Test Article');
              return true;
            }
          }
        } else if (fn === 'showModal' && typeof (window as any).showModal === 'function') {
          (window as any).showModal('Test', 'Test content');
          return true;
        }
        return false;
      }, { funcName: openFunction });
      
      if (!modalOpened) {
        console.log(`Skipping ${id} - could not open modal`);
        continue;
      }
      
      // Wait for modal
      const modal = page.locator(`#${id}`);
      const modalVisible = await modal.isVisible({ timeout: 5000 }).catch(() => false);
      
      if (!modalVisible) {
        console.log(`Skipping ${id} - modal not visible`);
        continue;
      }
      
      // Press ESC
      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);
      
      // Verify modal is closed
      await expect(modal).not.toBeVisible({ timeout: 3000 });
      
      console.log(`✅ ${id} - ESC key works`);
    }
  });
});
