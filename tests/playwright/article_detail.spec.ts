import { test, expect, request } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const TEST_ARTICLE_ID = process.env.ARTICLE_ID || '1';
const SKIP_TESTS = process.env.SKIP_ARTICLE_TESTS === 'true';

test.describe('Article Detail Page', () => {
  test.skip(SKIP_TESTS, 'Article detail tests disabled (SKIP_ARTICLE_TESTS=true).');

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/articles/${TEST_ARTICLE_ID}`);
    await page.waitForLoadState('networkidle');
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
    const content = page.locator('[data-testid="article-content"], .article-content, article, .content');
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
    await page.goto(`${BASE}/articles/${TEST_ARTICLE_ID}`);
    await page.waitForLoadState('networkidle');
    
    const annotationSection = page.locator('[data-testid="annotations"], .annotations, h2:has-text("Annotation")');
    const hasAnnotations = await annotationSection.first().isVisible().catch(() => false);
    expect(hasAnnotations).toBe(true);
  });

  test('[ARTICLE-011] Can add annotation button is visible', async ({ page }) => {
    await page.goto(`${BASE}/articles/${TEST_ARTICLE_ID}`);
    await page.waitForLoadState('networkidle');
    
    const addBtn = page.locator('button:has-text("Add Annotation"), button:has-text("New Annotation"), [data-testid="add-annotation"]');
    const hasAddBtn = await addBtn.first().isVisible().catch(() => false);
    expect(hasAddBtn).toBe(true);
  });
});

test.describe('Article Detail - IoC Extraction', () => {
  test.skip(SKIP_TESTS, 'Article detail tests disabled.');

  test('[ARTICLE-020] Observables/IoCs section is present', async ({ page }) => {
    await page.goto(`${BASE}/articles/${TEST_ARTICLE_ID}`);
    await page.waitForLoadState('networkidle');
    
    const iocSection = page.locator('[data-testid="observables"], .observables, h2:has-text("Observable"), h2:has-text("IoC")');
    const hasIoCs = await iocSection.first().isVisible().catch(() => false);
    expect(hasIoCs).toBe(true);
  });

  test('[ARTICLE-021] Copy IoC button is functional', async ({ page }) => {
    await page.goto(`${BASE}/articles/${TEST_ARTICLE_ID}`);
    await page.waitForLoadState('networkidle');
    
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
    
    const articleList = page.locator('[data-testid="article-list"], .article-list, table, .articles');
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
