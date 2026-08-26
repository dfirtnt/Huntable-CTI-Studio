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

  // --- ML Model Performance panel refresh (Todoist 6hJ8x4W8grvGqP63) ---------
  //
  // The four values were emitted once inside the modal's innerHTML template
  // literal with no id attributes, so updateChunkDebugResults() -- which
  // refreshes the tiles, cost analysis, visualisation and chunk details on
  // every threshold change -- had no handle on this panel and never touched it.
  // Moving the slider therefore left it showing the previous threshold's
  // numbers, including a mismatch count that contradicted the chunks the
  // "Show ML Mismatches" filter actually revealed.
  //
  // Both render paths now go through updateMlPerformancePanel(). These tests
  // drive the real re-render entry point rather than that writer directly, so
  // they fail if the wiring is removed even though the writer still works.

  const mlPanel = (page: Page) => page.evaluate(() => {
    const el = (id: string) => document.getElementById(id);
    return {
      total: el('mlTotalPredictions')?.textContent,
      correct: el('mlCorrectPredictions')?.textContent,
      accuracy: el('mlAccuracyPercent')?.textContent,
      band: el('mlAccuracyPercent')?.className.split(' ').pop(),
      mismatches: el('mlMismatches')?.textContent,
      note: el('mlPartialAnalysisNote')?.textContent,
    };
  });

  test('the ML panel renders from ml_stats on open', async ({ page }) => {
    await renderSyntheticModal(page, {
      chunk_analysis: [
        makeChunk({ chunk_id: 0, is_kept: true }),
        makeChunk({ chunk_id: 1, is_kept: false, ml_mismatch: true }),
      ],
      ml_stats: { total_predictions: 2, correct_predictions: 1, accuracy_percent: 50, mismatches: 1 },
    });

    expect(await mlPanel(page)).toMatchObject({
      total: '2', correct: '1', accuracy: '50.0%', band: 'text-red-400', mismatches: '1',
    });
  });

  test('a threshold re-render updates every ML value instead of stranding the previous ones', async ({ page }) => {
    await renderSyntheticModal(page, {
      min_confidence: 0.7,
      chunk_analysis: [makeChunk({ chunk_id: 0, is_kept: true, ml_mismatch: true })],
      ml_stats: { total_predictions: 36, correct_predictions: 30, accuracy_percent: 83.33333, mismatches: 6 },
    });
    expect(await mlPanel(page)).toMatchObject({ correct: '30', accuracy: '83.3%', mismatches: '6' });

    // The measured 0.7 -> 0.5 transition from the bug report: pre-fix the panel
    // stayed at 30 / 83.3% / 6 while the payload said 36 / 100% / 0.
    await page.evaluate((d) => (window as any).updateChunkDebugResults(d), buildSyntheticData({
      min_confidence: 0.5,
      chunk_analysis: [makeChunk({ chunk_id: 0, is_kept: true, ml_mismatch: false })],
      ml_stats: { total_predictions: 36, correct_predictions: 36, accuracy_percent: 100, mismatches: 0 },
    }));

    expect(await mlPanel(page)).toMatchObject({
      total: '36', correct: '36', accuracy: '100.0%', band: 'text-emerald-400', mismatches: '0',
    });
  });

  test('the agreement colour band is replaced, not accumulated, as the value crosses each boundary', async ({ page }) => {
    await renderSyntheticModal(page, {
      ml_stats: { total_predictions: 10, correct_predictions: 10, accuracy_percent: 100, mismatches: 0 },
    });
    expect((await mlPanel(page)).band).toBe('text-emerald-400');

    for (const [accuracy, band] of [[75, 'text-amber-400'], [42, 'text-red-400'], [80, 'text-emerald-400']] as const) {
      await page.evaluate((d) => (window as any).updateChunkDebugResults(d), buildSyntheticData({
        ml_stats: { total_predictions: 10, correct_predictions: 1, accuracy_percent: accuracy, mismatches: 9 },
      }));
      const panel = await mlPanel(page);
      expect(panel.band).toBe(band);
      // A stale colour left behind would show up as two colour classes at once.
      const classes = await page.evaluate(() => document.getElementById('mlAccuracyPercent')?.className ?? '');
      expect(classes.match(/text-(emerald|amber|red|gray)-400/g)?.length).toBe(1);
    }
  });

  test('the mismatch count always equals what the ML Mismatches filter reveals', async ({ page }) => {
    await renderSyntheticModal(page, {
      chunk_analysis: [
        makeChunk({ chunk_id: 0, is_kept: true, ml_mismatch: true }),
        makeChunk({ chunk_id: 1, is_kept: false, ml_mismatch: true }),
        makeChunk({ chunk_id: 2, is_kept: true, ml_mismatch: false }),
      ],
      ml_stats: { total_predictions: 3, correct_predictions: 1, accuracy_percent: 33.3, mismatches: 2 },
    });

    // Re-render with a payload where the mismatches disappear entirely -- the
    // exact self-contradiction reported: panel said 6, the filter showed none.
    await page.evaluate((d) => (window as any).updateChunkDebugResults(d), buildSyntheticData({
      chunk_analysis: [
        makeChunk({ chunk_id: 0, is_kept: true, ml_mismatch: false }),
        makeChunk({ chunk_id: 1, is_kept: false, ml_mismatch: false }),
        makeChunk({ chunk_id: 2, is_kept: true, ml_mismatch: false }),
      ],
      ml_stats: { total_predictions: 3, correct_predictions: 3, accuracy_percent: 100, mismatches: 0 },
    }));

    expect((await mlPanel(page)).mismatches).toBe('0');
    await expect(page.locator('.chunk-filter-btn[data-filter="mismatch"] .chunk-filter-count')).toHaveText('(0)');
  });

  test('the partial-analysis caveat in the ML header refreshes with the numbers it describes', async ({ page }) => {
    await renderSyntheticModal(page, {
      processing_summary: {
        processed_chunks: 150, total_chunks: 1250, chunk_limit_applied: true,
        concurrency_limit: 4, per_chunk_timeout_seconds: 12.0, full_analysis: false, remaining_chunks: 1100,
      },
    });
    expect((await mlPanel(page)).note).toBe('(based on 150 of 1250 chunks)');

    // A full re-analysis must clear it; leaving it behind would caveat numbers
    // that now describe every chunk.
    await page.evaluate((d) => (window as any).updateChunkDebugResults(d), buildSyntheticData());
    expect((await mlPanel(page)).note).toBe('');
  });

  // --- Dialog accessibility (Todoist 6hJ8x5Gp96F42C43) -----------------------
  //
  // ModalManager stacks, shows, and focuses the first input it finds -- it has no
  // focus trap, no focus restore and no scroll lock, so this modal wires those
  // itself. The "first input" heuristic also meant focus landed on the threshold
  // slider; these pin the deterministic close-button target instead.

  test('the close button has an accessible name and the dialog name matches its visible title', async ({ page }) => {
    await renderSyntheticModal(page);

    const closeBtn = page.locator('#chunkDebugCloseButton');
    await expect(closeBtn).toHaveAttribute('aria-label', 'Close Junk Filter Tuning');
    // type=button, or a close control inside a form would submit it.
    await expect(closeBtn).toHaveAttribute('type', 'button');

    // WCAG 2.5.3 Label in Name: the dialog used aria-label="Chunk debug" against a
    // visible "Junk Filter Tuning", so voice control could not address it by name.
    const modal = page.locator('#chunkDebugModal');
    await expect(modal).not.toHaveAttribute('aria-label', /.*/);
    await expect(modal).toHaveAttribute('aria-labelledby', 'chunkDebugModalTitle');
    const accessibleName = await page.locator('#chunkDebugModalTitle').textContent();
    expect(accessibleName?.trim()).toBe('Junk Filter Tuning');
  });

  test('opening moves focus into the dialog, onto a non-destructive control', async ({ page }) => {
    await renderSyntheticModal(page);
    // Out-wait ModalManager's own 100ms first-input focus, which would otherwise
    // leave focus on the threshold slider.
    await page.waitForTimeout(400);

    const focused = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      const modal = document.getElementById('chunkDebugModal');
      return {
        id: el?.id ?? null,
        insideModal: !!(modal && el && modal.contains(el)),
        // The Correct/Incorrect buttons POST into the ML training corpus, so a
        // single Space on the opening focus position must never submit training data.
        isFeedbackButton: /correct|incorrect/i.test(el?.textContent ?? ''),
      };
    });

    expect(focused.insideModal).toBe(true);
    expect(focused.id).toBe('chunkDebugCloseButton');
    expect(focused.isFeedbackButton).toBe(false);
  });

  test('background scroll is locked while open and restored on close', async ({ page }) => {
    const before = await page.evaluate(() => document.body.style.overflow);
    await renderSyntheticModal(page);
    expect(await page.evaluate(() => document.body.style.overflow)).toBe('hidden');

    await page.evaluate(() => (window as any).closeChunkDebugModal());
    await page.waitForTimeout(200);

    expect(await page.evaluate(() => document.body.style.overflow)).toBe(before);
    // The saved value must not linger, or a later open would restore the wrong one.
    expect(await page.evaluate(() => document.body.dataset.chunkDebugPrevOverflow ?? null)).toBeNull();
  });

  test('closing returns focus to whatever opened the dialog', async ({ page }) => {
    // Give the page a real opener to restore to.
    await page.evaluate(() => {
      const b = document.createElement('button');
      b.id = 'syntheticOpener';
      b.textContent = 'Junk Filter Tuning';
      document.body.prepend(b);
      b.focus();
    });

    await renderSyntheticModal(page);
    await page.waitForTimeout(400);
    expect(await page.evaluate(() => document.activeElement?.id)).toBe('chunkDebugCloseButton');

    await page.evaluate(() => (window as any).closeChunkDebugModal());
    await page.waitForTimeout(300);

    // Pre-fix this dropped to BODY, restarting a keyboard user's traversal.
    expect(await page.evaluate(() => document.activeElement?.id)).toBe('syntheticOpener');
  });
});
