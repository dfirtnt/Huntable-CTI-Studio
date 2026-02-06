// Popup script for the browser extension
document.addEventListener('DOMContentLoaded', function() {
    const scrapeBtn = document.getElementById('scrape-btn');
    const refreshBtn = document.getElementById('refresh-btn');
    const statusDiv = document.getElementById('status');
    const articleTitle = document.getElementById('article-title');
    const articleUrl = document.getElementById('article-url');
    const articleDomain = document.getElementById('article-domain');
    const wordCount = document.getElementById('word-count');
    const apiUrlInput = document.getElementById('api-url');
    const forceScrapeCheckbox = document.getElementById('force-scrape');
    const extractImagesBtn = document.getElementById('extract-images-btn');
    const imageList = document.getElementById('image-list');
    const ocrStatus = document.getElementById('ocr-status');
    const enableOcrCheckbox = document.getElementById('enable-ocr');

    let currentArticleData = null;
    let extractedImages = [];
    let ocrResults = {};

    // Check if URL is from non-routable IP address
    function isNonRoutableIP(url) {
        try {
            const urlObj = new URL(url);
            const hostname = urlObj.hostname;
            
            // Check for non-routable IP addresses
            const nonRoutablePatterns = [
                /^127\./,                    // 127.0.0.0/8 (localhost)
                /^10\./,                     // 10.0.0.0/8 (private)
                /^172\.(1[6-9]|2[0-9]|3[0-1])\./, // 172.16.0.0/12 (private)
                /^192\.168\./,               // 192.168.0.0/16 (private)
                /^169\.254\./,               // 169.254.0.0/16 (link-local)
                /^::1$/,                     // IPv6 localhost
                /^fe80:/,                    // IPv6 link-local
                /^fc00:/,                    // IPv6 unique local
                /^fd00:/                     // IPv6 unique local
            ];
            
            // Check if hostname matches any non-routable pattern
            return nonRoutablePatterns.some(pattern => pattern.test(hostname));
        } catch (e) {
            return false; // If URL parsing fails, allow it
        }
    }

    // Load saved configuration
    chrome.storage.local.get(['apiUrl', 'forceScrape'], (result) => {
        if (result.apiUrl) {
            apiUrlInput.value = result.apiUrl;
        }
        if (result.forceScrape !== undefined) {
            forceScrapeCheckbox.checked = result.forceScrape;
        }
    });

    // Save configuration when changed
    apiUrlInput.addEventListener('change', () => {
        const apiUrl = apiUrlInput.value.trim();
        if (apiUrl && isNonRoutableIP(apiUrl)) {
            showError('❌ Cannot use non-routable IP addresses for API URL');
            apiUrlInput.value = 'http://127.0.0.1:8001'; // Reset to default
            return;
        }
        chrome.storage.local.set({ apiUrl: apiUrlInput.value });
    });

    forceScrapeCheckbox.addEventListener('change', () => {
        chrome.storage.local.set({ forceScrape: forceScrapeCheckbox.checked });
    });

    // Load article data
    function loadArticleData() {
        chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
            if (tabs[0]) {
                // First try to get from storage (set by content script)
                chrome.storage.local.get(['currentArticleData'], (result) => {
                    if (result.currentArticleData && result.timestamp && (Date.now() - result.timestamp < 30000)) {
                        // Use cached data if it's recent (within 30 seconds)
                        currentArticleData = result.currentArticleData;
                        updateUI(result.currentArticleData);
                    } else {
                        // Try to inject content script and extract data
                        chrome.scripting.executeScript({
                            target: { tabId: tabs[0].id },
                            function: extractArticleDataFromPage
                        }, (results) => {
                            console.log('Scripting results:', results);
                            if (results && results[0] && results[0].result) {
                                currentArticleData = results[0].result;
                                updateUI(results[0].result);
                                // Cache the data
                                chrome.storage.local.set({ 
                                    currentArticleData: results[0].result,
                                    timestamp: Date.now()
                                });
                            } else {
                                // Fallback: try to send message to content script
                                chrome.tabs.sendMessage(tabs[0].id, { action: 'extractArticleData' }, (response) => {
                                    if (response) {
                                        currentArticleData = response;
                                        updateUI(response);
                                        chrome.storage.local.set({ 
                                            currentArticleData: response,
                                            timestamp: Date.now()
                                        });
                                    } else {
                                        showError('Unable to extract article data from this page');
                                    }
                                });
                            }
                        });
                    }
                });
            }
        });
    }

    // Function to extract article data (injected into page)
    function extractArticleDataFromPage() {
        const data = {
            url: window.location.href,
            title: '',
            content: '',
            domain: window.location.hostname,
            wordCount: 0
        };

        // Try to extract title from various sources
        const titleSelectors = [
            'h1',
            'title',
            '.article-title',
            '.post-title',
            '.entry-title',
            '[data-testid="article-title"]',
            '.headline',
            '.story-title',
            '.page-title',
            '.content-title'
        ];

        for (const selector of titleSelectors) {
            const element = document.querySelector(selector);
            if (element && element.textContent.trim()) {
                data.title = element.textContent.trim();
                break;
            }
        }

        // If no title found, use document title
        if (!data.title) {
            data.title = document.title || 'Untitled Article';
        }

        // Try to extract main content from various sources
        const contentSelectors = [
            'article',
            'main',
            '.content',
            '.post-content',
            '.article-content',
            '.entry-content',
            '.story-content',
            '.article-body',
            '.post-body',
            '[data-testid="article-content"]',
            '.article-text',
            '.post-text',
            '[class*="cmp-text"]',
            '[class*="text--blog-content"]',
            '.entry',
            '.post',
            '.story',
            // CISA-specific selectors
            '.usa-prose',
            '.field--name-body',
            '.node__content',
            '.field--type-text-with-summary',
            '.field--name-field-body',
            // General content areas
            '#main-content',
            '#content',
            '.main-content',
            '.page-content',
            '.body-content'
        ];

        let contentElement = null;
        let bestContentElement = null;
        let maxContentLength = 0;

        for (const selector of contentSelectors) {
            const element = document.querySelector(selector);
            if (element) {
                const text = element.textContent.trim();
                if (text.length > maxContentLength) {
                    maxContentLength = text.length;
                    bestContentElement = element;
                }
                // If we find substantial content, use it immediately
                if (text.length > 500) {
                    contentElement = element;
                    break;
                }
            }
        }

        // If no substantial content found, use the best available
        if (!contentElement && bestContentElement) {
            contentElement = bestContentElement;
        }

        // If still no content element found, use body but exclude navigation and footer
        if (!contentElement) {
            contentElement = document.body;
        }

        if (contentElement) {
            // Clean up the content by removing unwanted elements
            const clone = contentElement.cloneNode(true);
            
            // Remove unwanted elements (less aggressive for government sites)
            const unwantedSelectors = [
                'nav', 'header', 'footer', '.nav', '.navigation', '.menu',
                '.sidebar', '.advertisement', '.ad', '.ads', '.social',
                '.comments', '.comment', '.related', '.recommended',
                '.newsletter', '.subscribe', '.cookie', '.cookie-banner',
                'script', 'style', 'noscript', '.header', '.footer',
                '.breadcrumb', '.breadcrumbs', '.pagination', '.pager',
                // Government site specific
                '.site-header', '.site-footer', '.site-navigation',
                '.skip-link', '.usa-skipnav', '.usa-banner',
                '.usa-header', '.usa-footer', '.usa-nav'
            ];

            unwantedSelectors.forEach(selector => {
                const elements = clone.querySelectorAll(selector);
                elements.forEach(el => el.remove());
            });

            data.content = clone.textContent.trim();
        }

        // Calculate word count
        if (data.content) {
            data.wordCount = data.content.split(/\s+/).filter(word => word.length > 0).length;
        }

        // Debug logging
        console.log('CTIScraper Debug:', {
            title: data.title,
            contentLength: data.content ? data.content.length : 0,
            wordCount: data.wordCount,
            contentPreview: data.content ? data.content.substring(0, 200) + '...' : 'No content'
        });

        return data;
    }

    // Update UI with article data
    function updateUI(data) {
        articleTitle.textContent = data.title || 'Untitled Article';
        articleUrl.textContent = data.url || '';
        articleDomain.textContent = data.domain || '';
        wordCount.textContent = `${data.wordCount || 0} words`;
        
        // Check if URL is from non-routable IP and show warning
        if (isNonRoutableIP(data.url)) {
            showError('⚠️ Current page is from non-routable IP - cannot ingest');
            scrapeBtn.disabled = true;
            scrapeBtn.textContent = 'Non-routable IP';
            return;
        }
        
        // Enable/disable scrape button based on content
        if (data.wordCount < 50) {
            scrapeBtn.disabled = true;
            scrapeBtn.textContent = 'Content too short';
        } else {
            scrapeBtn.disabled = false;
            scrapeBtn.innerHTML = `
                <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
                </svg>
                Send to CTIScraper
            `;
        }
    }

    // Show status message
    function showStatus(message, type = 'loading') {
        statusDiv.textContent = message;
        statusDiv.className = `status ${type}`;
        statusDiv.classList.remove('hidden');
    }

    // Show error message
    function showError(message) {
        showStatus(message, 'error');
    }

    // Show success message
    function showSuccess(message) {
        showStatus(message, 'success');
    }

    // Hide status
    function hideStatus() {
        statusDiv.classList.add('hidden');
    }

    // Scrape URL to CTIScraper
    function scrapeToCTIScraper() {
        if (!currentArticleData) {
            showError('No article data available. Try clicking Refresh first.');
            return;
        }

        // Check if current page URL is from non-routable IP
        if (isNonRoutableIP(currentArticleData.url)) {
            showError('❌ Cannot ingest from non-routable IP addresses (127.0.0.1, 192.168.x.x, etc.)');
            return;
        }

        const apiUrl = apiUrlInput.value.trim();
        if (!apiUrl) {
            showError('Please enter CTIScraper API URL');
            return;
        }

        // Append OCR text to content if enabled
        let contentToSend = currentArticleData.content || '';
        if (enableOcrCheckbox.checked && Object.keys(ocrResults).length > 0) {
            const ocrText = getOCRText();
            if (ocrText) {
                contentToSend = contentToSend + ocrText;
            }
        }

        showStatus('Sending to CTIScraper...', 'loading');
        scrapeBtn.disabled = true;
        scrapeBtn.innerHTML = '<div class="spinner"></div> Sending...';

        const requestData = {
            url: currentArticleData.url,
            title: currentArticleData.title,
            apiUrl: apiUrl,
            forceScrape: forceScrapeCheckbox.checked,
            content: contentToSend  // Include content with OCR text
        };

        chrome.runtime.sendMessage({
            action: 'scrapeUrl',
            data: requestData
        }, (response) => {
            scrapeBtn.disabled = false;
            scrapeBtn.innerHTML = `
                <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/>
                </svg>
                Send to CTIScraper
            `;

            if (response && response.success) {
                const result = response.data;
                if (result.success) {
                    showSuccess(`✅ Article sent successfully! ID: ${result.article_id}`);
                    
                    // Open the article in CTIScraper
                    setTimeout(() => {
                        chrome.tabs.create({
                            url: `${apiUrl}/articles/${result.article_id}`
                        });
                    }, 1500);
                } else {
                    if (result.error === 'Article already exists') {
                        showSuccess(`⚠️ Article already exists (ID: ${result.article_id})`);
                        setTimeout(() => {
                            chrome.tabs.create({
                                url: `${apiUrl}/articles/${result.article_id}`
                            });
                        }, 1500);
                    } else {
                        showError(`Error: ${result.error}`);
                    }
                }
            } else {
                const error = response?.error || 'Unknown error occurred';
                showError(`Failed to send to CTIScraper: ${error}`);
            }
        });
    }

    // Event listeners
    scrapeBtn.addEventListener('click', scrapeToCTIScraper);
    refreshBtn.addEventListener('click', loadArticleData);

    // Extract images from page
    async function extractImagesFromPage() {
        extractImagesBtn.disabled = true;
        extractImagesBtn.innerHTML = '<div class="spinner"></div> Extracting...';
        imageList.innerHTML = '';
        extractedImages = [];
        ocrResults = {};

        chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
            if (!tabs[0]) {
                extractImagesBtn.disabled = false;
                extractImagesBtn.innerHTML = 'Extract Images from Page';
                return;
            }

            try {
                const results = await chrome.scripting.executeScript({
                    target: { tabId: tabs[0].id },
                    function: extractImagesFromPageDOM
                });

                if (results && results[0] && results[0].result) {
                    extractedImages = results[0].result;
                    displayImageList();
                } else {
                    showError('No images found on this page');
                }
            } catch (error) {
                console.error('Error extracting images:', error);
                showError('Failed to extract images: ' + error.message);
            } finally {
                extractImagesBtn.disabled = false;
                extractImagesBtn.innerHTML = `
                    <svg class="icon" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/>
                    </svg>
                    Extract Images from Page
                `;
            }
        });
    }

    // Function injected into page to extract images
    function extractImagesFromPageDOM() {
        const images = Array.from(document.querySelectorAll('img'));
        const imageData = [];

        images.forEach((img, index) => {
            // Skip very small images (likely icons/sprites)
            if (img.naturalWidth < 50 || img.naturalHeight < 50) {
                return;
            }

            // Skip data URLs that are too small
            if (img.src.startsWith('data:') && img.src.length < 1000) {
                return;
            }

            // Get image source
            let src = img.src || img.currentSrc;
            
            // Try to get full resolution image
            if (img.dataset.src) {
                src = img.dataset.src;
            } else if (img.dataset.lazySrc) {
                src = img.dataset.lazySrc;
            }

            // Skip if no valid source
            if (!src || src.startsWith('data:image/svg')) {
                return;
            }

            imageData.push({
                id: `img_${index}`,
                src: src,
                alt: img.alt || `Image ${index + 1}`,
                width: img.naturalWidth || img.width,
                height: img.naturalHeight || img.height
            });
        });

        return imageData;
    }

    // Display list of extracted images
    function displayImageList() {
        if (extractedImages.length === 0) {
            imageList.innerHTML = '<div style="padding: 8px; color: #718096; font-size: 12px;">No images found</div>';
            return;
        }

        imageList.innerHTML = extractedImages.map(img => `
            <div class="image-item" data-image-id="${img.id}">
                <img src="${img.src}" alt="${img.alt}" crossorigin="anonymous" onerror="this.src='data:image/svg+xml,%3Csvg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'40\\' height=\\'40\\'%3E%3Crect fill=\\'%23e5e7eb\\' width=\\'40\\' height=\\'40\\'/%3E%3Ctext x=\\'50%25\\' y=\\'50%25\\' text-anchor=\\'middle\\' dy=\\'0.3em\\' fill=\\'%23999\\' font-size=\\'10\\'%3E?%3C/text%3E%3C/svg%3E'">
                <div class="image-item-info">
                    <div class="image-item-name">${img.alt || 'Image'}</div>
                    <div class="image-item-status" id="status-${img.id}">Ready</div>
                </div>
                <div class="image-item-actions">
                    <button class="btn btn-secondary btn-small" onclick="window.ocrImage('${img.id}')">OCR</button>
                </div>
            </div>
        `).join('');

        // Make OCR function available globally for onclick handlers
        window.ocrImage = async (imageId) => {
            await performOCR(imageId);
        };
    }

    // Perform OCR on a specific image
    async function performOCR(imageId) {
        const image = extractedImages.find(img => img.id === imageId);
        if (!image) return;

        const statusEl = document.getElementById(`status-${imageId}`);
        if (!statusEl) return;

        statusEl.textContent = 'Processing...';
        statusEl.style.color = '#2a4365';

        try {
            // Check if Tesseract is available
            if (typeof Tesseract === 'undefined') {
                throw new Error('Tesseract.js not loaded. Please refresh the extension.');
            }

            showStatus('Running OCR...', 'loading');

            // Create a canvas to handle CORS issues
            const img = new Image();
            img.crossOrigin = 'anonymous';
            
            // Use a proxy approach: fetch image via content script
            const imageData = await new Promise((resolve, reject) => {
                chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
                    chrome.scripting.executeScript({
                        target: { tabId: tabs[0].id },
                        function: fetchImageAsDataURL,
                        args: [image.src]
                    }, (results) => {
                        if (results && results[0] && results[0].result) {
                            resolve(results[0].result);
                        } else {
                            reject(new Error('Failed to fetch image'));
                        }
                    });
                });
            });

            // Perform OCR
            const { data: { text } } = await Tesseract.recognize(imageData, 'eng', {
                logger: m => {
                    if (m.status === 'recognizing text') {
                        statusEl.textContent = `OCR: ${Math.round(m.progress * 100)}%`;
                    }
                }
            });

            ocrResults[imageId] = text.trim();
            statusEl.textContent = '✓ OCR Complete';
            statusEl.style.color = '#22543d';
            
            hideStatus();
            showSuccess(`OCR completed for ${image.alt || 'image'}`);

        } catch (error) {
            console.error('OCR error:', error);
            statusEl.textContent = '✗ OCR Failed';
            statusEl.style.color = '#742a2a';
            showError(`OCR failed: ${error.message}`);
        }
    }

    // Function to fetch image as data URL (injected into page)
    function fetchImageAsDataURL(imageSrc) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.crossOrigin = 'anonymous';
            
            img.onload = function() {
                const canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                
                try {
                    const dataURL = canvas.toDataURL('image/png');
                    resolve(dataURL);
                } catch (e) {
                    reject(e);
                }
            };
            
            img.onerror = () => reject(new Error('Failed to load image'));
            img.src = imageSrc;
        });
    }

    // Get OCR text to append to content
    function getOCRText() {
        if (!enableOcrCheckbox.checked || Object.keys(ocrResults).length === 0) {
            return '';
        }

        const ocrTexts = [];
        extractedImages.forEach(img => {
            if (ocrResults[img.id]) {
                ocrTexts.push(`\n\n[Image OCR: ${img.alt || 'Image'}]\n${ocrResults[img.id]}`);
            }
        });

        return ocrTexts.join('\n\n');
    }


    // Event listeners
    extractImagesBtn.addEventListener('click', extractImagesFromPage);
    enableOcrCheckbox.addEventListener('change', () => {
        chrome.storage.local.set({ enableOCR: enableOcrCheckbox.checked });
    });

    // Load OCR preference
    chrome.storage.local.get(['enableOCR'], (result) => {
        if (result.enableOCR !== undefined) {
            enableOcrCheckbox.checked = result.enableOCR;
        }
    });

    // Load article data on popup open
    loadArticleData();
});
