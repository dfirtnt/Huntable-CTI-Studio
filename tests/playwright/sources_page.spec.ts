import { test, expect, Locator, Page, APIRequestContext } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

type SourceRecord = {
  id: number;
  name: string;
  active?: boolean;
  lookback_days?: number;
  check_frequency?: number;
  config?: { min_content_length?: number } | Record<string, unknown>;
};

async function gotoSources(page: Page): Promise<void> {
  await page.goto(`${BASE}/sources`);
  await page.waitForLoadState('networkidle');
}

async function listSources(request: APIRequestContext): Promise<SourceRecord[]> {
  const response = await request.fetch(`${BASE}/api/sources`, {
    method: 'GET',
    data: { active: null, identifier: null },
  });
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(Array.isArray(body.sources)).toBeTruthy();
  return body.sources as SourceRecord[];
}

async function getFirstNonManualSource(request: APIRequestContext): Promise<SourceRecord | null> {
  const sources = await listSources(request);
  return sources.find((s) => (s.name || '').toLowerCase() !== 'manual') ?? null;
}

async function requireFirstNonManualSource(request: APIRequestContext): Promise<SourceRecord> {
  const source = await getFirstNonManualSource(request);
  test.skip(!source, 'No non-manual source available in test environment');
  return source as SourceRecord;
}

// Post-refresh (commit 9103ee41), source cards use `.source-card[data-source-id]`
// instead of Tailwind `.rounded-lg` wrappers. Configure/Toggle/Stats buttons live
// inside a `.src-dropdown` that is `display:none` until the `.btn-overflow` button
// is clicked (toggleOverflow() adds `.open`).
function cardForSource(page: Page, id: number): Locator {
  return page.locator(`.source-card[data-source-id="${id}"]`);
}

async function openSourceOverflow(page: Page, id: number): Promise<void> {
  await cardForSource(page, id).locator('.btn-overflow').click();
  // Dropdown animates open via class toggle; wait for it to be visible.
  await expect(cardForSource(page, id).locator('.src-dropdown.open')).toBeVisible();
}

