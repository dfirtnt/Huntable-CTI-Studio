// Workflow — page-level module (modal stack, similar rules, deep-linking,
// help, live-execution SSE, and page initialisation).
//
// Extracted verbatim from src/web/templates/workflow.html (formerly lines
// 3877-5509). Loaded as a classic script immediately after the inline shell
// that still declares the shared header this reads (`currentTab`, `queue`,
// `switchTab`, the canonical agent lists).
//
// It loads BEFORE executions.js / queue.js / config.js on purpose. This file
// owns two DOMContentLoaded registrations -- the ModalManager registration and
// the page-init block -- and inline they ran after the early <script> block's
// listener and before the two column-resize listeners at the end of the
// template. None of the other modules register a DOMContentLoaded handler, so
// loading here keeps that relative firing order exactly as it was.

// Modal stack management - use unified ModalManager
// Legacy compatibility functions
function pushModal(modalId, hidePrevious = true) {
    if (window.ModalManager) {
        window.ModalManager.open(modalId, hidePrevious);
    } else {
        // Fallback if ModalManager not loaded
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.classList.remove('hidden');
        }
    }
}

function popModal() {
    if (window.ModalManager) {
        window.ModalManager.closeTop();
        return window.ModalManager.getStack().length > 0 ? window.ModalManager.getStack()[window.ModalManager.getStack().length - 1] : null;
    }
    return null;
}

function isModalOpen(modalId) {
    if (window.ModalManager) {
        return window.ModalManager.getStack().includes(modalId);
    }
    const modal = document.getElementById(modalId);
    return modal && !modal.classList.contains('hidden');
}

// Register modals with ModalManager on page load
document.addEventListener('DOMContentLoaded', function() {
    if (window.ModalManager) {
        // Register static modals
        const staticModals = [
            'configPresetListModal',
            'configVersionListModal',
            'executionModal',
            'triggerWorkflowModal',
            'ruleModal',
            'enrichModal',
            'presetListModal'
        ];
        
        staticModals.forEach(modalId => {
            const modal = document.getElementById(modalId);
            if (modal) {
                const hasInput = modal.querySelector('input, textarea, select') !== null;
                const submitBtn = modal.querySelector('button[type="submit"], button.bg-purple-500, button.bg-purple-600, button.bg-emerald-600');
                
                window.ModalManager.register(modalId, {
                    hasInput: hasInput,
                    submitButton: submitBtn,
                    isDynamic: false
                });
            }
        });
    }
});

// Similar Rules functionality
let currentQueueRule = null;
let isSimilarRulesModalExpanded = false;

async function checkSimilarRulesForQueue() {
    const rule = queue.find(r => r.id === currentRuleId);
    if (!rule) {
        showNotification('Rule not found', 'error');
        return;
    }
    
    // Persist current modal content so similarity search uses it
    const currentYaml = getCurrentRuleYamlFromModal();
    if (currentYaml !== rule.rule_yaml) {
        try {
            const putResponse = await fetch(`/api/sigma-queue/${currentRuleId}/yaml`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ rule_yaml: currentYaml })
            });
            if (putResponse.ok) {
                rule.rule_yaml = currentYaml;
                editedYaml = currentYaml;
                originalYaml = currentYaml;
            }
        } catch (e) {
            console.warn('Failed to save rule before similarity search:', e);
        }
    }
    
    currentQueueRule = rule;
    
    // Show loading indicator
    const loadingMsg = document.createElement('div');
    loadingMsg.id = 'similarRulesLoading';
    loadingMsg.className = 'fixed inset-0 bg-gray-600 bg-opacity-50 z-50 flex items-center justify-center';
    loadingMsg.setAttribute('role', 'status');
    loadingMsg.setAttribute('aria-live', 'polite');
    loadingMsg.setAttribute('aria-label', 'Searching for similar rules');
    loadingMsg.innerHTML = `
        <div class="card p-6">
            <div class="text-center">
                <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
                <p class="text-gray-700 dark:text-gray-300">Searching for similar rules across indexed repositories...</p>
                <p class="text-sm text-gray-500 dark:text-gray-400 mt-2">This may take 20-30 seconds</p>
            </div>
        </div>
    `;
    document.body.appendChild(loadingMsg);
    
    try {
        // Use the queued rule's direct comparison endpoint
        // This compares the specific queued rule's YAML, not the article's generated rules
        const response = await fetch(`/api/sigma-queue/${currentRuleId}/similar-rules?force=true`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
            signal: AbortSignal.timeout(60000)  // 60 second timeout
        });
        
        const data = await response.json();
        if (!response.ok) {
            const detail = data.detail || data.message || `HTTP error! status: ${response.status}`;
            throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
        }
        
        // Remove loading indicator
        const loadingEl = document.getElementById('similarRulesLoading');
        if (loadingEl) loadingEl.remove();
        
        // Debug logging
        console.log('Similarity search response:', {
            success: data.success,
            matchesCount: data.matches ? data.matches.length : 0,
            assessmentMethod: data.assessment_method,
            matches: data.matches ? data.matches.slice(0, 2) : null
        });
        
        if (data.success) {
            // Parse current rule YAML to extract rule structure
            let currentRuleParsed = null;
            // Server ships the already-parsed current rule (PyYAML-parsed dict).
            // Trust it when present; fall back to the legacy JS YAML parser only
            // for older responses that didn't include this field.
            if (data.current_rule && typeof data.current_rule === 'object') {
                currentRuleParsed = {
                    title: data.current_rule.title || '',
                    description: data.current_rule.description || '',
                    tags: Array.isArray(data.current_rule.tags) ? data.current_rule.tags : [],
                    logsource: data.current_rule.logsource || {},
                    detection: data.current_rule.detection || {},
                    level: data.current_rule.level || '',
                    status: data.current_rule.status || ''
                };
            }
            try {
                if (currentRuleParsed) {
                    // Server-parsed current_rule is authoritative; skip the legacy JS YAML parser.
                } else {
                const yaml = rule.rule_yaml || '';
                const metadata = rule.rule_metadata || {};
                
                if (yaml) {
                    // Function to parse YAML block (improved parser for nested structures)
                    function parseYamlBlock(blockText, indentLevel = 0) {
                        const lines = blockText.split('\n');
                        const result = {};
                        let i = 0;
                        
                        while (i < lines.length) {
                            const line = lines[i];
                            const trimmed = line.trim();
                            if (!trimmed || trimmed.startsWith('#')) {
                                i++;
                                continue;
                            }
                            
                            // Get current line indent
                            const currentIndent = line.match(/^(\s*)/)[1].length;
                            
                            // Check for key-value pair (allow keys with underscores, hyphens, etc.)
                            // Pattern: key: value or key: (with nested content on next line)
                            const kvMatch = trimmed.match(/^([\w_-]+(?:\|[\w_-]+)*):\s*(.*)$/);
                            if (kvMatch) {
                                const key = kvMatch[1];
                                let value = kvMatch[2].trim();
                                
                                // Remove quotes if present
                                if ((value.startsWith('"') && value.endsWith('"')) || 
                                    (value.startsWith("'") && value.endsWith("'"))) {
                                    value = value.slice(1, -1);
                                }
                                
                                // Check if next line starts a nested block or if value is empty (nested content)
                                if (i + 1 < lines.length) {
                                    const nextLine = lines[i + 1];
                                    if (nextLine.trim()) {
                                    const nextIndent = nextLine.match(/^(\s*)/)[1].length;
                                    
                                        if (nextIndent > currentIndent || (!value && nextIndent >= currentIndent)) {
                                        // Nested block - extract it
                                        const nestedLines = [];
                                        let j = i + 1;
                                        while (j < lines.length) {
                                                const nestedLine = lines[j];
                                                if (!nestedLine.trim()) {
                                                    nestedLines.push(nestedLine);
                                                    j++;
                                                    continue;
                                                }
                                                const nestedIndent = nestedLine.match(/^(\s*)/)[1].length;
                                                // Stop if we hit same or less indentation (and it's not empty)
                                                if (nestedIndent <= currentIndent && nestedLine.trim()) {
                                                break;
                                            }
                                                nestedLines.push(nestedLine);
                                            j++;
                                        }
                                        const nestedBlock = nestedLines.join('\n');
                                            if (nestedBlock.trim()) {
                                        value = parseYamlBlock(nestedBlock, nextIndent);
                                            }
                                        i = j - 1;
                                        } else if (!value) {
                                            // Empty value, no nested content
                                            value = null;
                                        }
                                    }
                                }
                                
                                // Handle array values (lines starting with -)
                                if (typeof value === 'string' && value.startsWith('-')) {
                                    const arrayValues = [];
                                    let arrayLine = i;
                                    while (arrayLine < lines.length) {
                                        const arrLine = lines[arrayLine].trim();
                                        if (arrLine.startsWith('-')) {
                                            const arrValue = arrLine.substring(1).trim();
                                            // Remove quotes
                                            const cleanValue = (arrValue.startsWith('"') && arrValue.endsWith('"')) || 
                                                              (arrValue.startsWith("'") && arrValue.endsWith("'")) ?
                                                              arrValue.slice(1, -1) : arrValue;
                                            arrayValues.push(cleanValue);
                                        } else if (arrLine && !arrLine.startsWith('#')) {
                                            break;
                                        }
                                        arrayLine++;
                                    }
                                    if (arrayValues.length > 0) {
                                        value = arrayValues;
                                        i = arrayLine - 1;
                                    }
                                }
                                
                                result[key] = value;
                            }
                            i++;
                        }
                        
                        return result;
                    }
                    
                    // Extract logsource block
                    let logsourceObj = metadata.logsource || {};
                    const logsourceMatch = yaml.match(/^logsource:\s*\n((?:\s{2,}.*\n?)*)/m);
                    if (logsourceMatch && (!logsourceObj || Object.keys(logsourceObj).length === 0)) {
                        try {
                            logsourceObj = parseYamlBlock(logsourceMatch[1]);
                        } catch (e) {
                            console.warn('Could not parse logsource:', e);
                        }
                    }
                    
                    // Extract detection block (more complex, nested structure)
                    // Prefer metadata.detection if it exists and is complete
                    let detectionObj = metadata.detection || {};
                    
                    // Check if metadata detection is complete (has more than just condition)
                    const hasCompleteDetection = detectionObj && 
                        Object.keys(detectionObj).length > 1 || 
                        (Object.keys(detectionObj).length === 1 && Object.keys(detectionObj)[0] !== 'condition');
                    
                    if (!hasCompleteDetection) {
                        // Try to parse from YAML using improved parser
                    const detectionMatch = yaml.match(/^detection:\s*\n((?:\s{2,}.*\n?)*)/m);
                        if (detectionMatch) {
                            try {
                                // Use a more robust approach: try to parse the entire detection block
                                // Find where detection block ends (next top-level key or end of YAML)
                                const detectionStart = yaml.indexOf('detection:');
                                if (detectionStart !== -1) {
                                    const afterDetection = yaml.substring(detectionStart + 'detection:'.length);
                                    // Find next top-level key (starts at column 0, not indented)
                                    const nextTopLevelMatch = afterDetection.match(/\n^(\w+):/m);
                                    const detectionEnd = nextTopLevelMatch ? 
                                        detectionStart + 'detection:'.length + nextTopLevelMatch.index : 
                                        yaml.length;
                                    
                                    const detectionBlock = yaml.substring(detectionStart, detectionEnd);
                                    detectionObj = parseYamlBlock(detectionBlock.replace(/^detection:\s*\n?/, ''));
                                }
                        } catch (e) {
                                console.warn('Could not parse detection from YAML:', e);
                                // Fall back to metadata even if incomplete
                            }
                        }
                    }
                    
                    // Final fallback: ensure we have at least condition
                    if (!detectionObj || Object.keys(detectionObj).length === 0) {
                        detectionObj = { condition: 'selection' };
                    }
                    
                    currentRuleParsed = {
                        title: metadata.title || '',
                        description: metadata.description || '',
                        tags: metadata.tags || [],
                        logsource: logsourceObj,
                        detection: detectionObj,
                        level: metadata.level || '',
                        status: metadata.status || ''
                    };
                } else {
                    // No YAML, use metadata only
                    currentRuleParsed = {
                        title: metadata.title || '',
                        description: metadata.description || '',
                        tags: metadata.tags || [],
                        logsource: metadata.logsource || {},
                        detection: metadata.detection || {},
                        level: metadata.level || '',
                        status: metadata.status || ''
                    };
                }
                }
            } catch (e) {
                console.warn('Could not parse rule structure:', e);
                if (!currentRuleParsed) {
                    // Fallback to metadata only when server didn't ship current_rule.
                    const metadata = rule.rule_metadata || {};
                    currentRuleParsed = {
                        title: metadata.title || '',
                        description: metadata.description || '',
                        tags: metadata.tags || [],
                        logsource: metadata.logsource || {},
                        detection: metadata.detection || {},
                        level: metadata.level || '',
                        status: metadata.status || ''
                    };
                }
            }
            
            // Use parsed rule or create from metadata
            const generatedRules = currentRuleParsed ? [currentRuleParsed] : [];
            showSimilarRulesModal(data.matches, data.coverage_summary, generatedRules, data.assessment_method, data.diagnostic, {
                totalCandidatesEvaluated: data.total_candidates_evaluated,
                behavioralMatchesFound: data.behavioral_matches_found,
                engineUsed: data.engine_used,
                canonicalClass: data.canonical_class ?? null,
                logsourceKey: data.logsource_key ?? null
            });
        } else {
            showNotification('Failed to find similar rules: ' + (data.message || 'Unknown error'), 'error');
        }
    } catch (error) {
        // Remove loading indicator
        const loadingEl = document.getElementById('similarRulesLoading');
        if (loadingEl) loadingEl.remove();
        
        console.error('Error checking similar rules:', error);
        if (error.name === 'AbortError' || error.name === 'TimeoutError') {
            showNotification('Request timed out - LLM reranking may still be processing. Try again in a moment.', 'warning');
        } else {
            showNotification('Error checking similar rules: ' + error.message, 'error');
        }
    }
}

