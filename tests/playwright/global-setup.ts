import { FullConfig } from '@playwright/test';
import * as http from 'http';
import * as https from 'https';
import { URL } from 'url';

/**
 * Global setup to ensure web server is running before tests start
 * Uses Node.js built-in http/https modules for compatibility
 */
async function httpRequest(url: string, timeout: number = 5000): Promise<{ status: number; data: any }> {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const client = urlObj.protocol === 'https:' ? https : http;
    
    const req = client.get(url, {
      timeout,
      headers: { 'Accept': 'application/json' }
    }, (res) => {
      let data = '';
      res.on('data', (chunk) => { data += chunk; });
      res.on('end', () => {
        try {
          const jsonData = data ? JSON.parse(data) : {};
          resolve({ status: res.statusCode || 500, data: jsonData });
        } catch (e) {
          resolve({ status: res.statusCode || 500, data: {} });
        }
      });
    });
    
    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });
  });
}

async function globalSetup(config: FullConfig) {
  const baseURL = config.use?.baseURL || process.env.CTI_SCRAPER_URL || 'http://localhost:8001';
  const healthURL = `${baseURL}/health`;
  
  console.log(`🔍 Checking web server health at ${healthURL}...`);
  
  const maxAttempts = 30;
  const delayMs = 2000;
  
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const { status, data } = await httpRequest(healthURL, 5000);
      
      if (status >= 200 && status < 300) {
        console.log(`✅ Web server is healthy (attempt ${attempt}/${maxAttempts})`);
        console.log(`   Status: ${data.status || 'OK'}`);
        return;
      } else {
        console.log(`⚠️  Server responded with status ${status} (attempt ${attempt}/${maxAttempts})`);
      }
    } catch (error: any) {
      if (attempt < maxAttempts) {
        console.log(`⏳ Server not ready (attempt ${attempt}/${maxAttempts}): ${error.message}`);
        console.log(`   Retrying in ${delayMs/1000}s...`);
        await new Promise(resolve => setTimeout(resolve, delayMs));
      } else {
        console.error(`❌ Web server health check failed after ${maxAttempts} attempts`);
        console.error(`   URL: ${healthURL}`);
        console.error(`   Error: ${error.message}`);
        throw new Error(
          `Web server at ${baseURL} is not responding. ` +
          `Please ensure the server is running before running tests. ` +
          `You can start it with: docker-compose up -d web ` +
          `Or: python -m uvicorn src.web.modern_main:app --host 0.0.0.0 --port 8001`
        );
      }
    }
  }
}

export default globalSetup;

