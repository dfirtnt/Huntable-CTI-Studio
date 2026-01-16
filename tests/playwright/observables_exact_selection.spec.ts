import { test, expect } from '@playwright/test';

const BASE_URL = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const ARTICLE_ID = 658;

async function selectAndSaveObservable(page, phrase: string) {
  // Ensure Observables mode and plain surface is visible
  const observablesBtn = page.locator('#annotation-mode-observables');
  await expect(observablesBtn).toBeVisible();
  await observablesBtn.click();

  const plain = page.locator('#article-content-plain');
  await expect(plain).toBeVisible();

  // Ensure simpleTextManager is available
  await page.waitForFunction(() => (window as any).simpleTextManager);

  // Programmatically select the exact phrase inside the plain container
  await page.evaluate((targetPhrase) => {
    const plainEl = document.getElementById('article-content-plain');
    if (!plainEl) throw new Error('Plain article content not found');

    const text = plainEl.textContent || '';
    const idx = text.indexOf(targetPhrase);
    if (idx === -1) throw new Error(`Phrase not found: ${targetPhrase}`);

    const findNodeAtOffset = (root: Node, offset: number) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
      let pos = 0;
      let node: Node | null;
      while ((node = walker.nextNode())) {
        const len = (node.textContent || '').length;
        if (pos + len >= offset) {
          return { node, offset: offset - pos };
        }
        pos += len;
      }
      throw new Error('Offset outside text nodes');
    };

    const start = findNodeAtOffset(plainEl, idx);
    const end = findNodeAtOffset(plainEl, idx + targetPhrase.length);

    const range = document.createRange();
    range.setStart(start.node, start.offset);
    range.setEnd(end.node, end.offset);

    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);

    const mgr = (window as any).simpleTextManager;
    if (!mgr || typeof mgr.validateAndExtractObservableSelection !== 'function') {
      throw new Error('simpleTextManager not ready');
    }
    const validated = mgr.validateAndExtractObservableSelection();
    if (!validated) {
      throw new Error('Validation failed');
    }
    mgr.showObservableModal(validated.selectedText, validated.start, validated.end);
  }, phrase);

  // Save the observable
  const saveBtn = page.getByRole('button', { name: 'Save CMD' });
  await expect(saveBtn).toBeVisible();
  await saveBtn.click();
  await page.waitForTimeout(300);

  // Fetch annotations and assert selected_text matches exactly
  const resp = await page.request.get(`${BASE_URL}/api/articles/${ARTICLE_ID}/annotations`);
  expect(resp.ok()).toBeTruthy();
  const data = await resp.json();
  const annotations = data.annotations || [];
  const found = annotations.find((a: any) => a.selected_text === phrase);
  expect(found).toBeTruthy();
  expect(found.selected_text).toBe(phrase);
  expect(found.end_position - found.start_position).toBe(phrase.length);
}

test.describe('Observables exact selection (plain surface)', () => {
  test('selects and saves exact phrases without expansion', async ({ page }) => {
    await page.goto(`${BASE_URL}/articles/${ARTICLE_ID}`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);  // Wait for page to fully load

    await selectAndSaveObservable(page, 'Cloudflare page');
    await page.waitForTimeout(1000);  // Wait for first annotation to save
    await selectAndSaveObservable(page, 'After loading');
    await page.waitForTimeout(1000);  // Wait for second annotation to save
  });
});
