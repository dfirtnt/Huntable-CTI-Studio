import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

test.describe('Agent Config Restore After Collapse', () => {
  test.beforeEach(async ({ page }) => {
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

    // Wait for config form to be visible
    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    await page.waitForTimeout(2000); // Wait for config to fully load
  });

  test('should render Rank Agent config content after restore when panel was collapsed', async ({ page }) => {
    const panelId = 'rank-agent-configs-panel';
    const content = page.locator(`#${panelId}-content`);
    const button = page.locator(`button[onclick*="${panelId}"]`);
    const container = page.locator('#rank-agent-model-container');

    // First, ensure panel is expanded and manually trigger loadAgentModels to populate it
    const isHidden = await content.evaluate(el => el.classList.contains('hidden'));
    if (isHidden) {
      await button.click();
      await page.waitForTimeout(300);
    }

    // Manually trigger loadAgentModels to populate containers
    await page.evaluate(async () => {
      if (typeof loadAgentModels === 'function') {
        await loadAgentModels();
      }
    });
    await page.waitForTimeout(2000); // Wait for API call and rendering

    // Check if container has content (may be empty if API fails, but structure should exist)
    const containerExists = await container.count() > 0;
    expect(containerExists).toBe(true);

    // Now collapse the panel BEFORE checking content
    await button.click();
    await page.waitForTimeout(300);
    await expect(content).toHaveClass(/hidden/);

    // Verify container still exists in DOM even when hidden
    const containerWhenHidden = await container.evaluate(el => el !== null);
    expect(containerWhenHidden).toBe(true);

    // Trigger a config reload (simulating what happens after save)
    // This is the critical test - can we render to a container in a hidden panel?
    await page.evaluate(async () => {
      if (typeof loadAgentModels === 'function') {
        await loadAgentModels();
      }
    });
    await page.waitForTimeout(2000);

    // Expand the panel again
    await button.click();
    await page.waitForTimeout(500);

    // Verify content is accessible after expanding
    await expect(content).toBeVisible();
    
    // Wait a bit for content to render
    await page.waitForTimeout(500);
    
    // Check if container has content (even if hidden due to CSS)
    const containerAfterRestore = page.locator('#rank-agent-model-container');
    const containerContent = await containerAfterRestore.evaluate(el => el.innerHTML);
    
    // The key test: container should have content even after being collapsed and reloaded
    // This verifies the fix works - content is rendered regardless of panel visibility
    expect(containerContent.length).toBeGreaterThan(0);
    
    // Container should exist in DOM
    const containerAfterRestoreExists = await containerAfterRestore.count() > 0;
    expect(containerAfterRestoreExists).toBe(true);
  });

  test('should render Extract Agent config content after restore when panel was collapsed', async ({ page }) => {
    const panelId = 'extract-agent-panel';
    const content = page.locator(`#${panelId}-content`);
    const button = page.locator(`button[onclick="toggleCollapsible('${panelId}')"]`);
    const container = page.locator('#extract-agent-model-container');

    // Ensure panel is expanded initially
    const isHidden = await content.evaluate(el => el.classList.contains('hidden'));
    if (isHidden) {
      await button.click();
      await page.waitForTimeout(300);
    }

    // Wait for container to exist in DOM
    await page.waitForSelector('#extract-agent-model-container', { state: 'attached', timeout: 5000 });
    await page.waitForTimeout(2000);

    // Verify container has content
    const containerContent = await container.evaluate(el => el.innerHTML);
    expect(containerContent.length).toBeGreaterThan(0);
    expect(containerContent).toContain('Extract Agent Model');

    // Collapse the panel
    await button.click();
    await page.waitForTimeout(300);
    await expect(content).toHaveClass(/hidden/);

    // Trigger config reload
    await page.evaluate(async () => {
      if (typeof loadAgentModels === 'function') {
        await loadAgentModels();
      }
    });
    await page.waitForTimeout(1000);

    // Expand the panel again
    await button.click();
    await page.waitForTimeout(500);

    // Verify content is still there
    await expect(content).toBeVisible();
    const containerAfterRestore = page.locator('#extract-agent-model-container');
    await expect(containerAfterRestore).toBeVisible();
    
    const contentAfterRestore = await containerAfterRestore.evaluate(el => el.innerHTML);
    expect(contentAfterRestore.length).toBeGreaterThan(0);
    expect(contentAfterRestore).toContain('Extract Agent Model');
  });

  test('should render OS Detection Agent config content after restore when panel was collapsed', async ({ page }) => {
    const panelId = 'os-detection-panel';
    const content = page.locator(`#${panelId}-content`);
    const button = page.locator(`button[onclick*="${panelId}"]`);
    const container = page.locator('#os-detection-model-container');

    // Ensure panel is expanded initially
    const isHidden = await content.evaluate(el => el.classList.contains('hidden'));
    if (isHidden) {
      await button.click();
      await page.waitForTimeout(300);
    }

    // Wait for container to exist in DOM
    await page.waitForSelector('#os-detection-model-container', { state: 'attached', timeout: 5000 });
    await page.waitForTimeout(2000);

    // Verify container has content
    const containerContent = await container.evaluate(el => el.innerHTML);
    expect(containerContent.length).toBeGreaterThan(0);
    expect(containerContent).toContain('OS Detection Agent Model');

    // Collapse the panel
    await button.click();
    await page.waitForTimeout(300);
    await expect(content).toHaveClass(/hidden/);

    // Trigger config reload
    await page.evaluate(async () => {
      if (typeof loadAgentModels === 'function') {
        await loadAgentModels();
      }
    });
    await page.waitForTimeout(1000);

    // Expand the panel again
    await button.click();
    await page.waitForTimeout(500);

    // Verify content is still there
    await expect(content).toBeVisible();
    const containerAfterRestore = page.locator('#os-detection-model-container');
    await expect(containerAfterRestore).toBeVisible();
    
    const contentAfterRestore = await containerAfterRestore.evaluate(el => el.innerHTML);
    expect(contentAfterRestore.length).toBeGreaterThan(0);
    expect(contentAfterRestore).toContain('OS Detection Agent Model');
  });

  test('should render Sigma Agent config content after restore when panel was collapsed', async ({ page }) => {
    const panelId = 'sigma-agent-panel';
    const content = page.locator(`#${panelId}-content`);
    const button = page.locator(`button[onclick*="${panelId}"]`);
    const container = page.locator('#sigma-agent-model-container');

    // Ensure panel is expanded initially
    const isHidden = await content.evaluate(el => el.classList.contains('hidden'));
    if (isHidden) {
      await button.click();
      await page.waitForTimeout(300);
    }

    // Wait for container to exist in DOM
    await page.waitForSelector('#sigma-agent-model-container', { state: 'attached', timeout: 5000 });
    await page.waitForTimeout(2000);

    // Verify container has content
    const containerContent = await container.evaluate(el => el.innerHTML);
    expect(containerContent.length).toBeGreaterThan(0);
    expect(containerContent).toContain('SIGMA Generator Agent Model');

    // Collapse the panel
    await button.click();
    await page.waitForTimeout(300);
    await expect(content).toHaveClass(/hidden/);

    // Trigger config reload
    await page.evaluate(async () => {
      if (typeof loadAgentModels === 'function') {
        await loadAgentModels();
      }
    });
    await page.waitForTimeout(1000);

    // Expand the panel again
    await button.click();
    await page.waitForTimeout(500);

    // Verify content is still there
    await expect(content).toBeVisible();
    const containerAfterRestore = page.locator('#sigma-agent-model-container');
    await expect(containerAfterRestore).toBeVisible();
    
    const contentAfterRestore = await containerAfterRestore.evaluate(el => el.innerHTML);
    expect(contentAfterRestore.length).toBeGreaterThan(0);
    expect(contentAfterRestore).toContain('SIGMA Generator Agent Model');
  });
});

