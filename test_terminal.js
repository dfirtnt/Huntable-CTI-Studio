const puppeteer = require('puppeteer');

async function testTerminalFunctionality() {
  console.log('🚀 Starting terminal functionality test...');
  
  const browser = await puppeteer.launch({ 
    headless: false, 
    defaultViewport: null,
    args: ['--start-maximized']
  });
  
  const page = await browser.newPage();
  
  try {
    console.log('📱 Navigating to ML Hunt Comparison page...');
    await page.goto('http://127.0.0.1:8001/ml-hunt-comparison', { 
      waitUntil: 'networkidle2',
      timeout: 30000 
    });
    
    console.log('✅ Page loaded successfully');
    
    // Wait for the page to be ready
    await page.waitForSelector('#processEligibleBtn', { timeout: 10000 });
    console.log('✅ Process button found');
    
    // Test the logs API endpoint first
    console.log('🔍 Testing logs API endpoint...');
    const response = await page.evaluate(async () => {
      const res = await fetch('/api/ml-hunt-comparison/logs');
      return await res.json();
    });
    
    console.log('📊 API Response:', {
      success: response.success,
      logsLength: response.logs ? response.logs.length : 0,
      logsPreview: response.logs ? response.logs.substring(0, 100) + '...' : 'No logs'
    });
    
    if (!response.success) {
      throw new Error('API endpoint failed: ' + JSON.stringify(response));
    }
    
    // Click the process button
    console.log('🖱️ Clicking Process All Eligible Articles button...');
    await page.click('#processEligibleBtn');
    
    // Wait for terminal to appear
    console.log('⏳ Waiting for terminal to appear...');
    await page.waitForSelector('#terminalOutput', { timeout: 10000 });
    console.log('✅ Terminal appeared');
    
    // Check terminal content
    const terminalContent = await page.evaluate(() => {
      const content = document.getElementById('terminalContent');
      return content ? content.textContent : 'No content found';
    });
    
    console.log('📟 Terminal content:', terminalContent.substring(0, 200) + '...');
    
    // Wait for logs to update (not just "Fetching logs...")
    console.log('⏳ Waiting for logs to update...');
    await page.waitForFunction(() => {
      const content = document.getElementById('terminalContent');
      return content && content.textContent && 
             content.textContent.includes('Processing article') && 
             !content.textContent.includes('🔄 Fetching logs...');
    }, { timeout: 30000 });
    
    // Get final terminal content
    const finalContent = await page.evaluate(() => {
      const content = document.getElementById('terminalContent');
      return content ? content.textContent : 'No content found';
    });
    
    console.log('✅ Final terminal content:', finalContent.substring(0, 300) + '...');
    
    // Verify the content contains processing logs
    if (finalContent.includes('Processing article')) {
      console.log('🎉 SUCCESS: Terminal is showing real processing logs!');
    } else {
      console.log('❌ FAILURE: Terminal is not showing processing logs');
      console.log('Content:', finalContent);
    }
    
    // Keep browser open for manual inspection
    console.log('🔍 Browser will stay open for 30 seconds for manual inspection...');
    await page.waitForTimeout(30000);
    
  } catch (error) {
    console.error('❌ Test failed:', error.message);
  } finally {
    await browser.close();
  }
}

testTerminalFunctionality().catch(console.error);
