/**
 * Mobile-Optimized Text Annotation System for Huntable CTI Studio
 * 
 * Enhanced version with touch support for iPhone/iPad usage
 */

const HUNTABILITY_MODE = 'huntability';
const OBSERVABLE_MODE = 'observables';
const OBSERVABLE_TYPES = ['CMD', 'PROC_LINEAGE'];
const MOBILE_ANNOTATION_LABELS = {
    huntable: 'Huntable',
    not_huntable: 'Not Huntable',
    CMD: 'CMD',
    PROC_LINEAGE: 'Process Lineage'
};

class MobileTextAnnotationManager {
    constructor(container, articleId) {
        this.container = container;
        this.articleId = articleId;
        this.annotations = new Map();
        this.currentSelection = null;
        this.isSelecting = false;
        this.annotationMenu = null;
        this.isMobile = this.detectMobile();
        this.touchStartPos = null;
        this.touchEndPos = null;
        this.longPressTimer = null;
        this.isLongPress = false;
        
        this.init();
    }
    
    detectMobile() {
        return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
               ('ontouchstart' in window) ||
               (navigator.maxTouchPoints > 0);
    }

    getAnnotationMode() {
        return localStorage.getItem('annotationMode') || HUNTABILITY_MODE;
    }

    getObservableType() {
        const stored = localStorage.getItem('observableType');
        if (stored && OBSERVABLE_TYPES.includes(stored)) {
            return stored;
        }
        return 'CMD';
    }

    getAnnotationLabel(type) {
        return MOBILE_ANNOTATION_LABELS[type] || type;
    }
    
    init() {
        // Enable text selection
        this.container.style.userSelect = 'text';
        this.container.style.webkitUserSelect = 'text';
        this.container.style.touchAction = 'manipulation';
        
        // Add mobile-specific CSS
        this.addMobileStyles();
        
        // Bind events (both mouse and touch)
        this.bindEvents();
        
        // Load existing annotations
        this.loadAnnotations();
    }
    
    bindEvents() {
        if (this.isMobile) {
            // Touch events for mobile
            this.container.addEventListener('touchstart', this.handleTouchStart.bind(this), { passive: false });
            this.container.addEventListener('touchmove', this.handleTouchMove.bind(this), { passive: false });
            this.container.addEventListener('touchend', this.handleTouchEnd.bind(this), { passive: false });
            
            // Prevent zoom on double tap
            this.container.addEventListener('touchend', this.preventZoom.bind(this), { passive: false });
            
            // Handle text selection after touch
            this.container.addEventListener('selectionchange', this.handleSelectionChange.bind(this));
        } else {
            // Mouse events for desktop
            this.container.addEventListener('mouseup', this.handleSelection.bind(this));
            this.container.addEventListener('keyup', this.handleSelection.bind(this));
            this.container.addEventListener('mousedown', this.handleMouseDown.bind(this));
        }
        
        // Common events
        document.addEventListener('click', this.handleDocumentClick.bind(this));
        document.addEventListener('keydown', this.handleKeyDown.bind(this));
        
        // Handle orientation changes
        window.addEventListener('orientationchange', this.handleOrientationChange.bind(this));
    }
    
    handleTouchStart(event) {
        this.touchStartPos = {
            x: event.touches[0].clientX,
            y: event.touches[0].clientY,
            time: Date.now()
        };
        
        // Start long press timer
        this.longPressTimer = setTimeout(() => {
            this.isLongPress = true;
            this.showMobileAnnotationMenu(event.touches[0]);
        }, 500);
        
        // Clear any existing selection
        window.getSelection().removeAllRanges();
    }
    
    handleTouchMove(event) {
        // Cancel long press if user moves finger
        if (this.longPressTimer) {
            clearTimeout(this.longPressTimer);
            this.longPressTimer = null;
        }
        
        // Prevent scrolling while selecting
        if (this.isSelecting) {
            event.preventDefault();
        }
    }
    
