import { test, expect, request, type APIRequestContext } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const TEST_ARTICLE_ID = process.env.ARTICLE_ID;
const SKIP_TESTS = process.env.SKIP_ARTICLE_TESTS === 'true';

// Article detail page deprecated with RAG Chat UI removal (commit 824bb79d)
// Articles remain accessible via MCP search_articles tool
const SKIP_ARTICLE_DETAIL = true;

async function resolveArticleId(requestContext: APIRequestContext): Promise<string | null> {
  if (TEST_ARTICLE_ID) return TEST_ARTICLE_ID;
  const resp = await requestContext.get('/api/articles?limit=1');
  if (!resp.ok()) return null;
  const body = await resp.json();
  const first = body?.articles?.[0];
  return first?.id ? String(first.id) : null;
}

test.describe('Article Detail Page', () => {
  test.skip(SKIP_TESTS, 'Article detail tests disabled (SKIP_ARTICLE_TESTS=true).');

  test.beforeEach(async ({ page, request }) => {
    const articleId = await resolveArticleId(request);
    test.skip(!articleId, 'No article available for detail tests');
    await page.goto(`${BASE}/articles/${articleId}`);
    await page.waitForLoadState('domcontentloaded');
  });

  test('[ARTICLE-001] Article detail page loads successfully', async ({ page }) => {
    await expect(page).toHaveURL(/\/articles\/\d+/);
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });
    await page.waitForTimeout(250);
    expect(errors.filter((e) => !e.includes('favicon'))).toHaveLength(0);
  });

  test('[ARTICLE-002] Page title is displayed', async ({ page }) => {
    const title = await page.locator('h1, [data-testid="article-title"], .article-title').first().textContent();
    expect(title).toBeTruthy();
  });

  test('[ARTICLE-003] Article content is visible', async ({ page }) => {
    const content = page.locator('#article-content');
    await expect(content.first()).toBeVisible();
  });

  test('[ARTICLE-004] Source/link is displayed', async ({ page }) => {
    const link = page.locator('a[href^="http"], [data-testid="article-source"]');
    const hasLink = await link.first().isVisible().catch(() => false);
    expect(hasLink).toBe(true);
  });

  test('[ARTICLE-005] Back to articles navigation works', async ({ page }) => {
    const backLink = page.locator('a[href*="/articles"], a:has-text("Back"), a:has-text("Articles")');
    const hasBack = await backLink.first().isVisible().catch(() => false);
    expect(hasBack).toBe(true);
  });
});

test.describe('Article List Page', () => {
  test.skip(SKIP_TESTS || SKIP_ARTICLE_DETAIL, 'Article detail page deprecated with RAG Chat UI (commit 824bb79d).');

  test('[ARTICLE-030] Articles list page loads', async ({ page }) => {
    await page.goto(`${BASE}/articles`);
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/articles/);
  });
});
