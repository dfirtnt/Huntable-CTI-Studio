/**
 * Mobile Annotation Initialization Script
 * 
 * Automatically initializes mobile-optimized annotation system on article pages
 */

document.addEventListener('DOMContentLoaded', function() {
    // Check if we're on an article detail page
    const articleContent = document.getElementById('article-content');
    const articleId = window.location.pathname.match(/\/articles\/(\d+)/);
    
    if (articleContent && articleId) {
        console.log('Initializing mobile annotation system for article', articleId[1]);
        
        // Add mobile-specific instructions immediately
        addMobileInstructions();
        
        // Wait for mobile annotation manager to load
        const initMobileAnnotation = () => {
            if (typeof MobileTextAnnotationManager !== 'undefined') {
                // Initialize mobile annotation manager
                window.mobileAnnotationManager = new MobileTextAnnotationManager(articleContent, articleId[1]);
                console.log('Mobile annotation manager initialized');
            } else {
                // Retry after a short delay
                setTimeout(initMobileAnnotation, 100);
            }
        };
        
        initMobileAnnotation();
        
        // Also enhance the existing SimpleTextManager with mobile features
        enhanceExistingAnnotationSystem();
    }
});

function enhanceExistingAnnotationSystem() {
    // Wait for SimpleTextManager to be available
    const enhanceSystem = () => {
        if (window.simpleTextManager) {
            console.log('Enhancing existing annotation system with mobile features');
            
            // Add mobile auto-expansion to existing system
            const originalShowClassificationOptions = window.simpleTextManager.showClassificationOptions;
            window.simpleTextManager.showClassificationOptions = function(startPos, endPos) {
                // Auto-expand to 1000 characters for mobile
                const fullText = this.contentElement.textContent;
                const currentText = fullText.substring(startPos, endPos);
                const targetLength = 1000;
                
                if (currentText.length < targetLength) {
                    const expandBy = targetLength - currentText.length;
                    const halfExpand = Math.floor(expandBy / 2);
                    
                    let newStart = Math.max(0, startPos - halfExpand);
                    let newEnd = Math.min(fullText.length, endPos + halfExpand);
                    
                    // Adjust if we hit boundaries
                    if (newStart === 0 && newEnd < fullText.length) {
                        const remainingExpand = targetLength - (newEnd - newStart);
                        newEnd = Math.min(fullText.length, newEnd + remainingExpand);
                    } else if (newEnd === fullText.length && newStart > 0) {
                        const remainingExpand = targetLength - (newEnd - newStart);
                        newStart = Math.max(0, newStart - remainingExpand);
                    }
                    
                    // Ensure we don't exceed 1000 characters
                    const finalLength = newEnd - newStart;
                    if (finalLength > targetLength) {
                        const excess = finalLength - targetLength;
                        const halfExcess = Math.floor(excess / 2);
                        newStart += halfExcess;
                        newEnd -= (excess - halfExcess);
                    }
                    
                    console.log(`Mobile auto-expand: ${currentText.length} → ${newEnd - newStart} chars`);
                    startPos = newStart;
                    endPos = newEnd;
                }
                
                // Call original function with expanded selection
                return originalShowClassificationOptions.call(this, startPos, endPos);
            };
            
            console.log('Mobile enhancement applied to existing annotation system');
        } else {
            setTimeout(enhanceSystem, 100);
        }
    };
    
    enhanceSystem();
}

function addMobileInstructions() {
    // Instructions removed - no longer displayed
    return;
}
