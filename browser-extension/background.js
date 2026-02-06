// Background script for API communication
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'scrapeUrl') {
        scrapeUrlToCTIScraper(request.data)
            .then(result => sendResponse({ success: true, data: result }))
            .catch(error => sendResponse({ success: false, error: error.message }));
        return true; // Keep message channel open for async response
    }
    
    if (request.action === 'articleDataExtracted') {
        // Store article data for popup to access
        chrome.storage.local.set({ 
            currentArticleData: request.data,
            timestamp: Date.now()
        });
    }
});

async function scrapeUrlToCTIScraper(data) {
    const { url, title, apiUrl, forceScrape, content } = data;
    
    try {
        const requestBody = {
            url: url,
            title: title || null,
            force_scrape: forceScrape || false
        };
        
        // Include content if provided (e.g., with OCR text)
        if (content) {
            requestBody.content = content;
        }
        
        const response = await fetch(`${apiUrl}/api/scrape-url`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
        }

        const result = await response.json();
        return result;
    } catch (error) {
        console.error('CTIScraper API error:', error);
        throw error;
    }
}

// Handle extension installation
chrome.runtime.onInstalled.addListener((details) => {
    if (details.reason === 'install') {
        // Set default configuration
        chrome.storage.local.set({
            apiUrl: 'http://127.0.0.1:8001',
            forceScrape: false
        });
    }
});
