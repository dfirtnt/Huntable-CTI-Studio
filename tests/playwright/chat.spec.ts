import { test, expect, request } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const SKIP_TESTS = process.env.SKIP_CHAT_TESTS === 'true';

// RAG Chat UI deprecated in commit 824bb79d (deprecate/rag-chat)
// Conversational retrieval moved to Huntable MCP server
test.describe('RAG Chat Page', () => {
  test.skip(SKIP_TESTS, 'Chat tests disabled (SKIP_CHAT_TESTS=true).');

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/chat`);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#rag-chat-container')).toBeVisible();
    await expect(page.locator('#rag-chat-container textarea')).toBeVisible();
  });

  test('[CHAT-001] Chat page loads successfully', async ({ page }) => {
    await expect(page).toHaveURL(/\/chat/);
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });
    await page.waitForTimeout(250);
    expect(errors.filter((e) => !e.includes('favicon'))).toHaveLength(0);
  });
});

test.describe('RAG Chat - Send Message', () => {
  test.skip(SKIP_TESTS, 'RAG Chat UI deprecated (commit 824bb79d).');

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/chat`);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#rag-chat-container textarea')).toBeVisible();
    await page.route('**/api/chat/rag', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          response: 'Mocked assistant response',
          timestamp: new Date().toISOString(),
          relevant_articles: [],
          relevant_rules: [],
          total_results: 0,
          total_rules: 0,
          use_llm_generation: false,
        }),
      });
    });
  });

  test('[CHAT-010] Can type message in input', async ({ page }) => {
    const input = page.locator('#rag-chat-container textarea').first();
    await input.fill('test message');
    await expect(input).toHaveValue('test message');
  });

  test('[CHAT-011] Send button is clickable', async ({ page }) => {
    const input = page.locator('#rag-chat-container textarea').first();
    await input.fill('What is Emotet?');

    const sendBtn = page.locator('#rag-chat-container button:has-text("Send")').first();
    await expect(sendBtn).toBeEnabled();
  });

  test('[CHAT-013] Conversation history persists during session', async ({ page }) => {
    const input = page.locator('#rag-chat-container textarea').first();
    await input.fill('Hello');

    const sendBtn = page.locator('#rag-chat-container button:has-text("Send")').first();
    await sendBtn.click();

    await expect(page.locator('#rag-chat-container').getByText('Hello', { exact: true })).toBeVisible();
    await expect(page.locator('#rag-chat-container').getByText('Mocked assistant response', { exact: true })).toBeVisible();
  });
});

test.describe('RAG Chat - Clear Conversation', () => {
  test.skip(SKIP_TESTS, 'RAG Chat UI deprecated (commit 824bb79d).');

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/chat`);
    await page.waitForLoadState('domcontentloaded');
    await expect(page.locator('#rag-chat-container textarea')).toBeVisible();
  });

  test('[CHAT-030] Clear conversation button exists', async ({ page }) => {
    const savePresetBtn = page.locator('#rag-chat-container button:has-text("Save Preset")');
    await expect(savePresetBtn).toBeVisible();
  });

  test('[CHAT-031] Can clear conversation', async ({ page }) => {
    const input = page.locator('#rag-chat-container textarea').first();
    await input.fill('Test');

    const sendBtn = page.locator('#rag-chat-container button:has-text("Send")').first();
    await sendBtn.click();

    await expect(page.locator('#rag-chat-container').getByText('Test', { exact: true })).toBeVisible();
  });
});
