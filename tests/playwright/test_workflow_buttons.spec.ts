import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const TEST_ARTICLE_ID = '68';

test.describe('Workflow Test Buttons', () => {
  test('test all "Test with Custom ArticleID" buttons with article 68', async ({ page }) => {
    // Navigate to workflow config tab
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    
    // Wait for page to fully load and config to load
    await page.waitForTimeout(3000);
    
    // Ensure we're on the config tab
    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(1000);
    
    // Wait for config form to be visible
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    await page.waitForTimeout(2000);
    
    // Use JavaScript to expand all collapsible panels at once
    await page.evaluate(() => {
      // All panels that need to be expanded
      const panelsToExpand = [
        'rank-agent-configs-panel',
        'extract-agent-panel',
        'cmdlineextract-agent-panel',
        'proctreeextract-agent-panel',
        'sigma-agent-panel'
      ];
      
      panelsToExpand.forEach(panelId => {
        const content = document.getElementById(`${panelId}-content`);
        const toggle = document.getElementById(`${panelId}-toggle`);
        
        if (content && content.classList.contains('hidden')) {
          content.classList.remove('hidden');
          if (toggle) {
            toggle.textContent = '▲';
            toggle.style.transform = 'rotate(0deg)';
          }
        }
      });
    });
    
    // Wait for panels to be visible
    await page.waitForTimeout(1000);
    
    // Set up dialog handler to automatically accept with article ID 68
    page.on('dialog', async dialog => {
      expect(dialog.type()).toBe('prompt');
      await dialog.accept(TEST_ARTICLE_ID);
    });
    
    // Define all buttons to test with their selectors
    const buttonsToTest = [
      { agentName: 'RankAgent', selector: 'button[onclick*="testRankAgent"]' },
      { agentName: 'CmdlineExtract', selector: 'button[onclick*="testSubAgent(\'CmdlineExtract\'"]' },
      { agentName: 'ProcTreeExtract', selector: 'button[onclick*="testSubAgent(\'ProcTreeExtract\'"]' },
      { agentName: 'SigmaAgent', selector: 'button[onclick*="testSigmaAgent"]' },
    ];
    
    const results: Array<{agent: string, status: string, error?: string}> = [];
    
    // Test each button
    for (const { agentName, selector } of buttonsToTest) {
      console.log(`Testing ${agentName}...`);
      
      try {
        // Find button by selector
        const button = page.locator(selector).filter({ hasText: 'Test with Custom ArticleID' }).first();
        
        // Scroll button into view
        await button.scrollIntoViewIfNeeded();
        await page.waitForTimeout(500);
        
        // Wait for button to be visible and enabled
        await expect(button).toBeVisible({ timeout: 10000 });
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
          { timeout: 60000 }
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
        
        // Close any open modals before next test
        try {
          // Wait a bit for modal to show results
          await page.waitForTimeout(2000);
          
          // Try to close modal via close button
          const closeButton = page.locator('#test-subagent-modal button:has-text("Close"), #test-rankagent-modal button:has-text("Close"), #test-sigmaagent-modal button:has-text("Close")').first();
          if (await closeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
            await closeButton.click();
            await page.waitForTimeout(500);
          }
          
          // Force close modals via JavaScript if still open
          await page.evaluate(() => {
            const modals = ['test-subagent-modal', 'test-rankagent-modal', 'test-sigmaagent-modal'];
            modals.forEach(modalId => {
              const modal = document.getElementById(modalId);
              if (modal) {
                modal.classList.add('hidden');
                modal.style.display = 'none';
              }
            });
          });
          
          // Wait for modals to be hidden
          await page.waitForTimeout(500);
        } catch (error) {
          // Modal might already be closed, continue
          console.log(`Note: Could not close modal (might already be closed): ${error}`);
        }
        
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

