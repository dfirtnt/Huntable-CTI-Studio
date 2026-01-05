import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const TEST_ARTICLE_ID = '68';

test.describe('Workflow Test Buttons', () => {
  test('test all "Test with Custom ArticleID" buttons with article 68', async ({ page }) => {
    // Navigate to workflow page
    await page.goto(`${BASE}/workflow`);
    await page.waitForLoadState('networkidle');
    
    // Wait for page to fully load
    await page.waitForTimeout(2000);
    
    // Set up dialog handler to automatically accept with article ID 68
    page.on('dialog', async dialog => {
      expect(dialog.type()).toBe('prompt');
      await dialog.accept(TEST_ARTICLE_ID);
    });
    
    // Find all "Test with Custom ArticleID" buttons
    const testButtons = page.locator('button:has-text("🎯 Test with Custom ArticleID")');
    const count = await testButtons.count();
    
    console.log(`Found ${count} test buttons`);
    
    // List of expected agents based on the code
    const expectedAgents = [
      'RankAgent',
      'CmdlineExtract',
      'SigExtract',
      'EventCodeExtract',
      'ProcTreeExtract',
      'RegExtract',
      'SigmaAgent'
    ];
    
    const results: Array<{agent: string, status: string, error?: string}> = [];
    
    // Test each button
    for (let i = 0; i < count; i++) {
      const button = testButtons.nth(i);
      
      // Get button's onclick to identify which agent it tests
      const onclick = await button.getAttribute('onclick');
      let agentName = `Button ${i + 1}`;
      
      if (onclick?.includes('testRankAgent')) {
        agentName = 'RankAgent';
      } else if (onclick?.includes('testSigmaAgent')) {
        agentName = 'SigmaAgent';
      } else if (onclick?.includes("testSubAgent('CmdlineExtract'")) {
        agentName = 'CmdlineExtract';
      } else if (onclick?.includes("testSubAgent('SigExtract'")) {
        agentName = 'SigExtract';
      } else if (onclick?.includes("testSubAgent('EventCodeExtract'")) {
        agentName = 'EventCodeExtract';
      } else if (onclick?.includes("testSubAgent('ProcTreeExtract'")) {
        agentName = 'ProcTreeExtract';
      } else if (onclick?.includes("testSubAgent('RegExtract'")) {
        agentName = 'RegExtract';
      }
      
      console.log(`Testing ${agentName}...`);
      
      try {
        // Wait for button to be visible and enabled
        await expect(button).toBeVisible({ timeout: 5000 });
        await expect(button).toBeEnabled({ timeout: 5000 });
        
        // Set up response listener for the API call
        const responsePromise = page.waitForResponse(
          (resp) => {
            const url = resp.url();
            return (
              url.includes('/api/workflow/config/test-') &&
              resp.request().method() === 'POST'
            );
          },
          { timeout: 10000 }
        );
        
        // Click the button
        await button.click();
        
        // Wait for API response
        const response = await responsePromise;
        const responseData = await response.json();
        
        // Verify response contains task_id
        expect(responseData).toHaveProperty('task_id');
        expect(response.status()).toBe(200);
        
        console.log(`✅ ${agentName}: Task ID ${responseData.task_id}`);
        
        results.push({
          agent: agentName,
          status: 'success',
        });
        
        // Wait a bit before next test
        await page.waitForTimeout(1000);
        
      } catch (error: any) {
        console.error(`❌ ${agentName} failed:`, error.message);
        results.push({
          agent: agentName,
          status: 'failed',
          error: error.message,
        });
      }
    }
    
    // Print summary
    console.log('\n=== Test Summary ===');
    results.forEach(r => {
      if (r.status === 'success') {
        console.log(`✅ ${r.agent}: PASSED`);
      } else {
        console.log(`❌ ${r.agent}: FAILED - ${r.error}`);
      }
    });
    
    // Verify all tests passed
    const failed = results.filter(r => r.status === 'failed');
    expect(failed.length).toBe(0);
  });
});

