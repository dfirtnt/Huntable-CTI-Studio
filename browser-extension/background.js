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
    const { imageDataUrl, provider, apiKey, model } = data;

    // Strip the data URL prefix to get raw base64
    const base64 = imageDataUrl.replace(/^data:image\/[a-z]+;base64,/, '');
    const mediaType = (imageDataUrl.match(/^data:(image\/[a-z]+);/) || [])[1] || 'image/png';

    const prompt = 'Extract all visible text from this image exactly as it appears. Return only the extracted text with no commentary or formatting changes.';

    if (provider === 'openai') {
        const response = await fetch('https://api.openai.com/v1/chat/completions', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${apiKey}`
            },
            body: JSON.stringify({
                model: model || 'gpt-4o',
                max_tokens: 4096,
                messages: [{
                    role: 'user',
                    content: [
                        { type: 'image_url', image_url: { url: imageDataUrl } },
                        { type: 'text', text: prompt }
                    ]
                }]
            })
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error?.message || `OpenAI HTTP ${response.status}`);
        }
        const result = await response.json();
        return result.choices[0].message.content.trim();
    }

    if (provider === 'anthropic') {
        const response = await fetch('https://api.anthropic.com/v1/messages', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': apiKey,
                'anthropic-version': '2023-06-01'
            },
            body: JSON.stringify({
                model: model || 'claude-opus-4-7',
                max_tokens: 4096,
                messages: [{
                    role: 'user',
                    content: [
                        { type: 'image', source: { type: 'base64', media_type: mediaType, data: base64 } },
                        { type: 'text', text: prompt }
                    ]
                }]
            })
        });
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.error?.message || `Anthropic HTTP ${response.status}`);
        }
        const result = await response.json();
        return result.content[0].text.trim();
    }

    throw new Error(`Unknown vision provider: ${provider}`);
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