    handleTouchEnd(event) {
        this.touchEndPos = {
            x: event.changedTouches[0].clientX,
            y: event.changedTouches[0].clientY,
            time: Date.now()
        };
        
        // Cancel long press timer
        if (this.longPressTimer) {
            clearTimeout(this.longPressTimer);
            this.longPressTimer = null;
        }
        
        // Handle selection after a short delay
        setTimeout(() => {
            this.handleSelection(event);
        }, 100);
    }
    
    preventZoom(event) {
        // Prevent double-tap zoom
        if (event.touches && event.touches.length > 1) {
            event.preventDefault();
        }
    }
    
    handleSelectionChange(event) {
        // Handle text selection changes on mobile
        setTimeout(() => {
            const selection = window.getSelection();
            const selectedText = selection.toString().trim();
            
            if (selectedText && selectedText.length > 0 && !this.isLongPress) {
                // Don't auto-expand here - let the main system handle it
                this.currentSelection = {
                    text: selectedText,
                    range: selection.getRangeAt(0).cloneRange(),
                    startContainer: selection.getRangeAt(0).startContainer,
                    startOffset: selection.getRangeAt(0).startOffset,
                    endContainer: selection.getRangeAt(0).endContainer,
                    endOffset: selection.getRangeAt(0).endOffset
                };
                
                this.showMobileAnnotationMenu();
            }
        }, 50);
    }
    
    showMobileAnnotationMenu(touchEvent = null) {
        this.hideAnnotationMenu();
        
        this.annotationMenu = this.createMobileAnnotationMenu();
        document.body.appendChild(this.annotationMenu);
        
        // Position menu
        if (touchEvent) {
            this.positionMobileMenu(touchEvent);
        } else {
            this.positionMenuFromSelection();
        }
        
        // Show with animation
        requestAnimationFrame(() => {
            this.annotationMenu.classList.add('annotation-menu-visible');
        });
    }
    
    createMobileAnnotationMenu() {
        if (!this.currentSelection) return null;
        
        const selectedText = this.currentSelection.text;
        const charCount = selectedText.length;
        
        // Determine length status and color
        let lengthStatus = '';
        let lengthColor = '';
        if (charCount >= 950 && charCount <= 1000) {
            lengthStatus = '✅ Perfect length for ML training';
            lengthColor = 'text-green-600';
        } else if (charCount >= 800 && charCount < 950) {
            lengthStatus = '🔵 Good length';
            lengthColor = 'text-blue-600';
        } else if (charCount < 800) {
            lengthStatus = '🟡 Short - auto-expanded';
            lengthColor = 'text-yellow-600';
        } else {
            lengthStatus = '🔴 Long - auto-trimmed';
            lengthColor = 'text-red-600';
        }
        
        const menu = document.createElement('div');
        menu.className = 'annotation-menu mobile-annotation-menu';
        menu.innerHTML = `
            <div class="annotation-menu-content">
                <div class="annotation-menu-header">
                    <span class="annotation-menu-title">Mark as:</span>
                    <div class="char-counter mobile-char-counter">
                        <span class="char-count ${lengthColor}">${charCount}/1000 chars</span>
                        <div class="length-status ${lengthColor}">${lengthStatus}</div>
                    </div>
                </div>
                
                <div class="annotation-menu-actions mobile-actions">
                    <button class="annotation-btn annotation-btn-huntable mobile-btn" data-type="huntable">
                        <span class="annotation-icon">🎯</span>
                        <span class="annotation-label">Huntable</span>
                    </button>
                    <button class="annotation-btn annotation-btn-not-huntable mobile-btn" data-type="not_huntable">
                        <span class="annotation-icon">❌</span>
                        <span class="annotation-label">Not Huntable</span>
                    </button>
                    <button class="annotation-btn annotation-btn-cancel mobile-btn" data-action="cancel">
                        <span class="annotation-icon">✕</span>
                        <span class="annotation-label">Cancel</span>
                    </button>
                </div>
                <div class="annotation-menu-preview mobile-preview">
                    <span class="annotation-preview-text">"${selectedText.substring(0, 150)}${selectedText.length > 150 ? '...' : ''}"</span>
                </div>
            </div>
        `;
        
        // Bind menu events
        menu.addEventListener('click', this.handleMenuClick.bind(this));
        
        return menu;
    }
    
