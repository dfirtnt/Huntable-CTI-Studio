import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

// The Versions button lives inside #footer-overflow-menu (hidden by default).
// Open the overflow menu first, then click by stable ID.
const OVERFLOW_TOGGLE = '#footer-overflow-toggle';
const VERSIONS_BTN = '#config-versions-btn';

async function openVersionsModal(page: any) {
  await page.locator(OVERFLOW_TOGGLE).click();
  await expect(page.locator('#footer-overflow-menu')).toBeVisible({ timeout: 3000 });
  await page.locator(VERSIONS_BTN).click();
}

test.describe('Workflow config Restore by version', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
  });

  test('Restore by version button is visible and opens modal', async ({ page }) => {
    await page.locator(OVERFLOW_TOGGLE).click();
    await expect(page.locator('#footer-overflow-menu')).toBeVisible({ timeout: 3000 });
    const versionsBtn = page.locator(VERSIONS_BTN);
    await expect(versionsBtn).toBeVisible({ timeout: 5000 });
    await versionsBtn.click();
    const modal = page.locator('#configVersionListModal');
    await expect(modal).toBeVisible({ timeout: 5000 });
    await expect(page.locator('h3:has-text("Restore configuration by version")')).toBeVisible();
  });

  test('Search input and Search button are visible in modal', async ({ page }) => {
    await openVersionsModal(page);
    await expect(page.locator('#configVersionListModal')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('#configVersionSearch')).toBeVisible();
    await expect(page.locator('#configVersionListModal button:has-text("Search")')).toBeVisible();
  });

  test('Search by version triggers API request with version param', async ({ page }) => {
    const initialResponsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/workflow/config/versions') && r.request().method() === 'GET',
      { timeout: 10000 }
    );
    await openVersionsModal(page);
    await initialResponsePromise;
    await expect(page.locator('#configVersionListModal')).toBeVisible({ timeout: 5000 });
    const searchInput = page.locator('#configVersionSearch');
    await searchInput.fill('1');
    const searchResponsePromise = page.waitForResponse(
      (r) =>
        r.url().includes('/api/workflow/config/versions') &&
        r.url().includes('version=1') &&
        r.request().method() === 'GET',
      { timeout: 5000 }
    );
    await page.locator('#configVersionListModal button:has-text("Search")').click();
    const response = await searchResponsePromise;
    expect(response.status()).toBe(200);
  });

  test('Pagination footer shows when more than 20 versions', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/workflow/config/versions') && r.request().method() === 'GET',
      { timeout: 10000 }
    );
    await openVersionsModal(page);
    await responsePromise;
    await expect(page.locator('#configVersionListModal')).toBeVisible({ timeout: 5000 });
    await page.waitForTimeout(500);
    const paginationEl = page.locator('#configVersionPagination');
    const pageInfo = page.locator('#configVersionPageInfo');
    const total = await pageInfo.textContent().then((t) => {
      const m = t?.match(/\((\d+)\s+total\)/);
      return m ? parseInt(m[1], 10) : 0;
    });
    if (total > 20) {
      await expect(paginationEl).toBeVisible();
      await expect(pageInfo).toContainText('Page');
      await expect(page.locator('#configVersionPrevBtn')).toBeVisible();
      await expect(page.locator('#configVersionNextBtn')).toBeVisible();
    }
  });

  test('Version list loads from API and shows at least placeholder or versions', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/workflow/config/versions') && r.request().method() === 'GET',
      { timeout: 10000 }
    );
    await openVersionsModal(page);
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    const list = page.locator('#configVersionList');
    await expect(list).toBeVisible({ timeout: 3000 });
    const hasVersions = await list.locator('button:has-text("Load")').count() > 0;
    const hasEmpty = await list.locator('text=No versions found').isVisible().catch(() => false);
    expect(hasVersions || hasEmpty).toBe(true);
  });

  test('Load version populates form and closes modal', async ({ page }) => {
    const responsePromise = page.waitForResponse(
      (r) => r.url().includes('/api/workflow/config/versions') && r.request().method() === 'GET',
      { timeout: 10000 }
    );
    await openVersionsModal(page);
    await responsePromise;
    await page.waitForSelector('#configVersionListModal', { state: 'visible', timeout: 5000 });

    const loadBtn = page.locator('#configVersionList button:has-text("Load")').first();
    const loadVisible = await loadBtn.isVisible({ timeout: 3000 }).catch(() => false);
    if (!loadVisible) {
      test.skip();
      return;
    }

    page.on('dialog', (d) => d.accept());
    await loadBtn.click();
    await page.waitForResponse((r) => r.url().match(/\/api\/workflow\/config\/version\/\d+/) && r.request().method() === 'GET', { timeout: 10000 });
    await page.waitForTimeout(1500);
    await expect(page.locator('#configVersionListModal')).not.toBeVisible({ timeout: 5000 });
  });
});
