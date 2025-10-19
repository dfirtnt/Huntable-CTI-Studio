const puppeteer = require('puppeteer');

async function testAPI() {
  console.log('🚀 Testing API endpoint directly...');
  
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
    
    // Test the API endpoint directly
    console.log('🔍 Testing logs API endpoint...');
    const response = await page.evaluate(async () => {
      try {
        const res = await fetch('/api/ml-hunt-comparison/logs');
        const data = await res.json();
        return {
          status: res.status,
          statusText: res.statusText,
          success: data.success,
          logsLength: data.logs ? data.logs.length : 0,
          logsPreview: data.logs ? data.logs.substring(0, 100) : 'No logs',
          error: data.error || null
        };
      } catch (error) {
        return { error: error.message };
      }
    });
    
    console.log('📊 API Response:', response);
    
    if (response.error) {
      console.log('❌ API Error:', response.error);
    } else if (response.success) {
      console.log('✅ API working, logs length:', response.logsLength);
    } else {
      console.log('❌ API failed:', response);
    }
    
    // Keep browser open for manual inspection
    console.log('🔍 Browser will stay open for 30 seconds...');
    await new Promise(resolve => setTimeout(resolve, 30000));
    
  } catch (error) {
    console.error('❌ Test failed:', error.message);
  } finally {
    await browser.close();
  }
}

testAPI().catch(console.error);