    positionMobileMenu(touchEvent) {
        if (!this.annotationMenu) return;
        
        const menuRect = this.annotationMenu.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        
        let left = touchEvent.clientX - (menuRect.width / 2);
        let top = touchEvent.clientY - menuRect.height - 20;
        
        // Adjust if menu goes off screen
        if (left < 10) left = 10;
        if (left + menuRect.width > viewportWidth - 10) {
            left = viewportWidth - menuRect.width - 10;
        }
        
        if (top < 10) {
            top = touchEvent.clientY + 20;
        }
        
        this.annotationMenu.style.position = 'fixed';
        this.annotationMenu.style.left = `${left}px`;
        this.annotationMenu.style.top = `${top}px`;
        this.annotationMenu.style.zIndex = '9999';
    }
    
    positionMenuFromSelection() {
        if (!this.annotationMenu || !this.currentSelection) return;
        
        const rect = this.currentSelection.range.getBoundingClientRect();
        const menuRect = this.annotationMenu.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        
        let left = rect.left + (rect.width / 2) - (menuRect.width / 2);
        let top = rect.bottom + 10;
        
        // Adjust if menu goes off screen
        if (left < 10) left = 10;
        if (left + menuRect.width > viewportWidth - 10) {
            left = viewportWidth - menuRect.width - 10;
        }
        
        if (top + menuRect.height > viewportHeight - 10) {
            top = rect.top - menuRect.height - 10;
        }
        
        this.annotationMenu.style.position = 'fixed';
        this.annotationMenu.style.left = `${left}px`;
        this.annotationMenu.style.top = `${top}px`;
        this.annotationMenu.style.zIndex = '9999';
    }
    
    handleSelection(event) {
        // Small delay to ensure selection is complete
        setTimeout(() => {
            const selection = window.getSelection();
            const selectedText = selection.toString().trim();
            
            if (selectedText && selectedText.length > 0 && !this.isLongPress) {
                // Don't auto-expand here - let the main system handle it
                this.currentSelection = {
                    text: selectedText,
                    range: selection.getRangeAt(0).cloneRange(),
                    startContainer: selection.getRangeAt(0).startContainer,
                    startOffset: selection.getRangeAt(0).startOffset,
                    endContainer: selection.getRangeAt(0).endContainer,
                    endOffset: selection.getRangeAt(0).endOffset
                };
                
                if (this.getAnnotationMode() === OBSERVABLE_MODE) {
                    this.createAnnotation(this.getObservableType(), { skipLengthValidation: true });
                } else {
                    this.showAnnotationMenu(event);
                }
            }
        }, 10);
    }
    
