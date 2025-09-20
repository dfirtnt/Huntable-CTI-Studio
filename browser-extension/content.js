// Content script to extract article data from the current page
(function() {
    'use strict';

    // Extract article information from the current page
    function extractArticleData() {
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
            '.story-title'
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
            '.post-text'
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
                'script', 'style', 'noscript'
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

    // Send article data to popup
    function sendArticleData() {
        const articleData = extractArticleData();
        
        // Store in session storage for popup to access
        sessionStorage.setItem('ctiscraper_article_data', JSON.stringify(articleData));
        
        // Also send message to background script
        chrome.runtime.sendMessage({
            action: 'articleDataExtracted',
            data: articleData
        });
    }

    // Extract data when page loads
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', sendArticleData);
    } else {
        sendArticleData();
    }

    // Listen for messages from popup
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
        if (request.action === 'extractArticleData') {
            const articleData = extractArticleData();
            sendResponse(articleData);
        }
    });

    // Re-extract data when page content changes (for SPAs)
    const observer = new MutationObserver((mutations) => {
        let shouldReextract = false;
        
        mutations.forEach((mutation) => {
            if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                // Check if significant content was added
                mutation.addedNodes.forEach((node) => {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        const element = node;
                        if (element.tagName === 'ARTICLE' || 
                            element.classList.contains('article') ||
                            element.classList.contains('content') ||
                            element.classList.contains('post')) {
                            shouldReextract = true;
                        }
                    }
                });
            }
        });

        if (shouldReextract) {
            setTimeout(sendArticleData, 1000); // Debounce
        }
    });

    // Start observing
    observer.observe(document.body, {
        childList: true,
        subtree: true
    });

})();
