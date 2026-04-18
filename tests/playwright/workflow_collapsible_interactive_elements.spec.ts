import { test, expect, Page } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://127.0.0.1:8001';

async function openStep(page: Page, n: number) {
  await page.evaluate((idx) => {
    if (typeof scrollToStep === 'function') scrollToStep(idx);
    else if (typeof toggle === 'function') toggle(`s${idx}`);
  }, n);
  await page.waitForTimeout(600);
}

async function openAllPromptSteps(page: Page) {
  for (const step of [0, 2, 3, 4]) {
    await openStep(page, step);
  }
}

async function waitForPromptPanels(page: Page) {
  await page.waitForFunction(
    () => {
      const panels = document.querySelectorAll('#workflowConfigForm [data-collapsible-panel]');
      return Array.from(panels).some((el) => (el as HTMLElement).offsetParent !== null);
    },
    { timeout: 15000 }
  );
}

function firstPromptPanel(page: Page) {
  return page.locator('#workflowConfigForm [data-collapsible-panel]:visible').first();
}

test.describe('Workflow Collapsible Panels - Interactive Element Click Prevention', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/workflow#config`);
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    await page.evaluate(() => {
      if (typeof switchTab === 'function') {
        switchTab('config');
      }
    });
    await page.waitForTimeout(1000);

    await page.waitForSelector('#workflowConfigForm', { timeout: 10000 });
    await page.waitForTimeout(1000);

    // Open step 0 to render prompt panels
    await openAllPromptSteps(page);
    await waitForPromptPanels(page);
  });

  test('should not toggle when clicking button inside header', async ({ page }) => {
    const header = firstPromptPanel(page);
    const panelId = await header.getAttribute('data-collapsible-panel');
    const content = page.locator(`#${panelId}-content`);

    const initialVisible = await content.isVisible();
    const buttonInHeader = header.locator('button').first();

    if (await buttonInHeader.count() > 0) {
      await buttonInHeader.click();
      await page.waitForTimeout(300);
      const newVisible = await content.isVisible();
      expect(newVisible).toBe(initialVisible);
    } else {
      test.skip(true, 'No button found inside prompt panel header');
    }
  });

  test('should not toggle when clicking input inside header', async ({ page }) => {
    const header = firstPromptPanel(page);
    const panelId = await header.getAttribute('data-collapsible-panel');
    const content = page.locator(`#${panelId}-content`);

    const initialVisible = await content.isVisible();
    const inputInHeader = header.locator('input').first();

    if (await inputInHeader.count() > 0) {
      await inputInHeader.click();
      await page.waitForTimeout(300);
      const newVisible = await content.isVisible();
      expect(newVisible).toBe(initialVisible);
    } else {
      test.skip(true, 'No input found inside prompt panel header');
    }
  });

  test('should not toggle when clicking select inside header', async ({ page }) => {
    const header = firstPromptPanel(page);
    const panelId = await header.getAttribute('data-collapsible-panel');
    const content = page.locator(`#${panelId}-content`);

    const initialVisible = await content.isVisible();
    const selectInHeader = header.locator('select').first();

    if (await selectInHeader.count() > 0) {
      await selectInHeader.click();
      await page.waitForTimeout(300);
      const newVisible = await content.isVisible();
      expect(newVisible).toBe(initialVisible);
    } else {
      test.skip(true, 'No select found inside prompt panel header');
    }
  });

  test.skip('should not toggle when clicking label inside header', async ({ page }) => {
    const header = firstPromptPanel(page);
    const panelId = await header.getAttribute('data-collapsible-panel');
    const content = page.locator(`#${panelId}-content`);

    const initialVisible = await content.isVisible();
    const labelInHeader = header.locator('label').first();

    if (await labelInHeader.count() > 0) {
      await labelInHeader.click();
      await page.waitForTimeout(300);
      const newVisible = await content.isVisible();
      expect(newVisible).toBe(initialVisible);
    } else {
      test.skip(true, 'No label found inside prompt panel header');
    }
  });

  test('should not toggle when clicking link inside header', async ({ page }) => {
    const header = firstPromptPanel(page);
    const panelId = await header.getAttribute('data-collapsible-panel');
    const content = page.locator(`#${panelId}-content`);

    const initialVisible = await content.isVisible();
    const linkInHeader = header.locator('a').first();

    if (await linkInHeader.count() > 0) {
      await linkInHeader.click();
      await page.waitForTimeout(300);
      const newVisible = await content.isVisible();
      expect(newVisible).toBe(initialVisible);
    } else {
      test.skip(true, 'No link found inside prompt panel header');
    }
  });

  test('should not toggle when clicking textarea inside header', async ({ page }) => {
    const header = firstPromptPanel(page);
    const panelId = await header.getAttribute('data-collapsible-panel');
    const content = page.locator(`#${panelId}-content`);

    const initialVisible = await content.isVisible();
    const textareaInHeader = header.locator('textarea').first();

    if (await textareaInHeader.count() > 0) {
      await textareaInHeader.click();
      await page.waitForTimeout(300);
      const newVisible = await content.isVisible();
      expect(newVisible).toBe(initialVisible);
    } else {
      test.skip(true, 'No textarea found inside prompt panel header');
    }
  });

  test('should toggle when clicking non-interactive elements in header', async ({ page }) => {
    const header = firstPromptPanel(page);
    const panelId = await header.getAttribute('data-collapsible-panel');
    const content = page.locator(`#${panelId}-content`);

    // Ensure collapsed
    const isHidden = await content.evaluate(el => el.classList.contains('hidden')).catch(() => true);
    if (!isHidden) {
      await header.click();
      await page.waitForTimeout(300);
    }
    await expect(content).toHaveClass(/hidden/);

    // Click on header text (h4 element)
    const headerText = header.locator('h4').first();
    if (await headerText.count() > 0) {
      await headerText.click();
      await page.waitForTimeout(300);
      await expect(content).toBeVisible();
    } else {
      await header.click();
      await page.waitForTimeout(300);
      await expect(content).toBeVisible();
    }
  });

  test('should toggle when clicking empty space in header', async ({ page }) => {
    const header = firstPromptPanel(page);
    const panelId = await header.getAttribute('data-collapsible-panel');
    const content = page.locator(`#${panelId}-content`);

    // Ensure collapsed
    const isHidden = await content.evaluate(el => el.classList.contains('hidden')).catch(() => true);
    if (!isHidden) {
      await header.click({ position: { x: 10, y: 10 } });
      await page.waitForTimeout(300);
    }

    const wasHidden = await content.evaluate(el => el.classList.contains('hidden'));
    await header.click({ position: { x: 10, y: 10 } });
    await page.waitForTimeout(300);

    // State should have toggled
    const nowHidden = await content.evaluate(el => el.classList.contains('hidden'));
    expect(nowHidden).not.toBe(wasHidden);
  });
});
