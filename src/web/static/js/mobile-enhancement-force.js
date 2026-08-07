/**
 * Force Mobile Enhancement
 * 
 * Ensures mobile annotation features work by overriding existing system
 */

(function() {
    'use strict';
    
    // Wait for page to load
    function waitForElement(selector, callback, maxAttempts = 50) {
        let attempts = 0;
        const checkElement = () => {
            const element = document.querySelector(selector);
            if (element) {
                callback(element);
            } else if (attempts < maxAttempts) {
                attempts++;
                setTimeout(checkElement, 100);
            }
        };
        checkElement();
    }
    
    // Force mobile enhancement
    function forceMobileEnhancement() {
        console.log('🚀 Forcing mobile annotation enhancement...');
        
        // Find article content
        const articleContent = document.getElementById('article-content');
        if (!articleContent) {
            console.log('❌ Article content not found');
            return;
        }
        
        // Mobile instructions removed - no longer displayed
        
        // Enhance text selection with auto-expansion
        let originalMouseUp = null;
        
        // Override mouseup events
        articleContent.addEventListener('mouseup', function(e) {
            setTimeout(() => {
                const selection = window.getSelection();
                const selectedText = selection.toString().trim();
                
                if (selectedText && selectedText.length > 0) {
                    console.log(`📱 Mobile selection detected: ${selectedText.length} chars`);
                    
                    // Auto-expand to 1000 characters
                    const fullText = articleContent.textContent;
                    const startPos = fullText.indexOf(selectedText);
                    
                    if (startPos !== -1 && selectedText.length < 1000) {
                        const endPos = startPos + selectedText.length;
                        const expandBy = 1000 - selectedText.length;
                        const halfExpand = Math.floor(expandBy / 2);
                        
                        let newStart = Math.max(0, startPos - halfExpand);
                        let newEnd = Math.min(fullText.length, endPos + halfExpand);
                        
                        // Adjust if we hit boundaries
                        if (newStart === 0 && newEnd < fullText.length) {
                            const remainingExpand = 1000 - (newEnd - newStart);
                            newEnd = Math.min(fullText.length, newEnd + remainingExpand);
                        } else if (newEnd === fullText.length && newStart > 0) {
                            const remainingExpand = 1000 - (newEnd - newStart);
                            newStart = Math.max(0, newStart - remainingExpand);
                        }
                        
                        // Ensure we don't exceed 1000 characters
                        const finalLength = newEnd - newStart;
                        if (finalLength > 1000) {
                            const excess = finalLength - 1000;
                            const halfExcess = Math.floor(excess / 2);
                            newStart += halfExcess;
                            newEnd -= (excess - halfExcess);
                        }
                        
                        const expandedText = fullText.substring(newStart, newEnd);
                        console.log(`🎯 Auto-expanded: ${selectedText.length} → ${expandedText.length} chars`);
                        
                        // Show mobile annotation menu
                        showMobileAnnotationMenu(expandedText, newStart, newEnd);
                    }
                }
            }, 100);
        });
        
        // Add touch events for mobile
        articleContent.addEventListener('touchstart', function(e) {
            this.touchStartTime = Date.now();
        }, { passive: true });
        
        articleContent.addEventListener('touchend', function(e) {
            const touchDuration = Date.now() - (this.touchStartTime || 0);
            
            if (touchDuration > 500) { // Long press
                console.log('📱 Long press detected');
                const selection = window.getSelection();
                const selectedText = selection.toString().trim();
                
                if (selectedText) {
                    showMobileAnnotationMenu(selectedText, 0, selectedText.length);
                }
            }
        }, { passive: true });
        
        console.log('✅ Mobile enhancement applied');
    }
    
    // Show mobile annotation menu
    function showMobileAnnotationMenu(text, startPos, endPos) {
        // Remove existing menu
        const existingMenu = document.querySelector('.mobile-annotation-menu');
        if (existingMenu) {
            existingMenu.remove();
        }
        
        const charCount = text.length;
        let lengthStatus = '';
        let lengthColor = '';
        
        if (charCount >= 950 && charCount <= 1000) {
            lengthStatus = '✅ Perfect for ML training';
            lengthColor = 'text-green-600';
        } else if (charCount >= 800) {
            lengthStatus = '🔵 Good length';
            lengthColor = 'text-blue-600';
        } else {
            lengthStatus = '🟡 Auto-expanded';
            lengthColor = 'text-yellow-600';
        }
        
        const menu = document.createElement('div');
        menu.className = 'mobile-annotation-menu fixed bg-white border border-gray-300 rounded-lg shadow-lg p-4 z-50';
        menu.style.left = '50%';
        menu.style.top = '50%';
        menu.style.transform = 'translate(-50%, -50%)';
        menu.style.minWidth = '300px';
        menu.style.maxWidth = '90vw';
        
        menu.innerHTML = `
            <div class="text-center mb-4">
                <div class="text-sm font-semibold text-gray-700 mb-2">Mark as:</div>
                <div class="text-xs ${lengthColor} mb-2">${charCount}/1000 chars - ${lengthStatus}</div>
            </div>
            
            <div class="flex flex-col space-y-3 mb-4">
                <button class="mobile-annotation-btn bg-green-600 text-white px-6 py-3 rounded-lg font-semibold" data-type="huntable">
                    🎯 Huntable
                </button>
                <button class="mobile-annotation-btn bg-red-600 text-white px-6 py-3 rounded-lg font-semibold" data-type="not_huntable">
                    ❌ Not Huntable
                </button>
                <button class="mobile-annotation-btn bg-gray-400 text-white px-6 py-3 rounded-lg font-semibold" data-action="cancel">
                    ✕ Cancel
                </button>
            </div>
            
            <div class="text-xs text-gray-600 text-center">
                "${text.substring(0, 100)}${text.length > 100 ? '...' : ''}"
            </div>
        `;
        
        // Add click handlers
        menu.addEventListener('click', function(e) {
            const button = e.target.closest('.mobile-annotation-btn');
            if (button) {
                const type = button.dataset.type;
                const action = button.dataset.action;
                
                if (action === 'cancel') {
                    menu.remove();
                    window.getSelection().removeAllRanges();
                } else if (type) {
                    // Create annotation
                    createMobileAnnotation(text, startPos, endPos, type);
                    menu.remove();
                    window.getSelection().removeAllRanges();
                }
            }
        });
        
        document.body.appendChild(menu);
        console.log('✅ Mobile annotation menu shown');
    }
    
    // Create annotation via API
    async function createMobileAnnotation(text, startPos, endPos, type) {
        try {
            // Validate length (must be ~1000 chars)
            const textLength = text.length;
            if (textLength < 950 || textLength > 1050) {
                window.showNotification(
                    `Selection must be approximately 1000 characters (current: ${textLength})`,
                    'error'
                );
                return;
            }
            
            const articleId = window.location.pathname.match(/\/articles\/(\d+)/)?.[1];
            if (!articleId) {
                console.error('❌ Could not find article ID');
                return;
            }
            
            const annotationData = {
                annotation_type: type,
                selected_text: text,
                start_position: startPos,
                end_position: endPos,
                context_before: '',
                context_after: '',
                confidence_score: 1.0
            };
            
            const response = await fetch(`/api/articles/${articleId}/annotations`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(annotationData)
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    console.log(`✅ Mobile annotation created: ${type}`);
                    window.showNotification(`Marked as ${type === 'huntable' ? 'Huntable' : 'Not Huntable'}`, 'success');
                } else {
                    console.error('❌ Annotation creation failed:', result.message);
                }
            } else {
                console.error('❌ API request failed:', response.status);
            }
        } catch (error) {
            console.error('❌ Error creating annotation:', error);
        }
    }
    
    // Show notification
    // NOTE: global window.showNotification at base.html is canonical — this local shadow removed.
    
    // Initialize when page loads
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', forceMobileEnhancement);
    } else {
        forceMobileEnhancement();
    }
    
    // Also try after a delay to ensure everything is loaded
    setTimeout(forceMobileEnhancement, 1000);
    
})();
