import { test, expect } from '@playwright/test';

/**
 * Tests for SIGMA rule Enrich functionality.
 * 
 * Tests:
 * - Enrich button visibility and clickability
 * - Enrich modal opens/closes correctly
 * - Enrich modal UI elements
 * - Enrich API integration
 * - Error handling
 */

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

test.describe('SIGMA Enrich Functionality', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to sigma queue page
    await page.goto(`${BASE}/sigma-queue`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000); // Wait for page to fully initialize
    
    // Wait for page to be ready - check for any visible content
    await page.waitForSelector('body', { state: 'visible' });
  });

  test('should display enrich button in rule preview modal', async ({ page }) => {
    // Wait for queue table body to exist (it may be empty)
    await page.waitForSelector('#queueTableBody', { timeout: 15000, state: 'attached' });
    await page.waitForTimeout(2000); // Wait for queue to potentially load
    
    // Check if there are rules in the queue
    const queueRows = page.locator('#queueTableBody tr');
    const rowCount = await queueRows.count();
    
    if (rowCount > 0) {
      const firstRowText = await queueRows.first.textContent();
      if (firstRowText && !firstRowText.includes('No queued rules')) {
        // Click Preview button on first rule
        const previewButton = page.locator('button:has-text("Preview")').first();
        await expect(previewButton).toBeVisible({ timeout: 5000 });
        await previewButton.click();
        
        // Wait for rule modal to open
        const ruleModal = page.locator('#ruleModal');
        await expect(ruleModal).toBeVisible({ timeout: 5000 });
        await expect(ruleModal).not.toHaveClass(/hidden/);
        
        // Check for Enrich button in action buttons
        const enrichButton = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")');
        await expect(enrichButton).toBeVisible({ timeout: 2000 });
      } else {
        test.skip();
      }
    } else {
      // Skip test if no rules available
      test.skip();
    }
  });

  test('should open enrich modal when enrich button is clicked', async ({ page }) => {
    // Wait for queue table body to exist (it may be empty)
    await page.waitForSelector('#queueTableBody', { timeout: 15000, state: 'attached' });
    
    // Wait a bit for queue to potentially load
    await page.waitForTimeout(2000);
    
    const queueRows = page.locator('#queueTableBody tr');
    const rowCount = await queueRows.count();
    
    if (rowCount > 0 && !(await queueRows.first.textContent()).includes('No queued rules')) {
      // Open rule preview modal
      const previewButton = page.locator('button:has-text("Preview")').first();
      await previewButton.click();
      
      // Wait for rule modal
      const ruleModal = page.locator('#ruleModal');
      await expect(ruleModal).toBeVisible({ timeout: 5000 });
      
      // Click Enrich button
      const enrichButton = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first();
      await expect(enrichButton).toBeVisible({ timeout: 2000 });
      await enrichButton.click();
      
      // Wait for enrich modal to open
      const enrichModal = page.locator('#enrichModal');
      await expect(enrichModal).toBeVisible({ timeout: 5000 });
      await expect(enrichModal).not.toHaveClass(/hidden/);
    } else {
      test.skip();
    }
  });

  test('should display enrich modal UI elements', async ({ page }) => {
    await page.waitForSelector('#queueTableBody', { timeout: 15000, state: 'attached' });
    await page.waitForTimeout(2000);
    
    const queueRows = page.locator('#queueTableBody tr');
    const rowCount = await queueRows.count();
    
    if (rowCount > 0) {
      // Open rule preview and enrich modal
      const previewButton = page.locator('button:has-text("Preview")').first();
      await previewButton.click();
      
      const ruleModal = page.locator('#ruleModal');
      await expect(ruleModal).toBeVisible({ timeout: 5000 });
      
      const enrichButton = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first();
      await enrichButton.click();
      
      const enrichModal = page.locator('#enrichModal');
      await expect(enrichModal).toBeVisible({ timeout: 5000 });
      
      // Check for key UI elements
      await expect(page.locator('#enrichOriginalRule')).toBeVisible();
      await expect(page.locator('#enrichInstruction')).toBeVisible();
      await expect(page.locator('#enrichBtn')).toBeVisible();
      await expect(page.locator('button:has-text("Cancel")')).toBeVisible();
      
      // Check that result/error sections are initially hidden
      const enrichResult = page.locator('#enrichResult');
      const enrichError = page.locator('#enrichError');
      
      // These should be hidden initially
      const resultClasses = await enrichResult.getAttribute('class');
      const errorClasses = await enrichError.getAttribute('class');
      
      expect(resultClasses).toContain('hidden');
      expect(errorClasses).toContain('hidden');
    } else {
      test.skip();
    }
  });

  test('should close enrich modal when cancel button is clicked', async ({ page }) => {
    await page.waitForSelector('#queueTableBody', { timeout: 15000, state: 'attached' });
    await page.waitForTimeout(2000);
    
    const queueRows = page.locator('#queueTableBody tr');
    const rowCount = await queueRows.count();
    
    if (rowCount > 0) {
      // Open rule preview and enrich modal
      const previewButton = page.locator('button:has-text("Preview")').first();
      await previewButton.click();
      
      const ruleModal = page.locator('#ruleModal');
      await expect(ruleModal).toBeVisible({ timeout: 5000 });
      
      const enrichButton = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first();
      await enrichButton.click();
      
      const enrichModal = page.locator('#enrichModal');
      await expect(enrichModal).toBeVisible({ timeout: 5000 });
      
      // Click Cancel button
      const cancelButton = page.locator('#enrichModal button:has-text("Cancel")');
      await cancelButton.click();
      
      // Wait for modal to close
      await expect(enrichModal).toHaveClass(/hidden/, { timeout: 2000 });
    } else {
      test.skip();
    }
  });

  test('should close enrich modal with Escape key', async ({ page }) => {
    await page.waitForSelector('#queueTableBody', { timeout: 15000, state: 'attached' });
    await page.waitForTimeout(2000);
    
    const queueRows = page.locator('#queueTableBody tr');
    const rowCount = await queueRows.count();
    
    if (rowCount > 0) {
      // Open rule preview and enrich modal
      const previewButton = page.locator('button:has-text("Preview")').first();
      await previewButton.click();
      
      const ruleModal = page.locator('#ruleModal');
      await expect(ruleModal).toBeVisible({ timeout: 5000 });
      
      const enrichButton = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first();
      await enrichButton.click();
      
      const enrichModal = page.locator('#enrichModal');
      await expect(enrichModal).toBeVisible({ timeout: 5000 });
      
      // Press Escape key
      await page.keyboard.press('Escape');
      
      // Wait for modal to close
      await expect(enrichModal).toHaveClass(/hidden/, { timeout: 2000 });
    } else {
      test.skip();
    }
  });

  test('should populate enrich modal with rule YAML', async ({ page }) => {
    await page.waitForSelector('#queueTableBody', { timeout: 15000, state: 'attached' });
    await page.waitForTimeout(2000);
    
    const queueRows = page.locator('#queueTableBody tr');
    const rowCount = await queueRows.count();
    
    if (rowCount > 0) {
      // Open rule preview and enrich modal
      const previewButton = page.locator('button:has-text("Preview")').first();
      await previewButton.click();
      
      const ruleModal = page.locator('#ruleModal');
      await expect(ruleModal).toBeVisible({ timeout: 5000 });
      
      // Get rule YAML from preview modal (if visible)
      const ruleYamlPreview = page.locator('#ruleModal pre, #ruleModal textarea').first();
      let expectedYaml = '';
      if (await ruleYamlPreview.isVisible()) {
        expectedYaml = await ruleYamlPreview.textContent() || '';
      }
      
      const enrichButton = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first();
      await enrichButton.click();
      
      const enrichModal = page.locator('#enrichModal');
      await expect(enrichModal).toBeVisible({ timeout: 5000 });
      
      // Check that original rule YAML is populated
      const originalRuleTextarea = page.locator('#enrichOriginalRule');
      await expect(originalRuleTextarea).toBeVisible();
      
      const originalYaml = await originalRuleTextarea.inputValue();
      expect(originalYaml.length).toBeGreaterThan(0);
      
      // If we got YAML from preview, verify it matches
      if (expectedYaml.length > 0) {
        // Normalize whitespace for comparison
        const normalizedOriginal = originalYaml.trim().replace(/\s+/g, ' ');
        const normalizedExpected = expectedYaml.trim().replace(/\s+/g, ' ');
        expect(normalizedOriginal).toContain(normalizedExpected.substring(0, 50));
      }
    } else {
      test.skip();
    }
  });

  test('should show error when enrich API fails', async ({ page }) => {
    await page.waitForSelector('#queueTableBody', { timeout: 15000, state: 'attached' });
    await page.waitForTimeout(2000);
    
    const queueRows = page.locator('#queueTableBody tr');
    const rowCount = await queueRows.count();
    
    if (rowCount > 0) {
      // Mock API failure
      await page.route('**/api/sigma-queue/*/enrich', async route => {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({ error: 'Internal server error' })
        });
      });
      
      // Open rule preview and enrich modal
      const previewButton = page.locator('button:has-text("Preview")').first();
      await previewButton.click();
      
      const ruleModal = page.locator('#ruleModal');
      await expect(ruleModal).toBeVisible({ timeout: 5000 });
      
      const enrichButton = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first();
      await enrichButton.click();
      
      const enrichModal = page.locator('#enrichModal');
      await expect(enrichModal).toBeVisible({ timeout: 5000 });
      
      // Click Enrich Rule button
      const enrichRuleButton = page.locator('#enrichBtn');
      await enrichRuleButton.click();
      
      // Wait for error to appear
      const enrichError = page.locator('#enrichError');
      await expect(enrichError).toBeVisible({ timeout: 10000 });
      await expect(enrichError).not.toHaveClass(/hidden/);
      
      // Verify error message is displayed
      const errorText = await enrichError.textContent();
      expect(errorText).toBeTruthy();
      expect(errorText!.length).toBeGreaterThan(0);
    } else {
      test.skip();
    }
  });

  test('should handle enrich button click without API key', async ({ page }) => {
    await page.waitForSelector('#queueTableBody', { timeout: 15000, state: 'attached' });
    await page.waitForTimeout(2000);
    
    const queueRows = page.locator('#queueTableBody tr');
    const rowCount = await queueRows.count();
    
    if (rowCount > 0) {
      // Mock API response for missing API key
      await page.route('**/api/sigma-queue/*/enrich', async route => {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ 
            error: 'API key is required',
            message: 'Please configure your OpenAI API key in Settings first.'
          })
        });
      });
      
      // Open rule preview and enrich modal
      const previewButton = page.locator('button:has-text("Preview")').first();
      await previewButton.click();
      
      const ruleModal = page.locator('#ruleModal');
      await expect(ruleModal).toBeVisible({ timeout: 5000 });
      
      const enrichButton = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first();
      await enrichButton.click();
      
      const enrichModal = page.locator('#enrichModal');
      await expect(enrichModal).toBeVisible({ timeout: 5000 });
      
      // Click Enrich Rule button
      const enrichRuleButton = page.locator('#enrichBtn');
      await enrichRuleButton.click();
      
      // Wait for error message about API key
      const enrichError = page.locator('#enrichError');
      await expect(enrichError).toBeVisible({ timeout: 10000 });
      
      const errorText = await enrichError.textContent();
      expect(errorText).toContain('API key');
    } else {
      test.skip();
    }
  });

  test('should disable enrich button during enrichment', async ({ page }) => {
    await page.waitForSelector('#queueTableBody', { timeout: 15000, state: 'attached' });
    await page.waitForTimeout(2000);
    
    const queueRows = page.locator('#queueTableBody tr');
    const rowCount = await queueRows.count();
    
    if (rowCount > 0) {
      // Mock slow API response
      await page.route('**/api/sigma-queue/*/enrich', async route => {
        await new Promise(resolve => setTimeout(resolve, 2000));
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            enriched_yaml: 'title: Test Rule\nid: test-123',
            message: 'Rule enriched successfully'
          })
        });
      });
      
      // Open rule preview and enrich modal
      const previewButton = page.locator('button:has-text("Preview")').first();
      await previewButton.click();
      
      const ruleModal = page.locator('#ruleModal');
      await expect(ruleModal).toBeVisible({ timeout: 5000 });
      
      const enrichButton = page.locator('button:has-text("✨ Enrich"), button:has-text("Enrich")').first();
      await enrichButton.click();
      
      const enrichModal = page.locator('#enrichModal');
      await expect(enrichModal).toBeVisible({ timeout: 5000 });
      
      // Click Enrich Rule button
      const enrichRuleButton = page.locator('#enrichBtn');
      await enrichRuleButton.click();
      
      // Check that button is disabled and shows loading state
      await expect(enrichRuleButton).toBeDisabled({ timeout: 1000 });
      
      // Check for loading indicator text
      const buttonText = await enrichRuleButton.textContent();
      expect(buttonText).toContain('Enriching');
    } else {
      test.skip();
    }
  });
});
