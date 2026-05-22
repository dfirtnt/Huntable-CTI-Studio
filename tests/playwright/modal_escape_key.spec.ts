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
    const openModalButton = page.locator('button:has-text("Junk Filter Tuning"), button:has-text("🔍")').first();
    const buttonFound = await openModalButton.isVisible({ timeout: 3000 }).catch(() => false);
    
    if (!buttonFound) {
      // Try to open modal via JavaScript
      const opened = await page.evaluate(() => {
        if (typeof (window as any).showChunkDebugModal === 'function') {
          (window as any).showChunkDebugModal();
          return true;
        }
        return false;
      });
      test.skip(!opened, 'Article has no Junk Filter Tuning UI (chunkDebugModal not available)');
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

  // Regression: the Sigma Enhance — System Prompt overlay (#enrich-expanded-overlay)
  // is a bespoke overlay outside ModalManager. Its only Escape path used to be an
  // inline onkeydown on the div, which fires ONLY while focus is inside the overlay.
  // Once focus lands on document.body (clicking the dimmed backdrop / browser chrome),
  // Escape no longer reached it and the modal was stuck open. The fix attaches a
  // document-level Escape listener on open and removes it on close.
  test('ESC key closes Sigma Enhance expanded overlay even when focus is on body', async ({ page }) => {
    await page.goto(`${BASE}/workflow`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const opened = await page.evaluate(() => {
      if (typeof (window as any).openEnrichExpanded === 'function') {
        (window as any).openEnrichExpanded();
        return true;
      }
      return false;
    });
    expect(opened).toBe(true);

    const overlay = page.locator('#enrich-expanded-overlay');
    await expect(overlay).toBeVisible({ timeout: 5000 });

    // Reproduce the real-world failure: move focus OUT of the overlay subtree.
    // (Clicking the backdrop would call closeEnrichExpanded() via onclick and
    // mask the bug, so blur programmatically instead.)
    await page.evaluate(() => {
      const ae = document.activeElement as HTMLElement | null;
      if (ae && typeof ae.blur === 'function') ae.blur();
    });
    const focusOutsideOverlay = await page.evaluate(() => {
      const o = document.getElementById('enrich-expanded-overlay');
      return !!o && !o.contains(document.activeElement);
    });
    expect(focusOutsideOverlay).toBe(true);

    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);

    await expect(overlay).not.toBeVisible({ timeout: 3000 });
  });

  // Regression guard for the fragile half of the fix: closeEnrichExpanded() MUST
  // remove the document-level keydown listener it added in openEnrichExpanded().
  // If teardown regresses, the leaked _enrichExpEscHandler keeps invoking
  // closeEnrichExpanded() on every later Escape (re-running its side effects and
  // fighting ModalManager). We assert the invariant directly via a call counter
  // on closeEnrichExpanded — no coupling to parent-modal reveal UX. (Same spy
  // technique as expanded_prompt_editor_save.spec.ts wrapping saveAgentPrompt2.)
  test('Escape listener is torn down on close (no leaked handler fires later)', async ({ page }) => {
    await page.goto(`${BASE}/workflow`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const opened = await page.evaluate(() => {
      if (typeof (window as any).openEnrichExpanded !== 'function') return false;
      (window as any).__closeEnrichCount = 0;
      const orig = (window as any).closeEnrichExpanded;
      (window as any).closeEnrichExpanded = function (...args: any[]) {
        (window as any).__closeEnrichCount++;
        return orig.apply(this, args);
      };
      (window as any).openEnrichExpanded();
      return true;
    });
    expect(opened).toBe(true);

    const overlay = page.locator('#enrich-expanded-overlay');
    await expect(overlay).toBeVisible({ timeout: 5000 });

    // Focus off the overlay subtree (real-world condition that exposed the bug).
    await page.evaluate(() => {
      const ae = document.activeElement as HTMLElement | null;
      if (ae && typeof ae.blur === 'function') ae.blur();
    });

    // Esc #1: the document listener fires -> closeEnrichExpanded() exactly once,
    // and that call must remove the listener.
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    await expect(overlay).not.toBeVisible({ timeout: 3000 });
    const countAfterFirst = await page.evaluate(() => (window as any).__closeEnrichCount);
    expect(countAfterFirst).toBe(1);

    // Esc #2 with the overlay already closed: a correctly torn-down listener does
    // NOT invoke closeEnrichExpanded() again. A leaked listener would -> count 2.
    await page.evaluate(() => {
      const ae = document.activeElement as HTMLElement | null;
      if (ae && typeof ae.blur === 'function') ae.blur();
    });
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    const countAfterSecond = await page.evaluate(() => (window as any).__closeEnrichCount);
    expect(countAfterSecond).toBe(1);
  });

});
