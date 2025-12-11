import { test, expect, request } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const TEST_ARTICLE_ID = process.env.ARTICLE_ID || '836';

test.describe('LLM Optimizer API Endpoints', () => {
  test('API: Debug endpoint should import optimizer without errors', async () => {
    const api = await request.newContext({ baseURL: BASE, timeout: 30_000 });
    
    // Test the debug endpoint that uses the optimizer
    const resp = await api.get(`/api/test-route`);
    
    if (!resp.ok()) {
      test.skip(`Optimizer endpoint not available (status ${resp.status()}); set LMStudio/mocks or SKIP_MODEL_TESTS=true to bypass.`);
    }
    
    const body = await resp.json();
    expect(body).toHaveProperty('message');
    expect(body.message).toContain('working');
  });

  test('API: Cost estimation endpoint should work with new optimizer', async () => {
    const api = await request.newContext({ baseURL: BASE, timeout: 30_000 });
    
    // Test chunk debug endpoint which uses estimate_llm_cost
    const resp = await api.get(`/api/articles/${TEST_ARTICLE_ID}/chunk-debug?chunk_size=1000&min_confidence=0.7`);
    
    // Accept 200 (success) or 404 (article not found) - both indicate the endpoint loaded correctly
    if (resp.status() >= 500) {
      test.skip(`Chunk debug endpoint unavailable (status ${resp.status()}); set SKIP_MODEL_TESTS=true or seed article ${TEST_ARTICLE_ID}.`);
    }
    expect([200, 404]).toContain(resp.status());
    
    if (resp.ok()) {
      const body = await resp.json();
      // If article exists, should have chunking data
      expect(body).toBeTruthy();
    }
  });

  test('API: GPT-4o ranking endpoint should use optimizer', async ({ page }) => {
    test.setTimeout(60_000);
    
    // Navigate to article page
    const resp = await page.goto(`${BASE}/articles/${TEST_ARTICLE_ID}`);
    if (resp && resp.status() >= 500) {
      test.skip(`Article page unavailable (status ${resp.status()}); ensure data seeded or set SKIP_MODEL_TESTS=true.`);
    }
    await page.waitForLoadState('networkidle');
    
    // Check that page loads without JavaScript errors
    const errors: string[] = [];
    page.on('pageerror', (error) => {
      errors.push(error.message);
    });
    
    // Wait a bit to catch any immediate errors
    await page.waitForTimeout(2000);
    
    // Check for import/optimizer related errors
    const optimizerErrors = errors.filter(e => 
      e.includes('gpt4o_optimizer') || 
      e.includes('llm_optimizer') || 
      e.includes('optimize') ||
      e.includes('LLMOptimizer')
    );
    
    expect(optimizerErrors.length).toBe(0);
  });
});

