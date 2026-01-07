import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

async function selectPhrase(page, phrase: string) {
  // remove any existing annotation spans to avoid collisions
  await page.evaluate(() => {
    document.querySelectorAll('span[data-annotation-type]').forEach((s) => s.remove());
  });

  const result = await page.evaluate((p) => {
    const el = document.getElementById('article-content-plain');
    if (!el) return { error: 'plain container missing' };
    const text = el.textContent || '';
    const idx = text.indexOf(p);
    if (idx === -1) return { error: `phrase not found: ${p}` };
    const end = idx + p.length;

    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, null, false);
    let pos = 0;
    let startNode: Node | null = null;
    let endNode: Node | null = null;
    let startOffset = 0;
    let endOffset = 0;

    while (walker.nextNode()) {
      const n = walker.currentNode as Text;
      const len = n.textContent.length;
      if (!startNode && pos + len >= idx) {
        startNode = n;
        startOffset = idx - pos;
      }
      if (!endNode && pos + len >= end) {
        endNode = n;
        endOffset = end - pos;
        break;
      }
      pos += len;
    }

    if (!startNode || !endNode) return { error: 'range nodes not found' };

    const range = document.createRange();
    range.setStart(startNode, startOffset);
    range.setEnd(endNode, endOffset);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    const manager = (window as any).simpleTextManager;
    if (manager && typeof manager.showObservableModal === 'function') {
      manager.showObservableModal(p, idx, end);
      return { ok: true };
    }
    return { error: 'manager not ready' };
  }, phrase);

  if (result.error) throw new Error(result.error);

  await expect(page.getByRole('button', { name: 'Save CMD' })).toBeVisible();
  await page.getByRole('button', { name: 'Save CMD' }).click();
}

test.describe('Observables plain selection', () => {
  test('saves exact highlighted text on article 658', async ({ page }) => {
    await page.goto(`${BASE}/articles/658`);
    await page.waitForLoadState('networkidle');
    await page.getByRole('button', { name: 'Observables Mode' }).click();
    await page.waitForSelector('#article-content-plain', { state: 'visible' });
    await page.waitForFunction(() => Boolean((window as any).SimpleTextManager || (window as any).simpleTextManager));
    await page.evaluate(() => {
      const w = window as any;
      if (!w.simpleTextManager && typeof w.SimpleTextManager === 'function') {
        w.simpleTextManager = new w.SimpleTextManager();
      }
    });

    const phrases = ['Cloudflare verification prompt', 'After the device restarts'];
    for (const phrase of phrases) {
      await selectPhrase(page, phrase);
      const resp = await page.request.get(`${BASE}/api/articles/658/annotations`);
      expect(resp.ok()).toBeTruthy();
      const data = await resp.json();
      const match = (data.annotations || []).find((a: any) => a.selected_text === phrase);
      expect(match).toBeTruthy();
      expect(match.selected_text).toBe(phrase);
      expect(match.end_position - match.start_position).toBe(phrase.length);
    }
  });
});
