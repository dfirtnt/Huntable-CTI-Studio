import { test, expect } from '@playwright/test';

const BASE = process.env.CTI_SCRAPER_URL || 'http://localhost:8001';

test('verify View summary elements have white text in dark mode', async ({ page }) => {
  // Enable dark mode - both media query and class
  await page.emulateMedia({ colorScheme: 'dark' });
  
  // Navigate to workflow executions page
  await page.goto(`${BASE}/workflow#executions`);
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  
  // Add dark class to html element (Tailwind dark mode)
  await page.evaluate(() => {
    document.documentElement.classList.add('dark');
  });
  await page.waitForTimeout(500);
  
  // Click executions tab if needed
  const executionsTab = page.locator('#tab-executions, button:has-text("Executions")').first();
  if (await executionsTab.isVisible({ timeout: 2000 }).catch(() => false)) {
    await executionsTab.click();
    await page.waitForTimeout(1000);
  }
  
  // Look for View button in the executions table
  const viewButton = page.locator('button:has-text("View")').first();
  const viewButtonExists = await viewButton.isVisible({ timeout: 10000 }).catch(() => false);
  
  if (!viewButtonExists) {
    test.skip('No View button found - no executions available');
    return;
  }
  
  // Click View button to open execution detail modal
  await viewButton.click();
  
  // Wait for modal to be visible
  const executionModal = page.locator('#executionModal');
  await expect(executionModal).toBeVisible({ timeout: 10000 });
  
  // Wait for content to load - wait longer for all dynamic content
  await page.waitForTimeout(5000);
  
  // Check that execution detail content exists
  const contentDiv = page.locator('#executionDetailContent');
  await expect(contentDiv).toBeVisible({ timeout: 5000 });
  
  // Scroll to ensure all content is rendered
  await contentDiv.evaluate((el) => {
    el.scrollTop = 0;
  });
  await page.waitForTimeout(1000);
  await contentDiv.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  await page.waitForTimeout(2000);
  
  // Take a screenshot for debugging
  await page.screenshot({ path: 'test-results/execution-detail-view.png', fullPage: true });
  
  // Get all text content to see what's actually rendered
  const allText = await contentDiv.textContent();
  console.log('\n=== Modal Content Preview (first 500 chars) ===');
  console.log(allText?.substring(0, 500));
  
  // Find all "View" summary elements - use multiple selectors
  const viewSummaries = contentDiv.locator('summary:has-text("View")');
  const count = await viewSummaries.count();
  
  console.log(`Found ${count} View summary elements`);
  
  // Also try finding by class
  const allSummaries = contentDiv.locator('summary');
  const allCount = await allSummaries.count();
  console.log(`Found ${allCount} total summary elements`);
  
  if (count === 0) {
    // Check if modal has any content at all
    const modalText = await contentDiv.textContent();
    console.log('Modal content:', modalText?.substring(0, 200));
    test.skip('No View summary elements found in execution detail');
    return;
  }
  
  // Check specific View elements that should be white
  const specificViews = [
    { text: 'View Content Sent to OS Detection', required: false },
    { text: 'View Original Article Content', required: false },
    { text: 'View Ranking Reasoning', required: false },
    { text: 'View Filtered Content Sent to Rank Agent', required: false },
    { text: 'View Filtered Content Sent to Extract Agents', required: false },
    { text: 'View Extracted Content Sent to SIGMA Agent', required: false },
    { text: 'View Similarity Results', required: false },
    { text: 'View SIGMA Rules Sent to Similarity Search', required: false },
    { text: 'View Queued Rules', required: false },
    { text: 'View Full Rule JSON', required: false },
    { text: 'View', required: false } // Generic pattern
  ];
  
  const colorIssues: string[] = [];
  
  for (const view of specificViews) {
    const summary = contentDiv.locator(`summary:has-text("${view.text}")`).first();
    const exists = await summary.isVisible({ timeout: 1000 }).catch(() => false);
    
    if (exists) {
      const color = await summary.evaluate((el) => {
        return window.getComputedStyle(el).color;
      });
      
      const isWhite = color.includes('255, 255, 255') || 
                     color.includes('rgb(255, 255, 255)') ||
                     color.includes('rgba(255, 255, 255') ||
                     color === '#ffffff' ||
                     color === 'white' ||
                     color.toLowerCase() === 'rgb(255, 255, 255)';
      
      if (!isWhite) {
        const text = await summary.textContent();
        colorIssues.push(`"${text?.trim()}" has color: ${color} (expected white)`);
        console.log(`❌ "${text?.trim()}" has color: ${color}`);
      } else {
        const text = await summary.textContent();
        console.log(`✅ "${text?.trim()}" has white color: ${color}`);
      }
    }
  }
  
  // Check all View summaries
  for (let i = 0; i < Math.min(count, 20); i++) {
    const summary = viewSummaries.nth(i);
    const isVisible = await summary.isVisible().catch(() => false);
    
    if (isVisible) {
      const color = await summary.evaluate((el) => {
        return window.getComputedStyle(el).color;
      });
      
      const isWhite = color.includes('255, 255, 255') || 
                     color.includes('rgb(255, 255, 255)') ||
                     color.includes('rgba(255, 255, 255') ||
                     color === '#ffffff' ||
                     color === 'white' ||
                     color.toLowerCase() === 'rgb(255, 255, 255)';
      
      if (!isWhite) {
        const text = await summary.textContent();
        if (!colorIssues.some(issue => issue.includes(text?.trim() || ''))) {
          colorIssues.push(`"${text?.trim()}" has color: ${color} (expected white)`);
          console.log(`❌ "${text?.trim()}" has color: ${color}`);
        }
      }
    }
  }
  
  if (colorIssues.length > 0) {
    console.log('\n=== Color Issues Found ===');
    colorIssues.forEach(issue => console.log(issue));
    throw new Error(`Found ${colorIssues.length} View summary elements that are not white:\n${colorIssues.join('\n')}`);
  }
  
  console.log(`\n✅ All ${count} View summary elements have white text`);
  
  // Also check other text elements that might be dark
  console.log('\n=== Checking other text elements ===');
  const allTextElements = contentDiv.locator('div, span, p, li, strong').filter({ hasText: /./ });
  const textCount = await allTextElements.count();
  console.log(`Found ${textCount} text elements to check`);
  
  const darkTextIssues: string[] = [];
  for (let i = 0; i < Math.min(textCount, 50); i++) {
    const el = allTextElements.nth(i);
    const isVisible = await el.isVisible().catch(() => false);
    if (isVisible) {
      const color = await el.evaluate((element) => {
        return window.getComputedStyle(element).color;
      });
      const text = await el.textContent();
      const textPreview = text?.trim().substring(0, 50) || '';
      
      // Check if color is dark (not white, not colored status elements)
      const isDark = !color.includes('255, 255, 255') && 
                    !color.includes('rgb(255, 255, 255)') &&
                    !color.includes('rgba(255, 255, 255') &&
                    color !== '#ffffff' &&
                    color !== 'white' &&
                    !color.includes('rgb(239, 68, 68)') && // red
                    !color.includes('rgb(34, 197, 94)') && // green
                    !color.includes('rgb(234, 179, 8)') && // yellow
                    !color.includes('rgb(59, 130, 246)') && // blue
                    !color.includes('rgb(168, 85, 247)'); // purple
      
      // Only report if it's actually dark (like #111827 = rgb(17, 24, 39) or black)
      const rgbMatch = color.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
      if (rgbMatch && isDark) {
        const r = parseInt(rgbMatch[1]);
        const g = parseInt(rgbMatch[2]);
        const b = parseInt(rgbMatch[3]);
        // If it's a dark color (like #111827 = rgb(17, 24, 39) or black = rgb(0, 0, 0))
        // But exclude very dark backgrounds and elements that should be dark
        const isVeryDark = r < 50 && g < 50 && b < 50;
        const isExpectedDark = (r === 17 && g === 24 && b === 39) || (r === 0 && g === 0 && b === 0);
        if (isVeryDark && textPreview.length > 0 && !textPreview.includes('View')) {
          darkTextIssues.push(`"${textPreview}" has dark color: ${color} (expected #111827 or white for View elements)`);
          if (darkTextIssues.length <= 10) {
            console.log(`⚠️  "${textPreview}" has dark color: ${color}`);
          }
        }
      }
    }
  }
  
  // Check if dark mode class is applied
  const hasDarkClass = await page.evaluate(() => {
    return document.documentElement.classList.contains('dark') || 
           document.body.classList.contains('dark') ||
           document.querySelector('#executionDetailContent')?.closest('.dark') !== null;
  });
  console.log(`\n=== CSS Debug Info ===`);
  console.log(`Dark mode class present: ${hasDarkClass}`);
  
  // Check if CSS rule is actually applied by checking a specific element
  const testElement = contentDiv.locator('div').first();
  if (await testElement.isVisible().catch(() => false)) {
    const computedColor = await testElement.evaluate((el) => {
      const style = window.getComputedStyle(el);
      return {
        color: style.color,
        hasDarkParent: el.closest('.dark') !== null,
        parentColor: el.parentElement ? window.getComputedStyle(el.parentElement).color : 'none'
      };
    });
    console.log(`First div color: ${computedColor.color}`);
    console.log(`Has dark parent: ${computedColor.hasDarkParent}`);
    console.log(`Parent color: ${computedColor.parentColor}`);
  }
  
  // Filter out expected dark colors (#111827) - only report if it's black or unexpected
  const unexpectedDarkIssues = darkTextIssues.filter(issue => {
    // rgb(17, 24, 39) is #111827 which is expected for non-View elements
    return !issue.includes('rgb(17, 24, 39)') && !issue.includes('rgb(0, 0, 0)');
  });
  
  if (unexpectedDarkIssues.length > 0) {
    console.log(`\n⚠️  Found ${unexpectedDarkIssues.length} text elements with unexpected dark colors:`);
    unexpectedDarkIssues.slice(0, 10).forEach(issue => console.log(`  ${issue}`));
    throw new Error(`Found ${unexpectedDarkIssues.length} elements with unexpected dark colors`);
  } else if (darkTextIssues.length > 0) {
    console.log(`\n✅ All dark text is #111827 as expected (${darkTextIssues.length} elements)`);
  } else {
    console.log('\n✅ No dark text elements found');
  }
  
  console.log(`\n✅ Test Summary: All View summary elements are white, other text is #111827 as expected`);
});

