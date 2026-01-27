import { defineConfig, devices } from '@playwright/test';
import { allure } from 'allure-playwright';

/**
 * Playwright configuration for CTIScraper tests
 * 
 * This configuration:
 * - Integrates Allure reporting for test visualization
 * - Outputs to the same allure-results directory as pytest tests
 * - Supports both TypeScript and JavaScript test files
 */
export default defineConfig({
  testDir: '.',
  testMatch: /.*\.(spec|test)\.(ts|js)$/,
  
  /* Run tests in files in parallel */
  fullyParallel: false,
  
  /* Fail the build on CI if you accidentally left test.only in the source code. */
  forbidOnly: !!process.env.CI,
  
  /* Retry on CI only */
  retries: process.env.CI ? 2 : 0,
  
  /* Opt out of parallel tests on CI. */
  workers: process.env.CI ? 1 : undefined,
  
  /* Reporter to use. See https://playwright.dev/docs/test-reporters */
  reporter: [
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
    ['list'],  // Shows test progress in terminal
    ['line'],  // Shows one line per test
    ['allure-playwright', { 
      outputFolder: 'allure-results',
      suiteTitle: false
    }]
  ],
  
  /* Maximum time one test can run for. */
  timeout: 300000, // 5 minutes for slow workflow tests
  
  /* Shared settings for all the projects below. See https://playwright.dev/docs/api/class-testoptions. */
  use: {
    /* Base URL to use in actions like `await page.goto('/')`. */
    baseURL: process.env.CTI_SCRAPER_URL || 'http://localhost:8001',
    
    /* Collect trace when retrying the failed test. See https://playwright.dev/docs/trace-viewer */
    trace: 'on-first-retry',
    
    /* Screenshot on failure */
    screenshot: 'only-on-failure',
    
    /* Video on failure */
    video: 'retain-on-failure',
  },

  /* Configure projects for major browsers */
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  /* Global setup to check web server health before tests */
  globalSetup: require.resolve('./playwright/global-setup.ts'),
  
  /* Run your local dev server before starting the tests */
  // Note: Server should be started manually or via Docker
  // webServer: {
  //   command: 'python -m uvicorn src.web.modern_main:app --host 0.0.0.0 --port 8001',
  //   url: 'http://localhost:8001/health',
  //   reuseExistingServer: !process.env.CI,
  //   timeout: 60000,
  // },
});

