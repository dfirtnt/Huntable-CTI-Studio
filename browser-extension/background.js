// Background script for API communication
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'scrapeUrl') {
        let responded = false;
        const safeSend = (payload) => {
            if (responded) return;
            responded = true;
            try {
                sendResponse(payload);
            } catch (_) {
                // Channel already closed (e.g. popup/tab closed)
            }
        };
        scrapeUrlToCTIScraper(request.data)
            .then(result => safeSend({ success: true, data: result }))
            .catch(error => safeSend({ success: false, error: error.message }));
        return true; // Keep message channel open for async response
    }

    if (request.action === 'fetchImageAsDataURL') {
        let responded = false;
        const safeSend = (payload) => {
            if (responded) return;
            responded = true;
            try { sendResponse(payload); } catch (_) {}
        };
        fetchImageAsDataURL(request.data.src)
            .then(dataUrl => safeSend({ success: true, dataUrl }))
            .catch(error => safeSend({ success: false, error: error.message }));
        return true;
    }

    if (request.action === 'callVisionLLM') {
        let responded = false;
        const safeSend = (payload) => {
            if (responded) return;
            responded = true;
            try {
                sendResponse(payload);
            } catch (_) {}
        };
        callVisionLLM(request.data)
            .then(text => safeSend({ success: true, text }))
            .catch(error => safeSend({ success: false, error: error.message }));
        return true;
    }

    if (request.action === 'articleDataExtracted') {
        // Store article data for popup to access
        chrome.storage.local.set({
            currentArticleData: request.data,
            timestamp: Date.now()
        });
    }
});

async function fetchImageAsDataURL(src) {
    const response = await fetch(src);
    if (!response.ok) throw new Error(`Image fetch failed: ${response.status}`);
    const blob = await response.blob();
    const mimeType = blob.type || 'image/png';
    const arrayBuffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(arrayBuffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
    return `data:${mimeType};base64,${btoa(binary)}`;
}

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

async function callVisionLLM(data) {
    const { imageDataUrl, provider, apiUrl } = data;

    const backendUrl = (apiUrl || 'http://127.0.0.1:8001').replace(/\/$/, '');
    const response = await fetch(`${backendUrl}/api/vision/extract`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ imageDataUrl, provider })
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${response.status}`);
    }

    const result = await response.json();
    return result.text;
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
