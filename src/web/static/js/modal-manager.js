/**
 * Unified Modal Management System
 * 
 * Features:
 * - Escape key closes topmost modal, returns to previous modal or base page
 * - Click away closes modal and navigates to clicked element
 * - Ctrl+Enter/Cmd+Enter submits modals with input fields
 * - Modal stack management for nested modals
 */

(function() {
    'use strict';

    // Global modal stack
    const modalStack = [];
    const modalRegistry = new Map(); // modalId -> { element, submitButton, isDynamic }

    /**
     * Register a modal with the system
     * @param {string} modalId - ID of the modal element
     * @param {Object} options - Configuration options
     * @param {string|HTMLElement} options.submitButton - Selector or element for submit button
     * @param {boolean} options.isDynamic - Whether modal is dynamically created (will be removed on close)
     * @param {Function} options.onClose - Callback when modal closes
     */
    function registerModal(modalId, options = {}) {
        const modal = document.getElementById(modalId);
        if (!modal) {
            console.warn(`Modal ${modalId} not found`);
            return;
        }

        // If already registered, remove old handlers first
        if (modalRegistry.has(modalId)) {
            const oldConfig = modalRegistry.get(modalId);
            // Remove old event listeners by cloning the modal (removes all listeners)
            // Actually, we'll just update the config since we can't easily remove listeners
            // But we should prevent duplicate registration
            console.warn(`Modal ${modalId} already registered, updating registration`);
        }

        const config = {
            element: modal,
            submitButton: options.submitButton || null,
            isDynamic: options.isDynamic || false,
            onClose: options.onClose || null,
            hasInput: options.hasInput !== false // Default true, set false if no inputs
        };

        modalRegistry.set(modalId, config);

        // Setup click-away handler (only if not already set up)
        if (!modal.hasAttribute('data-modal-click-handler')) {
            setupClickAwayHandler(modalId, modal);
            modal.setAttribute('data-modal-click-handler', 'true');
        }

        // Setup keyboard shortcuts for input modals
        if (config.hasInput && !modal.hasAttribute('data-modal-keyboard-handler')) {
            setupKeyboardShortcuts(modalId, modal, config.submitButton);
            modal.setAttribute('data-modal-keyboard-handler', 'true');
        }
    }

    /**
     * Setup click-away handler that navigates to clicked element
     */
    function setupClickAwayHandler(modalId, modal) {
        // Remove any existing handler first
        const existingHandler = modal._modalClickHandler;
        if (existingHandler) {
            modal.removeEventListener('mousedown', existingHandler);
        }
        
        const handler = function(e) {
            // Only handle clicks on the backdrop (modal itself)
            if (e.target === modal) {
                e.stopPropagation();
                // Store the click position to find what was clicked
                const clickX = e.clientX;
                const clickY = e.clientY;
                
                // Use a small delay to ensure modal closes first, then check what's underneath
                setTimeout(() => {
                    // Temporarily hide modal to see what's underneath
                    const wasHidden = modal.classList.contains('hidden');
                    if (!wasHidden) {
                        modal.style.pointerEvents = 'none';
                        const elementBelow = document.elementFromPoint(clickX, clickY);
                        modal.style.pointerEvents = '';
                        
                        closeModal(modalId, elementBelow);
                    }
                }, 10);
            }
        };
        
        modal._modalClickHandler = handler;
        modal.addEventListener('mousedown', handler);
    }

    /**
     * Setup keyboard shortcuts (Ctrl+Enter/Cmd+Enter for submit)
     */
    function setupKeyboardShortcuts(modalId, modal, submitButtonSelector) {
        modal.addEventListener('keydown', function(e) {
            // Ctrl+Enter (Windows/Linux) or Cmd+Enter (macOS)
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                e.stopPropagation();
                
                if (submitButtonSelector) {
                    const submitBtn = typeof submitButtonSelector === 'string' 
                        ? modal.querySelector(submitButtonSelector)
                        : submitButtonSelector;
                    
                    if (submitBtn && typeof submitBtn.click === 'function') {
                        submitBtn.click();
                    } else if (submitBtn && typeof submitBtn.onclick === 'function') {
                        submitBtn.onclick();
                    }
                } else {
                    // Try to find common submit button patterns
                    let submitBtn = modal.querySelector('button[type="submit"]');
                    if (!submitBtn) {
                        // Try buttons with common submit-related classes
                        submitBtn = modal.querySelector('button.bg-purple-500, button.bg-purple-600, button.bg-blue-500, button.bg-blue-600, button.bg-emerald-600');
                    }
                    if (!submitBtn) {
                        // Try buttons with common submit text
                        const buttons = modal.querySelectorAll('button');
                        for (const btn of buttons) {
                            const text = btn.textContent.trim().toLowerCase();
                            if (text.includes('save') || text.includes('submit') || text.includes('ok') || text.includes('confirm') || text.includes('apply')) {
                                submitBtn = btn;
                                break;
                            }
                        }
                    }
                    if (submitBtn) {
                        submitBtn.click();
                    }
                }
            }
        });
    }

    /**
     * Open a modal and add to stack
     * @param {string} modalId - ID of the modal
     * @param {boolean} hidePrevious - Whether to hide previous modal
     */
    function openModal(modalId, hidePrevious = true) {
        const modal = document.getElementById(modalId);
        if (!modal) {
            console.warn(`Modal ${modalId} not found`);
            return;
        }

        // Hide previous modal if requested
        if (hidePrevious && modalStack.length > 0) {
            const previousModalId = modalStack[modalStack.length - 1];
            const previousModal = document.getElementById(previousModalId);
            if (previousModal) {
                previousModal.classList.add('hidden');
            }
        }

        // Add to stack and show (avoid duplicates)
        if (!modalStack.includes(modalId)) {
            modalStack.push(modalId);
        }
        modal.classList.remove('hidden');

        // Ensure modal is registered
        if (!modalRegistry.has(modalId)) {
            registerModal(modalId, { isDynamic: false });
        }

        // Focus first input if available
        const firstInput = modal.querySelector('input, textarea, select');
        if (firstInput && typeof firstInput.focus === 'function') {
            setTimeout(() => firstInput.focus(), 100);
        }
    }

    /**
     * Close a modal and restore previous modal or return to base page
     * @param {string} modalId - ID of the modal to close
     * @param {HTMLElement} clickedElement - Element that was clicked (for navigation)
     */
    function closeModal(modalId, clickedElement = null) {
        if (!modalStack.includes(modalId)) {
            // Modal not in stack, try to close it anyway
            const modal = document.getElementById(modalId);
            if (modal) {
                const config = modalRegistry.get(modalId);
                if (config && config.isDynamic) {
                    modal.remove();
                } else {
                    modal.classList.add('hidden');
                }
                if (config && config.onClose) {
                    config.onClose();
                }
            }
            return;
        }

        // Remove from stack (remove all occurrences to handle duplicates)
        const index = modalStack.indexOf(modalId);
        if (index === -1) {
            // Modal not in stack, but might still exist - try to close it
            const modal = document.getElementById(modalId);
            if (modal) {
                const config = modalRegistry.get(modalId);
                if (config && config.isDynamic) {
                    modal.remove();
                } else {
                    modal.classList.add('hidden');
                }
                if (config && config.onClose) {
                    config.onClose();
                }
            }
            return;
        }

        // Remove all occurrences of this modal from stack
        const currentModalId = modalId;
        while (modalStack.includes(modalId)) {
            const idx = modalStack.indexOf(modalId);
            modalStack.splice(idx, 1);
        }
        const currentModal = document.getElementById(currentModalId);
        const config = modalRegistry.get(currentModalId);

        if (currentModal) {
            // Remove or hide modal
            if (config && config.isDynamic) {
                currentModal.remove();
            } else {
                currentModal.classList.add('hidden');
            }
        }

        // Call onClose callback
        if (config && config.onClose) {
            config.onClose();
        }

        // Handle clicked element navigation
        if (clickedElement) {
            // Check if clicked element is part of a previous modal
            let parentModal = clickedElement.closest('[id$="Modal"]');
            if (!parentModal) {
                // Try to find any modal ancestor
                let parent = clickedElement.parentElement;
                while (parent && parent !== document.body) {
                    if (parent.id && parent.id.includes('modal')) {
                        parentModal = parent;
                        break;
                    }
                    parent = parent.parentElement;
                }
            }

            if (parentModal && modalStack.includes(parentModal.id)) {
                // Clicked on a previous modal, restore it
                openModal(parentModal.id, false);
                return;
            }
            // Otherwise, clicked on base page - do nothing (modal already closed)
        }

        // Restore previous modal if exists
        if (modalStack.length > 0) {
            const previousModalId = modalStack[modalStack.length - 1];
            const previousModal = document.getElementById(previousModalId);
            if (previousModal) {
                previousModal.classList.remove('hidden');
            }
        }
    }

    /**
     * Close topmost modal (used by Escape key)
     */
    function closeTopModal() {
        if (modalStack.length === 0) return;

        const topModalId = modalStack[modalStack.length - 1];
        closeModal(topModalId);
    }

    /**
     * Check if any modal is open
     */
    function isAnyModalOpen() {
        return modalStack.length > 0;
    }

    /**
     * Get current modal stack
     */
    function getModalStack() {
        return [...modalStack];
    }

    // Global Escape key handler (only register once)
    if (!window._modalManagerEscHandlerRegistered) {
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && isAnyModalOpen()) {
                e.preventDefault();
                e.stopPropagation();
                closeTopModal();
            }
        }, true); // Use capture phase to handle before other handlers
        window._modalManagerEscHandlerRegistered = true;
    }

    // Export API
    window.ModalManager = {
        register: registerModal,
        open: openModal,
        close: closeModal,
        closeTop: closeTopModal,
        isOpen: isAnyModalOpen,
        getStack: getModalStack
    };

    // Helper function to register a modal
    function autoRegisterModal(modal, isDynamic = false) {
        if (!modal.id || modalRegistry.has(modal.id)) return;
        
        const hasInput = modal.querySelector('input, textarea, select') !== null;
        let submitBtn = modal.querySelector('button[type="submit"]');
        if (!submitBtn) {
            const buttons = modal.querySelectorAll('button');
            for (const btn of buttons) {
                const text = btn.textContent.trim().toLowerCase();
                if (text.includes('save') || text.includes('submit') || text.includes('ok') || text.includes('confirm') || text.includes('apply')) {
                    submitBtn = btn;
                    break;
                }
            }
        }
        
        registerModal(modal.id, {
            hasInput: hasInput,
            submitButton: submitBtn || null,
            isDynamic: isDynamic
        });
    }

    // Auto-register modals on DOMContentLoaded
    document.addEventListener('DOMContentLoaded', function() {
        // Find all modals with common patterns
        const modals = document.querySelectorAll('[id$="Modal"], [id*="modal"][class*="fixed"][class*="inset-0"]');
        modals.forEach(modal => {
            autoRegisterModal(modal, false);
        });
        
        // Watch for modals that become visible (for modals opened via classList.remove('hidden'))
        const classObserver = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                    const modal = mutation.target;
                    if (modal.id && modal.id.includes('Modal') && !modal.classList.contains('hidden')) {
                        // Ensure registered (only if not already registered)
                        if (!modalRegistry.has(modal.id)) {
                            autoRegisterModal(modal, false);
                        }
                        
                        // Add to stack if not already there
                        if (!modalStack.includes(modal.id)) {
                            // Hide previous modal
                            if (modalStack.length > 0) {
                                const previousModalId = modalStack[modalStack.length - 1];
                                const previousModal = document.getElementById(previousModalId);
                                if (previousModal) {
                                    previousModal.classList.add('hidden');
                                }
                            }
                            modalStack.push(modal.id);
                        }
                    }
                }
            });
        });
        
        // Observe all existing modals for class changes
        modals.forEach(modal => {
            classObserver.observe(modal, { attributes: true, attributeFilter: ['class'] });
        });
        
        // Watch for newly added modals
        const bodyObserver = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1 && node.id && node.id.includes('Modal') && 
                        (node.classList.contains('fixed') || node.className.includes('fixed')) &&
                        (node.classList.contains('inset-0') || node.className.includes('inset-0'))) {
                        // New modal added, register it (only if not already registered)
                        if (!modalRegistry.has(node.id)) {
                            autoRegisterModal(node, true);
                            
                            // Observe it for class changes
                            classObserver.observe(node, { attributes: true, attributeFilter: ['class'] });
                        }
                        
                        // If it's visible, add to stack (avoid duplicates)
                        if (!node.classList.contains('hidden') && !modalStack.includes(node.id)) {
                            if (modalStack.length > 0) {
                                const previousModalId = modalStack[modalStack.length - 1];
                                const previousModal = document.getElementById(previousModalId);
                                if (previousModal) {
                                    previousModal.classList.add('hidden');
                                }
                            }
                            modalStack.push(node.id);
                        }
                    }
                });
            });
        });
        
        bodyObserver.observe(document.body, { childList: true, subtree: true });
    });
})();
