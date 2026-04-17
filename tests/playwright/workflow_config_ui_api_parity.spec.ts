import { test, expect, Page } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';
const WORKFLOW_CONFIG_URL = `${BASE}/workflow#config`;

function normalizeDisplayText(s: string): string {
  return s
    .replace(/\s+/g, ' ')
    .replace(/\s*:\s*/g, ': ')
    .trim();
}

function extractVersion(text: string): number | null {
  const m = text.match(/Version:\s*(\d+)/);
  return m ? parseInt(m[1], 10) : null;
}

function extractThresholds(text: string): { ranking?: number; junk?: number; similarity?: number } {
  const normalized = normalizeDisplayText(text);
  const ranking = normalized.match(/Ranking Threshold:\s*([\d.]+)/)?.[1];
  const junk = normalized.match(/Junk Filter Threshold:\s*([\d.]+)/)?.[1];
  const similarity = normalized.match(/Similarity Threshold:\s*([\d.]+)/)?.[1];
  return {
    ranking: ranking ? parseFloat(ranking) : undefined,
    junk: junk ? parseFloat(junk) : undefined,
    similarity: similarity ? parseFloat(similarity) : undefined,
  };
}

async function switchToConfigTab(page: Page) {
  await page.evaluate(() => {
    if (typeof switchTab === 'function') {
      switchTab('config');
    }
  });
  await page.waitForTimeout(600);
}

async function waitForConfigReady(page: Page) {
  await page.waitForSelector('#workflowConfigForm', { timeout: 15000 });
  await page.waitForFunction(() => typeof currentConfig !== 'undefined' && currentConfig !== null, { timeout: 15000 });
  await page.evaluate(() => {
    const details = document.querySelector('details.current-config') as HTMLDetailsElement | null;
    if (details) {
      details.open = true;
    }
  });
  await page.waitForFunction(() => {
    const el = document.getElementById('configDisplay');
    const text = el?.textContent || '';
    return Boolean(el && /Version:\s*\d+/.test(text));
  }, { timeout: 15000 });
  await page.waitForTimeout(600);
}

async function openStepsForThresholdInputs(page: Page) {
  await page.evaluate(() => {
    ['s1', 's2', 's5'].forEach((id) => document.getElementById(id)?.classList.add('open'));
  });
  await page.waitForTimeout(300);
}

async function getInputNumberValue(page: Page, id: string): Promise<number> {
  await page.waitForSelector(`#${id}`, { state: 'attached', timeout: 15000 });
  const value = await page.evaluate((inputId: string) => {
    const el = document.getElementById(inputId) as HTMLInputElement | null;
    return el ? el.value : null;
  }, id);
  if (value === null) {
    throw new Error(`Input #${id} not found`);
  }
  const num = parseFloat(value);
  if (Number.isNaN(num)) {
    throw new Error(`Input #${id} value is not numeric: ${value}`);
  }
  return num;
}

test.describe('Workflow config UI/API parity', () => {
  test('Workflow UI renders the active /api/workflow/config version and thresholds', async ({ page }) => {
    test.setTimeout(90000);

    const activeResp = await page.request.get(`${BASE}/api/workflow/config`);
    expect(activeResp.ok()).toBeTruthy();
    const active = await activeResp.json();

    expect(typeof active.version).toBe('number');
    expect(typeof active.ranking_threshold).toBe('number');
    expect(typeof active.junk_filter_threshold).toBe('number');
    expect(typeof active.similarity_threshold).toBe('number');

    await page.goto(WORKFLOW_CONFIG_URL, { waitUntil: 'domcontentloaded' });
    await switchToConfigTab(page);
    await waitForConfigReady(page);
    await openStepsForThresholdInputs(page);

    const displayText = normalizeDisplayText(await page.locator('#configDisplay').innerText());
    const uiVersion = extractVersion(displayText);
    expect(uiVersion).not.toBeNull();
    expect(uiVersion).toBe(active.version);

    const uiThresholds = extractThresholds(displayText);
    expect(uiThresholds.ranking).not.toBeUndefined();
    expect(uiThresholds.junk).not.toBeUndefined();
    expect(uiThresholds.similarity).not.toBeUndefined();
    expect(uiThresholds.ranking).toBeCloseTo(active.ranking_threshold, 3);
    expect(uiThresholds.junk).toBeCloseTo(active.junk_filter_threshold, 3);
    expect(uiThresholds.similarity).toBeCloseTo(active.similarity_threshold, 3);

    const rankingInput = await getInputNumberValue(page, 'rankingThreshold');
    const junkInput = await getInputNumberValue(page, 'junkFilterThreshold');
    const similarityInput = await getInputNumberValue(page, 'similarityThreshold');

    expect(rankingInput).toBeCloseTo(active.ranking_threshold, 3);
    expect(junkInput).toBeCloseTo(active.junk_filter_threshold, 3);
    expect(similarityInput).toBeCloseTo(active.similarity_threshold, 3);
  });
});
