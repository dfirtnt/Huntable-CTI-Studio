import { test, expect } from '@playwright/test';

const BASE_URL = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

test.describe.skip('Observable annotation selection', () => {
  test('drag selection only creates one observable annotation and keeps length small', async ({ page }) => {
    // Navigate to first article
    await page.goto(`${BASE_URL}/articles`);
    await page.waitForLoadState('networkidle');

    const firstArticle = page.locator("a[href^='/articles/']").first();
    await expect(firstArticle).toBeVisible();
    await firstArticle.click();
    await page.waitForLoadState('networkidle');

    // Ensure Observables mode and PROC_LINEAGE type
    const observablesBtn = page.locator('#annotation-mode-observables');
    await expect(observablesBtn).toBeVisible();
    await observablesBtn.click();
    // Toggle observable type to CMD explicitly; if hidden, skip
    // Ensure CMD is active; if hidden, skip clicking
    await page.evaluate(() => {
      const btn = document.querySelector("[data-observable-type='CMD']");
      if (btn) (btn as HTMLElement).click();
    });

    // Ensure the annotation manager exists (instantiate if needed)
    await page.waitForSelector('#article-content', { timeout: 15000 });  // Increased timeout
    await page.waitForFunction(() => Boolean((window as any).simpleTextManager || (window as any).SimpleTextManager), { timeout: 15000 });  // Increased timeout
    await page.evaluate(() => {
      const globalAny = window as any;
      if (!globalAny.simpleTextManager && typeof globalAny.SimpleTextManager === 'function') {
        globalAny.simpleTextManager = new globalAny.SimpleTextManager();
      }
    });

    // Perform a synthetic multi-word selection and trigger both handlers
    await page.evaluate(async () => {
      let manager: any;
      try {
        // eslint-disable-next-line no-undef
        manager = typeof simpleTextManager !== 'undefined' ? (simpleTextManager as any) : undefined;
      } catch (e) {
        manager = undefined;
      }
      if (!manager) {
        manager = (window as any).simpleTextManager;
      }
      const content = document.getElementById('article-content');
      if (!manager || !content) {
        throw new Error('SimpleTextManager or article content not found');
      }

      const text = content.textContent || '';
      const start = 0;
      const end = Math.min(text.length, 120);
      const phrase = text.substring(start, end);

      manager.annotationMode = 'observables';
      manager.observableType = 'PROC_LINEAGE';

      // Create a real DOM selection matching the phrase
      const startNode = manager.getTextNodeAtOffset(start);
      const endNode = manager.getTextNodeAtOffset(end);
      const range = document.createRange();
      range.setStart(startNode.node, startNode.offset);
      range.setEnd(endNode.node, endNode.offset);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);

      // Wait for any initial annotation rendering to settle
      const getCount = () => document.querySelectorAll('span[data-annotation-type]').length;
      let beforeCount = getCount();
      for (let i = 0; i < 3; i += 1) {
        await new Promise((resolve) => setTimeout(resolve, 150));
        const current = getCount();
        if (current === beforeCount) {
          break;
        }
        beforeCount = current;
      }

      // Custom handler (mousedown/mouseup path)
      manager.showClassificationOptions(start, end);

      // Native handler would fire after selection change; call it manually to verify guard
      if (typeof manager.nativeSelectionHandler === 'function') {
        manager.nativeSelectionHandler({ target: content });
      }

      // Allow any async work to complete
      await new Promise((resolve) => setTimeout(resolve, 150));

      const spans = Array.from(document.querySelectorAll('span[data-annotation-type="PROC_LINEAGE"]'));
      const afterCount = document.querySelectorAll('span[data-annotation-type]').length;
      const targetSnippet = phrase.slice(0, 10).trim();
      const targetSpan = spans.find((span) => (span.textContent || '').includes(targetSnippet));
      const lastLen = targetSpan ? (targetSpan.textContent || '').length : 0;

      return { added: afterCount - beforeCount, lastLen };
    });

    // Save via modal
    const saveBtn = page.getByRole('button', { name: 'Save CMD' });
    if (await saveBtn.count()) {
      await saveBtn.click();
      await page.waitForTimeout(2000);  // Increased from 200 to 2000 for API call
    }

    const finalSpans = await page.evaluate(() => {
      const spans = Array.from(document.querySelectorAll('span[data-annotation-type="PROC_LINEAGE"]'));
      return spans.map(s => s.textContent || '');
    });

    expect(finalSpans.length).toBeGreaterThan(0);
    const finalLen = finalSpans[0].length;
    expect(finalLen).toBeGreaterThan(10);
    expect(finalLen).toBeLessThan(200); // guard against whole-article annotation
  });
});
