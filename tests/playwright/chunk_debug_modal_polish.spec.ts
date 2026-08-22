import { test, expect, type APIRequestContext, type Page } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

/**
 * Regression + acceptance coverage for the Junk Filter Tuning modal polish
 * sweep (Todoist parent 6hJ8x5QF67vC6qhV): a set of small display/labelling
 * fixes in the modal built by showChunkDebugModal() in article_detail.html.
 *
 * Every test drives the modal's global render functions directly with a
 * synthetic payload shaped like the real /api/articles/{id}/chunk-debug
 * response, rather than depending on live sklearn inference -- this keeps
 * every scenario (zero mismatches, chunk_limit_applied, etc.) deterministic
 * and fast, following the same direct-function-invocation pattern as
 * chunk_dialogs_xss_regression.spec.ts.
 */

async function firstArticleId(request: APIRequestContext): Promise<number | null> {
  const override = process.env.ARTICLE_ID;
  if (override) return Number(override);
  const resp = await request.get(`${BASE}/api/articles?limit=1`);
  if (!resp.ok()) return null;
  const body = await resp.json();
  const article = (body?.articles ?? [])[0];
  return typeof article?.id === 'number' ? article.id : null;
}

function makeChunk(overrides: Record<string, unknown> = {}) {
  return {
    chunk_id: 0,
    start: 0,
    end: 100,
    length: 100,
    text: 'sample chunk text',
    is_kept: true,
    has_threat_keywords: false,
    has_command_patterns: false,
    has_perfect_discriminators: false,
    ml_mismatch: false,
    confidence: 0.9,
    reason: 'Content filtered successfully',
    features: { cmdline_artifact_count: 0 },
    ml_details: {
      prediction_label: 'Huntable',
      confidence: 0.888,
      probabilities: { huntable: 0.888, not_huntable: 0.112 },
      error: null,
    },
    ...overrides,
  };
}

/** Builds a synthetic chunk-debug payload with two chunks (kept + removed,
 * no mismatches) unless the caller overrides chunk_analysis directly. */
function buildSyntheticData(overrides: Record<string, unknown> = {}) {
  const chunkAnalysis = (overrides.chunk_analysis as unknown[]) ?? [
    makeChunk({ chunk_id: 0, is_kept: true }),
    makeChunk({ chunk_id: 1, is_kept: false, ml_mismatch: false, reason: 'No huntable content found' }),
  ];

  return {
    article_id: 1,
    article_title: 'Synthetic Test Article',
    content_length: 1000,
    chunk_size: 1000,
    total_chunks: chunkAnalysis.length,
    kept_chunks: chunkAnalysis.filter((c: any) => c.is_kept).length,
    removed_chunks: chunkAnalysis.filter((c: any) => !c.is_kept).length,
    chunk_analysis: chunkAnalysis,
    processing_summary: {
      processed_chunks: chunkAnalysis.length,
      total_chunks: chunkAnalysis.length,
      chunk_limit_applied: false,
      concurrency_limit: 4,
      per_chunk_timeout_seconds: 12.0,
      full_analysis: true,
      remaining_chunks: 0,
    },
    filter_result: { is_huntable: true, confidence: 0.9, cost_savings: 0, kept_chunks_count: 1, removed_chunks_count: 1 },
    ml_stats: {
      total_predictions: chunkAnalysis.length,
      correct_predictions: chunkAnalysis.length,
      accuracy_percent: 100,
      mismatches: chunkAnalysis.filter((c: any) => c.ml_mismatch).length,
    },
    cost_estimate: { input_tokens: 100, output_tokens: 2000, input_cost: 0.001, output_cost: 0.02, total_cost: 0.021, cost_savings: 0, filtering_enabled: true, estimated_content_tokens: 100, prompt_tokens: 1508 },
    filtering_stats: { reduction_percent: 50.0, content_reduction_percent: 35.4, tokens_saved: 100, cost_savings: 0.001 },
    min_confidence: 0.7,
    ...overrides,
  };
}