test.describe('Sources Page - Executable Test Plan', () => {
  test.beforeEach(async ({ page }) => {
    await gotoSources(page);
  });

  test('[SOURCES-001] Sources page loads successfully', async ({ page }) => {
    await expect(page).toHaveURL(new RegExp(`${BASE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/sources/?$`));
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });
    await page.waitForTimeout(250);
    expect(errors.filter((e) => !e.includes('favicon')).length).toBe(0);
  });

  test('[SOURCES-002] Page title verification', async ({ page }) => {
    await expect(page).toHaveTitle(/Sources - Huntable CTI Studio/);
  });

  test('[SOURCES-004] Breadcrumb navigation', async ({ page }) => {
    const breadcrumb = page.locator('nav[aria-label="Breadcrumb"]');
    await expect(breadcrumb).toBeVisible();
    await breadcrumb.locator('a[href="/"]').first().click();
    await expect(page).toHaveURL(new RegExp(`^${BASE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/?$`));
  });

  test('[SOURCES-012] Source cards display correctly when sources exist', async ({ page, request }) => {
    const source = await getFirstNonManualSource(request);
    test.skip(!source, 'No non-manual source available in test environment');

    const card = cardForSource(page, source!.id);
    await expect(card).toBeVisible();
    await expect(card.getByRole('button', { name: /collect articles from/i })).toBeVisible();
  });

  test('[SOURCES-013] Source deep link filters and selects the matching card', async ({ page, request }) => {
    const source = await getFirstNonManualSource(request);
    test.skip(!source, 'No non-manual source available in test environment');

    await page.goto(`${BASE}/sources?source_id=${source!.id}&source=${encodeURIComponent(source!.name)}`);
    await page.waitForLoadState('networkidle');

    const card = cardForSource(page, source!.id);
    await expect(page.locator('#sourceSearch')).toHaveValue(source!.name);
    await expect(card).toBeVisible();
    await expect(card).toHaveClass(/source-selected/);
    await expect(card).toHaveAttribute('aria-current', 'true');
  });

  test('[SOURCES-016] Source metadata fields are displayed', async ({ page, request }) => {
    const source = await getFirstNonManualSource(request);
    test.skip(!source, 'No non-manual source available in test environment');

    // Post-refresh card-meta labels: Domain, Last Check, Frequency, Lookback
    const meta = cardForSource(page, source!.id).locator('.card-meta');
    await expect(meta.getByText('Domain', { exact: true })).toBeVisible();
    await expect(meta.getByText('Last Check', { exact: true })).toBeVisible();
    await expect(meta.getByText('Frequency', { exact: true })).toBeVisible();
    await expect(meta.getByText('Lookback', { exact: true })).toBeVisible();
  });

  test('[SOURCES-021] Collect Now triggers /collect API call', async ({ page, request }) => {
    const source = await requireFirstNonManualSource(request);
    let called = false;

    await page.route('**/api/sources/*/collect', async (route) => {
      called = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, task_id: 'task-123' }),
      });
    });

    await page.route('**/api/tasks/task-123/status', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'PENDING', ready: false }),
      });
    });

    // Enable the button in case the source is inactive (disabled buttons suppress onclick)
    const btn021 = page.locator(`button[onclick="collectFromSource(${source.id})"]`);
    await btn021.evaluate((el) => el.removeAttribute('disabled'));
    await btn021.click({ force: true });
    await expect.poll(() => called).toBeTruthy();
  });

  test('[SOURCES-024] Configure button opens modal', async ({ page, request }) => {
    const source = await requireFirstNonManualSource(request);
    await openSourceOverflow(page, source.id);
    const button = page.locator(`button[onclick^="openSourceConfig(${source.id},"]`).first();
    await button.click();
    await expect(page.locator('#sourceConfigModal')).toBeVisible();
    await expect(page.locator('#configLookbackDays')).toBeVisible();
  });

  test('[SOURCES-026] Toggle Status triggers /toggle API call', async ({ page, request }) => {
    const source = await requireFirstNonManualSource(request);
    let called = false;

    await page.route('**/api/sources/*/toggle', async (route) => {
      called = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          source_name: source.name,
          old_status: true,
          new_status: false,
          message: 'ok',
          database_updated: false,
        }),
      });
    });

    await openSourceOverflow(page, source.id);
    await page.locator(`button[onclick="toggleSourceStatus(${source.id})"]`).click();
    await expect.poll(() => called).toBeTruthy();
  });

  test('[SOURCES-040] Configuration modal form fields exist', async ({ page, request }) => {
    const source = await requireFirstNonManualSource(request);
    await openSourceOverflow(page, source.id);
    await page.locator(`button[onclick^="openSourceConfig(${source.id},"]`).first().click();
    await expect(page.locator('#configLookbackDays')).toBeVisible();
    await expect(page.locator('#configCheckFrequency')).toBeVisible();
    await expect(page.locator('#configMinContentLength')).toBeVisible();
  });

  test('[SOURCES-041] Configuration input constraints', async ({ page, request }) => {
    const source = await requireFirstNonManualSource(request);
    await openSourceOverflow(page, source.id);
    await page.locator(`button[onclick^="openSourceConfig(${source.id},"]`).first().click();

    await expect(page.locator('#configLookbackDays')).toHaveAttribute('min', '1');
    await expect(page.locator('#configLookbackDays')).toHaveAttribute('max', '999');
    await expect(page.locator('#configCheckFrequency')).toHaveAttribute('min', '1');
    await expect(page.locator('#configCheckFrequency')).toHaveAttribute('max', '1440');
    await expect(page.locator('#configMinContentLength')).toHaveAttribute('min', '0');
  });

  test('[SOURCES-042] Current source values pre-populate configuration form', async ({ page, request }) => {
    const source = await requireFirstNonManualSource(request);
    await openSourceOverflow(page, source.id);
    await page.locator(`button[onclick^="openSourceConfig(${source.id},"]`).first().click();

    const lookback = await page.locator('#configLookbackDays').inputValue();
    const checkFrequency = await page.locator('#configCheckFrequency').inputValue();
    const minLength = await page.locator('#configMinContentLength').inputValue();

    expect(parseInt(lookback, 10)).toBeGreaterThan(0);
    expect(parseInt(checkFrequency, 10)).toBeGreaterThan(0);
    expect(parseInt(minLength, 10)).toBeGreaterThanOrEqual(0);
  });

  test('[SOURCES-047] Configuration save triggers all three update API calls', async ({ page, request }) => {
    const source = await requireFirstNonManualSource(request);

    const endpointsHit = new Set<string>();
    await page.route('**/api/sources/*/lookback', async (route) => {
      endpointsHit.add('lookback');
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
    });
    await page.route('**/api/sources/*/check_frequency', async (route) => {
      endpointsHit.add('check_frequency');
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
    });
    await page.route('**/api/sources/*/min_content_length', async (route) => {
      endpointsHit.add('min_content_length');
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true }) });
    });

    await openSourceOverflow(page, source.id);
    await page.locator(`button[onclick^="openSourceConfig(${source.id},"]`).first().click();
    await page.locator('#configLookbackDays').fill('30');
    await page.locator('#configCheckFrequency').fill('60');
    await page.locator('#configMinContentLength').fill('200');
    await page.locator('#saveSourceConfigBtn').click();

    await expect.poll(() => endpointsHit.size).toBe(3);
  });

  test('[SOURCES-048] Configuration validation blocks invalid save', async ({ page, request }) => {
    const source = await requireFirstNonManualSource(request);
    let called = false;

    await page.route('**/api/sources/*/lookback', async (route) => {
      called = true;
      await route.continue();
    });

    await openSourceOverflow(page, source.id);
    await page.locator(`button[onclick^="openSourceConfig(${source.id},"]`).first().click();
    await page.locator('#configLookbackDays').fill('1000');
    await page.locator('#saveSourceConfigBtn').click();
    await page.waitForTimeout(500);
    expect(called).toBeFalsy();
  });

  test('[SOURCES-051] URL textarea accepts URLs and is required', async ({ page }) => {
    const textarea = page.locator('#adhocUrl');
    await expect(textarea).toBeVisible();
    await expect(textarea).toHaveAttribute('required', '');
    await textarea.fill('https://example.com/a\nhttps://example.com/b');
    await expect(textarea).toHaveValue(/example.com\/a/);
  });

  test('[SOURCES-055] URL scraping triggers /api/scrape-url with urls array', async ({ page }) => {
    let requestBody: any = null;

    await page.route('**/api/scrape-url', async (route) => {
      requestBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, total: 1, successful: 1, failed: 0, results: [] }),
      });
    });

    await page.locator('#adhocUrl').fill('https://example.com/article');
    await page.locator('#scrapeUrlBtn').click();

    await expect.poll(() => requestBody !== null).toBeTruthy();
    expect(Array.isArray(requestBody.urls)).toBeTruthy();
    expect(requestBody.urls[0]).toBe('https://example.com/article');
  });
});
