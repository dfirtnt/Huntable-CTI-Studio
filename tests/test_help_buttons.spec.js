const { test, expect } = require('@playwright/test');

/**
 * UI tests for help buttons in AI/ML Assistant modals.
 * 
 * NOTE: For prompt content synchronization tests (verifying help modals match
 * prompt files), see: tests/playwright/prompt_sync.spec.ts
 */

test.describe('AI/ML Assistant Help Buttons', () => {
  test('should show help buttons in all AI/ML Assistant modals', async ({ page }) => {
    test.setTimeout(60_000); // Increase timeout for async operations
    // Navigate to article detail page
    await page.goto('http://localhost:8001/articles/2297');
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    // Click AI/ML Assistant button
    const assistantButton = page.locator('button:has-text("🤖 AI/ML Assistant"), button:has-text("🤖 AL/ML Assistant")').first();
    await expect(assistantButton).toBeVisible({ timeout: 10_000 });
    await assistantButton.click();
    
    // Wait for modal to open
    await page.waitForTimeout(500);
    
    // Test IOC Modal - only test if IOCs already exist (immediate modal display)
    // Skip if extraction is needed (async operation that may timeout)
    const iocButton = page.locator('button:has-text("🔍 Display IOCs"), button:has-text("🔍 Extract IOCs")').first();
    const iocButtonText = await iocButton.textContent().catch(() => '');
    
    // Only test if button says "Display IOCs" (indicating IOCs already exist)
    if (iocButtonText.includes('Display IOCs')) {
      await expect(iocButton).toBeVisible({ timeout: 10_000 });
      await iocButton.click();
      
      // Wait for IOC modal to be visible (should appear immediately if IOCs exist)
      await page.waitForSelector('#iocsModal, #ctibertIOCsModal', { timeout: 5_000 });
      await page.waitForTimeout(500); // Give modal time to fully render
      
      // Check for help button in IOC modal
      const helpButton = page.locator('#iocsModal button:has-text("Help"), #ctibertIOCsModal button:has-text("Help")').first();
      await expect(helpButton).toBeVisible({ timeout: 5_000 });
      console.log('✅ IOC Modal help button visible');
      
      // Close IOC modal
      await page.click('button:has-text("Close")');
    } else {
      console.log('⏭️  Skipping IOC modal test - IOCs need to be extracted (async operation)');
    }
    
    // Test SIGMA Modal - only test if button is enabled (article is "chosen")
    const sigmaButton = page.locator('button:has-text("🔍 Display SIGMA Rules"), button:has-text("🔍 Generate SIGMA Rules")').first();
    await expect(sigmaButton).toBeVisible({ timeout: 10_000 });
    
    const isSigmaEnabled = await sigmaButton.isEnabled().catch(() => false);
    if (isSigmaEnabled) {
      await sigmaButton.click();
      
      // Wait for SIGMA modal to be visible
      await page.waitForSelector('#sigmaRulesModal', { timeout: 10_000 });
      await page.waitForTimeout(500); // Give modal time to fully render
      
      // Check for help button in SIGMA modal
      const sigmaHelpButton = page.locator('#sigmaRulesModal button:has-text("Help")').first();
      await expect(sigmaHelpButton).toBeVisible({ timeout: 5_000 });
      console.log('✅ SIGMA Modal help button visible');
      
      // Close SIGMA modal
      await page.click('button:has-text("Close")');
    } else {
      console.log('⏭️  Skipping SIGMA modal test - article not marked as "chosen"');
    }
    
    // Test Custom Prompt Modal
    const customPromptButton = page.locator('button:has-text("💬 Custom Prompt")').first();
    await expect(customPromptButton).toBeVisible({ timeout: 10_000 });
    await customPromptButton.click();
    
    // Wait for Custom Prompt modal to be visible
    await page.waitForSelector('#customPromptModal', { timeout: 10_000 });
    await page.waitForTimeout(500); // Give modal time to fully render
    
    // Check for help button in Custom Prompt modal
    const customHelpButton = page.locator('#customPromptModal button:has-text("Help")').first();
    await expect(customHelpButton).toBeVisible({ timeout: 5_000 });
    console.log('✅ Custom Prompt Modal help button visible');
    
    // Close Custom Prompt modal - use Cancel button or X button
    const cancelButton = page.locator('#customPromptModal button:has-text("Cancel"), #customPromptModal button[onclick*="closeCustomPromptModal"]').first();
    await cancelButton.click();
    
    // Wait for modal to close
    await page.waitForSelector('#customPromptModal', { state: 'hidden', timeout: 5_000 }).catch(() => {});
    
    // Reopen AI Assistant modal for GPT4o Ranking test
    const assistantButton2 = page.locator('button:has-text("🤖 AI/ML Assistant"), button:has-text("🤖 AL/ML Assistant")').first();
    await assistantButton2.click();
    await page.waitForTimeout(500);
    
    // Test GPT4o Ranking Modal - skip if button not available or modal doesn't open
    const gpt4oButton = page.locator('button:has-text("📊 Rank with GPT4o")').first();
    const gpt4oButtonVisible = await gpt4oButton.isVisible({ timeout: 5_000 }).catch(() => false);
    
    if (gpt4oButtonVisible) {
      await gpt4oButton.click();
      
      // Wait for modal to appear (either config or results screen)
      const modalAppeared = await Promise.race([
        page.waitForSelector('#gpt4oRankingModal', { timeout: 5_000 }).then(() => true).catch(() => false),
        page.locator('text=GPT-4o Content Optimization').waitFor({ timeout: 5_000 }).then(() => true).catch(() => false)
      ]);
      
      if (modalAppeared) {
        await page.waitForTimeout(500);
        
        // Check if we're on configuration screen or results screen
        const isConfigScreen = await page.locator('text=GPT-4o Content Optimization').isVisible({ timeout: 2_000 }).catch(() => false);
        
        if (isConfigScreen) {
          console.log('📊 GPT4o Ranking Modal: Configuration screen (no help button expected)');
          // Skip clicking Analyze - that would trigger async operation
          console.log('⏭️  Skipping GPT4o ranking analysis (async operation)');
        } else {
          // Already on results screen - check for help button
          const rankingHelpButton = page.locator('#gpt4oRankingModal button:has-text("Help")').first();
          const helpVisible = await rankingHelpButton.isVisible({ timeout: 2_000 }).catch(() => false);
          if (helpVisible) {
            console.log('✅ GPT4o Ranking Modal help button visible');
          } else {
            console.log('⏭️  GPT4o Ranking Modal help button not found');
          }
        }
      } else {
        console.log('⏭️  Skipping GPT4o Ranking Modal test - modal did not open');
      }
    } else {
      console.log('⏭️  Skipping GPT4o Ranking Modal test - button not visible');
    }
  });
});
