const { test, expect } = require('@playwright/test');

test.describe('ML Hunt Comparison Terminal', () => {
  test('terminal should show real-time logs when processing articles', async ({ page }) => {
    // Navigate to the ML Hunt Comparison page
    await page.goto('http://127.0.0.1:8001/ml-hunt-comparison');
    
    // Wait for page to load
    await page.waitForLoadState('networkidle');
    
    // Check that the page loaded correctly
    await expect(page.locator('h1')).toContainText('ML vs Hunt Scoring Comparison');
    
    // Click the "Process All Eligible Articles" button
    const processBtn = page.locator('#processEligibleBtn');
    await expect(processBtn).toBeVisible();
    await processBtn.click();
    
    // Wait for terminal to appear
    const terminalDiv = page.locator('#terminalOutput');
    await expect(terminalDiv).toBeVisible({ timeout: 10000 });
    
    // Check that terminal shows processing logs
    const terminalContent = page.locator('#terminalContent');
    await expect(terminalContent).toBeVisible();
    
    // Wait for logs to appear (not just "Fetching logs...")
    await page.waitForFunction(() => {
      const content = document.getElementById('terminalContent');
      return content && content.textContent && 
             content.textContent.includes('Processing article') && 
             !content.textContent.includes('🔄 Fetching logs...');
    }, { timeout: 30000 });
    
    // Verify that actual processing logs are shown
    const logText = await terminalContent.textContent();
    expect(logText).toContain('Processing article');
    expect(logText).not.toContain('🔄 Fetching logs...');
    
    console.log('Terminal content:', logText.substring(0, 200) + '...');
  });
  
  test('logs API endpoint should return valid data', async ({ page }) => {
    // Test the API endpoint directly
    const response = await page.request.get('http://127.0.0.1:8001/api/ml-hunt-comparison/logs');
    expect(response.ok()).toBeTruthy();
    
    const data = await response.json();
    expect(data.success).toBe(true);
    expect(data.logs).toBeDefined();
    expect(data.logs.length).toBeGreaterThan(0);
    
    console.log('API Response:', data.logs.substring(0, 200) + '...');
  });
});