async function renderSyntheticModal(page: Page, overrides: Record<string, unknown> = {}) {
  const data = buildSyntheticData(overrides);
  const ready = await page.evaluate((d) => typeof (window as any).showChunkDebugResults === 'function' && (() => {
    (window as any).showChunkDebugResults(d);
    return true;
  })(), data);
  expect(ready).toBe(true);
  await page.waitForSelector('#chunkDebugModal', { state: 'visible', timeout: 5000 });
  return data;
}

test.describe('Junk Filter Tuning modal polish sweep', () => {
  let articleId: number | null = null;

  test.beforeEach(async ({ request, page }) => {
    articleId = await firstArticleId(request);
    test.skip(articleId === null, 'No article available to host the modal render functions.');
    await page.goto(`${BASE}/articles/${articleId}`);
    await page.waitForLoadState('domcontentloaded');
    const globalsReady = await page.evaluate(() =>
      typeof (window as any).showChunkDebugResults === 'function' &&
      typeof (window as any).filterChunks === 'function'
    );
    test.skip(!globalsReady, 'Chunk-debug modal functions are not present on this page.');
  });

  test('Content Reduction tile shows character reduction, not the chunk-count ratio', async ({ page }) => {
    // reduction_percent (chunk-count ratio) = 50.0%, content_reduction_percent
    // (actual char reduction) = 35.4% -- pre-fix the tile bound to the former.
    await renderSyntheticModal(page);
    const tileText = await page.locator('#contentReductionPercent').textContent();
    expect(tileText?.trim()).toBe('35.4%');
    expect(tileText?.trim()).not.toBe('50.0%');
  });

  test('threshold preset cards track the active threshold with no disagreement', async ({ page }) => {
    await renderSyntheticModal(page, { min_confidence: 0.7 });

    const state = async () => page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll('.threshold-preset-card'));
      return cards.map((c) => ({
        threshold: (c as HTMLElement).dataset.presetThreshold,
        active: c.classList.contains('border-purple-500/50'),
        caption: c.querySelector('.preset-caption')?.textContent,
      }));
    });

    let cards = await state();
    expect(cards.find((c) => c.threshold === '0.7')?.active).toBe(true);
    expect(cards.find((c) => c.threshold === '0.7')?.caption).toBe('Selected threshold');
    expect(cards.find((c) => c.threshold === '0.5')?.active).toBe(false);

    // Simulate the slider moving to 0.5 (syncThresholdPresetCards is what
    // updateThreshold() calls -- exercised directly to avoid a live network fetch).
    await page.evaluate(() => (window as any).syncThresholdPresetCards(0.5));
    cards = await state();
    expect(cards.find((c) => c.threshold === '0.5')?.active).toBe(true);
    expect(cards.find((c) => c.threshold === '0.5')?.caption).toBe('Selected threshold');
    expect(cards.find((c) => c.threshold === '0.7')?.active).toBe(false);
    expect(cards.find((c) => c.threshold === '0.7')?.caption).not.toBe('Selected threshold');
  });

  test('an empty-matching filter shows a message instead of blank space, and it clears again', async ({ page }) => {
    await renderSyntheticModal(page, {
      chunk_analysis: [makeChunk({ chunk_id: 0, is_kept: true, ml_mismatch: false })],
    });

    await page.evaluate(() => (window as any).filterChunks('mismatch'));
    await expect(page.locator('#chunkFilterEmptyState')).toBeVisible();
    await expect(page.locator('#chunkFilterEmptyState')).toHaveText('No chunks match the selected filter.');

    await page.evaluate(() => (window as any).filterChunks('all'));
    await expect(page.locator('#chunkFilterEmptyState')).toBeHidden();
  });

  test('the ML Mismatch legend swatch is outlined, not solid amber', async ({ page }) => {
    await renderSyntheticModal(page);
    const swatchClass = await page.evaluate(() => {
      const span = Array.from(document.querySelectorAll('#chunkDebugModal span'))
        .find((s) => s.textContent?.trim() === 'ML Mismatch');
      return span?.previousElementSibling?.className ?? null;
    });
    expect(swatchClass).not.toBeNull();
    expect(swatchClass).toContain('ring-amber-400');
    expect(swatchClass).not.toContain('bg-amber-400');
  });

  test('model confidence and filter confidence are distinctly labelled', async ({ page }) => {
    await renderSyntheticModal(page);
    const chunkDetailsText = await page.locator('#chunkDetails').innerText();
    expect(chunkDetailsText).toContain('Model confidence:');
    expect(chunkDetailsText).toContain('Filter confidence:');
    // No bare "Confidence:" left over from before either label was qualified.
    expect(/(?<!Model |Filter )Confidence:/.test(chunkDetailsText)).toBe(false);
  });

  test('every chunk heading and feedback button has a unique, chunk-numbered accessible name', async ({ page }) => {
    await renderSyntheticModal(page, {
      chunk_analysis: [
        makeChunk({ chunk_id: 0 }),
        makeChunk({ chunk_id: 1, is_kept: false }),
        makeChunk({ chunk_id: 2 }),
      ],
    });

    const names = await page.evaluate(() => {
      const headings = Array.from(document.querySelectorAll('#chunkDetails h5')).map((h) => h.textContent?.trim());
      const buttons = Array.from(document.querySelectorAll('#chunkDetails button'))
        .filter((b) => b.getAttribute('onclick')?.includes('submitChunkFeedback'))
        .map((b) => b.getAttribute('aria-label'));
      return { headings, buttons };
    });

    expect(names.headings).toHaveLength(3);
    expect(new Set(names.headings).size).toBe(3);
    for (const h of names.headings) expect(h).toMatch(/Chunk \d+/);

    expect(names.buttons).toHaveLength(6); // 2 feedback buttons per chunk
    expect(new Set(names.buttons).size).toBe(6);
    for (const label of names.buttons) expect(label).toMatch(/Chunk \d+/);
  });

  test('panel headings note the sample size when the chunk cap was applied, and stay silent otherwise', async ({ page }) => {
    await renderSyntheticModal(page, {
      processing_summary: {
        processed_chunks: 150,
        total_chunks: 1250,
        chunk_limit_applied: true,
        concurrency_limit: 4,
        per_chunk_timeout_seconds: 12.0,
        full_analysis: false,
        remaining_chunks: 1100,
      },
    });

    let headingsText = await page.locator('#chunkDebugModal h4').allInnerTexts();
    let joined = headingsText.join(' | ');
    expect(joined).toContain('ML Model Performance (based on 150 of 1250 chunks)');
    expect(joined).toContain('Chunk Visualization (based on 150 of 1250 chunks)');
    expect(joined).toContain('Chunk Details (based on 150 of 1250 chunks)');

    // chunk_limit_applied: false -> no note anywhere.
    await renderSyntheticModal(page);
    headingsText = await page.locator('#chunkDebugModal h4').allInnerTexts();
    joined = headingsText.join(' | ');
    expect(joined).not.toContain('based on');
  });

  test('the applied filter button is the only one aria-pressed, and each button shows its match count', async ({ page }) => {
    await renderSyntheticModal(page, {
      chunk_analysis: [
        makeChunk({ chunk_id: 0, is_kept: true }),
        makeChunk({ chunk_id: 1, is_kept: false }),
        makeChunk({ chunk_id: 2, is_kept: true }),
      ],
    });

    const allBtn = page.locator('.chunk-filter-btn[data-filter="all"]');
    const keptBtn = page.locator('.chunk-filter-btn[data-filter="kept"]');
    await expect(allBtn).toHaveAttribute('aria-pressed', 'true');
    await expect(keptBtn).toHaveAttribute('aria-pressed', 'false');
    await expect(keptBtn.locator('.chunk-filter-count')).toHaveText('(2)');

    await page.evaluate(() => (window as any).filterChunks('kept'));
    await expect(allBtn).toHaveAttribute('aria-pressed', 'false');
    await expect(keptBtn).toHaveAttribute('aria-pressed', 'true');
  });
});
