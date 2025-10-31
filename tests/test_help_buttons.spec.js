const { test, expect } = require('@playwright/test');

/**
 * UI tests for help buttons in AI/ML Assistant modals.
 * 
 * NOTE: For prompt content synchronization tests (verifying help modals match
 * prompt files), see: tests/playwright/prompt_sync.spec.ts
 */

test.describe('AI/ML Assistant Help Buttons', () => {
  test('should show help buttons in all AI/ML Assistant modals', async ({ page }) => {
    // Navigate to article detail page
    await page.goto('http://localhost:8001/articles/2297');
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    // Click AI/ML Assistant button
    await page.click('button:has-text("🤖 AL/ML Assistant")');
    
    // Test IOC Modal
    await page.click('button:has-text("🔍 Display IOCs")');
    await expect(page.locator('button:has-text("Help")')).toBeVisible();
    console.log('✅ IOC Modal help button visible');
    
    // Close IOC modal
    await page.click('button:has-text("Close")');
    
    // Test SIGMA Modal
    await page.click('button:has-text("🔍 Display SIGMA Rules")');
    await expect(page.locator('button:has-text("Help")')).toBeVisible();
    console.log('✅ SIGMA Modal help button visible');
    
    // Close SIGMA modal
    await page.click('button:has-text("Close")');
    
    // Test Custom Prompt Modal
    await page.click('button:has-text("💬 Custom Prompt")');
    await expect(page.locator('button:has-text("Help")')).toBeVisible();
    console.log('✅ Custom Prompt Modal help button visible');
    
    // Close Custom Prompt modal
    await page.click('button:has-text("Close")');
    
    // Test GPT4o Ranking Modal (configuration screen)
    await page.click('button:has-text("📊 Rank with GPT4o")');
    
    // Check if we're on configuration screen or results screen
    const isConfigScreen = await page.locator('text=GPT-4o Content Optimization').isVisible();
    
    if (isConfigScreen) {
      console.log('📊 GPT4o Ranking Modal: Configuration screen (no help button expected)');
      // Click Analyze to trigger ranking
      await page.click('button:has-text("Analyze")');
      
      // Wait for results screen
      await page.waitForSelector('text=GPT-4O SIGMA Huntability Analysis', { timeout: 30000 });
      
      // Check for help button on results screen
      await expect(page.locator('button:has-text("Help")')).toBeVisible();
      console.log('✅ GPT4o Ranking Modal help button visible on results screen');
    } else {
      // Already on results screen
      await expect(page.locator('button:has-text("Help")')).toBeVisible();
      console.log('✅ GPT4o Ranking Modal help button visible');
    }
  });
});