function _workflowSimilarityCandidateFilterHint(metadata) {
    const cc = metadata?.canonicalClass;
    const lk = metadata?.logsourceKey;
    if (cc) {
        return ` <span class="text-gray-500 dark:text-gray-500">(canonical class: ${escapeHtml(String(cc))})</span>`;
    }
    if (lk && lk !== '|') {
        return ` <span class="text-gray-500 dark:text-gray-500">(logsource: ${escapeHtml(String(lk))})</span>`;
    }
    return '';
}

async function showSimilarRulesModal(matches, coverageSummary, generatedRules = [], assessmentMethod = null, diagnostic = null, metadata = {}) {
    // Remove any existing modal
    closeSimilarRulesModal();
    // Behavioral Overlap Engine: display only rules with jaccard > 0 (at least one shared atom)
    const jaccard = (m) => m.atom_jaccard ?? m.atom_details?.jaccard ?? 0;
    matches = (matches || []).filter(m => jaccard(m) > 0);
    const totalCandidatesEvaluated = metadata?.totalCandidatesEvaluated ?? -1;
    const behavioralMatchesFound = metadata?.behavioralMatchesFound ?? -1;
    const hasMetadata = totalCandidatesEvaluated >= 0;
    const filterHintHtml = _workflowSimilarityCandidateFilterHint(metadata);
    
    // Clean up existing modal properly
    const existingModal = document.getElementById('similarRulesModal');
    if (existingModal) {
        if (window.ModalManager) {
            const stack = window.ModalManager.getStack();
            while (stack.includes('similarRulesModal')) {
                const index = stack.indexOf('similarRulesModal');
                stack.splice(index, 1);
            }
        }
        existingModal.remove();
        await new Promise(resolve => setTimeout(resolve, 10));
    }
    
    const modal = document.createElement('div');
    modal.id = 'similarRulesModal';
    modal.className = 'fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-[65]';
    
    document.body.appendChild(modal);
    
    // Ensure modal is visible
    modal.classList.remove('hidden');
    
    // Push to modal stack (will hide previous modal)
    if (window.ModalManager) {
        setTimeout(() => {
            window.ModalManager.register('similarRulesModal', {
                isDynamic: true,
                hasInput: false
            });
            window.ModalManager.open('similarRulesModal', true);
            modal.classList.remove('hidden');
        }, 50);
    } else {
        pushModal('similarRulesModal', true);
    }
    
    // Add click outside to close
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeSimilarRulesModal();
        }
    });
    
    
    // Build matches HTML
    let matchesHtml = '';
    if (!matches || matches.length === 0) {
        const emptyTitle = (hasMetadata && totalCandidatesEvaluated === 0)
            ? 'Rule Corpus Unavailable'
            : 'No Behavioral Overlap Found';
        const emptySubtitle = (hasMetadata && totalCandidatesEvaluated === 0)
            ? 'No indexed rules were available for behavioral comparison.'
            : 'No indexed rules share detection logic with this rule.';
        matchesHtml = `
            <div class="text-center py-8">
                <span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-slate-200 dark:bg-slate-600 text-slate-700 dark:text-slate-200 mb-4">Precomputed Atom Set-Math</span>
                <p class="text-lg font-semibold text-gray-900 dark:text-white mb-2">${emptyTitle}</p>
                ${hasMetadata ? `<p class="text-sm text-gray-600 dark:text-gray-400 mb-2">${Number(totalCandidatesEvaluated).toLocaleString()} candidates evaluated${filterHintHtml}</p>` : ''}
                <p class="text-gray-600 dark:text-gray-400">${emptySubtitle}</p>
            </div>
        `;
    } else {
        // Get parsed data from current rule
        let newRuleLogsource = null;
        let newRuleDetection = null;
        if (generatedRules.length > 0) {
            const firstRule = generatedRules[0];
            newRuleLogsource = firstRule.logsource || null;
            newRuleDetection = firstRule.detection || null;
        }
        
        matchesHtml = matches.map((match, index) => {
            const similarityPercent = ((match.similarity || 0) * 100).toFixed(1);
            const coverageStatus = match.coverage_status || 'unknown';
            const statusIcon = coverageStatus === 'covered' ? '✓' : 
                              coverageStatus === 'extend' ? '⚡' : '✨';
            
            // Determine status color classes (using full class names for Tailwind)
            let similarityColorClass = 'text-purple-600 dark:text-purple-400';
            let statusBadgeClass = 'text-purple-600 dark:text-purple-400 bg-purple-100 dark:bg-purple-900';
            if (coverageStatus === 'covered') {
                similarityColorClass = 'text-emerald-400 dark:text-green-400';
                statusBadgeClass = 'text-emerald-400 dark:text-green-400 bg-green-100 dark:bg-green-900';
            } else if (coverageStatus === 'extend') {
                similarityColorClass = 'text-amber-400 dark:text-yellow-400';
                statusBadgeClass = 'text-amber-400 dark:text-yellow-400 bg-yellow-100 dark:bg-yellow-900';
            }
            
            // Escape logsource and detection for safe JSON display
            const logsourceJson = match.logsource ? JSON.stringify(match.logsource, null, 2).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : 'N/A';
            const detectionJson = match.detection ? JSON.stringify(match.detection, null, 2).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : 'N/A';
            // Escape new rule logsource and detection
            const newRuleLogsourceJson = newRuleLogsource ? JSON.stringify(newRuleLogsource, null, 2).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : 'N/A';
            const newRuleDetectionJson = newRuleDetection ? JSON.stringify(newRuleDetection, null, 2).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') : 'N/A';
            
            const isCustomerRule = (match.rule_id && String(match.rule_id).startsWith('cust-')) || (match.file_path && String(match.file_path).startsWith('customer/'));
            const repoOriginBadge = isCustomerRule
                ? '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-amber-100 dark:bg-amber-900 text-amber-800 dark:text-amber-200">Your repo</span>'
                : '<span class="px-1.5 py-0.5 rounded text-xs font-medium bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300">SigmaHQ</span>';
            return `
                <div class="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                    <div class="flex items-start justify-between">
                        <div class="flex-1">
                            <div class="flex items-center gap-2">
                                <h5 class="font-medium text-gray-900 dark:text-white">${escapeHtml(match.title || 'Untitled Rule')}</h5>
                                ${repoOriginBadge}
                            </div>
                            <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">${escapeHtml(match.description || 'No description')}</p>
                        </div>
                        <div class="ml-4 flex flex-col items-end">
                            <div class="text-lg font-bold ${similarityColorClass}">${similarityPercent}%</div>
                            <div class="text-xs ${statusBadgeClass} px-2 py-1 rounded mt-1">
                                ${statusIcon} ${coverageStatus.toUpperCase()}
                            </div>
                        </div>
                    </div>
                    
                    ${match.llm_explanation ? `
                        <div class="mt-3 p-2 bg-green-50 dark:bg-green-900 border border-green-200 dark:border-green-700 rounded">
                            <div class="text-xs font-bold text-green-900 dark:text-green-100 mb-1">🤖 LLM Explanation:</div>
                            <div class="text-xs text-green-800 dark:text-green-200 italic">${escapeHtml(match.llm_explanation)}</div>
                        </div>
                    ` : ''}
                    
                    ${match.atom_jaccard !== undefined ? renderSimilarityDisplay(match, {
                        mode: 'compact',
                        includeExplainability: true,
                        ruleALabel: 'Current Rule',
                        ruleBLabel: 'Similar Rule'
                    }) : ''}
                    
                    <div class="mt-3 grid grid-cols-2 gap-2 text-xs">
                        <div><span class="font-medium text-gray-700 dark:text-gray-300">Rule ID:</span> <code class="text-xs bg-gray-100 dark:bg-gray-700 px-1 rounded text-gray-900 dark:text-gray-100">${escapeHtml(match.rule_id || 'N/A')}</code></div>
                        <div><span class="font-medium text-gray-700 dark:text-gray-300">Status:</span> <span class="text-gray-600 dark:text-gray-400">${escapeHtml(match.status || 'N/A')}</span></div>
                    </div>
                    
                    ${match.tags && match.tags.length > 0 ? `
                        <div class="mt-2">
                            <div class="text-xs font-medium text-gray-700 dark:text-gray-300">Tags:</div>
                            <div class="flex flex-wrap gap-1 mt-1">
                                ${match.tags.slice(0, 5).map(tag => 
                                    `<span class="text-xs px-2 py-0.5 bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300 rounded">${escapeHtml(tag)}</span>`
                                ).join('')}
                                ${match.tags.length > 5 ? `<span class="text-xs text-gray-500 dark:text-gray-400">+${match.tags.length - 5} more</span>` : ''}
                            </div>
                        </div>
                    ` : ''}
                    
                    ${match.matched_discriminators && match.matched_discriminators.length > 0 ? `
                        <div class="mt-2">
                            <div class="text-xs font-medium text-gray-700 dark:text-gray-300">Matched Behaviors:</div>
                            <div class="flex flex-wrap gap-1 mt-1">
                                ${match.matched_discriminators.slice(0, 5).map(d => 
                                    `<span class="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300 rounded">${escapeHtml(d)}</span>`
                                ).join('')}
                                ${match.matched_discriminators.length > 5 ? `<span class="text-xs text-gray-500 dark:text-gray-400">+${match.matched_discriminators.length - 5} more</span>` : ''}
                            </div>
                        </div>
                    ` : ''}
                    
                    ${(match.logsource || match.detection || (generatedRules.length > 0 && (generatedRules[0].logsource || generatedRules[0].detection))) ? `
                        <div class="mt-3 border-t border-gray-200 dark:border-gray-700 pt-3">
                            <button onclick="event.stopPropagation(); toggleRuleDetails('rule-details-${index}', 'toggle-icon-${index}')" 
                                    class="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 font-medium flex items-center">
                                <svg id="toggle-icon-${index}" class="w-4 h-4 mr-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                                </svg>
                                <span>Show Logsource & Detection Comparison</span>
                            </button>
                            <div id="rule-details-${index}" class="hidden mt-2">
                                ${generatedRules.length > 0 ? `
                                    <div class="mb-4 p-2 bg-yellow-50 dark:bg-yellow-900 border border-yellow-200 dark:border-yellow-700 rounded">
                                        <h6 class="text-xs font-bold text-yellow-900 dark:text-yellow-100 mb-1">📝 Current Rule: ${escapeHtml(generatedRules[0].title || 'Untitled')}</h6>
                                    </div>
                                ` : ''}
                                <div class="space-y-4">
                                    <!-- Logsource Comparison -->
                                    <div>
                                        <h6 class="text-xs font-bold text-gray-700 dark:text-gray-300 mb-2">📋 Logsource Comparison</h6>
                                        <div class="grid grid-cols-2 gap-4">
                                            <div class="border border-gray-200 dark:border-gray-700 rounded p-2 bg-yellow-50 dark:bg-yellow-900">
                                                <h6 class="text-xs font-bold text-yellow-900 dark:text-yellow-100 mb-2">Current Rule</h6>
                                                <pre class="text-xs bg-gray-800 border border-gray-700 p-2 rounded border border-gray-200 dark:border-gray-700 overflow-x-auto whitespace-pre-wrap font-mono max-h-48 text-gray-900 dark:text-gray-100">${newRuleLogsourceJson}</pre>
                                            </div>
                                            <div class="border border-gray-200 dark:border-gray-700 rounded p-2 bg-blue-50 dark:bg-blue-900">
                                                <h6 class="text-xs font-bold text-blue-900 dark:text-blue-100 mb-2">Similar Rule</h6>
                                                <pre class="text-xs bg-gray-800 border border-gray-700 p-2 rounded border border-gray-200 dark:border-gray-700 overflow-x-auto whitespace-pre-wrap font-mono max-h-48 text-gray-900 dark:text-gray-100">${logsourceJson}</pre>
                                            </div>
                                        </div>
                                    </div>
                                    <!-- Detection Comparison -->
                                    <div>
                                        <h6 class="text-xs font-bold text-gray-700 dark:text-gray-300 mb-2">🔍 Detection Comparison</h6>
                                        <div class="grid grid-cols-2 gap-4">
                                            <div class="border border-gray-200 dark:border-gray-700 rounded p-2 bg-yellow-50 dark:bg-yellow-900">
                                                <h6 class="text-xs font-bold text-yellow-900 dark:text-yellow-100 mb-2">Current Rule</h6>
                                                <pre class="text-xs bg-gray-800 border border-gray-700 p-2 rounded border border-gray-200 dark:border-gray-700 overflow-x-auto whitespace-pre-wrap font-mono max-h-64 text-gray-900 dark:text-gray-100">${newRuleDetectionJson}</pre>
                                            </div>
                                            <div class="border border-gray-200 dark:border-gray-700 rounded p-2 bg-green-50 dark:bg-green-900">
                                                <h6 class="text-xs font-bold text-green-900 dark:text-green-100 mb-2">Similar Rule</h6>
                                                <pre class="text-xs bg-gray-800 border border-gray-700 p-2 rounded border border-gray-200 dark:border-gray-700 overflow-x-auto whitespace-pre-wrap font-mono max-h-64 text-gray-900 dark:text-gray-100">${detectionJson}</pre>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    ` : ''}
                    
                    <div class="mt-2 text-xs text-gray-500 dark:text-gray-400">
                        📁 ${escapeHtml(match.file_path || 'N/A')}
                    </div>
                </div>
            `;
        }).join('');
    }
    
    modal.innerHTML = `
        <div id="similarRulesModalContent" class="relative top-10 mx-auto p-5 border w-11/12 max-w-6xl shadow-lg rounded-md bg-gray-800 border border-gray-700 transition-all duration-300">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-lg font-medium text-gray-900 dark:text-white"><svg class="w-5 h-5 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/></svg> Similar Rules Across Indexed Repositories</h3>
                <div class="flex items-center space-x-2">
                    <button onclick="toggleSimilarRulesModalExpand()" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" title="Expand to full screen">
                        <svg id="expandIcon" class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"></path>
                        </svg>
                    </button>
                    <button onclick="closeSimilarRulesModal()" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                        </svg>
                    </button>
                </div>
            </div>
            
            ${matches && matches.length > 0 ? `
            <div class="mb-4 text-sm text-gray-600 dark:text-gray-400">
                ${hasMetadata ? Number(totalCandidatesEvaluated).toLocaleString() + ' candidates evaluated' + filterHintHtml + ' · ' : ''}Found ${matches.length} rules with behavioral overlap (sorted by similarity)
                ${matches[0] && matches[0].similarity_method === 'llm_reranked' ? `
                    <div class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        Analysis by: ${escapeHtml(matches[0].llm_provider || 'unknown')}${matches[0].llm_model ? ' — ' + escapeHtml(matches[0].llm_model) : ''}
                    </div>
                ` : ''}
            </div>
            ` : ''}
            
            <div id="similarRulesMatchesContainer" class="space-y-3 max-h-96 overflow-y-auto">
                ${matchesHtml}
            </div>
            
            <div class="mt-6 flex justify-end">
                <button onclick="closeSimilarRulesModal()" 
                        class="px-4 py-2 bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-md hover:bg-gray-400 dark:hover:bg-gray-500 transition-colors">
                    Close
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
}

function toggleSimilarRulesModalExpand() {
    const modalContent = document.getElementById('similarRulesModalContent');
    const expandIcon = document.getElementById('expandIcon');
    
    if (!modalContent) return;
    
    isSimilarRulesModalExpanded = !isSimilarRulesModalExpanded;
    
    const matchesContainer = document.getElementById('similarRulesMatchesContainer');
    
    if (isSimilarRulesModalExpanded) {
        // Expand to full screen
        modalContent.className = 'fixed inset-4 p-5 border shadow-lg rounded-md bg-gray-800 border border-gray-700 transition-all duration-300 flex flex-col';
        modalContent.style.top = '1rem';
        modalContent.style.left = '1rem';
        modalContent.style.right = '1rem';
        modalContent.style.bottom = '1rem';
        modalContent.style.width = 'auto';
        modalContent.style.maxWidth = 'none';
        modalContent.style.margin = '0';
        
        // Increase max height of matches container
        if (matchesContainer) {
            matchesContainer.className = 'space-y-3 flex-1 overflow-y-auto';
        }
        
        // Update icon to show minimize
        if (expandIcon) {
            expandIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25"></path>';
        }
    } else {
        // Return to normal size
        modalContent.className = 'relative top-10 mx-auto p-5 border w-11/12 max-w-6xl shadow-lg rounded-md bg-gray-800 border border-gray-700 transition-all duration-300';
        modalContent.style.top = '';
        modalContent.style.left = '';
        modalContent.style.right = '';
        modalContent.style.bottom = '';
        modalContent.style.width = '';
        modalContent.style.maxWidth = '';
        modalContent.style.margin = '';
        
        // Reset max height of matches container
        if (matchesContainer) {
            matchesContainer.className = 'space-y-3 max-h-96 overflow-y-auto';
        }
        
        // Update icon to show expand
        if (expandIcon) {
            expandIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"></path>';
        }
    }
}

function closeSimilarRulesModal() {
    if (window.ModalManager) {
        window.ModalManager.close('similarRulesModal');
    } else {
        const modal = document.getElementById('similarRulesModal');
        if (modal) {
            modal.remove();
        }
    }
    isSimilarRulesModalExpanded = false;
}

function toggleRuleDetails(detailsId, iconId) {
    const detailsDiv = document.getElementById(detailsId);
    const iconSvg = document.getElementById(iconId);
    const button = iconSvg ? iconSvg.closest('button') : null;
    
    if (!detailsDiv || !iconSvg) {
        return;
    }
    
    const isHidden = detailsDiv.classList.contains('hidden');
    
    if (isHidden) {
        detailsDiv.classList.remove('hidden');
        iconSvg.style.transform = 'rotate(180deg)';
        if (button) {
            const span = button.querySelector('span');
            if (span) span.textContent = 'Hide Logsource & Detection Comparison';
        }
    } else {
        detailsDiv.classList.add('hidden');
        iconSvg.style.transform = 'rotate(0deg)';
        if (button) {
            const span = button.querySelector('span');
            if (span) span.textContent = 'Show Logsource & Detection Comparison';
        }
    }
}

function filterQueue() {
    queuePage = 1;
    loadQueue();
}

function setQueueStatusFilter(status) {
    const el = document.getElementById('queueStatusFilter');
    if (!el) return;
    // Toggle off if already active
    el.value = el.value === status ? '' : status;
    filterQueue();
}

// Hash normalization will happen in DOMContentLoaded

// URL parameter utilities for deep-linking
function getURLParameter(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

function updateURLParameter(name, value) {
    const url = new URL(window.location);
    url.searchParams.set(name, value);
    window.history.replaceState({}, '', url);
}

function removeURLParameter(name) {
    const url = new URL(window.location);
    url.searchParams.delete(name);
    window.history.replaceState({}, '', url);
}

// Check URL for previewId and trigger preview if data is loaded
function checkAndTriggerPreview() {
    const previewId = getURLParameter('previewId');
    if (!previewId) {
        pendingPreviewId = null;
        return;
    }
    
    const ruleId = parseInt(previewId, 10);
    if (isNaN(ruleId)) {
        removeURLParameter('previewId');
        pendingPreviewId = null;
        return;
    }
    
    // Check if rule exists in loaded queue
    const rule = queue.find(r => r.id === ruleId);
    if (rule) {
        // Rule found, trigger preview
        pendingPreviewId = null;
        // Use setTimeout to ensure modal can be opened (avoid race conditions)
        setTimeout(() => {
            // Queue auto-refresh calls checkAndTriggerPreview(); previewRule() resets
            // isEditMode and reloads YAML from the server — do not interrupt an active edit.
            if (currentRuleId === ruleId && isEditMode) {
                return;
            }
            previewRule(ruleId);
        }, 100);
    } else {
        // Rule not found yet, store for later
        pendingPreviewId = ruleId;
    }
}

// Listen for URL changes (back/forward navigation)
window.addEventListener('popstate', function(event) {
    // Only check if we're on the queue tab
    if (currentTab === 'queue') {
        checkAndTriggerPreview();
    }
});

// Auto-refresh active tab
setInterval(() => {
    if (currentTab === 'executions') {
        loadExecutions();
    } else if (currentTab === 'queue') {
        loadQueue();
    }
}, currentTab === 'executions' ? 10000 : 30000);

// Help modal function
function showHelp(fieldName) {
    const helpTexts = {
        'minHuntScore': {
            title: 'Minimum Hunt Score (DISABLED)',
            content: `<div class="mb-3 p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded">
                        <p class="text-sm font-semibold text-yellow-800 dark:text-yellow-50 font-semibold">⚠️ This threshold check is currently DISABLED</p>
                        <p class="text-sm text-yellow-700 dark:text-yellow-300 mt-1">All articles enter the workflow regardless of hunt score.</p>
                      </div>
                      <p class="mb-2"><strong>Range:</strong> 0.0 - 100.0</p>
                      <p class="mb-2"><strong>Default:</strong> 97.0</p>
                      <p class="mb-2"><strong>Description:</strong></p>
                      <p class="mb-2">This is the ML model's threat hunting score threshold. <strong>When enabled</strong>, articles with a hunt score greater than or equal to this value will automatically trigger the agentic workflow.</p>
                      <p class="mb-2"><strong>How it works (when enabled):</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>Articles are scored by the ML model (0-100 scale)</li>
                          <li>Only articles with score ≥ this threshold enter the workflow</li>
                          <li>Higher values = fewer articles processed (more selective)</li>
                          <li>Lower values = more articles processed (less selective)</li>
                      </ul>
                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Recommended:</strong> 95.0-99.0 for production (high quality), 85.0-95.0 for testing (more volume)</p>`
        },
        'junkFilterConfidence': {
            title: 'Junk Filter Confidence',
            content: `<p class="mb-2"><strong>Range:</strong> 0.0 - 1.0</p>
                      <p class="mb-2"><strong>Description:</strong></p>
                      <p class="mb-2">How certain the Junk Filter was that the <em>kept</em> content is huntable. It is the average confidence score across all text chunks that survived filtering.</p>
                      <p class="mb-2"><strong>How it is calculated:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>The article is split into ~1000-character chunks</li>
                          <li>Each chunk is scored by the ML classifier (or pattern-based fallback)</li>
                          <li>Only chunks above the configured threshold are kept</li>
                          <li>This value is the mean confidence of those kept chunks</li>
                      </ul>
                      <p class="mb-2"><strong>What it means:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li><strong>0.9+</strong> - Very high confidence; retained content is almost certainly huntable</li>
                          <li><strong>0.7-0.9</strong> - Normal range; content passed with solid evidence</li>
                          <li><strong>Below 0.7</strong> - Marginal; content was kept but the classifier was uncertain</li>
                      </ul>
                      <p class="text-sm text-gray-600 dark:text-gray-400">This score reflects quality of what was <em>kept</em>, not whether the article passed the filter overall.</p>`
        },
        'junkFilterThreshold': {
            title: 'Junk Filter Threshold',
            content: `<p class="mb-2"><strong>Range:</strong> 0.0 - 1.0</p>
                      <p class="mb-2"><strong>Default:</strong> 0.8</p>
                      <p class="mb-2"><strong>Description:</strong></p>
                      <p class="mb-2">Minimum confidence level for content filtering. Higher values mean stricter filtering (more content removed), lower values mean more lenient filtering.</p>
                      <p class="mb-2"><strong>How it works:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>Content is chunked and each chunk is scored for huntability by the ML model</li>
                          <li>Confidence score (0.0-1.0) indicates how likely the chunk is huntable (high = more huntable)</li>
                          <li>Chunks classified as huntable AND with confidence &ge; threshold are kept</li>
                          <li>Chunks below the threshold or classified as non-huntable are filtered out</li>
                      </ul>
                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Recommended:</strong> 0.7-0.9 (0.8 is balanced). Higher = stricter (less junk), Lower = more lenient (more content passes)</p>`
        },
        'rankingThreshold': {
            title: 'Ranking Threshold',
            content: `<p class="mb-2"><strong>Range:</strong> 0.0 - 10.0</p>
                      <p class="mb-2"><strong>Default:</strong> 6.0</p>
                      <p class="mb-2"><strong>Description:</strong></p>
                      <p class="mb-2">The minimum LLM ranking score (1-10 scale) required for an article to continue through the workflow. If the LLM ranks an article below this threshold, the workflow stops.</p>
                      <p class="mb-2"><strong>How it works:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>After junk filtering, the LLM evaluates the article's huntability</li>
                          <li>LLM returns a score from 1-10 (10 = highly huntable)</li>
                          <li>If score < threshold: workflow stops (not huntable enough)</li>
                          <li>If score ≥ threshold: workflow continues to extraction</li>
                      </ul>
                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Recommended:</strong> 5.0-7.0 (6.0 is balanced). Lower = more lenient, Higher = more strict</p>`
        },
        'similarityThreshold': {
            title: 'Similarity Threshold',
            content: `<p class="mb-2"><strong>Range:</strong> 0.0 - 1.0</p>
                      <p class="mb-2"><strong>Default:</strong> 0.5</p>
                      <p class="mb-2"><strong>Description:</strong></p>
                      <p class="mb-2">Maximum behavioral similarity allowed for queueing SIGMA rules. Rules with similarity above this threshold are considered duplicates and won't be queued.</p>
                      <p class="mb-2"><strong>How it works:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>After generating a SIGMA rule, the system searches for similar existing rules using behavioral novelty assessment</li>
                          <li><strong>Precomputed atom path</strong>: Similarity = (Jaccard x Containment) - Filter penalty using stored rule atoms and metadata. Jaccard measures overlap of detection predicates; containment measures subset overlap; filter penalty reduces similarity for filter/logsource differences.</li>
                          <li><strong>On-the-fly atom path</strong>: Used when precomputed atoms are unavailable. Similarity = 70% atom Jaccard + 30% logic shape similarity. Service mismatches and filter differences apply penalties.</li>
                          <li><strong>Atom Jaccard:</strong> Measures overlap of detection predicates (field/operator/value combinations)</li>
                          <li>If similarity > threshold: rule is NOT queued (duplicate detected)</li>
                          <li>If similarity ≤ threshold: rule is queued (unique enough)</li>
                      </ul>
                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Recommended:</strong> 0.4-0.6 (0.5 is balanced). Lower = stricter (fewer duplicates), Higher = more lenient (more rules queued)</p>`
        },
        'osDetectionAgent': {
            title: 'Platform Detection',
            content: `<p class="mb-2"><strong>Description:</strong></p>
                      <p class="mb-2">Step 0 of the workflow. Determines which host platform(s) an article concerns. The verdict never stops the workflow — it becomes the platform context that routes the extraction sub-agents.</p>
                      <p class="mb-2"><strong>How it works:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li><strong>Step 1 — Keyword registry (deterministic):</strong> Platform-tagged registry entries are scored for Windows, Linux, and macOS simultaneously. Confidence is margin-based: the top platform must clear an absolute evidence floor and lead the runner-up by half its own score to rate "high". Any platform scoring within 50% of the top is co-labelled, so genuinely mixed articles return multiple platforms; thin evidence returns Unknown rather than a guess. This verdict is normally computed once at ingest scoring time and reused here without re-scanning.</li>
                          <li><strong>ATT&amp;CK reinforcement:</strong> Cited technique IDs (e.g. T1059.001) add weight only to platforms the registry already evidenced. A citation on its own never originates a verdict — broad write-ups name techniques across platforms.</li>
                          <li><strong>Step 2 — Windows keyword safety net (deterministic):</strong> When Step 1 is low confidence, three or more Windows indicators (powershell.exe, HKLM, system32, Event ID, …) settle the article as Windows.</li>
                          <li><strong>Step 3 — LLM adjudication (fallback):</strong> Fires only when both deterministic steps remain inconclusive. The model classifies the first 8,000 characters and returns a strict-JSON verdict with evidence. On a failed call, unparseable output, or "no clear signal", the deterministic verdict stands.</li>
                          <li><strong>Result:</strong> Windows, Linux, MacOS, multiple, or Unknown. An Unknown whose sub-floor evidence still leans Windows is promoted to Windows.</li>
                          <li><strong>Routing:</strong> RegistryExtract, ServicesExtract, and ScheduledTasksExtract are Windows-only and are skipped with an <code>unsupported_platform</code> reason on non-Windows verdicts. Cmdline, ProcTree, Hunt Queries, and Network Indicators run on every platform, including Unknown.</li>
                      </ul>
                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>No model to configure.</strong> The deterministic steps resolve the common case at zero cost. The Step 3 fallback uses the <code>PlatformAdjudicator</code> model/provider when set in the config, otherwise it inherits Extract Agent (then Rank Agent). Eval runs bypass Platform Detection entirely and assume Windows.</p>`
        },
	        'rankAgent': {
	            title: 'Rank / Triage Agent Model',
	            content: `<p class="mb-2"><strong>Description:</strong></p>
	                      <p class="mb-2">The LLM model used to evaluate and rank articles for huntability. This agent determines whether an article contains actionable threat intelligence worth extracting.</p>
	                      <p class="mb-2"><strong>Hard rule:</strong> Atomic IOCs (hashes, IPs, domains) are ignored for scoring. Articles must be ranked on behavioral/telemetry patterns, not indicator lists.</p>
	                      <p class="mb-2"><strong>How it works:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>After junk filtering, the Rank Agent evaluates the article</li>
                          <li>Returns a score from 1-10 (10 = highly huntable)</li>
                          <li>If score ≥ ranking threshold: workflow continues</li>
                          <li>If score < ranking threshold: workflow stops</li>
                      </ul>
                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Rationale:</strong> Requires real reasoning and comparison, not extraction. Distilled R1 variants excel at judgment tasks. Llama/Qwen Instruct provide stable classification at lower cost.</p>`
        },
        'extractAgent': {
            title: 'Extract Agents Fallback Model',
            content: `<p class="mb-2"><strong>Description:</strong></p>
                      <p class="mb-2">The default LLM model used by sub-agents when no specific model is configured for them.</p>
                      <p class="mb-2"><strong>How it works:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>Each sub-agent can have its own model configured</li>
                          <li>If a sub-agent has no model set, it falls back to this model</li>
                          <li>The extraction workflow runs sub-agents sequentially via Python (not LLM orchestration)</li>
                      </ul>
                      <p class="mb-2"><strong>Sub-Agents:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li><strong>CmdlineExtract:</strong> Complete literal command lines for EDR/Sigma</li>
                          <li><strong>ProcTreeExtract:</strong> Process parent-child relationships</li>
                          <li><strong>HuntQueriesExtract:</strong> EDR/SIEM queries (KQL, SPL, etc.)</li>
                          <li><strong>RegistryExtract:</strong> Windows registry artifacts</li>
                          <li><strong>ServicesExtract:</strong> Malicious Windows service definitions</li>
                          <li><strong>ScheduledTasksExtract:</strong> Scheduled task identity, triggers, and principal metadata</li>
                          <li><strong>NetworkIndicatorExtract:</strong> Network indicators of compromise (domains, IPs, URLs, user-agents)</li>
                      </ul>
                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Rationale:</strong> Verbatim literal extraction only. Qwen Instruct models are strongest at constraint obedience. Coder variant helps preserve exact token sequences in JSON.</p>`
        },
        'cmdlineExtract': {
            title: 'Command-Line Extraction Agent (Windows)',
            content: `<p class="mb-2"><strong>Description:</strong></p>
                      <p class="mb-2">Specialized sub-agent for extracting command line arguments and command executions from threat intelligence articles.</p>
	                      <p class="mb-2"><strong>What it extracts:</strong></p>
	                      <ul class="list-disc list-inside mb-2 space-y-1">
	                          <li>Command line arguments and switches</li>
	                          <li>Executable names and paths</li>
	                          <li>Command execution patterns</li>
	                          <li>PowerShell commands and scripts</li>
	                          <li>CMD and batch commands</li>
	                      </ul>
	                      <p class="mb-2"><strong>Exclusions (contract):</strong></p>
	                      <ul class="list-disc list-inside mb-2 space-y-1">
	                          <li>Multi-line commands are excluded. If split across physical lines, or uses continuation characters (^ in cmd, backtick in PowerShell): SKIP.</li>
	                          <li>Wrapper stripping applies ONLY to cmd.exe and %COMSPEC% with /c or /k. Strip the wrapper prefix and evaluate the post-wrapper substring. PowerShell wrappers are never stripped.</li>
	                      </ul>
	                      <p class="mb-2"><strong>How it works:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>Orchestrated by the Extract Agents supervisor</li>
                          <li>Focuses specifically on command-line indicators</li>
                          <li>Outputs structured command line data for SIGMA rules</li>
                          <li>Can use Extract Agents model or override with dedicated model</li>
                      </ul>
                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Rationale:</strong> Verbatim literal extraction only. Qwen Instruct models are strongest at constraint obedience. Coder variant helps preserve exact token sequences in JSON.</p>`
        },
        'procTreeExtract': {
            title: 'ProcTreeExtract Model',
            content: `<p class="mb-2"><strong>Description:</strong></p>
                      <p class="mb-2">Specialized sub-agent for extracting process lineage, parent-child relationships, and process tree structures from threat intelligence articles.</p>
	                      <p class="mb-2"><strong>What it extracts:</strong></p>
	                      <ul class="list-disc list-inside mb-2 space-y-1">
	                          <li>Process parent-child relationships</li>
	                          <li>Process execution chains</li>
	                          <li>Process lineage and hierarchies</li>
	                          <li>Process spawning patterns</li>
	                      </ul>
	                      <p class="mb-2"><strong>Exclusions (contract):</strong></p>
	                      <ul class="list-disc list-inside mb-2 space-y-1">
	                          <li>Parent = cmd.exe after normalization: blanket omission. cmd.exe parents are noise at scale and must be skipped entirely.</li>
	                      </ul>
	                      <p class="mb-2"><strong>How it works:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>Orchestrated by the Extract Agents supervisor</li>
                          <li>Identifies process relationships and execution chains</li>
                          <li>Extracts process tree data for SIGMA rule generation</li>
                          <li>Can use Extract Agents model or override with dedicated model</li>
                      </ul>
                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Rationale:</strong> Requires grounding judgments — confirming relationships are explicitly stated vs. inferred. R1 distills and Qwen Instruct are strongest for strict source comparison.</p>`
        },
	        'huntQueriesExtract': {
	            title: 'Hunt Query Extractor Agent',
	            content: `<p class="mb-2"><strong>Description:</strong></p>
	                      <p class="mb-2">Specialized sub-agent for extracting EDR and SIEM queries from threat intelligence articles. Extracts detection queries in various formats (KQL, SPL, etc.).</p>
	                      <p class="mb-2"><strong>Hard rules (contract):</strong></p>
	                      <ul class="list-disc list-inside mb-2 space-y-1">
	                          <li>For Sigma: require BOTH logsource: and detection: keys. Partial Sigma blocks are skipped.</li>
	                          <li>Pseudocode and hypothetical or defensive detection guidance is excluded. Only extract runnable, observed detection artifacts.</li>
	                      </ul>
	                      <p class="mb-2"><strong>What it extracts:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>EDR detection queries (KQL, SPL, etc.)</li>
                          <li>SIEM search queries</li>
                          <li>Query syntax and logic</li>
                          <li>Query parameters and filters</li>
                      </ul>
                      <p class="mb-2"><strong>How it works:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>Orchestrated by the Extract Agents supervisor</li>
                          <li>Identifies and extracts query syntax from articles</li>
                          <li>Preserves exact query formatting and structure</li>
                          <li>Can use Extract Agents model or override with dedicated model</li>
                      </ul>
	                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Rationale:</strong> Coder models best preserve query syntax and field names. Low temperature prevents query reconstruction or completion. Moderately constrained Top-P tolerates complex query punctuation. Optimized for literal string selection under hard gating.</p>`
	        },
	        'registryExtract': {
	            title: 'Registry Artifact Extraction Agent (Windows)',
	            content: `<p class="mb-2"><strong>Description:</strong></p>
	                      <p class="mb-2">Specialized sub-agent for extracting literal Windows registry artifacts (keys, value names, value data, and operation) from threat intelligence articles.</p>
	                      <p class="mb-2"><strong>Hard rules (contract):</strong></p>
	                      <ul class="list-disc list-inside mb-2 space-y-1">
	                          <li>Extract hive-rooted paths only (HKLM\\\\, HKCU\\\\, HKU\\\\, HKCR\\\\, HKCC\\\\ or long forms). Partial paths without a hive root are skipped.</li>
	                          <li>Do not infer or expand shorthand (e.g., "Run key", "IFEO"). Preserve paths exactly as written.</li>
	                          <li>Do not extract reg.exe/PowerShell command lines, process lineage, services ImagePath values, or detection logic owned by sibling agents.</li>
	                      </ul>
	                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Rationale:</strong> Registry telemetry is high-signal only when paths are explicit and observable (Sysmon 12/13/14, Security 4657/4663, EDR).</p>`
	        },
	        'servicesExtract': {
	            title: 'Windows Service Extraction Agent',
	            content: `<p class="mb-2"><strong>Description:</strong></p>
	                      <p class="mb-2">Specialized sub-agent for extracting literal Windows service artifacts (service_name, display_name, image_path, startup_mode, creation_command) from threat intelligence articles.</p>
	                      <p class="mb-2"><strong>Hard rules (contract):</strong></p>
	                      <ul class="list-disc list-inside mb-2 space-y-1">
	                          <li>Require a service indicator (e.g., Event ID 7045/4697, sc.exe/New-Service/net start, Services\\\\ registry path) AND an actionable field (service_name or image_path).</li>
	                          <li>Preserve service_name/image_path/creation_command exactly as written (including spacing/quoting).</li>
	                          <li>Do not extract the sc.exe/PowerShell command line as a command artifact (CmdLineExtract owns the command); do not extract detection logic (HuntQueriesExtract) or process lineage (ProcTreeExtract).</li>
	                      </ul>
	                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Rationale:</strong> Service creation is observable via System 7045, Security 4697, registry telemetry under Services\\\\, and EDR service events.</p>`
	        },
	        'sigmaAgent': {
	            title: 'SIGMA Rule Generation Agent',
	            content: `<p class="mb-2"><strong>Description:</strong></p>
                      <p class="mb-2">The LLM model used to generate SIGMA detection rules from extracted behaviors and IOCs. Converts threat intelligence into actionable detection rules.</p>
                      <p class="mb-2"><strong>How it works:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>Receives extracted behaviors and IOCs from Extract Agents</li>
                          <li>Generates SIGMA YAML rules following SIGMA specification</li>
                          <li>Creates detection rules for Windows Event Logs, Sysmon, etc.</li>
                          <li>Rules are then checked for similarity against existing rules</li>
                          <li>Unique rules are queued for human review and PR submission</li>
                      </ul>
                      <p class="mb-2"><strong>Output Format:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>YAML format following SIGMA specification</li>
                          <li>Includes: title, description, detection logic, tags, falsepositives</li>
                          <li>Compatible with SIEM systems (Splunk, Elastic, QRadar, etc.)</li>
                      </ul>
                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Rationale:</strong> Detection engineering requires controlled reasoning. Coder models excel at structured YAML output. R1 distills help with logic synthesis (must be tightly gated).</p>`
        },
        'scheduledTasksExtract': {
            title: 'Scheduled Task Extraction Agent (Windows)',
            content: `<p class="mb-2"><strong>Description:</strong></p>
                      <p class="mb-2">Specialized sub-agent for extracting Windows scheduled task identity and scheduling metadata from threat intelligence articles.</p>
                      <p class="mb-2"><strong>Hard rules (contract):</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>Extract task name/path, trigger semantics, principal (RunAs/RunLevel), task-store file paths, and operation context only when explicitly stated.</li>
                          <li>Trigger semantics from a schtasks.exe command-line only (e.g., /sc daily) are NOT extracted here unless also described as a task property in prose or XML.</li>
                          <li>Do NOT extract the schtasks.exe / Register-ScheduledTask invocation itself (CmdlineExtract owns it), the payload command inside &lt;Actions&gt;&lt;Exec&gt; (CmdlineExtract), registry paths (RegistryExtract), or process lineage (ProcTreeExtract).</li>
                      </ul>
                      <p class="mb-2"><strong>What it extracts:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>Task name and full path (e.g., \\Microsoft\\Windows\\folder\\TaskName)</li>
                          <li>Trigger type: OnLogon, OnStartup, Daily, Weekly, OnEvent, etc.</li>
                          <li>Principal: RunAs account, RunLevel (HighestAvailable / LeastPrivilege)</li>
                          <li>Task-store file paths (C:\\Windows\\System32\\Tasks\\...)</li>
                          <li>Operation: created, modified, deleted, queried, executed</li>
                      </ul>
                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Rationale:</strong> Scheduled task telemetry is observable via Security EID 4698/4699/4700/4701/4702 and Microsoft-Windows-TaskScheduler/Operational. Identity and trigger metadata are the detection-relevant fields at that source.</p>`
        },
        'networkIndicatorExtract': {
            title: 'Network Indicator Extraction Agent',
            content: `<p class="mb-2"><strong>Description:</strong></p>
                      <p class="mb-2">Specialized sub-agent for extracting network indicators of compromise (domains, IP addresses, URLs, and user-agent strings) from threat intelligence articles.</p>
                      <p class="mb-2"><strong>Hard rules (contract):</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>Extract network indicators (domains, IPv4/IPv6 addresses, URLs, user-agent strings) exactly as written, only when explicitly stated as attacker infrastructure or observed network activity.</li>
                          <li>Preserve indicator values verbatim (including defanging such as hxxp:// or 1.2.3[.]4 as written); do not normalize or re-fang.</li>
                          <li>Do NOT extract command lines (CmdlineExtract owns them), registry paths (RegistryExtract), process lineage (ProcTreeExtract), or detection logic (HuntQueriesExtract).</li>
                      </ul>
                      <p class="mb-2"><strong>What it extracts:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>Domains and fully-qualified hostnames (e.g., c2.example.com)</li>
                          <li>IPv4 / IPv6 addresses</li>
                          <li>URLs and URI paths (including defanged forms)</li>
                          <li>User-agent strings tied to malicious traffic</li>
                      </ul>
                      <p class="text-sm text-gray-600 dark:text-gray-400"><strong>Rationale:</strong> Network indicators are observable via proxy, DNS, firewall, and EDR network telemetry. Verbatim, defang-preserving extraction keeps the indicators pivot-ready for detection and threat hunting.</p>`
        },
        'sigmaEnrich': {
            title: 'How AI Rule Enrichment Works',
            content: `<p class="mb-2"><strong>Enrich Rule</strong> sends your current SIGMA rule (from the editor) to an LLM, which attempts to improve detection logic, add fields, and refine metadata.</p>
                      <p class="mb-3"><strong>Enrich Further</strong> sends the <em>most recent LLM-generated rule</em> back for another refinement pass. This is useful for iterative improvement -- each pass can tighten logic, add edge cases, or polish metadata.</p>
                      <div class="p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded mb-3">
                          <p class="text-sm font-semibold text-blue-800 dark:text-blue-50">How Enrich Further works</p>
                          <p class="text-sm text-blue-700 dark:text-blue-300 mt-1">"Enrich Further" feeds the latest LLM output (not your original rule) to the next call. If the last result looked good, this refines it further. If the last result was off, the next pass starts from that weaker output -- so check each result before continuing.</p>
                      </div>
                      <p class="mb-2"><strong>Tips:</strong></p>
                      <ul class="list-disc list-inside mb-2 space-y-1">
                          <li>Glance at each result before clicking "Enrich Further" to make sure it is heading in the right direction</li>
                          <li>If a result drifted or hallucinated, click "Enrich Rule" to start fresh from your editor content</li>
                          <li>You can also "Apply Enriched Rule" first, tweak it manually, then enrich again from that edited baseline</li>
                      </ul>`
        }
    };

    const help = helpTexts[fieldName];
    if (!help) return;

    const modalId = 'workflowHelpModal';
    const existing = document.getElementById(modalId);
    if (existing) existing.remove();

    // Create modal
    const modal = document.createElement('div');
    modal.id = modalId;
    modal.className = 'fixed inset-0 hidden bg-black bg-opacity-50 flex items-center justify-center z-[9999]';
    modal.innerHTML = `
        <div class="bg-gray-800 border border-gray-700 rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div class="p-6">
                <div class="flex justify-between items-start mb-4">
                    <h3 class="text-xl font-semibold text-gray-900 dark:text-white">${help.title}</h3>
                    <button onclick="window.ModalManager.close('workflowHelpModal')"
                            class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus:outline-none">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                        </svg>
                    </button>
                </div>
                <div class="text-gray-700 dark:text-gray-300 prose prose-sm dark:prose-invert max-w-none">
                    ${help.content}
                </div>
                <div class="mt-6 flex justify-end">
                    <button onclick="window.ModalManager.close('workflowHelpModal')"
                            class="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md transition-colors">
                        Close
                    </button>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);
    window.ModalManager.register(modalId, { isDynamic: true, hasInput: false, forceUpdate: true });
    window.ModalManager.open(modalId);
}
// showSimilarRuleDetails / closeSimilarRuleModal moved to shared component:
// /static/js/components/similar-rule-modal.js

