/**
 * Robust Text Annotation System for Huntable Detection Studio
 * 
 * Handles text selection, annotation creation, and display with proper
 * error handling and DOM manipulation.
 */

class TextAnnotationManager {
    constructor(container, articleId) {
        this.container = container;
        this.articleId = articleId;
        this.annotations = new Map();
        this.currentSelection = null;
        this.isSelecting = false;
        this.annotationMenu = null;
        
        this.init();
    }
    
    init() {
        // Enable text selection
        this.container.style.userSelect = 'text';
        this.container.style.webkitUserSelect = 'text';
        
        // Bind events
        this.bindEvents();
        
        // Load existing annotations
        this.loadAnnotations();
        
        // Add CSS for annotations
        this.addAnnotationStyles();
    }
    
    bindEvents() {
        // Handle text selection
        this.container.addEventListener('mouseup', this.handleSelection.bind(this));
        this.container.addEventListener('keyup', this.handleSelection.bind(this));
        
        // Prevent conflicts with existing selections
        this.container.addEventListener('mousedown', this.handleMouseDown.bind(this));
        
        // Handle clicks outside to close menu
        document.addEventListener('click', this.handleDocumentClick.bind(this));
        
        // Handle escape key
        document.addEventListener('keydown', this.handleKeyDown.bind(this));
    }
    
    handleSelection(event) {
        // Small delay to ensure selection is complete
        setTimeout(() => {
            const selection = window.getSelection();
            const selectedText = selection.toString().trim();
            
            if (selectedText && selectedText.length > 0) {
                this.currentSelection = {
                    text: selectedText,
                    range: selection.getRangeAt(0).cloneRange(),
                    startContainer: selection.getRangeAt(0).startContainer,
                    startOffset: selection.getRangeAt(0).startOffset,
                    endContainer: selection.getRangeAt(0).endContainer,
                    endOffset: selection.getRangeAt(0).endOffset
                };
                
                this.showAnnotationMenu(event);
            }
        }, 10);
    }
    
    handleMouseDown(event) {
        // Clear any existing selection if clicking outside annotation menu
        if (this.annotationMenu && !this.annotationMenu.contains(event.target)) {
            this.hideAnnotationMenu();
        }
    }
    
    handleDocumentClick(event) {
        // Close menu if clicking outside
        if (this.annotationMenu && !this.annotationMenu.contains(event.target) && 
            !this.container.contains(event.target)) {
            this.hideAnnotationMenu();
        }
    }
    
    handleKeyDown(event) {
        if (event.key === 'Escape') {
            this.hideAnnotationMenu();
            window.getSelection().removeAllRanges();
        }
    }
    
    showAnnotationMenu(event) {
        this.hideAnnotationMenu(); // Remove any existing menu
        
        this.annotationMenu = this.createAnnotationMenu();
        document.body.appendChild(this.annotationMenu);
        
        // Position menu near selection
        this.positionMenu(event);
        
        // Show with animation
        requestAnimationFrame(() => {
            this.annotationMenu.classList.add('annotation-menu-visible');
        });
    }
    
    hideAnnotationMenu() {
        if (this.annotationMenu) {
            this.annotationMenu.classList.remove('annotation-menu-visible');
            setTimeout(() => {
                if (this.annotationMenu && this.annotationMenu.parentNode) {
                    this.annotationMenu.parentNode.removeChild(this.annotationMenu);
                }
                this.annotationMenu = null;
            }, 200);
        }
    }
    
    createAnnotationMenu() {
        const menu = document.createElement('div');
        menu.className = 'annotation-menu';
        menu.innerHTML = `
            <div class="annotation-menu-content">
                <div class="annotation-menu-header">
                    <span class="annotation-menu-title">Mark as:</span>
                </div>
                <div class="annotation-menu-actions">
                    <button class="annotation-btn annotation-btn-huntable" data-type="huntable">
                        <span class="annotation-icon">🎯</span>
                        <span class="annotation-label">Huntable</span>
                    </button>
                    <button class="annotation-btn annotation-btn-not-huntable" data-type="not_huntable">
                        <span class="annotation-icon">❌</span>
                        <span class="annotation-label">Not Huntable</span>
                    </button>
                    <button class="annotation-btn annotation-btn-cancel" data-action="cancel">
                        <span class="annotation-icon">✕</span>
                        <span class="annotation-label">Cancel</span>
                    </button>
                </div>
                <div class="annotation-menu-preview">
                    <span class="annotation-preview-text">"${this.currentSelection.text.substring(0, 50)}${this.currentSelection.text.length > 50 ? '...' : ''}"</span>
                </div>
            </div>
        `;
        
        // Bind menu events
        menu.addEventListener('click', this.handleMenuClick.bind(this));
        
        return menu;
    }
    
