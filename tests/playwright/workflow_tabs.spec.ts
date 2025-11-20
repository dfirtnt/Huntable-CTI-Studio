import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

test.describe('Workflow Agent Config Subpages', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow`);
    await page.waitForLoadState('networkidle');
  });

  test('should display all three tab buttons', async ({ page }) => {
    // Verify all three tab buttons are visible
    const configTab = page.locator('#tab-config');
    const executionsTab = page.locator('#tab-executions');
    const queueTab = page.locator('#tab-queue');

    await expect(configTab).toBeVisible();
    await expect(executionsTab).toBeVisible();
    await expect(queueTab).toBeVisible();

    // Verify tab button text
    await expect(configTab).toContainText('Configuration');
    await expect(executionsTab).toContainText('Executions');
    await expect(queueTab).toContainText('SIGMA Queue');
  });

  test('should show Configuration tab content when clicked', async ({ page }) => {
    // Click Configuration tab
    await page.locator('#tab-config').click();
    await page.waitForTimeout(500);

    // Verify Configuration tab content is visible
    const configContent = page.locator('#tab-content-config');
    await expect(configContent).toBeVisible();
    await expect(configContent).not.toHaveClass(/hidden/);

    // Verify Configuration tab button is active
    const configTab = page.locator('#tab-config');
    await expect(configTab).toHaveClass(/border-purple-500/);

    // Verify Configuration-specific content exists
    await expect(page.locator('#workflowConfigForm')).toBeVisible();
    await expect(page.locator('#description')).toBeVisible();
    
    // Verify other tabs are hidden
    await expect(page.locator('#tab-content-executions')).toHaveClass(/hidden/);
    await expect(page.locator('#tab-content-queue')).toHaveClass(/hidden/);
  });

  test('should show Executions tab content when clicked', async ({ page }) => {
    // Click Executions tab
    await page.locator('#tab-executions').click();
    await page.waitForTimeout(500);

    // Verify Executions tab content is visible
    const executionsContent = page.locator('#tab-content-executions');
    await expect(executionsContent).toBeVisible();
    await expect(executionsContent).not.toHaveClass(/hidden/);

    // Verify Executions tab button is active
    const executionsTab = page.locator('#tab-executions');
    await expect(executionsTab).toHaveClass(/border-purple-500/);

    // Verify Executions-specific content exists
    await expect(executionsContent.locator('button:has-text("Refresh")')).toBeVisible();
    await expect(executionsContent.locator('button:has-text("Trigger Workflow")')).toBeVisible();
    await expect(page.locator('#executionStats')).toBeVisible();
    await expect(page.locator('#executionsTableBody')).toBeVisible();

    // Verify other tabs are hidden
    await expect(page.locator('#tab-content-config')).toHaveClass(/hidden/);
    await expect(page.locator('#tab-content-queue')).toHaveClass(/hidden/);
  });

  test('should show Queue tab content when clicked', async ({ page }) => {
    // Click Queue tab
    await page.locator('#tab-queue').click();
    await page.waitForTimeout(500);

    // Verify Queue tab content is visible
    const queueContent = page.locator('#tab-content-queue');
    await expect(queueContent).toBeVisible();
    await expect(queueContent).not.toHaveClass(/hidden/);

    // Verify Queue tab button is active
    const queueTab = page.locator('#tab-queue');
    await expect(queueTab).toHaveClass(/border-purple-500/);

    // Verify Queue-specific content exists
    await expect(queueContent.locator('button:has-text("Refresh")')).toBeVisible();
    await expect(page.locator('#queueStats')).toBeVisible();
    await expect(page.locator('#pendingCount')).toBeVisible();
    await expect(page.locator('#approvedCount')).toBeVisible();

    // Verify other tabs are hidden
    await expect(page.locator('#tab-content-config')).toHaveClass(/hidden/);
    await expect(page.locator('#tab-content-executions')).toHaveClass(/hidden/);
  });

  test('should navigate to Configuration tab via hash URL', async ({ page }) => {
    // Navigate directly to config hash
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    // Verify Configuration tab content is visible
    const configContent = page.locator('#tab-content-config');
    await expect(configContent).toBeVisible();
    await expect(configContent).not.toHaveClass(/hidden/);

    // Verify Configuration tab button is active
    const configTab = page.locator('#tab-config');
    await expect(configTab).toHaveClass(/border-purple-500/);

    // Verify URL hash is correct
    expect(page.url()).toContain('#config');
  });

  test('should navigate to Executions tab via hash URL', async ({ page }) => {
    // Navigate directly to executions hash
    await page.goto(`${BASE}/workflow#executions`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    // Verify Executions tab content is visible
    const executionsContent = page.locator('#tab-content-executions');
    await expect(executionsContent).toBeVisible();
    await expect(executionsContent).not.toHaveClass(/hidden/);

    // Verify Executions tab button is active
    const executionsTab = page.locator('#tab-executions');
    await expect(executionsTab).toHaveClass(/border-purple-500/);

    // Verify URL hash is correct
    expect(page.url()).toContain('#executions');
  });

  test('should navigate to Queue tab via hash URL', async ({ page }) => {
    // Navigate directly to queue hash
    await page.goto(`${BASE}/workflow#queue`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(500);

    // Verify Queue tab content is visible
    const queueContent = page.locator('#tab-content-queue');
    await expect(queueContent).toBeVisible();
    await expect(queueContent).not.toHaveClass(/hidden/);

    // Verify Queue tab button is active
    const queueTab = page.locator('#tab-queue');
    await expect(queueTab).toHaveClass(/border-purple-500/);

    // Verify URL hash is correct
    expect(page.url()).toContain('#queue');
  });

  test('should switch between all tabs sequentially', async ({ page }) => {
    // Start with Configuration
    await page.locator('#tab-config').click();
    await page.waitForTimeout(500);
    await expect(page.locator('#tab-content-config')).toBeVisible();
    await expect(page.locator('#tab-content-executions')).toHaveClass(/hidden/);
    await expect(page.locator('#tab-content-queue')).toHaveClass(/hidden/);

    // Switch to Executions
    await page.locator('#tab-executions').click();
    await page.waitForTimeout(500);
    await expect(page.locator('#tab-content-executions')).toBeVisible();
    await expect(page.locator('#tab-content-config')).toHaveClass(/hidden/);
    await expect(page.locator('#tab-content-queue')).toHaveClass(/hidden/);

    // Switch to Queue
    await page.locator('#tab-queue').click();
    await page.waitForTimeout(500);
    await expect(page.locator('#tab-content-queue')).toBeVisible();
    await expect(page.locator('#tab-content-config')).toHaveClass(/hidden/);
    await expect(page.locator('#tab-content-executions')).toHaveClass(/hidden/);

    // Switch back to Configuration
    await page.locator('#tab-config').click();
    await page.waitForTimeout(500);
    await expect(page.locator('#tab-content-config')).toBeVisible();
    await expect(page.locator('#tab-content-executions')).toHaveClass(/hidden/);
    await expect(page.locator('#tab-content-queue')).toHaveClass(/hidden/);
  });

  test('should update URL hash when switching tabs', async ({ page }) => {
    // Start at base URL
    await page.goto(`${BASE}/workflow`);
    await page.waitForLoadState('networkidle');

    // Click Configuration tab
    await page.locator('#tab-config').click();
    await page.waitForTimeout(500);
    expect(page.url()).toContain('#config');

    // Click Executions tab
    await page.locator('#tab-executions').click();
    await page.waitForTimeout(500);
    expect(page.url()).toContain('#executions');

    // Click Queue tab
    await page.locator('#tab-queue').click();
    await page.waitForTimeout(500);
    expect(page.url()).toContain('#queue');
  });

  test('should show unique content for each tab', async ({ page }) => {
    // Configuration tab should have form
    await page.locator('#tab-config').click();
    await page.waitForTimeout(500);
    await expect(page.locator('#workflowConfigForm')).toBeVisible();
    await expect(page.locator('#description')).toBeVisible();

    // Executions tab should have execution stats and table
    await page.locator('#tab-executions').click();
    await page.waitForTimeout(500);
    await expect(page.locator('#executionStats')).toBeVisible();
    await expect(page.locator('#executionsTableBody')).toBeVisible();
    await expect(page.locator('button:has-text("Trigger Workflow")')).toBeVisible();

    // Queue tab should have queue stats
    await page.locator('#tab-queue').click();
    await page.waitForTimeout(500);
    await expect(page.locator('#queueStats')).toBeVisible();
    await expect(page.locator('#pendingCount')).toBeVisible();
    await expect(page.locator('#approvedCount')).toBeVisible();
  });
});

