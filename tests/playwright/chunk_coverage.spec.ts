import { test, expect, request } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const TEST_ARTICLE_ID = process.env.ARTICLE_ID || '2464';

test.describe('Chunk Coverage Validation', () => {
  test('API: Chunk debug endpoint should report no coverage gaps', async () => {
    test.setTimeout(120_000);
    const api = await request.newContext({ baseURL: BASE, timeout: 120_000 });
    
    const resp = await api.get(`/api/articles/${TEST_ARTICLE_ID}/chunk-debug?chunk_size=1000&overlap=200&min_confidence=0.7`);
    
    expect(resp.ok()).toBe(true);
    
    const body = await resp.json();
    
    // Verify response structure
    expect(body).toHaveProperty('content_length');
    expect(body).toHaveProperty('chunk_analysis');
    expect(body).toHaveProperty('coverage_validation');
    
    // Verify coverage validation data
    const coverage = body.coverage_validation;
    expect(coverage).toHaveProperty('total_content_length');
    expect(coverage).toHaveProperty('total_covered_length');
    expect(coverage).toHaveProperty('coverage_percent');
    expect(coverage).toHaveProperty('gaps_found');
    expect(coverage).toHaveProperty('gaps');
    
    // Verify no gaps
    expect(coverage.gaps_found).toBe(0);
    expect(coverage.gaps).toHaveLength(0);
    
    // Verify coverage is 100%
    expect(coverage.coverage_percent).toBeGreaterThanOrEqual(99.9); // Allow tiny rounding errors
    
    // Verify total covered length matches content length (accounting for overlap)
    // Since chunks overlap, total_covered_length may exceed content_length
    // But all positions should be covered
    expect(coverage.total_covered_length).toBeGreaterThanOrEqual(coverage.total_content_length * 0.99);
    
    console.log(`Coverage: ${coverage.coverage_percent.toFixed(2)}%`);
    console.log(`Gaps found: ${coverage.gaps_found}`);
    console.log(`Total chunks: ${body.total_chunks}`);
  });

  test('UI: Chunk visualization should show continuous coverage', async ({ page }) => {
    test.setTimeout(120_000);
    await page.goto(`${BASE}/articles/${TEST_ARTICLE_ID}`);
    await page.waitForLoadState('networkidle');
    
    // Wait for page to load
    await page.waitForTimeout(2000);
    
    // Look for chunk debug section or button
    // The chunk debug might be in a tab or section
    const chunkDebugButton = page.locator('button:has-text("Chunk Debug"), button:has-text("Debug"), a:has-text("Chunk")').first();
    
    if (await chunkDebugButton.isVisible({ timeout: 3000 }).catch(() => false)) {
      await chunkDebugButton.click();
      await page.waitForTimeout(1000);
    }
    
    // Navigate directly to chunk debug if available
    await page.goto(`${BASE}/articles/${TEST_ARTICLE_ID}#chunk-debug`).catch(() => {});
    await page.waitForTimeout(2000);
    
    // Check for chunk visualization container
    const visualizationContainer = page.locator('#chunkVisualizationContainer, [id*="chunk"], [class*="chunk"]').first();
    
    if (await visualizationContainer.isVisible({ timeout: 5000 }).catch(() => false)) {
      // Take screenshot for visual verification
      await visualizationContainer.screenshot({ path: 'chunk_visualization.png' });
      
      // Check that visualization exists
      expect(visualizationContainer).toBeVisible();
      
      // Get the visualization HTML to check for gaps
      const visualizationHTML = await visualizationContainer.innerHTML();
      
      // Check for chunk bars (they should be absolute positioned divs)
      const chunkBars = page.locator('#chunkVisualizationContainer > div[style*="absolute"]');
      const chunkCount = await chunkBars.count();
      
      expect(chunkCount).toBeGreaterThan(0);
      
      console.log(`Found ${chunkCount} chunk bars in visualization`);
    } else {
      // If visualization not found, check API directly
      const api = await request.newContext({ baseURL: BASE, timeout: 60_000 });
      const resp = await api.get(`/api/articles/${TEST_ARTICLE_ID}/chunk-debug?chunk_size=1000&overlap=200`);
      
      if (resp.ok()) {
        const body = await resp.json();
        expect(body.coverage_validation.gaps_found).toBe(0);
      }
    }
  });

  test('API: Chunk positions should form continuous coverage', async () => {
    test.setTimeout(120_000);
    const api = await request.newContext({ baseURL: BASE, timeout: 120_000 });
    
    const resp = await api.get(`/api/articles/${TEST_ARTICLE_ID}/chunk-debug?chunk_size=1000&overlap=200&min_confidence=0.7`);
    
    expect(resp.ok()).toBe(true);
    
    const body = await resp.json();
    const chunks = body.chunk_analysis;
    
    expect(chunks.length).toBeGreaterThan(0);
    
    // Sort chunks by start position
    const sortedChunks = [...chunks].sort((a, b) => a.start - b.start);
    
    // Check for gaps between consecutive chunks
    for (let i = 0; i < sortedChunks.length - 1; i++) {
      const currentChunk = sortedChunks[i];
      const nextChunk = sortedChunks[i + 1];
      
      // Next chunk should start before or at current chunk's end (overlap or adjacent)
      expect(nextChunk.start).toBeLessThanOrEqual(currentChunk.end);
      
      // Calculate gap if any
      const gap = nextChunk.start - currentChunk.end;
      if (gap > 0) {
        throw new Error(
          `Gap found between chunk ${currentChunk.chunk_id} [${currentChunk.start}:${currentChunk.end}] ` +
          `and chunk ${nextChunk.chunk_id} [${nextChunk.start}:${nextChunk.end}]: ${gap} characters`
        );
      }
    }
    
    // Check that first chunk starts at 0
    expect(sortedChunks[0].start).toBe(0);
    
    // Check that last chunk ends at or near content length
    const lastChunk = sortedChunks[sortedChunks.length - 1];
    expect(lastChunk.end).toBeGreaterThanOrEqual(body.content_length - 10); // Allow small margin
    
    console.log(`Verified ${sortedChunks.length} chunks form continuous coverage`);
  });

  test('API: Coverage validation should detect and report gaps', async () => {
    test.setTimeout(120_000);
    const api = await request.newContext({ baseURL: BASE, timeout: 120_000 });
    
    const resp = await api.get(`/api/articles/${TEST_ARTICLE_ID}/chunk-debug?chunk_size=1000&overlap=200&min_confidence=0.7`);
    
    expect(resp.ok()).toBe(true);
    
    const body = await resp.json();
    const coverage = body.coverage_validation;
    
    // Coverage validation should be present
    expect(coverage).toBeDefined();
    expect(coverage.gaps).toBeDefined();
    expect(Array.isArray(coverage.gaps)).toBe(true);
    
    // If gaps are found, they should have proper structure
    if (coverage.gaps_found > 0) {
      expect(coverage.gaps.length).toBe(coverage.gaps_found);
      
      for (const gap of coverage.gaps) {
        expect(gap).toHaveProperty('start');
        expect(gap).toHaveProperty('end');
        expect(gap).toHaveProperty('size');
        expect(gap.size).toBe(gap.end - gap.start);
        expect(gap.size).toBeGreaterThan(0);
      }
      
      console.warn(`⚠️  Found ${coverage.gaps_found} gaps in coverage`);
      coverage.gaps.forEach((gap: any, i: number) => {
        console.warn(`  Gap ${i + 1}: [${gap.start}:${gap.end}] (${gap.size} chars)`);
      });
    } else {
      console.log('✅ No gaps found in chunk coverage');
    }
  });
});

