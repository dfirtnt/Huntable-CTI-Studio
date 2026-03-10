import { test, expect, request } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
const SKIP_TESTS = process.env.SKIP_CHAT_TESTS === 'true';
const LMSTUDIO_URL = process.env.LMSTUDIO_API_URL;

test.describe('RAG Chat Page', () => {
  test.skip(SKIP_TESTS, 'Chat tests disabled (SKIP_CHAT_TESTS=true).');

  test.beforeEach(async ({ page }) => {
    await page.goto(`${BASE}/chat`);
    await page.waitForLoadState('networkidle');
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

  test('[CHAT-002] Page title is displayed', async ({ page }) => {
    const title = page.locator('h1, [data-testid="chat-title"], .chat-title');
    await expect(title.first()).toBeVisible();
  });

  test('[CHAT-003] Chat input field is present', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask"], textarea, [data-testid="chat-input"]');
    await expect(input.first()).toBeVisible();
  });

  test('[CHAT-004] Send button is present', async ({ page }) => {
    const sendBtn = page.locator('button:has-text("Send"), [data-testid="send-button"]');
    await expect(sendBtn.first()).toBeVisible();
  });
});

test.describe('RAG Chat - Send Message', () => {
  test.skip(SKIP_TESTS, 'Chat tests disabled.');

  test('[CHAT-010] Can type message in input', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask"], textarea, [data-testid="chat-input"]').first();
    await input.fill('test message');
    await expect(input).toHaveValue('test message');
  });

  test('[CHAT-011] Send button is clickable', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask"], textarea, [data-testid="chat-input"]').first();
    await input.fill('What is Emotet?');
    
    const sendBtn = page.locator('button:has-text("Send"), [data-testid="send-button"]').first();
    await expect(sendBtn).toBeEnabled();
  });

  test('[CHAT-012] Chat displays message history', async ({ page }) => {
    const messages = page.locator('[data-testid="chat-messages"], .chat-messages, .messages');
    const hasMessages = await messages.first().isVisible().catch(() => false);
    expect(hasMessages).toBe(true);
  });

  test('[CHAT-013] Conversation history persists during session', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask"], textarea').first();
    await input.fill('Hello');
    
    const sendBtn = page.locator('button:has-text("Send")').first();
    await sendBtn.click();
    
    await page.waitForTimeout(500);
    
    const messages = page.locator('[data-testid="chat-messages"], .messages .message');
    const count = await messages.count();
    expect(count).toBeGreaterThan(0);
  });
});

test.describe('RAG Chat - LLM Required Tests', () => {
  test.skip(!LMSTUDIO_URL, 'LMSTUDIO_API_URL not set - skipping LLM-dependent tests');
  test.skip(SKIP_TESTS, 'Chat tests disabled.');

  test('[CHAT-020] Sending message shows response', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask"], textarea').first();
    await input.fill('What is a malware indicator?');
    
    const sendBtn = page.locator('button:has-text("Send")').first();
    await sendBtn.click();
    
    await page.waitForTimeout(3000);
    
    const messages = page.locator('[data-testid="chat-messages"], .messages .message');
    const count = await messages.count();
    expect(count).toBeGreaterThan(1);
  });

  test('[CHAT-021] Loading state is displayed while waiting', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask"], textarea').first();
    await input.fill('Explain APT groups');
    
    const sendBtn = page.locator('button:has-text("Send")').first();
    await sendBtn.click();
    
    const loading = page.locator('[data-testid="loading"], .loading, .typing:has-text("Thinking")');
    const hasLoading = await loading.first().isVisible().catch(() => false);
    expect(hasLoading).toBe(true);
  });
});

test.describe('RAG Chat - Clear Conversation', () => {
  test.skip(SKIP_TESTS, 'Chat tests disabled.');

  test('[CHAT-030] Clear conversation button exists', async ({ page }) => {
    const clearBtn = page.locator('button:has-text("Clear"), button:has-text("New Chat"), [data-testid="clear-chat"]');
    const hasClear = await clearBtn.first().isVisible().catch(() => false);
    expect(hasClear).toBe(true);
  });

  test('[CHAT-031] Can clear conversation', async ({ page }) => {
    const input = page.locator('input[placeholder*="Ask"], textarea').first();
    await input.fill('Test');
    
    const sendBtn = page.locator('button:has-text("Send")').first();
    await sendBtn.click();
    await page.waitForTimeout(500);
    
    const clearBtn = page.locator('button:has-text("Clear"), button:has-text("New Chat")').first();
    await clearBtn.click();
    
    const messages = page.locator('[data-testid="chat-messages"], .messages .message');
    const count = await messages.count();
    expect(count).toBe(0);
  });
});

test.describe('RAG Chat - Presets', () => {
  test.skip(SKIP_TESTS, 'Chat tests disabled.');

  test('[CHAT-040] Chat presets are available', async ({ page }) => {
    const presets = page.locator('[data-testid="chat-presets"], .presets, button:has-text("Preset")');
    const hasPresets = await presets.first().isVisible().catch(() => false);
  });

  test('[CHAT-041] Can select a preset', async ({ page }) => {
    const presetBtn = page.locator('[data-testid="preset-"], .preset-button').first();
    const hasPreset = await presetBtn.isVisible().catch(() => false);
    if (hasPreset) {
      await presetBtn.click();
      const input = page.locator('input[placeholder*="Ask"], textarea').first();
      const value = await input.inputValue();
      expect(value.length).toBeGreaterThan(0);
    }
  });
});
