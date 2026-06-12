/**
 * Shared "Similar Rule Details" modal.
 *
 * Phase 4 of the sigma-similarity rendering unification: this collapses the two
 * showSimilarRuleDetails / closeSimilarRuleModal copies that had drifted between
 * workflow.html and workflow_executions.html into one definition, and renders the
 * behavioral similarity breakdown via the shared renderSimilarityDisplay()
 * component (the modals previously showed only a bare "Similarity: X%" with no
 * atom-jaccard / logic-shape / containment / shared-atoms breakdown).
 *
 * Loaded AFTER similarity-display.js (provides renderSimilarityDisplay + escapeHtml).
 *
 * The two source copies diverged in modal infrastructure -- workflow.html uses a
 * pushModal() fallback that does not exist on workflow_executions.html. This
 * unified version guards that fallback (typeof pushModal === 'function') so one
 * function is correct on both pages, adopts HTML escaping on all interpolated
 * rule fields (workflow.html previously did not -- a small XSS hardening), and
 * keeps the ESC-to-close handler.
 */

function showSimilarRuleDetails(ruleIdx, resultIdx) {
    const clickedElement = event.currentTarget;
    const ruleDataStr = clickedElement.getAttribute('data-rule-data');
    if (!ruleDataStr) return;

    try {
        const ruleData = JSON.parse(ruleDataStr.replace(/&#39;/g, "'"));
        const sourceFromRepo =
            (ruleData.rule_id && String(ruleData.rule_id).startsWith('cust-')) ||
            (ruleData.file_path && String(ruleData.file_path).startsWith('customer/'));
        const sourceLabel = sourceFromRepo ? 'Your repo' : 'SigmaHQ';
        const sourceBadgeClass = sourceFromRepo
            ? 'bg-amber-100 dark:bg-amber-900 text-amber-800 dark:text-amber-200'
            : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300';

        // Remove any existing modal
        const existingModal = document.getElementById('similarRuleModal');
        if (existingModal) {
            if (window.ModalManager) {
                const stack = window.ModalManager.getStack();
                while (stack.includes('similarRuleModal')) {
                    const index = stack.indexOf('similarRuleModal');
                    stack.splice(index, 1);
                }
            }
            existingModal.remove();
        }

        const modal = document.createElement('div');
        modal.id = 'similarRuleModal';
        modal.className = 'fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-[70]';

        const tagsHtml = ruleData.tags && ruleData.tags.length > 0 ? `
            <div class="mb-4">
                <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-2">Tags:</h4>
                <div class="flex flex-wrap gap-2">
                    ${ruleData.tags.map(tag =>
                        `<span class="px-3 py-1 bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300 rounded text-sm">${escapeHtml(tag)}</span>`
                    ).join('')}
                </div>
            </div>
        ` : '';

        const detectionHtml = ruleData.detection ? `
            <div class="mb-4">
                <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-2">Detection Logic:</h4>
                <pre class="bg-gray-50 dark:bg-gray-900 p-3 rounded text-xs overflow-x-auto border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300">${escapeHtml(JSON.stringify(ruleData.detection, null, 2))}</pre>
            </div>
        ` : '';

        const logsourceHtml = ruleData.logsource ? `
            <div class="mb-4">
                <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-2">Log Source:</h4>
                <pre class="bg-gray-50 dark:bg-gray-900 p-3 rounded text-xs overflow-x-auto border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300">${escapeHtml(JSON.stringify(ruleData.logsource, null, 2))}</pre>
            </div>
        ` : '';

        // Behavioral similarity breakdown via the shared component (replaces the
        // bare "Similarity: X%" the modals showed before -- ruleData already
        // carries the full engine match).
        const similarityBreakdownHtml = renderSimilarityDisplay(ruleData, { mode: 'compact', includeExplainability: true });

        modal.innerHTML = `
            <div class="card relative top-20 mx-auto p-5 w-11/12 max-w-4xl shadow-lg" style="margin-bottom: 50px;">
                <div class="flex justify-between items-center mb-4">
                    <h3 class="text-lg font-medium text-gray-900 dark:text-white"><svg class="w-5 h-5 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/></svg> Similar Rule Details</h3>
                    <button onclick="closeSimilarRuleModal()" aria-label="Close" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                        </svg>
                    </button>
                </div>

                <div class="space-y-4 text-gray-700 dark:text-gray-300 max-h-96 overflow-y-auto">
                    <div>
                        <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-1">Title:</h4>
                        <div class="text-base flex items-center gap-2 flex-wrap">
                            <span>${escapeHtml(ruleData.title || 'Untitled Rule')}</span>
                            <span class="text-xs px-2 py-0.5 rounded ${sourceBadgeClass}">${sourceLabel}</span>
                        </div>
                    </div>

                    ${ruleData.description ? `
                        <div>
                            <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-1">Description:</h4>
                            <div class="text-sm">${escapeHtml(ruleData.description)}</div>
                        </div>
                    ` : ''}

                    <div class="grid grid-cols-2 gap-4">
                        ${ruleData.rule_id ? `
                            <div>
                                <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-1">Rule ID:</h4>
                                <div class="text-sm">${escapeHtml(ruleData.rule_id)}</div>
                            </div>
                        ` : ''}
                        ${ruleData.status ? `
                            <div>
                                <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-1">Status:</h4>
                                <div class="text-sm"><span class="px-2 py-1 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 rounded">${escapeHtml(ruleData.status)}</span></div>
                            </div>
                        ` : ''}
                    </div>

                    <div>
                        <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-1">Behavioral Similarity:</h4>
                        ${similarityBreakdownHtml}
                    </div>

                    ${ruleData.file_path ? `
                        <div>
                            <h4 class="text-sm font-medium text-gray-900 dark:text-white mb-1">File Path:</h4>
                            <div class="text-xs font-mono text-gray-600 dark:text-gray-400">${escapeHtml(ruleData.file_path)}</div>
                        </div>
                    ` : ''}

                    ${tagsHtml}
                    ${logsourceHtml}
                    ${detectionHtml}
                </div>

                <div class="mt-6 flex justify-end">
                    <button onclick="closeSimilarRuleModal()"
                            class="px-4 py-2 bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-400 dark:hover:bg-gray-500 transition-colors">
                        Close
                    </button>
                </div>
            </div>
        `;

        modal.addEventListener('click', function (e) {
            if (e.target === modal) {
                closeSimilarRuleModal();
            }
        });

        const handleEsc = function (e) {
            if (e.key === 'Escape') {
                closeSimilarRuleModal();
                document.removeEventListener('keydown', handleEsc);
            }
        };
        document.addEventListener('keydown', handleEsc);

        document.body.appendChild(modal);
        modal.classList.remove('hidden');

        if (window.ModalManager) {
            setTimeout(() => {
                window.ModalManager.register('similarRuleModal', {
                    isDynamic: true,
                    hasInput: false
                });
                window.ModalManager.open('similarRuleModal', true);
                modal.classList.remove('hidden');
            }, 50);
        } else if (typeof pushModal === 'function') {
            // Legacy fallback (workflow.html only -- absent on executions page).
            pushModal('similarRuleModal', true);
        }
    } catch (error) {
        console.error('Error parsing rule data:', error);
        if (typeof showNotification === 'function') {
            showNotification('Error displaying rule details', 'error');
        }
    }
}

function closeSimilarRuleModal() {
    if (window.ModalManager) {
        window.ModalManager.close('similarRuleModal');
    } else {
        const modal = document.getElementById('similarRuleModal');
        if (modal) {
            modal.remove();
        }
    }
}
