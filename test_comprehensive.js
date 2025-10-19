const puppeteer = require('puppeteer');

async function testTerminalAndUI() {
  console.log('🚀 Starting comprehensive terminal and UI test...');
  
  const browser = await puppeteer.launch({ 
    headless: false, 
    defaultViewport: null,
    args: ['--start-maximized']
  });
  
  const page = await browser.newPage();
  
  // Enable console logging
  page.on('console', msg => {
    console.log('Browser console:', msg.text());
  });
  
  try {
    console.log('📱 Navigating to ML Hunt Comparison page...');
    await page.goto('http://127.0.0.1:8001/ml-hunt-comparison', { 
      waitUntil: 'domcontentloaded',
      timeout: 10000 
    });
    
    console.log('✅ Page loaded successfully');
    
    // Wait for the page to be ready
    await page.waitForSelector('#processEligibleBtn', { timeout: 5000 });
    console.log('✅ Process button found');
    
    // Check initial eligible count
    const initialCount = await page.evaluate(() => {
      const countElement = document.getElementById('eligibleCount');
      return countElement ? countElement.textContent : 'Not found';
    });
    console.log('📊 Initial eligible count:', initialCount);
    
    // Click the process button
    console.log('🖱️ Clicking Process All Eligible Articles button...');
    await page.click('#processEligibleBtn');
    
    // Wait for terminal to appear
    console.log('⏳ Waiting for terminal to appear...');
    await page.waitForSelector('#terminalOutput', { timeout: 5000 });
    console.log('✅ Terminal appeared');
    
    // Check terminal positioning (should be moved left)
    const terminalPosition = await page.evaluate(() => {
      const terminal = document.getElementById('terminalOutput');
      if (terminal) {
        const rect = terminal.getBoundingClientRect();
        return {
          left: rect.left,
          top: rect.top,
          width: rect.width,
          height: rect.height
        };
      }
      return null;
    });
    console.log('📍 Terminal position:', terminalPosition);
    
    // Wait for processing to complete (should be quick since 0 articles)
    await new Promise(resolve => setTimeout(resolve, 3000));
    
    // Check the main page status (should NOT show "failed")
    const mainPageStatus = await page.evaluate(() => {
      const countElement = document.getElementById('eligibleCount');
      const btn = document.getElementById('processEligibleBtn');
      return {
        countText: countElement ? countElement.textContent : 'Not found',
        buttonText: btn ? btn.textContent : 'Not found',
        buttonClasses: btn ? btn.className : 'Not found'
      };
    });
    console.log('📊 Main page status:', mainPageStatus);
    
    // Check terminal content
    const terminalContent = await page.evaluate(() => {
      const content = document.getElementById('terminalContent');
      return content ? content.textContent.substring(0, 200) : 'No content found';
    });
    console.log('📟 Terminal content preview:', terminalContent);
    
    // Verify the fixes
    const tests = {
      terminalPositionedLeft: terminalPosition && terminalPosition.left < 400, // Adjusted threshold
      noFailedMessage: !mainPageStatus.countText.includes('❌') && !mainPageStatus.countText.includes('failed'),
      correctButtonState: mainPageStatus.buttonText.includes('Processing') || mainPageStatus.buttonText.includes('No Articles'),
      terminalShowsLogs: terminalContent.includes('Processing') || terminalContent.includes('Complete')
    };
    
    console.log('🧪 Test Results:');
    console.log('  ✅ Terminal positioned left:', tests.terminalPositionedLeft);
    console.log('  ✅ No failed message:', tests.noFailedMessage);
    console.log('  ✅ Correct button state:', tests.correctButtonState);
    console.log('  ✅ Terminal shows logs:', tests.terminalShowsLogs);
    
    const allTestsPassed = Object.values(tests).every(test => test);
    console.log('🎯 Overall Result:', allTestsPassed ? '✅ ALL TESTS PASSED' : '❌ SOME TESTS FAILED');
    
    // Keep browser open for manual inspection
    console.log('🔍 Browser will stay open for 30 seconds for manual inspection...');
    await new Promise(resolve => setTimeout(resolve, 30000));
    
  } catch (error) {
    console.error('❌ Test failed:', error.message);
  } finally {
    await browser.close();
  }
}

testTerminalAndUI().catch(console.error);