// Highlight a specific queued rule (called from link click)
function highlightQueuedRule(ruleId) {
    // Navigate to queue page with previewId parameter to auto-open preview modal
    window.location.href = `/workflow?previewId=${ruleId}#queue`;
}

// Live execution view with SSE streaming
let liveExecutionEventSource = null;
let liveExecutionId = null;
let liveExecutionCompleted = false;

function openLiveExecutionView(executionId) {
    liveExecutionId = executionId;
    liveExecutionCompleted = false;
    
    // Create modal
    const modal = document.createElement('div');
    modal.id = 'liveExecutionModal';
    modal.className = 'fixed inset-0 bg-black bg-opacity-50 z-50 flex items-center justify-center';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-label', 'Live execution view');
    modal.innerHTML = `
        <div class="bg-gray-900 dark:bg-gray-800 rounded-lg shadow-xl w-11/12 max-w-6xl h-5/6 flex flex-col">
            <div class="flex justify-between items-center p-4 border-b border-gray-700">
                <h2 class="text-xl font-bold text-white"><svg class="w-5 h-5 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 20.25h12m-7.5-3v3m3-3v3m-10.125-3h17.25c.621 0 1.125-.504 1.125-1.125V4.875c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125z"/></svg> Live Execution View - Execution ${executionId}</h2>
                <button onclick="closeLiveExecutionView()" aria-label="Close" class="text-gray-400 hover:text-white text-lg">&times;</button>
            </div>
            <div id="liveExecutionOutput" class="flex-1 overflow-y-auto p-4 font-mono text-sm text-green-400 bg-black rounded m-4" style="min-height: 400px;">
                <div class="text-gray-500">Connecting to execution stream...</div>
            </div>
            <div class="p-4 border-t border-gray-700 flex justify-between items-center">
                <div class="text-sm text-gray-400">
                    <span id="liveExecutionStatus">Status: Connecting...</span>
                </div>
                <button onclick="closeLiveExecutionView()" class="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded">Close</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    
    // Add click outside to close
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeLiveExecutionView();
        }
    });
    
    // Add ESC key to close
    const handleEsc = function(e) {
        if (e.key === 'Escape') {
            closeLiveExecutionView();
            document.removeEventListener('keydown', handleEsc);
        }
    };
    document.addEventListener('keydown', handleEsc);
    
    // Start SSE connection
    startLiveExecutionStream(executionId);
}

function closeLiveExecutionView() {
    if (liveExecutionEventSource) {
        liveExecutionEventSource.close();
        liveExecutionEventSource = null;
    }
    liveExecutionCompleted = false;
    const modal = document.getElementById('liveExecutionModal');
    if (modal) {
        modal.remove();
    }
    liveExecutionId = null;
}

function startLiveExecutionStream(executionId) {
    const outputDiv = document.getElementById('liveExecutionOutput');
    const statusSpan = document.getElementById('liveExecutionStatus');
    liveExecutionCompleted = false;
    
    // Clear previous content
    outputDiv.innerHTML = '<div class="text-gray-500">Connecting to execution stream...</div>';
    
    // Create EventSource connection
    const eventSource = new EventSource(`/api/workflow/executions/${executionId}/stream`);
    liveExecutionEventSource = eventSource;
    
    // Format timestamp
    function formatTime() {
        return new Date().toLocaleTimeString();
    }
    
    // Append to output
    function appendOutput(text, className = 'text-green-400') {
        const line = document.createElement('div');
        line.className = className;
        line.textContent = `[${formatTime()}] ${text}`;
        outputDiv.appendChild(line);
        outputDiv.scrollTop = outputDiv.scrollHeight;
    }
    
    // Handle connection open
    eventSource.onopen = () => {
        appendOutput('✅ Connected to execution stream', 'text-green-400');
        statusSpan.textContent = 'Status: Connected';
    };
    
    // Handle messages
    eventSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            
            switch (data.type) {
                case 'step':
                    appendOutput(`📍 Step: ${data.step}`, 'text-blue-400');
                    break;

                case 'step_complete':
                    appendOutput(`✅ Step Complete: ${data.step}`, 'text-green-400');
                    break;
                    
                case 'status':
                    appendOutput(`📊 Status: ${data.status}`, 'text-yellow-400');
                    statusSpan.textContent = `Status: ${data.status}`;
                    if (data.status === 'completed' || data.status === 'failed') {
                        liveExecutionCompleted = true;
                    }
                    break;
                    
                case 'llm_interaction':
                    appendOutput(`\n🤖 LLM Call - ${data.agent} (Attempt ${data.attempt})`, 'text-cyan-400');
                    if (data.attention_preprocessor) {
                        const ap = data.attention_preprocessor;
                        const n = ap.snippet_count ?? 0;
                        appendOutput(`  📌 Attention preprocessor: ${ap.enabled ? n + ' snippets surfaced' : 'disabled'}`, 'text-violet-400');
                    }
                    if (data.messages && data.messages.length > 0) {
                        data.messages.forEach((msg, idx) => {
                            const role = msg.role || 'user';
                            const content = msg.content || '';
                            const preview = content.length > 500 ? content.substring(0, 500) + '...' : content;
                            appendOutput(`  ${role.toUpperCase()}: ${preview}`, 'text-gray-400');
                        });
                    }
                    if (data.response) {
                        const responsePreview = data.response.length > 1000 ? data.response.substring(0, 1000) + '...' : data.response;
                        appendOutput(`  RESPONSE: ${responsePreview}`, 'text-green-300');
                    }
                    if (data.generated_rule_count !== undefined) {
                        appendOutput(`  Generated Rules: ${data.generated_rule_count}`, 'text-yellow-300');
                    }
                    if (data.valid_rule_count !== undefined) {
                        appendOutput(`  Valid Rules: ${data.valid_rule_count}`, 'text-green-300');
                    }
                    if (data.invalid_rule_count !== undefined) {
                        appendOutput(`  Invalid Rules: ${data.invalid_rule_count}`, 'text-red-300');
                    }
                    if (data.score !== undefined) {
                        appendOutput(`  Score: ${data.score}/10`, 'text-yellow-300');
                    }
                    if (data.discrete_huntables_count !== undefined) {
                        appendOutput(`  Discrete Huntables: ${data.discrete_huntables_count}`, 'text-yellow-300');
                    }
                    break;
                    
                case 'qa_result':
                    const verdictIcon = data.verdict === 'pass' ? '✅' : data.verdict === 'critical_failure' ? '❌' : '⚠️';
                    appendOutput(`\n${verdictIcon} QA Result - ${data.agent}: ${data.verdict.toUpperCase()}`, 
                        data.verdict === 'pass' ? 'text-green-400' : data.verdict === 'critical_failure' ? 'text-red-400' : 'text-yellow-400');
                    if (data.summary) {
                        appendOutput(`  Summary: ${data.summary}`, 'text-gray-300');
                    }
                    if (data.issues && data.issues.length > 0) {
                        appendOutput(`  Issues (${data.issues.length}):`, 'text-orange-400');
                        data.issues.forEach((issue, idx) => {
                            appendOutput(`    ${idx + 1}. [${issue.severity}] ${issue.type}: ${issue.description}`, 'text-orange-300');
                        });
                    }
                    break;
                    
                case 'ranking':
                    appendOutput(`\n📊 Ranking Score: ${data.score}/10`, 'text-yellow-400');
                    if (data.reasoning) {
                        const reasoningPreview = data.reasoning.length > 500 ? data.reasoning.substring(0, 500) + '...' : data.reasoning;
                        appendOutput(`  Reasoning: ${reasoningPreview}`, 'text-gray-300');
                    }
                    break;
                    
                case 'complete':
                    liveExecutionCompleted = true;
                    appendOutput(`\n🏁 Execution ${data.status.toUpperCase()}`, 
                        data.status === 'completed' ? 'text-green-400' : 'text-red-400');
                    if (data.error_message) {
                        appendOutput(`  Error: ${data.error_message}`, 'text-red-300');
                    }
                    statusSpan.textContent = `Status: ${data.status}`;
                    // Close stream after a delay
                    setTimeout(() => {
                        if (liveExecutionEventSource) {
                            liveExecutionEventSource.close();
                            liveExecutionEventSource = null;
                        }
                    }, 2000);
                    break;
                    
                case 'error':
                    appendOutput(`❌ Error: ${data.message}`, 'text-red-400');
                    statusSpan.textContent = 'Status: Error';
                    break;
                    
                default:
                    appendOutput(`Unknown event type: ${data.type}`, 'text-gray-500');
            }
        } catch (e) {
            appendOutput(`Error parsing event: ${e.message}`, 'text-red-400');
        }
    };
    
    // Handle errors
    eventSource.onerror = (error) => {
        if (liveExecutionCompleted) {
            appendOutput('Stream closed after execution completion.', 'text-gray-500');
            statusSpan.textContent = 'Status: Completed';
            return;
        }
        appendOutput('❌ Stream error or connection closed', 'text-red-400');
        statusSpan.textContent = 'Status: Disconnected';
        if (eventSource.readyState === EventSource.CLOSED) {
            appendOutput('Stream closed. Execution may have completed.', 'text-gray-500');
        }
    };
}

/**
 * Accordion behavior for workflow config agent panels: only one agent panel open at a time.
 * Uses capturing listeners so they run before initCollapsiblePanels' toggle (click and keydown).
 */
function initWorkflowConfigAgentAccordion() {
    const container = document.getElementById('workflowConfigForm');
    if (!container) return;
    // Abort previous controller so we can re-init when panels are re-rendered (no duplicate listeners)
    if (container._accordionAbort) {
        container._accordionAbort.abort();
    }
    const ac = new AbortController();
    container._accordionAbort = ac;
    const signal = ac.signal;
    function isAgentPanel(panelId) {
        return panelId && (panelId.endsWith('-prompt-panel') || panelId.endsWith('-qa-prompt-panel'));
    }
    function collapseOthersExcept(header) {
        const agentPanels = container.querySelectorAll('[data-collapsible-panel$="-prompt-panel"], [data-collapsible-panel$="-qa-prompt-panel"]');
        agentPanels.forEach(function(other) {
            if (other === header) return;
            const otherId = other.dataset.collapsiblePanel;
            const otherContent = document.getElementById(otherId + '-content');
            const otherToggle = document.getElementById(otherId + '-toggle');
            if (!otherContent || otherContent.classList.contains('hidden')) return;
            otherContent.classList.add('hidden');
            if (otherToggle) {
                if (otherToggle.tagName === 'svg' || otherToggle.querySelector('svg')) {
                    const svg = otherToggle.tagName === 'svg' ? otherToggle : otherToggle.querySelector('svg');
                    if (svg) svg.style.transform = 'rotate(0deg)';
                } else {
                    otherToggle.textContent = '▼';
                }
            }
            other.setAttribute('aria-expanded', 'false');
        });
    }
    function maybeCollapseOthers(e) {
        const header = e.target.closest('[data-collapsible-panel]');
        if (!header || !container.contains(header)) return;
        const panelId = header.dataset.collapsiblePanel;
        if (!isAgentPanel(panelId)) return;
        collapseOthersExcept(header);
    }
    container.addEventListener('click', maybeCollapseOthers, { capture: true, signal });
    container.addEventListener('keydown', function(e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        maybeCollapseOthers(e);
    }, { capture: true, signal });
}

// Initialize on page load
function initializeTabs() {
    // Hide all tabs initially
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.add('hidden');
    });

    // Function to handle hash and switch tab
    function handleHashAndSwitch() {
        let hash = window.location.hash.substring(1);
        // Normalize hash: 'execution' -> 'executions'
        if (hash === 'execution') {
            hash = 'executions';
            window.location.hash = 'executions';
            return;
        }
        const target = (hash && ['config', 'executions', 'queue'].includes(hash)) ? hash : 'config';
        // switchTab() writes window.location.hash itself, which fires hashchange right back
        // here. Without this guard that self-inflicted event re-enters switchTab for the tab
        // we are already on and re-runs its loader — which is why a bare /workflow load fired
        // loadConfig() (and therefore GET /config/prompts) twice, ~1ms apart. Back/forward to
        // a genuinely different tab still switches, since currentTab differs there.
        if (target === currentTab) {
            return;
        }
        switchTab(target);
    }

    // Delegated click: any .tab-button click switches tab (works even if inline onclick fails)
    document.addEventListener('click', function tabClickDelegated(e) {
        const btn = e.target.closest('.tab-button[data-tab]');
        if (!btn || !btn.getAttribute('data-tab')) return;
        const tab = btn.getAttribute('data-tab');
        if (['config', 'executions', 'queue'].includes(tab)) {
            e.preventDefault();
            switchTab(tab);
        }
    });

    window.addEventListener('hashchange', handleHashAndSwitch);
    window.addEventListener('pageshow', function (event) {
        if (event.persisted) handleHashAndSwitch();
    });

    // Initial load - sync tab to current hash
    var initialHash = window.location.hash.substring(1);
    if (initialHash === 'execution') {
        initialHash = 'executions';
        window.location.hash = 'executions';
    }
    if (initialHash && ['config', 'executions', 'queue'].includes(initialHash)) {
        switchTab(initialHash);
    } else {
        switchTab('config');
    }
    initWorkflowConfigAgentAccordion();

    // Auto-open a specific execution when arriving from an article's "View last run" link.
    // The link encodes the execution ID as ?open_execution=<id> so we can deep-link into the modal.
    var openExecId = new URLSearchParams(window.location.search).get('open_execution');
    if (openExecId && /^\d+$/.test(openExecId)) {
        switchTab('executions');
        // Give the executions tab a moment to render before opening the modal.
        setTimeout(function() {
            if (typeof viewExecution === 'function') {
                viewExecution(parseInt(openExecId, 10));
            }
        }, 400);
    }

    // Prevent hash-driven scroll: we use hash only for tab state. Reset scroll so the page
    // opens at the top. Also set flag so loadConfig can scroll after it finishes (async).
    function scrollWorkflowToTop() {
        window.scrollTo(0, 0);
        if (document.documentElement) {
            document.documentElement.scrollTop = 0;
        }
        if (document.body) {
            document.body.scrollTop = 0;
        }
    }
    if (window.location.hash) {
        if (typeof history !== 'undefined' && history.scrollRestoration) {
            history.scrollRestoration = 'manual';
        }
        window._workflowScrollToTopOnLoad = true;
        scrollWorkflowToTop();
        requestAnimationFrame(scrollWorkflowToTop);
        setTimeout(scrollWorkflowToTop, 200);
    }
}

// Initialize save button state on page load
function initializeSaveButton() {
    const saveButton = document.getElementById('save-config-button');
    if (saveButton) {
        saveButton.disabled = true;
        saveButton.classList.add('opacity-50', 'cursor-not-allowed');
        saveButton.style.opacity = '0.5';
        saveButton.style.cursor = 'not-allowed';
    }
}



// Global sub-agent fallback definitions moved to /static/js/workflow/config.js

// Run immediately if DOM is ready, otherwise wait for DOMContentLoaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', async () => {
        initializeSaveButton();
        initializeTabs();
        
        // Load enabled providers from Settings FIRST before rendering
        await loadEnabledProviders();
        
        // Ensure agent model containers are rendered even if config hasn't loaded yet
        if (typeof loadAgentModels === 'function') {
            loadAgentModels().catch(err => console.error('Error loading agent models on init:', err));
        }
        if (typeof refreshAllProviderBlocks === 'function') {
            refreshAllProviderBlocks();
        }
        
        // __dbgLog('H5', 'DOMContentLoaded fired', { ready: document.readyState });
    });
} else {
    // DOM is already loaded, run immediately
    (async () => {
        initializeSaveButton();
        initializeTabs();
        
        // Load enabled providers from Settings FIRST before rendering
        await loadEnabledProviders();
        
        // Ensure agent model containers are rendered even if config hasn't loaded yet
        if (typeof loadAgentModels === 'function') {
            loadAgentModels().catch(err => console.error('Error loading agent models on init:', err));
        }
        if (typeof refreshAllProviderBlocks === 'function') {
            refreshAllProviderBlocks();
        }
        
        // __dbgLog('H5', 'DOMContentLoaded immediate branch', { ready: document.readyState });
    })();
}
