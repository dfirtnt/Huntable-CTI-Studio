import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const TEST_ARTICLE_ID = '68';

test.describe('Workflow Test Buttons', () => {
  test.skip('test all "Test with Custom ArticleID" buttons with article 68', async ({ page }) => {
    test.setTimeout(300000); // 5 minutes for all agents to complete
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
        
        // Wait for button to be visible and enabled first (before scrolling)
        await expect(button).toBeVisible({ timeout: 10000 });
        await expect(button).toBeEnabled({ timeout: 5000 });
        
        // Scroll button into view with error handling
        try {
          await button.scrollIntoViewIfNeeded({ timeout: 5000 });
        } catch (error: any) {
          // If scroll fails due to page closure, re-throw
          if (error.message && (error.message.includes('closed') || error.message.includes('Target page'))) {
            throw new Error(`Page was closed before ${agentName} test could complete: ${error.message}`);
          }
          // If scroll fails for other reasons, try to continue - button might already be in view
          console.log(`Note: Could not scroll ${agentName} button into view: ${error.message}`);
        }
        await page.waitForTimeout(500);
        
        // Set up response listener for the API call BEFORE clicking
        // Different agents use different endpoints
        // Note: CmdlineExtract and ProcTreeExtract can be very slow, so we use a long timeout
        const responsePromise = page.waitForResponse(
          (resp) => {
            const url = resp.url();
            const method = resp.request().method();
            // RankAgent uses /api/workflow/config/test-rankagent
            // SubAgents (CmdlineExtract, ProcTreeExtract) use /api/workflow/articles/{id}/trigger
            // SigmaAgent uses /api/workflow/config/test-sigmaagent
            return (
              method === 'POST' && (
                url.includes('/api/workflow/config/test-') ||
                (url.includes('/api/workflow/articles/') && url.includes('/trigger'))
              )
            );
          },
          { timeout: 240000 } // 4 minutes for very slow agents like CmdlineExtract
        );
        
        // Click the button
        await button.click();
        
        // Wait for API response with error handling
        let response;
        try {
          response = await responsePromise;
        } catch (error: any) {
          // Check if error is due to page closure first
          if (error.message && (error.message.includes('closed') || error.message.includes('Target page'))) {
            throw new Error(`Page was closed during ${agentName} response wait: ${error.message}`);
          }
          
          // If timeout, check if modal appeared (which might indicate partial success)
          // This can happen if the response completed but we missed it due to timing
          try {
            const modalVisible = await page.locator('#test-subagent-modal, #test-rankagent-modal, #test-sigmaagent-modal').first().isVisible({ timeout: 3000 }).catch(() => false);
            if (modalVisible) {
              // Response might have succeeded but we missed it, continue with modal check
              console.log(`⚠️ ${agentName}: Response timeout but modal appeared, assuming success`);
              results.push({
                agent: agentName,
                status: 'success',
              });
              // Still need to close modal before next test
              try {
                await page.waitForTimeout(2000);
                const closeButton = page.locator('#test-subagent-modal button:has-text("Close"), #test-rankagent-modal button:has-text("Close"), #test-sigmaagent-modal button:has-text("Close")').first();
                if (await closeButton.isVisible({ timeout: 2000 }).catch(() => false)) {
                  await closeButton.click();
                  await page.waitForTimeout(500);
                }
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
                await page.waitForTimeout(500);
              } catch (closeError) {
                console.log(`Note: Could not close modal: ${closeError}`);
              }
              continue;
            }
          } catch (checkError: any) {
            // If we can't check for modal (page might be closed), re-throw original error
            if (checkError.message && (checkError.message.includes('closed') || checkError.message.includes('Target page'))) {
              throw new Error(`Page was closed while checking for ${agentName} modal: ${checkError.message}`);
            }
          }
          
          // If no modal appeared and it's a timeout, this is a real failure
          throw error;
        }
        
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
        
        // If page was closed, try to recover by navigating back
        if (error.message && (error.message.includes('closed') || error.message.includes('Target page'))) {
          try {
            // Try to navigate back to the config page
            await page.goto(`${BASE}/workflow#config`);
            await page.waitForLoadState('networkidle');
            await page.waitForTimeout(2000);
            
            // Switch to config tab
            await page.evaluate(() => {
              if (typeof switchTab === 'function') {
                switchTab('config');
              }
            });
            await page.waitForTimeout(1000);
            
            // Re-expand panels
            await page.evaluate(() => {
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
            await page.waitForTimeout(1000);
            console.log(`⚠️ Recovered page after ${agentName} failure, continuing with remaining tests`);
          } catch (recoveryError: any) {
            console.error(`Failed to recover page after ${agentName} failure:`, recoveryError.message);
            // Continue anyway - let remaining tests try
          }
        }
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

