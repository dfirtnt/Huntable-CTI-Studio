import { test, expect } from '@playwright/test';

test('test', async ({ page }) => {
  await page.goto('http://127.0.0.1:8001/');
  await page.getByRole('link', { name: 'MLOps MLOps' }).click();
  await page.getByRole('link', { name: 'View Analysis' }).click();
  await page.getByRole('button', { name: 'Process All Eligible Articles' }).click();
});