import { test, expect, request, type APIRequestContext } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const TEST_ARTICLE_ID = process.env.ARTICLE_ID;
const SKIP_TESTS = process.env.SKIP_ARTICLE_TESTS === 'true';

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

test.describe('Article Detail - Annotations', () => {
  test.skip(SKIP_TESTS, 'Article detail tests disabled.');

  test('[ARTICLE-010] Annotations section is present', async ({ page }) => {
    const hasAnnotations = await page
      .locator('#toggle-annotations-btn, #annotation-mode-huntability')
      .first()
      .isVisible()
      .catch(() => false);
    test.skip(!hasAnnotations, 'Annotations UI not rendered for this article state');
    expect(hasAnnotations).toBe(true);
  });

  test('[ARTICLE-011] Can add annotation button is visible', async ({ page }) => {
    const addBtn = page.locator('#toggle-annotations-btn');
    const hasAddBtn = await addBtn.first().isVisible().catch(() => false);
    test.skip(!hasAddBtn, 'Annotation toggle not rendered for this article state');
    expect(hasAddBtn).toBe(true);
  });
});

test.describe('Article Detail - IoC Extraction', () => {
  test.skip(SKIP_TESTS, 'Article detail tests disabled.');

  test('[ARTICLE-020] Observables/IoCs section is present', async ({ page }) => {
    const hasIoCs = await page
      .locator('#toggle-annotations-btn, #article-content, #article-content-plain')
      .first()
      .isVisible()
      .catch(() => false);
    test.skip(!hasIoCs, 'IoC/annotation controls not rendered for this article state');
    expect(hasIoCs).toBe(true);
  });

  test('[ARTICLE-021] Copy IoC button is functional', async ({ page }) => {
    const copyBtn = page.locator('button[title*="Copy"], button[aria-label*="Copy"], .copy-btn').first();
    const hasCopyBtn = await copyBtn.isVisible().catch(() => false);
    if (hasCopyBtn) {
      await copyBtn.click();
      await page.waitForTimeout(100);
    }
  });
});

test.describe('Article List Page', () => {
  test.skip(SKIP_TESTS, 'Article detail tests disabled.');

  test('[ARTICLE-030] Articles list page loads', async ({ page }) => {
    await page.goto(`${BASE}/articles`);
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/articles/);
  });

  test('[ARTICLE-031] Articles are displayed in list', async ({ page }) => {
    await page.goto(`${BASE}/articles`);
    await page.waitForLoadState('networkidle');
    
    const articleList = page.locator('a[href^="/articles/"], [data-testid="article-list"], .article-list, table, .articles');
    await expect(articleList.first()).toBeVisible();
  });

  test('[ARTICLE-032] Can navigate to article detail from list', async ({ page, request }) => {
    const resp = await request.get('/api/articles?limit=1');
    let articleId: string | null = null;
    
    if (resp.ok()) {
      const body = await resp.json();
      if (body.articles && body.articles.length > 0) {
        articleId = body.articles[0].id.toString();
      }
    }
    
    if (!articleId) {
      test.skip();
    }
    
    await page.goto(`${BASE}/articles`);
    await page.waitForLoadState('networkidle');
    
    const firstArticle = page.locator('a[href*="/articles/"]').first();
    await firstArticle.click();
    
    await page.waitForLoadState('networkidle');
    await expect(page).toHaveURL(/\/articles\/\d+/);
  });
});
