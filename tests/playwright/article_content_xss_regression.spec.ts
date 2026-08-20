import { test, expect, type APIRequestContext } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

/**
 * Regression test for stored XSS in the server-rendered article body.
 *
 * Bug: article_detail.html renders
 * `{{ article.content|highlight_keywords(...)|safe }}`. The filter
 * (src/web/utils/jinja_filters.py) short-circuited on the literal substring
 * `<span class=` in the stored article text and returned that text VERBATIM
 * into the |safe expression, so the entire article body reached the DOM
 * unescaped. It did the same whenever keyword metadata was absent. Scraped CTI
 * posts routinely contain that substring -- HTML written as `&lt;span
 * class="x"&gt;` inside a code block is entity-decoded during ingestion and
 * lands in articles.content as literal `<span class=`. At the time of the fix,
 * 21 stored articles matched, 5 of which also carried raw <img>/<script> tags.
 *
 * Fix: removed both raw early returns so every input flows through
 * render_highlighted_content, which html-escapes each non-match segment and
 * emits only its own generated highlight markup.
 *
 * Unlike annotation_xss_regression.spec.ts, this escaping happens server-side
 * in Python, so it cannot be exercised by loading a JS file on about:blank --
 * the assertions have to run against a real rendered page. The spec therefore
 * locates an article that actually carries the trigger substring and skips
 * cleanly when the database has none (a fresh install, for example).
 */

// Articles known to carry the trigger when this was filed. Treated only as
// hints: the content is re-verified through the API before a page is asserted
// on, and the scan below takes over if these rows are gone.
const CANDIDATE_HINTS = [2095, 2097, 2099, 2101, 2226];
const TRIGGER = '<span class=';
const SCAN_LIMIT = 200;

interface Candidate {
  id: number;
  content: string;
}

async function findTriggerArticle(request: APIRequestContext): Promise<Candidate | null> {
  const override = process.env.XSS_ARTICLE_ID;
  const hints = override ? [Number(override), ...CANDIDATE_HINTS] : CANDIDATE_HINTS;

  for (const id of hints) {
    const resp = await request.get(`${BASE}/api/articles/${id}`);
    if (!resp.ok()) continue;
    const body = await resp.json();
    const content: string = body?.content ?? '';
    if (content.includes(TRIGGER)) return { id, content };
  }

  // Hinted rows are gone -- fall back to a bounded scan rather than skipping.
  const listResp = await request.get(`${BASE}/api/articles?limit=${SCAN_LIMIT}`);
  if (!listResp.ok()) return null;
  const list = await listResp.json();
  for (const article of list?.articles ?? []) {
    if (typeof article?.content === 'string' && article.content.includes(TRIGGER)) {
      return { id: article.id, content: article.content };
    }
  }
  return null;
}

/** Slice the article-content div out of the raw HTML response.
 *  Safe because the div's contents are escaped text plus generated highlight
 *  spans -- there are no nested divs to confuse the first closing tag. If the
 *  bug regressed, raw article markup could contain a </div>, which would only
 *  make this slice SHORTER, never hide an unescaped tag before it. */
function sliceArticleContent(html: string): string {
  const start = html.indexOf('id="article-content"');
  if (start === -1) return '';
  const open = html.indexOf('>', start);
  const close = html.indexOf('</div>', open);
  return html.slice(open + 1, close === -1 ? undefined : close);
}

test.describe('Article content XSS regression', () => {
  let candidate: Candidate | null = null;

  test.beforeEach(async ({ request }) => {
    candidate = await findTriggerArticle(request);
    test.skip(!candidate, `No stored article contains "${TRIGGER}"; nothing to regress against.`);
  });

  test('[ART-XSS-001] stored markup renders as inert text, not live DOM nodes', async ({ page }) => {
    await page.goto(`${BASE}/articles/${candidate!.id}`);
    await page.waitForLoadState('domcontentloaded');

    const result = await page.evaluate(() => {
      const el = document.getElementById('article-content');
      if (!el) return null;
      return {
        liveTags: el.querySelectorAll('img, script, iframe, svg, object, embed').length,
        eventHandlerNodes: Array.from(el.querySelectorAll('*')).filter((node) =>
          Array.from(node.attributes).some((attr) => attr.name.toLowerCase().startsWith('on')),
        ).length,
        // The renderer emits keyword-highlight spans and nothing else, so any
        // other span means stored markup was parsed as HTML.
        foreignSpans: el.querySelectorAll('span:not(.keyword-highlight)').length,
        innerText: el.innerText,
      };
    });

    expect(result).not.toBeNull();
    expect(result!.liveTags).toBe(0);
    expect(result!.eventHandlerNodes).toBe(0);
    expect(result!.foreignSpans).toBe(0);
    // The stored markup must be VISIBLE as text -- proof it was escaped rather
    // than merely stripped or dropped.
    expect(result!.innerText).toContain(TRIGGER);
  });

  test('[ART-XSS-002] the server response body itself carries no unescaped article markup', async ({ request }) => {
    const resp = await request.get(`${BASE}/articles/${candidate!.id}`);
    expect(resp.ok()).toBe(true);

    const body = sliceArticleContent(await resp.text());
    expect(body.length).toBeGreaterThan(0);

    // Asserted on the raw response, so a future client-side innerHTML rewrite
    // cannot mask a server-side regression the way a DOM-only check would.
    expect(body).not.toMatch(/<(img|script|iframe|svg|object|embed)\b/i);
    expect(body).toContain('&lt;span class=');
  });

  test('[ART-XSS-003] keyword highlighting still renders on the same article', async ({ page }) => {
    await page.goto(`${BASE}/articles/${candidate!.id}`);
    await page.waitForLoadState('domcontentloaded');

    // Escaping must not have cost the feature: the heuristic that caused the
    // bug also silently disabled highlighting for exactly these articles, so
    // this asserts the fix restored it rather than trading one loss for another.
    const highlights = await page.locator('#article-content span.keyword-highlight').count();
    expect(highlights).toBeGreaterThan(0);
  });
});
