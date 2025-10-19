const puppeteer = require('puppeteer');

async function testTerminalFunctionality() {
  console.log('🚀 Starting terminal functionality test...');
  
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
    
    // Click the process button
    console.log('🖱️ Clicking Process All Eligible Articles button...');
    await page.click('#processEligibleBtn');
    
    // Wait for terminal to appear
    console.log('⏳ Waiting for terminal to appear...');
    await page.waitForSelector('#terminalOutput', { timeout: 5000 });
    console.log('✅ Terminal appeared');
    
    // Wait a bit for any initial logs
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // Check terminal content
    const terminalContent = await page.evaluate(() => {
      const content = document.getElementById('terminalContent');
      return content ? content.textContent : 'No content found';
    });
    
    console.log('📟 Terminal content:', terminalContent.substring(0, 200) + '...');
    
    // Keep browser open for manual inspection
    console.log('🔍 Browser will stay open for 60 seconds for manual inspection...');
    console.log('Check the browser console for JavaScript errors');
    await new Promise(resolve => setTimeout(resolve, 60000));
    
  } catch (error) {
    console.error('❌ Test failed:', error.message);
  } finally {
    await browser.close();
  }
}

testTerminalFunctionality().catch(console.error);