    showAnnotationMenu(event) {
        this.hideAnnotationMenu();
        
        this.annotationMenu = this.createAnnotationMenu();
        document.body.appendChild(this.annotationMenu);
        
        // Position menu near selection
        this.positionMenu(event);
        
        // Show with animation
        requestAnimationFrame(() => {
            this.annotationMenu.classList.add('annotation-menu-visible');
        });
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
    
    handleOrientationChange() {
        // Reposition menu after orientation change
        setTimeout(() => {
            if (this.annotationMenu && this.currentSelection) {
                this.positionMenuFromSelection();
            }
        }, 100);
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
        
        const allowedTypes = ['huntable', 'not_huntable', ...OBSERVABLE_TYPES];
        if (type && allowedTypes.includes(type)) {
            const skipValidation = !this.shouldEnforceLength(type);
            this.createAnnotation(type, { skipLengthValidation: skipValidation });
        }
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
    
    shouldEnforceLength(type) {
        return ['huntable', 'not_huntable'].includes(type);
    }
    
    async createAnnotation(type, options = {}) {
        if (!this.currentSelection) return;
        const skipLengthValidation = options.skipLengthValidation || false;
        
        // Validate length (must be ~1000 chars)
        const textLength = this.currentSelection.text.length;
        if (!skipLengthValidation && (textLength < 950 || textLength > 1050)) {
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
            const context = this.calculateTextPositions();
            const annotationData = {
                annotation_type: type,
                selected_text: this.currentSelection.text,
                start_position: context.start,
                end_position: context.end,
                context_before: context.contextBefore,
                context_after: context.contextAfter,
                confidence_score: 1.0
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
                const label = this.getAnnotationLabel(type);
                this.showNotification(`Saved ${label}`, 'success');
                
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
        const fullText = this.container.textContent || this.container.innerText;
        const selectedText = this.currentSelection.text;
        const startPos = fullText.indexOf(selectedText);
        const endPos = startPos + selectedText.length;
        
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
        const highlight = document.createElement('span');
        highlight.className = `annotation-highlight annotation-${annotation.annotation_type}`;
        highlight.dataset.annotationId = annotation.id;
        highlight.dataset.annotationType = annotation.annotation_type;
        highlight.title = `Marked as ${this.getAnnotationLabel(annotation.annotation_type)}`;
        
        try {
            this.currentSelection.range.surroundContents(highlight);
        } catch (error) {
            console.warn('Could not wrap selection, using alternative method');
            this.alternativeHighlight(annotation, highlight);
        }
    }
    
    alternativeHighlight(annotation, highlight) {
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
            highlight.dataset.annotationType = annotation.annotation_type;
            highlight.title = `Marked as ${this.getAnnotationLabel(annotation.annotation_type)}`;
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
        this.hideAnnotationMenu();
    }
    
    showNotification(message, type = 'info') {
        const notification = document.createElement('div');
        notification.className = `annotation-notification annotation-notification-${type}`;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        requestAnimationFrame(() => {
            notification.classList.add('annotation-notification-visible');
        });
        
        setTimeout(() => {
            notification.classList.remove('annotation-notification-visible');
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }, 3000);
    }
    
    autoExpandTo1000(selectedText) {
        const fullText = this.container.textContent || this.container.innerText;
        const targetLength = 1000;
        const currentLength = selectedText.length;
        
        // Find the position of the selected text in the full text
        const startPos = fullText.indexOf(selectedText);
        if (startPos === -1) {
            // Fallback: use original selection
            const selection = window.getSelection();
            return {
                text: selectedText,
                range: selection.getRangeAt(0).cloneRange()
            };
        }
        
        const endPos = startPos + currentLength;
        let newStart = startPos;
        let newEnd = endPos;
        
        if (currentLength < targetLength) {
            // Need to expand - calculate how much to add
            const expandBy = targetLength - currentLength;
            const halfExpand = Math.floor(expandBy / 2);
            
            // Expand symmetrically
            newStart = Math.max(0, startPos - halfExpand);
            newEnd = Math.min(fullText.length, endPos + halfExpand);
            
            // If we hit boundaries, expand more on the other side
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
        } else if (currentLength > targetLength) {
            // Need to trim - calculate how much to remove
            const trimBy = currentLength - targetLength;
            const halfTrim = Math.floor(trimBy / 2);
            newStart = startPos + halfTrim;
            newEnd = endPos - (trimBy - halfTrim);
        }
        
        // Apply smart boundary detection (find word/sentence boundaries)
        const smartBoundaries = this.findSmartBoundaries(fullText, newStart, newEnd);
        newStart = smartBoundaries.start;
        newEnd = smartBoundaries.end;
        
        // Final check - ensure we don't exceed 1000 characters
        const finalLength = newEnd - newStart;
        if (finalLength > targetLength) {
            const excess = finalLength - targetLength;
            const halfExcess = Math.floor(excess / 2);
            newStart += halfExcess;
            newEnd -= (excess - halfExcess);
        }
        
        const expandedText = fullText.substring(newStart, newEnd);
        
        // Create new range for the expanded selection
        const range = document.createRange();
        const walker = document.createTreeWalker(
            this.container,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let currentPos = 0;
        let startNode = null;
        let endNode = null;
        let startOffset = 0;
        let endOffset = 0;
        
        let node = walker.nextNode();
        while (node) {
            const nodeLength = node.textContent.length;
            
            if (!startNode && currentPos + nodeLength > newStart) {
                startNode = node;
                startOffset = newStart - currentPos;
            }
            
            if (!endNode && currentPos + nodeLength >= newEnd) {
                endNode = node;
                endOffset = newEnd - currentPos;
                break;
            }
            
            currentPos += nodeLength;
            node = walker.nextNode();
        }
        
        if (startNode && endNode) {
            range.setStart(startNode, startOffset);
            range.setEnd(endNode, endOffset);
        }
        
        console.log(`Mobile auto-expand: ${currentLength} → ${expandedText.length} chars`);
        
        return {
            text: expandedText,
            range: range
        };
    }
    
    findSmartBoundaries(fullText, start, end) {
        // Find word boundaries near the start
        let smartStart = start;
        for (let i = start; i > Math.max(0, start - 50); i--) {
            if (fullText[i] === ' ' || fullText[i] === '\n' || fullText[i] === '.') {
                smartStart = i + 1;
                break;
            }
        }
        
        // Find word boundaries near the end
        let smartEnd = end;
        for (let i = end; i < Math.min(fullText.length, end + 50); i++) {
            if (fullText[i] === ' ' || fullText[i] === '\n' || fullText[i] === '.') {
                smartEnd = i;
                break;
            }
        }
        
        return { start: smartStart, end: smartEnd };
    }
    
    addMobileStyles() {
        if (document.getElementById('mobile-annotation-styles')) return;
        
        const styles = document.createElement('style');
        styles.id = 'mobile-annotation-styles';
        styles.textContent = `
            /* Mobile-specific annotation styles */
            .mobile-annotation-menu {
                min-width: 280px;
                max-width: 90vw;
            }
            
            .mobile-actions {
                flex-direction: column;
                gap: 8px;
            }
            
            .mobile-btn {
                padding: 12px 16px;
                font-size: 16px;
                min-height: 44px;
                touch-action: manipulation;
            }
            
            .mobile-btn .annotation-icon {
                font-size: 18px;
            }
            
            .mobile-btn .annotation-label {
                font-size: 14px;
                font-weight: 600;
            }
            
            .mobile-preview {
                padding: 12px;
                font-size: 14px;
                line-height: 1.5;
            }
            
            .mobile-preview .annotation-preview-text {
                font-size: 13px;
            }
            
            /* Touch-friendly highlights */
            .annotation-highlight {
                padding: 4px 6px;
                border-radius: 4px;
                cursor: pointer;
                transition: all 0.2s ease;
                position: relative;
                min-height: 24px;
                display: inline-block;
            }
            
            .annotation-highlight:active {
                transform: scale(0.98);
            }
            
            /* Prevent text selection issues on mobile */
            @media (max-width: 768px) {
                .annotation-menu {
                    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
                    border: 2px solid #e5e7eb;
                }
                
                .annotation-menu-content {
                    padding: 16px;
                }
                
                .annotation-menu-title {
                    font-size: 14px;
                    margin-bottom: 12px;
                }
            }
            
            /* Base annotation styles (from original) */
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

            .annotation-CMD {
                background-color: #f3e8ff;
                border: 1px solid #a855f7;
                color: #6b21a8;
            }

            .annotation-PROC_LINEAGE {
                background-color: #fef9c3;
                border: 1px solid #f59e0b;
                color: #92400e;
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
    module.exports = MobileTextAnnotationManager;
}
