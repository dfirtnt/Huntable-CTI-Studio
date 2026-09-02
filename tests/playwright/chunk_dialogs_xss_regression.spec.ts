import { test, expect, type APIRequestContext } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

/**
 * Regression test for stored DOM-XSS in the article-detail chunk dialogs.
 *
 * Bug: article_detail.html builds two modals by string-interpolating raw
 * article-derived chunk text into an HTML string that is then written to the
 * DOM, WITHOUT escaping:
 *
 *   - showRemovedChunksDialog (~L5500): `${chunk.text.replace(/\n/g, '<br>')}`
 *     assigned via `modal.innerHTML`. Auto-opens after a filtered GPT4o
 *     ranking run. `chunk.text` is a verbatim slice of articles.content.
 *   - displayFeedbackComparisonModal (~L10033/10034): `title="${c.chunk_text}"`
 *     (attribute context) and `${c.chunk_text}` (body context), inserted via
 *     `document.body.insertAdjacentHTML`.
 *
 * Scraped CTI posts routinely carry literal markup (e.g. `<img src=x
 * onerror=...>` decoded out of a code block during ingestion). Unescaped, that
 * markup becomes live DOM nodes when either dialog opens -- stored XSS.
 *
 * Both renderers are global functions on article_detail.html's inline script,
 * so the test drives them directly with a poisoned payload -- no billed GPT4o
 * call, no dependence on stored data, only a real article page to host them.
 *
 * Fix: route every chunk-text interpolation through the shared global
 * escapeHtml() (src/web/static/js/utils.js), which escapes & < > " '. For the
 * removed-chunks dialog the escape happens BEFORE `\n -> <br>` so intended line
 * breaks survive while attacker markup does not.
 */

const XSS_MARKER = 'onerror';
// Angle brackets, an attribute-breakout quote, and an event handler in one
// string, so a single payload exercises the body sink and the title= attribute
// sink at once.
const PAYLOAD = '"><img src=x onerror="window.__chunkXss=1"><svg onload="window.__chunkXss=1">line-a\nline-b';

async function firstArticleId(request: APIRequestContext): Promise<number | null> {
  const override = process.env.XSS_ARTICLE_ID;
  if (override) return Number(override);
  const resp = await request.get(`${BASE}/api/articles?limit=1`);
  if (!resp.ok()) return null;
  const body = await resp.json();
  const article = (body?.articles ?? [])[0];
  return typeof article?.id === 'number' ? article.id : null;
}

test.describe('Article chunk-dialog XSS regression', () => {
  let articleId: number | null = null;

  test.beforeEach(async ({ request, page }) => {
    articleId = await firstArticleId(request);
    test.skip(articleId === null, 'No article available to host the dialog functions.');
    await page.goto(`${BASE}/articles/${articleId}`);
    await page.waitForLoadState('domcontentloaded');
    // The dialog renderers and escapeHtml must be reachable as globals.
    const ready = await page.evaluate(() =>
      typeof (window as any).showRemovedChunksDialog === 'function' &&
      typeof (window as any).displayFeedbackComparisonModal === 'function' &&
      typeof (window as any).escapeHtml === 'function',
    );
    expect(ready, 'showRemovedChunksDialog/displayFeedbackComparisonModal/escapeHtml must be global').toBe(true);
  });

  test('[CHUNK-XSS-001] removed-chunks dialog renders chunk text as inert, escaped text', async ({ page }) => {
    const result = await page.evaluate((payload) => {
      (window as any).__chunkXss = undefined;
      (window as any).showRemovedChunksDialog({
        chunks_removed: 1,
        reduction_percent: 10,
        original_length: 100,
        filtered_length: 90,
        removed_chunks: [
          { chunk_id: 'x1', text: payload, reason: 'test', confidence: 0.5 },
        ],
      });
      const modal = document.querySelector('[aria-label="Removed chunks"]');
      if (!modal) return null;
      return {
        // These modals contain zero legitimate <img>, so any is payload markup
        // parsed as HTML. (svg / onclick are excluded: the dialog chrome uses
        // both legitimately, so they cannot signal injection.)
        injectedImages: modal.querySelectorAll('img').length,
        // onerror/onload never appear on legitimate dialog chrome (only onclick).
        payloadHandlerNodes: Array.from(modal.querySelectorAll('*')).filter(
          (node) => node.hasAttribute('onerror') || node.hasAttribute('onload'),
        ).length,
        text: (modal as HTMLElement).innerText,
        // Line-break preservation must survive escaping: escape first, THEN \n -> <br>.
        brCount: modal.querySelectorAll('br').length,
      };
    }, PAYLOAD);

    expect(result).not.toBeNull();
    expect(result!.injectedImages).toBe(0);
    expect(result!.payloadHandlerNodes).toBe(0);
    // The markup must be visible as text -- proof it was escaped, not stripped.
    expect(result!.text).toContain(XSS_MARKER);
    // \n between line-a and line-b must still become a <br>.
    expect(result!.brCount).toBeGreaterThan(0);
    // Give any injected onerror/onload a chance to fire, then confirm it did not.
    await page.waitForTimeout(150);
    const fired = await page.evaluate(() => (window as any).__chunkXss === 1);
    expect(fired).toBe(false);
  });

  test('[CHUNK-XSS-002] feedback-comparison modal escapes chunk text in body and title attribute', async ({ page }) => {
    const result = await page.evaluate((payload) => {
      (window as any).__chunkXss = undefined;
      const TEST_ID = 987654;
      (window as any).chunkDebugData = { article_id: TEST_ID };
      (window as any).displayFeedbackComparisonModal({
        model_version: 'vTest',
        previous_model_version: 'vPrev',
        comparison_period: 'now',
        feedback_comparisons: [
          {
            article_id: TEST_ID,
            chunk_text: payload,
            old_huntable_probability: 0.1,
            new_huntable_probability: 0.2,
            huntable_probability_change: 0.1,
            old_classification: 'a',
            new_classification: 'b',
            is_correct: true,
            user_classification: 'huntable',
          },
        ],
      });
      const modal = document.getElementById('feedbackComparisonModal');
      if (!modal) return null;
      const titled = modal.querySelector('.max-w-xs');
      return {
        // No legitimate <img> in this modal; any is body- or attribute-sink
        // markup parsed as HTML. onerror/onload never appear on its chrome.
        injectedImages: modal.querySelectorAll('img').length,
        payloadHandlerNodes: Array.from(modal.querySelectorAll('*')).filter(
          (node) => node.hasAttribute('onerror') || node.hasAttribute('onload'),
        ).length,
        // Read back the attribute: escaping stores the literal payload string.
        title: titled ? titled.getAttribute('title') : null,
        text: (modal as HTMLElement).innerText,
      };
    }, PAYLOAD);

    expect(result).not.toBeNull();
    expect(result!.injectedImages).toBe(0);
    expect(result!.payloadHandlerNodes).toBe(0);
    // The title attribute must hold the payload verbatim, not a broken-out tag.
    expect(result!.title).toBe(PAYLOAD);
    expect(result!.text).toContain(XSS_MARKER);
    await page.waitForTimeout(150);
    const fired = await page.evaluate(() => (window as any).__chunkXss === 1);
    expect(fired).toBe(false);
  });
});