    positionMenu(event) {
        if (!this.annotationMenu || !this.currentSelection) return;
        
        const rect = this.currentSelection.range.getBoundingClientRect();
        const menuRect = this.annotationMenu.getBoundingClientRect();
        
        let left = rect.left + (rect.width / 2) - (menuRect.width / 2);
        let top = rect.bottom + 10;
        
        // Adjust if menu goes off screen
        if (left < 10) left = 10;
        if (left + menuRect.width > window.innerWidth - 10) {
            left = window.innerWidth - menuRect.width - 10;
        }
        
        if (top + menuRect.height > window.innerHeight - 10) {
            top = rect.top - menuRect.height - 10;
        }
        
        this.annotationMenu.style.position = 'fixed';
        this.annotationMenu.style.left = `${left}px`;
        this.annotationMenu.style.top = `${top}px`;
        this.annotationMenu.style.zIndex = '9999';
    }
    
    handleMenuClick(event) {
        event.stopPropagation();
        
        const button = event.target.closest('.annotation-btn');
        if (!button) return;
        
        const action = button.dataset.action;
        const type = button.dataset.type;
        
        if (action === 'cancel') {
            this.hideAnnotationMenu();
            window.getSelection().removeAllRanges();
            return;
        }
        
        if (type && ['huntable', 'not_huntable'].includes(type)) {
            this.createAnnotation(type);
        }
    }
    
