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

    let currentArticleData = null;

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
            '.entry',
            '.post',
            '.story'
        ];

        let contentElement = null;
        for (const selector of contentSelectors) {
            contentElement = document.querySelector(selector);
            if (contentElement) {
                // Check if it has substantial content
                const text = contentElement.textContent.trim();
                if (text.length > 200) {
                    break;
                }
            }
        }

        // If no content element found, use body but exclude navigation and footer
        if (!contentElement) {
            contentElement = document.body;
        }

        if (contentElement) {
            // Clean up the content by removing unwanted elements
            const clone = contentElement.cloneNode(true);
            
            // Remove unwanted elements
            const unwantedSelectors = [
                'nav', 'header', 'footer', '.nav', '.navigation', '.menu',
                '.sidebar', '.advertisement', '.ad', '.ads', '.social',
                '.comments', '.comment', '.related', '.recommended',
                '.newsletter', '.subscribe', '.cookie', '.cookie-banner',
                'script', 'style', 'noscript', '.header', '.footer',
                '.breadcrumb', '.breadcrumbs', '.pagination', '.pager'
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

        return data;
    }

    // Update UI with article data
    function updateUI(data) {
        articleTitle.textContent = data.title || 'Untitled Article';
        articleUrl.textContent = data.url || '';
        articleDomain.textContent = data.domain || '';
        wordCount.textContent = `${data.wordCount || 0} words`;
        
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

        const apiUrl = apiUrlInput.value.trim();
        if (!apiUrl) {
            showError('Please enter CTIScraper API URL');
            return;
        }

        showStatus('Sending to CTIScraper...', 'loading');
        scrapeBtn.disabled = true;
        scrapeBtn.innerHTML = '<div class="spinner"></div> Sending...';

        const requestData = {
            url: currentArticleData.url,
            title: currentArticleData.title,
            apiUrl: apiUrl,
            forceScrape: forceScrapeCheckbox.checked
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

    // Load article data on popup open
    loadArticleData();
});