    async createAnnotation(type) {
        if (!this.currentSelection) return;
        
        // Validate length (must be ~1000 chars)
        const textLength = this.currentSelection.text.length;
        if (textLength < 950 || textLength > 1050) {
            this.showNotification(
                `Selection must be approximately 1000 characters (current: ${textLength})`,
                'error'
            );
            return;
        }
        
        try {
            // Show loading state
            this.showLoadingState();
            
            // Calculate positions in the article content
            const positions = this.calculateTextPositions();
            
            // Prepare annotation data
            const annotationData = {
                annotation_type: type,
                selected_text: this.currentSelection.text,
                start_position: positions.start,
                end_position: positions.end,
                context_before: positions.contextBefore,
                context_after: positions.contextAfter,
                confidence_score: 1.0 // Default confidence
            };
            
            // Send to API
            const response = await fetch(`/api/articles/${this.articleId}/annotations`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(annotationData)
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const result = await response.json();
            
            if (result.success) {
                // Add annotation to local storage
                this.annotations.set(result.annotation.id, result.annotation);
                
                // Highlight the text
                this.highlightAnnotation(result.annotation);
                
                // Show success message
                this.showNotification(`Marked as ${type === 'huntable' ? 'Huntable' : 'Not Huntable'}`, 'success');
                
                // Hide menu
                this.hideAnnotationMenu();
                window.getSelection().removeAllRanges();
            } else {
                throw new Error(result.message || 'Failed to create annotation');
            }
            
        } catch (error) {
            console.error('Error creating annotation:', error);
            this.showNotification(`Failed to create annotation: ${error.message}`, 'error');
            this.hideLoadingState();
        }
    }
    
    calculateTextPositions() {
        // Get the full text content of the article
        const fullText = this.container.textContent || this.container.innerText;
        
        // Find the position of the selected text
        const selectedText = this.currentSelection.text;
        const startPos = fullText.indexOf(selectedText);
        const endPos = startPos + selectedText.length;
        
        // Get context (50 characters before and after)
        const contextBefore = fullText.substring(Math.max(0, startPos - 50), startPos);
        const contextAfter = fullText.substring(endPos, Math.min(fullText.length, endPos + 50));
        
        return {
            start: startPos,
            end: endPos,
            contextBefore: contextBefore,
            contextAfter: contextAfter
        };
    }
    
    highlightAnnotation(annotation) {
        // Create highlight element
        const highlight = document.createElement('span');
        highlight.className = `annotation-highlight annotation-${annotation.annotation_type}`;
        highlight.dataset.annotationId = annotation.id;
        highlight.title = `Marked as ${annotation.annotation_type === 'huntable' ? 'Huntable' : 'Not Huntable'}`;
        
        // Wrap the selected text
        try {
            this.currentSelection.range.surroundContents(highlight);
        } catch (error) {
            // If surroundContents fails, try a different approach
            console.warn('Could not wrap selection, using alternative method');
            this.alternativeHighlight(annotation, highlight);
        }
    }
    
    alternativeHighlight(annotation, highlight) {
        // Alternative method for highlighting
        const fullText = this.container.textContent;
        const startPos = annotation.start_position;
        const endPos = annotation.end_position;
        
        if (startPos >= 0 && endPos <= fullText.length) {
            const beforeText = fullText.substring(0, startPos);
            const selectedText = fullText.substring(startPos, endPos);
            const afterText = fullText.substring(endPos);
            
            highlight.textContent = selectedText;
            this.container.innerHTML = beforeText + highlight.outerHTML + afterText;
        }
    }
    
    async loadAnnotations() {
        try {
            const response = await fetch(`/api/articles/${this.articleId}/annotations`);
            if (!response.ok) return;
            
            const result = await response.json();
            if (result.success && result.annotations) {
                result.annotations.forEach(annotation => {
                    this.annotations.set(annotation.id, annotation);
                    this.renderExistingAnnotation(annotation);
                });
            }
        } catch (error) {
            console.error('Error loading annotations:', error);
        }
    }
    
    renderExistingAnnotation(annotation) {
        // This would render existing annotations on page load
        // Implementation depends on how you want to display them
        const fullText = this.container.textContent;
        const startPos = annotation.start_position;
        const endPos = annotation.end_position;
        
        if (startPos >= 0 && endPos <= fullText.length) {
            const beforeText = fullText.substring(0, startPos);
            const selectedText = fullText.substring(startPos, endPos);
            const afterText = fullText.substring(endPos);
            
            const highlight = document.createElement('span');
            highlight.className = `annotation-highlight annotation-${annotation.annotation_type}`;
            highlight.dataset.annotationId = annotation.id;
            highlight.title = `Marked as ${annotation.annotation_type === 'huntable' ? 'Huntable' : 'Not Huntable'}`;
            highlight.textContent = selectedText;
            
            this.container.innerHTML = beforeText + highlight.outerHTML + afterText;
        }
    }
    
    showLoadingState() {
        if (this.annotationMenu) {
            const actions = this.annotationMenu.querySelector('.annotation-menu-actions');
            if (actions) {
                actions.innerHTML = '<div class="annotation-loading">Creating annotation...</div>';
            }
        }
    }
    
    hideLoadingState() {
        // Restore original menu content
        this.hideAnnotationMenu();
    }
    
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `annotation-notification annotation-notification-${type}`;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        // Show with animation
        requestAnimationFrame(() => {
            notification.classList.add('annotation-notification-visible');
        });
        
        // Remove after 3 seconds
        setTimeout(() => {
            notification.classList.remove('annotation-notification-visible');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }
    
    addAnnotationStyles() {
        if (document.getElementById('annotation-styles')) return;
        
        const styles = document.createElement('style');
        styles.id = 'annotation-styles';
        styles.textContent = `
            .annotation-menu {
                position: fixed;
                background: white;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.15);
                padding: 0;
                opacity: 0;
                transform: translateY(-10px);
                transition: all 0.2s ease;
                z-index: 9999;
                min-width: 200px;
            }
            
            .annotation-menu-visible {
                opacity: 1;
                transform: translateY(0);
            }
            
            .annotation-menu-content {
                padding: 12px;
            }
            
            .annotation-menu-header {
                margin-bottom: 8px;
            }
            
            .annotation-menu-title {
                font-size: 12px;
                font-weight: 600;
                color: #6b7280;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            
            .annotation-menu-actions {
                display: flex;
                gap: 6px;
                margin-bottom: 8px;
            }
            
            .annotation-btn {
                display: flex;
                align-items: center;
                gap: 4px;
                padding: 6px 10px;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                background: white;
                cursor: pointer;
                font-size: 12px;
                font-weight: 500;
                transition: all 0.15s ease;
                flex: 1;
                justify-content: center;
            }
            
            .annotation-btn:hover {
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            }
            
            .annotation-btn-huntable:hover {
                background: #dcfce7;
                border-color: #16a34a;
                color: #15803d;
            }
            
            .annotation-btn-not-huntable:hover {
                background: #fef2f2;
                border-color: #dc2626;
                color: #dc2626;
            }
            
            .annotation-btn-cancel:hover {
                background: #f3f4f6;
                border-color: #9ca3af;
                color: #6b7280;
            }
            
            .annotation-icon {
                font-size: 14px;
            }
            
            .annotation-label {
                font-size: 11px;
            }
            
            .annotation-menu-preview {
                padding-top: 8px;
                border-top: 1px solid #f3f4f6;
            }
            
            .annotation-preview-text {
                font-size: 11px;
                color: #6b7280;
                font-style: italic;
                line-height: 1.4;
            }
            
            .annotation-highlight {
                padding: 2px 4px;
                border-radius: 3px;
                cursor: pointer;
                transition: all 0.2s ease;
                position: relative;
            }
            
            .annotation-highlight:hover {
                transform: scale(1.02);
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }
            
            .annotation-huntable {
                background-color: #dcfce7;
                border: 1px solid #16a34a;
                color: #15803d;
            }
            
            .annotation-not_huntable {
                background-color: #fef2f2;
                border: 1px solid #dc2626;
                color: #dc2626;
            }
            
            .annotation-loading {
                text-align: center;
                padding: 8px;
                font-size: 12px;
                color: #6b7280;
            }
            
            .annotation-notification {
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 12px 16px;
                border-radius: 6px;
                color: white;
                font-size: 14px;
                font-weight: 500;
                z-index: 10000;
                opacity: 0;
                transform: translateX(100%);
                transition: all 0.3s ease;
            }
            
            .annotation-notification-visible {
                opacity: 1;
                transform: translateX(0);
            }
            
            .annotation-notification-success {
                background: #16a34a;
            }
            
            .annotation-notification-error {
                background: #dc2626;
            }
            
            .annotation-notification-info {
                background: #2563eb;
            }
        `;
        
        document.head.appendChild(styles);
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = TextAnnotationManager;
}
