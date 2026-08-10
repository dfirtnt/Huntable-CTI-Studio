// Workflow — executions module.
//
// Extracted verbatim from src/web/templates/workflow.html (formerly lines
// 10531-12584). Loaded as a classic script AFTER workflow.html's main inline
// block so that state it reads (`executions`, `totalExecutions`) is already
// initialised, and BEFORE the column-resize block that wraps
// `window.loadExecutions`.

// Execution Functions

function getStatusBadge(status) {
    const known = ['pending', 'running', 'completed', 'failed'];
    const cls = known.includes(status) ? status : '';
    const label = status ? status.charAt(0).toUpperCase() + status.slice(1) : 'Unknown';
    return `<span class="q-badge ${cls}">${label}</span>`;
}

function getTerminationBadge(reason) {
    if (!reason) return '';
    const labels = {
        'rank_below_threshold': 'Below Threshold',
        'no_sigma_rules_generated': 'No SIGMA Rules',
        'no_huntable_content': 'Junk Filtered'
    };
    const label = labels[reason] || reason;
    return `<span class="q-badge-term">${label}</span>`;
}

function describeTermination(reason, details) {
    if (!reason) {
        return '';
    }
    const payload = details?.details || {};
    switch (reason) {
        case 'rank_below_threshold': {
            const score = typeof payload.ranking_score === 'number' ? payload.ranking_score.toFixed(1) : payload.ranking_score;
            const threshold = typeof payload.ranking_threshold === 'number' ? payload.ranking_threshold.toFixed(1) : payload.ranking_threshold;
            return `Stopped after ranking (score ${score || 'N/A'} vs threshold ${threshold || 'N/A'})`;
        }
        case 'no_sigma_rules_generated': {
            return 'Completed without generating SIGMA rules';
        }
        case 'no_huntable_content': {
            const confidence = typeof payload.confidence === 'number' ? (payload.confidence * 100).toFixed(0) : null;
            const threshold = typeof payload.threshold === 'number' ? (payload.threshold * 100).toFixed(0) : null;
            return confidence !== null && threshold !== null
                ? `Stopped at junk filter — no chunks met the ${threshold}% confidence threshold (best: ${confidence}%)`
                : 'Stopped at junk filter — no huntable content found';
        }
        default:
            return reason;
    }
}

function getStepBadge(step) {
    const steps = {
        'junk_filter': '🔍 Filter',
        'rank_article': '📊 Rank',
        'extract_agent': '🔬 Extract',
        'generate_sigma': '⚡ SIGMA',
        'similarity_search': '🔎 Similarity',
        'promote_to_queue': '📥 Queue'
    };
    return steps[step] || step || '-';
}

function formatLocalDateTime(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return '-';
    return date.toLocaleString('en-US', { dateStyle: 'short', timeStyle: 'short' });
}

function highlightCurrentStep(step) {
    document.querySelectorAll('.workflow-node').forEach(node => {
        node.style.filter = 'none';
        node.style.stroke = 'none';
        node.style.strokeWidth = '0';
    });
    
    if (step) {
        const node = document.querySelector(`[data-step="${step}"]`);
        if (node) {
            node.style.filter = 'url(#glow)';
            node.style.stroke = 'var(--action-warning)';
            node.style.strokeWidth = '3';
        }
    }
}

function getExecutionTableColumnCount() {
    const baseColumns = 8; // Status indicator, ID, Article, Status, Step, Rank, Created, Actions
    return showObservableCounts ? baseColumns + observableCountColumns.length : baseColumns;
}

const executionSortState = { sortBy: 'created_at', sortOrder: 'desc' };
let _execPage = 1;
const _execLimit = 50;

function setExecutionSort(column) {
    if (executionSortState.sortBy === column) {
        executionSortState.sortOrder = executionSortState.sortOrder === 'asc' ? 'desc' : 'asc';
    } else {
        executionSortState.sortBy = column;
        executionSortState.sortOrder = 'desc';
    }
    loadExecutions();
}

function getSortIndicator(column) {
    if (executionSortState.sortBy !== column) return ' ↕';
    return executionSortState.sortOrder === 'asc' ? ' ↑' : ' ↓';
}

function renderExecutionHeader() {
    const headerRow = document.getElementById('executionsHeaderRow');
    if (!headerRow) return;
    
    const sortableClass = 'cursor-pointer select-none';
    const sortableColumns = [
        { key: 'id', label: 'ID', className: 'q-col-id', ecol: 'ecol-id' },
        { key: 'article_id', label: 'Article', className: 'q-col-article', ecol: 'ecol-article' },
        { key: 'status', label: 'Status', className: 'q-col-status', ecol: 'ecol-status' },
        { key: 'current_step', label: 'Step', className: 'q-col-step', ecol: 'ecol-step' },
        { key: 'ranking_score', label: 'Score', className: 'q-col-score', ecol: 'ecol-score' }
    ];

    const handle = '<div class="exec-resize-handle"></div>';
    // Helper used by observable-count columns and post-loop headers below
    const sortTh = (key, label, className = '', ecol = '') =>
        `<th class="${[sortableClass, className, ecol ? 'exec-resizable' : ''].filter(Boolean).join(' ')}" onclick="setExecutionSort('${key}')" title="Click to sort"${ecol ? ` data-ecol="${ecol}" style="position:relative"` : ''}>${label}${getSortIndicator(key)}${ecol ? handle : ''}</th>`;
    const plainTh = (label, className = '') =>
        `<th class="${className}">${label}</th>`;

    let html =
        '<th class="q-status-indicator-header q-col-status-indicator" aria-hidden="true"></th>' +
        sortableColumns.map((col, i) =>
            `<th class="${sortableClass} ${col.className} exec-resizable" onclick="setExecutionSort('${col.key}')" title="Click to sort" data-ecol="${col.ecol}" style="${i === 0 ? 'padding-left:24px;' : ''}position:relative">${col.label}${getSortIndicator(col.key)}${handle}</th>`
        ).join('');

    if (showObservableCounts) {
        html += observableCountColumns.map(col => plainTh(col.label, 'q-col-observable-count')).join('');
    }
    html += sortTh('created_at', 'Created', 'q-col-created', 'ecol-created');
    html += '<th class="q-col-actions">Actions</th>';
    
    headerRow.innerHTML = html;
}

function formatObservableCount(exec, key) {
    const counts = exec?.extraction_counts || {};
    const value = counts[key];
    return typeof value === 'number' ? value : 0;
}

async function loadExecutions() {
    try {
        renderExecutionHeader();
        const statusFilterEl = document.getElementById('statusFilter');
        const stepFilterEl = document.getElementById('stepFilter');
        const articleIdEl = document.getElementById('articleIdFilter');
        const statusFilter = statusFilterEl ? statusFilterEl.value : '';
        const stepFilter = stepFilterEl ? stepFilterEl.value : '';
        const articleId = articleIdEl && articleIdEl.value.trim() ? parseInt(articleIdEl.value.trim(), 10) : null;
        const excludeEvalsEl = document.getElementById('excludeEvalsToggle');
        const excludeEvals = excludeEvalsEl ? excludeEvalsEl.checked : false;
        const params = new URLSearchParams();
        if (statusFilter) params.set('status', statusFilter);
        if (stepFilter) params.set('step', stepFilter);
        if (articleId && !isNaN(articleId)) params.set('article_id', articleId);
        if (excludeEvals) params.set('exclude_evals', 'true');
        params.set('sort_by', executionSortState.sortBy);
        params.set('sort_order', executionSortState.sortOrder);
        params.set('page', _execPage);
        params.set('limit', _execLimit);
        const url = `/api/workflow/executions?${params.toString()}`;
        
        const response = await fetch(url);
        if (response.ok) {
            const data = await response.json();
            executions = data.executions || []; // Always use executions array
            totalExecutions = data.total !== undefined ? data.total : executions.length;
            renderExecutions();
            updateStats(data); // Pass full data object to use API-provided stats
            const totalPages = data.total_pages ?? 1;
            const paginationEl = document.getElementById('executionPagination');
            if (paginationEl) {
                paginationEl.classList.toggle('hidden', totalExecutions <= _execLimit);
                document.getElementById('executionPageInfo').textContent = `Page ${_execPage} of ${totalPages} (${totalExecutions} total)`;
                document.getElementById('executionPrevBtn').disabled = _execPage <= 1;
                document.getElementById('executionNextBtn').disabled = _execPage >= totalPages;
            }
        } else {
            console.error('Failed to load executions:', response.status, response.statusText);
            const tbody = document.getElementById('executionsTableBody');
            if (tbody) {
                const columns = getExecutionTableColumnCount();
                renderExecutionHeader();
                tbody.innerHTML = `<tr><td colspan="${columns}" class="px-6 py-4 text-center text-red-500">Error loading executions</td></tr>`;
            }
        }
    } catch (error) {
        console.error('Error loading executions:', error);
        const tbody = document.getElementById('executionsTableBody');
        if (tbody) {
            const columns = getExecutionTableColumnCount();
            renderExecutionHeader();
            tbody.textContent = '';
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.colSpan = columns;
            td.className = 'px-6 py-4 text-center text-red-500';
            td.textContent = 'Error: ' + error.message;
            tr.appendChild(td);
            tbody.appendChild(tr);
        }
    }
}

function renderExecutions() {
    const tbody = document.getElementById('executionsTableBody');
    if (!tbody) {
        console.error('executionsTableBody element not found');
        return;
    }
    function execEscapeAttr(str) {
        if (str == null) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;')
            .replace(/</g, '&lt;');
    }
    
    renderExecutionHeader();
    const columns = getExecutionTableColumnCount();
    
    if (executions.length === 0) {
        tbody.innerHTML = `<tr><td colspan="${columns}" class="px-6 py-4 text-center text-gray-500">No executions found</td></tr>`;
        return;
    }
    
    /* NOTE: Pre-existing innerHTML pattern — all values from own DB, not user input. */
    tbody.innerHTML = executions.map(exec => `
        <tr data-status="${exec.status || ''}">
            <td class="q-status-indicator-cell q-col-status-indicator" aria-hidden="true"></td>
            <td class="q-cell-id q-col-id" style="padding-left:24px">${exec.id}</td>
            <td class="q-cell-article q-col-article">
                <a href="/articles/${exec.article_id}">
                    ${exec.article_title || 'Article ' + exec.article_id}
                </a>
            </td>
            <td class="q-col-status">
                <div style="display:flex;align-items:center">${getStatusBadge(exec.status)}${getTerminationBadge(exec.termination_reason)}</div>
            </td>
            <td class="q-step-badge q-col-step">${getStepBadge(exec.current_step)}</td>
            <td class="q-cell-sim q-col-score">${exec.ranking_score ? exec.ranking_score.toFixed(1) : '-'}</td>
            ${showObservableCounts ? observableCountColumns.map(col => `
                <td class="q-cell-sim q-col-observable-count" style="text-align:center">${formatObservableCount(exec, col.key)}</td>
            `).join('') : ''}
            <td class="q-cell-date q-col-created">
                ${formatLocalDateTime(exec.created_at)}
            </td>
            <td class="q-col-actions"><div class="q-actions-cell">
                <button onclick="viewExecution(${exec.id})" class="q-action preview">View</button>${(exec.status === 'running' || exec.status === 'pending') ? `<button onclick="openLiveExecutionView(${exec.id})" class="q-action preview" title="Live streaming view">Live</button>` : ''}<button onclick="debugInAgentChat(${exec.id})" class="q-action approve" title="Open Langfuse session">Trace</button>${exec.status === 'failed' ? `<button onclick="retryExecution(${exec.id}, false)" class="q-action approve" title="Retry in background">Retry</button>` : ''}
            </div></td>
        </tr>
    `).join('');
}

function toggleObservableCounts(event) {
    showObservableCounts = !!event?.target?.checked;
    renderExecutions();
}


function updateStats(data) {
    // Use API-provided stats if available, otherwise calculate from executions array
    const stats = data ? {
        total: data.total !== undefined ? data.total : totalExecutions,
        running: data.running !== undefined ? data.running : executions.filter(e => e.status === 'running').length,
        completed: data.completed !== undefined ? data.completed : executions.filter(e => e.status === 'completed').length,
        failed: data.failed !== undefined ? data.failed : executions.filter(e => e.status === 'failed').length
    } : {
        total: totalExecutions,
        running: executions.filter(e => e.status === 'running').length,
        completed: executions.filter(e => e.status === 'completed').length,
        failed: executions.filter(e => e.status === 'failed').length
    };
    
    const totalEl = document.getElementById('totalExecutions');
    const runningEl = document.getElementById('runningExecutions');
    const completedEl = document.getElementById('completedExecutions');
    const failedEl = document.getElementById('failedExecutions');
    
    if (totalEl) totalEl.textContent = stats.total;
    if (runningEl) runningEl.textContent = stats.running;
    if (completedEl) completedEl.textContent = stats.completed;
    if (failedEl) failedEl.textContent = stats.failed;
}

async function viewExecution(executionId) {
    try {
        const response = await fetch(`/api/workflow/executions/${executionId}`);
        if (response.ok) {
            const exec = await response.json();
            const downloadTraceBtn = document.getElementById('downloadTraceBundleBtn');
            if (downloadTraceBtn) {
                downloadTraceBtn.dataset.executionId = executionId;
                downloadTraceBtn.disabled = false;
            }
            
            // Fetch active config to get agent_models if not in config_snapshot
            let activeConfig = null;
            try {
                const configResponse = await fetch('/api/workflow/config');
                if (configResponse.ok) {
                    activeConfig = await configResponse.json();
                }
            } catch (e) {
                console.warn('Could not fetch active config:', e);
            }
            
            // Helper function to get model name
            const getModel = (agentName) => {
                // First try config_snapshot
                if (exec.config_snapshot?.agent_models?.[agentName]) {
                    return exec.config_snapshot.agent_models[agentName];
                }
                // Then try active config
                if (activeConfig?.agent_models?.[agentName]) {
                    return activeConfig.agent_models[agentName];
                }
                // Fallback to environment
                return 'From environment';
            };
            
            highlightCurrentStep(exec.current_step);
            
            // Build step-by-step inputs/outputs
            const steps = [];
            
            // Step 0: Platform Detection (runs first in workflow)
            // Check for platform detection data in error_log.os_detection_result, termination_details, or error_log.os_detection
            const osDetectionResult = exec.error_log?.os_detection_result;
            // Prioritize os_detection_result over termination_details to ensure correct data source
            const osDetectionData = osDetectionResult || exec.termination_details || {};
            const osDetectionError = exec.error_log?.os_detection;
            const detectedOS = osDetectionData.detected_os || (osDetectionError ? null : undefined);
            const platformsDetected = Array.isArray(osDetectionData.platforms_detected) && osDetectionData.platforms_detected.length > 0
                ? osDetectionData.platforms_detected
                : (Array.isArray(exec.extraction_result?.summary?.platforms_detected) && exec.extraction_result.summary.platforms_detected.length > 0
                    ? exec.extraction_result.summary.platforms_detected
                    : (detectedOS ? [detectedOS] : []));
            const platformsDetectedLabel = platformsDetected.length > 0 ? platformsDetected.join(', ') : 'Unknown';

            // Show Platform Detection step if:
            // 1. Platform detection result exists in error_log
            // 2. OS was detected (in termination_details when workflow stopped)
            // 3. There was a platform detection error
            // 4. Workflow has any steps (platform detection runs first, so it should always be present)
            if (osDetectionResult || detectedOS !== undefined || osDetectionError || exec.status !== 'pending') {
                // Read method from detection_method field, ensuring we don't accidentally use fallback model name
                const osMethod = (osDetectionData.detection_method && typeof osDetectionData.detection_method === 'string') 
                    ? osDetectionData.detection_method 
                    : 'Unknown';
                const osConfidence = (osDetectionData.confidence && typeof osDetectionData.confidence === 'string')
                    ? osDetectionData.confidence
                    : (osDetectionData.confidence !== undefined ? String(osDetectionData.confidence) : 'Unknown');
                const osSimilarities = (osDetectionData.similarities && typeof osDetectionData.similarities === 'object')
                    ? osDetectionData.similarities
                    : {};
                // Ensure max_similarity is a number, not null/undefined
                const osMaxSimilarity = (typeof osDetectionData.max_similarity === 'number' && !isNaN(osDetectionData.max_similarity))
                    ? osDetectionData.max_similarity
                    : undefined;
                const workflowContinued = (exec.extraction_result != null) || (exec.junk_filter_result != null);
                
                // Build similarities display
                let similaritiesHtml = '';
                if (Object.keys(osSimilarities).length > 0) {
                    const similaritiesList = Object.entries(osSimilarities)
                        .map(([os, sim]) => `<div>• ${os}: ${(sim * 100).toFixed(1)}%</div>`)
                        .join('');
                    similaritiesHtml = `<details class="mt-2 w-full">
                        <summary class="cursor-pointer text-xs text-gray-700 dark:text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: var(--text-emphasis) !important;">View Platform Score Distribution</summary>
                        <div class="mt-2 w-full bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs text-gray-900 dark:text-white">
                            ${similaritiesList}
                        </div>
                    </details>`;
                }
                
                // Platform detection runs first and receives original article content (not junk-filtered)
                const osInputContentLength = exec.article_content?.length || exec.junk_filter_result?.original_length || 0;
                const osInputDetails = exec.article_content ? `<details class="mt-2 w-full">
                    <summary class="cursor-pointer text-xs text-gray-700 dark:text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: var(--text-emphasis) !important;">View Content Sent to Platform Detection (${osInputContentLength} chars)</summary>
                    <div class="mt-2 w-full max-h-96 overflow-y-auto bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs font-mono text-gray-900 dark:text-white whitespace-pre-wrap break-words">
                        ${exec.article_content.replace(/</g, '&lt;').replace(/>/g, '&gt;')}
                    </div>
                </details>` : '';
                
                let osOutput = '';
                if (osDetectionError) {
                    osOutput = `<div class="space-y-1 text-red-700 dark:text-red-400">
                        <div><strong>Error:</strong> ${osDetectionError}</div>
                    </div>`;
                } else if (detectedOS !== undefined) {
                    osOutput = `<div class="space-y-1 text-gray-700 dark:text-gray-300">
                        <div><strong>Detected OS:</strong> ${detectedOS}</div>
                        <div><strong>Platforms Detected:</strong> ${platformsDetectedLabel}</div>
                        <div><strong>Method:</strong> ${osMethod}</div>
                        <div><strong>Confidence:</strong> ${osConfidence}</div>
                        ${osMaxSimilarity !== undefined ? `<div><strong>Top Platform Score:</strong> ${(osMaxSimilarity * 100).toFixed(1)}%</div>` : ''}
                        <div><strong>Decision:</strong> Continue to capability routing</div>
                    </div>`;
                } else if (!osDetectionResult) {
                    // No platform detection data stored - could be legacy execution
                    const workflowContinued = exec.junk_filter_result !== null && exec.junk_filter_result !== undefined;
                    osOutput = `<div class="space-y-1 text-gray-700 dark:text-gray-300">
                        <div><strong>Platforms Detected:</strong> ${workflowContinued ? 'Unknown (legacy execution continued)' : 'Unknown (no data stored)'}</div>
                        <div><strong>Decision:</strong> ${workflowContinued ? 'Continue to capability routing' : 'Unknown'}</div>
                        ${!workflowContinued ? `<div class="mt-2 text-xs text-gray-500 dark:text-gray-400">Note: platform detection data not stored for this execution. Check logs for detection errors.</div>` : ''}
                    </div>`;
                }
                
                steps.push({
                    id: 'os_detection',
                    shortName: 'Platform Detection',
                    status: osDetectionError ? 'error' : 'pass',
                    metric: platformsDetectedLabel,
                    name: 'Step 0: Platform Detection',
                    input: `<div class="space-y-1">
                        <div>• Original article content (${osInputContentLength} chars)</div>
                        <div>• Method: <span class="font-mono text-xs">deterministic (entity/keyword registry)</span></div>
                    </div>`,
                    inputDetails: osInputDetails,
                    output: osOutput,
                    details: similaritiesHtml
                });
            }
            
            // Step 1: Junk Filter
            if (exec.junk_filter_result) {
                const originalContentPreview = exec.article_content_preview || '';
                const contentInputDetails = exec.article_content ? `<details class="mt-2 w-full">
                    <summary class="cursor-pointer text-xs text-gray-700 dark:text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: var(--text-emphasis) !important;">View Original Article Content</summary>
                    <div class="mt-2 w-full max-h-96 overflow-y-auto bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs font-mono text-gray-900 dark:text-white whitespace-pre-wrap break-words">
                        ${exec.article_content.replace(/</g, '&lt;').replace(/>/g, '&gt;')}
                    </div>
                </details>` : '';
                
                steps.push({
                    id: 'junk_filter',
                    shortName: 'Junk Filter',
                    status: exec.junk_filter_result.is_huntable ? 'pass' : 'stopped',
                    metric: (exec.junk_filter_result.confidence * 100).toFixed(0) + '%',
                    name: 'Step 1: Junk Filter',
                    input: `<div class="space-y-1">
                        <div>• Article content: ${exec.junk_filter_result.original_length || 0} chars</div>
                    </div>`,
                    inputDetails: contentInputDetails,
                    output: `<div class="space-y-1 text-gray-700 dark:text-gray-300">
                        <div><strong>Filtered:</strong> ${exec.junk_filter_result.is_huntable ? 'Yes' : 'No'}</div>
                        <div><strong>Confidence:</strong> ${(exec.junk_filter_result.confidence || 0).toFixed(2)} <button type="button" onclick="event.stopPropagation(); showHelp('junkFilterConfidence')" class="text-blue-500 hover:text-blue-700 dark:text-blue-400 focus:outline-none inline-align-middle" title="What is this?"><svg class="w-3 h-3 inline" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-3a1 1 0 00-.867.5 1 1 0 11-1.731-1A3 3 0 0113 8a3.001 3.001 0 01-2 2.83V11a1 1 0 11-2 0v-1a1 1 0 011-1 1 1 0 100-2zm0 8a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd"/></svg></button></div>
                        <div><strong>Original Length:</strong> ${exec.junk_filter_result.original_length || 0} chars</div>
                        <div><strong>Filtered Length:</strong> ${exec.junk_filter_result.filtered_length || 0} chars</div>
                        <div><strong>Chunks Kept:</strong> ${exec.junk_filter_result.chunks_kept || 0}</div>
                        <div><strong>Chunks Removed:</strong> ${exec.junk_filter_result.chunks_removed || 0}</div>
                    </div>`
                });
            }
            
            // Step 2: Rank Article
            if (exec.ranking_score !== null && exec.ranking_score !== undefined) {
                const rankingDetails = exec.ranking_reasoning ? `<details class="mt-2 w-full">
                    <summary class="cursor-pointer text-xs text-gray-700 dark:text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: var(--text-emphasis) !important;">View Ranking Reasoning (Full LLM Output)</summary>
                    <div class="mt-2 w-full max-h-96 overflow-y-auto bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs font-mono text-gray-900 dark:text-white whitespace-pre-wrap break-words">
                        <!-- COMMENTED OUT: Truncation control -->
                        ${exec.ranking_reasoning}
                        <!-- ${exec.ranking_reasoning.substring(0, 5000)}${exec.ranking_reasoning.length > 5000 ? '\n\n... (truncated)' : ''} -->
                    </div>
                </details>` : '';
                
                // Show filtered content that was sent to ranking agent
                const filteredContentLength = exec.junk_filter_result?.filtered_length || exec.article_content?.length || 0;
                const filteredContentDetails = exec.article_content ? `<details class="mt-2 w-full">
                    <summary class="cursor-pointer text-xs text-gray-700 dark:text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: var(--text-emphasis) !important;">View Filtered Content Sent to Rank Agent (${filteredContentLength} chars)</summary>
                    <div class="mt-2 w-full max-h-96 overflow-y-auto bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs font-mono text-gray-900 dark:text-white whitespace-pre-wrap break-words">
                        ${exec.article_content.replace(/</g, '&lt;').replace(/>/g, '&gt;')}
                    </div>
                </details>` : '';
                
                // Get model used for ranking
                const rankModel = getModel('RankAgent');
                const rankThreshold = exec.config_snapshot?.ranking_threshold ?? 6.0;

                steps.push({
                    id: 'ranking',
                    shortName: 'Ranking',
                    status: exec.ranking_score >= rankThreshold ? 'pass' : 'stopped',
                    metric: exec.ranking_score.toFixed(1) + ' / ' + rankThreshold.toFixed(1),
                    name: 'Step 2: LLM Ranking',
                    input: `<div class="space-y-1">
                        <div>• Filtered article content (${filteredContentLength} chars)</div>
                        <div>• Article title: "${exec.article_title || 'N/A'}"</div>
                        <div>• Article URL: ${exec.article_url || 'N/A'}</div>
                        <div>• Source metadata</div>
                        <div>• RankAgent prompt from workflow config</div>
                        <div>• Model: <span class="font-mono text-xs">${rankModel}</span></div>
                    </div>`,
                    inputDetails: filteredContentDetails,
                    output: `<div class="space-y-1 text-gray-700 dark:text-gray-300">
                        <div><strong>Ranking Score:</strong> ${exec.ranking_score.toFixed(1)}/10</div>
                        <div><strong>Threshold:</strong> ${rankThreshold.toFixed(1)}/10</div>
                        <div><strong>Decision:</strong> ${exec.ranking_score >= rankThreshold ? '✅ Continue' : '❌ Stop'}</div>
                    </div>${exec.termination_reason === 'rank_below_threshold' ? '<div class="mt-2 text-amber-400 dark:text-yellow-400">⚠️ Workflow ended after ranking because the huntability score was below the threshold.</div>' : ''}`,
                    details: rankingDetails
                });
            }
            
            // Step 3: Extract Agents
            if (exec.extraction_result) {
                const observables = exec.extraction_result.observables || [];
                const summary = exec.extraction_result.summary || {};
                const discreteHuntablesCount = exec.extraction_result.discrete_huntables_count || summary.count || 0;
                const obsCount = observables.length;
                const capabilitySkips = Array.isArray(exec.extraction_result.capability_skips)
                    ? exec.extraction_result.capability_skips
                    : (Array.isArray(exec.error_log?.extract_agent?.capability_skips)
                        ? exec.error_log.extract_agent.capability_skips
                        : []);
                
                // Build expandable sections for all findings
                const detailsSections = [];
                
                // Observables (new format)
                if (obsCount > 0) {
                    detailsSections.push(`<details class="mt-2 w-full">
                            <summary class="cursor-pointer text-xs !text-white dark:!text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: white !important;">View Observables (${obsCount} items)</summary>
                            <div class="mt-2 w-full max-h-96 overflow-y-auto bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs">
                                <div class="space-y-3">
                                    ${observables.map((obs, idx) => {
                                        const type = obs.type || 'Unknown';
                                        const value = obs.value || '';
                                        const platform = obs.platform || 'Unknown';
                                        const telemetryCategory = obs.telemetry_category || '';
                                        const logsourceHint = obs.logsource_hint || '';
                                        const sourceContext = obs.source_context || '';
                                        return `<div class="border-b border-gray-300 dark:border-gray-600 pb-2">
                                            <div class="font-semibold text-gray-900 dark:text-white">${idx + 1}. ${type}</div>
                                            <div class="text-gray-700 dark:text-gray-300 mt-1 break-all">${value}</div>
                                            ${platform !== 'Unknown' ? `<div class="text-gray-600 dark:text-gray-400 mt-1">Platform: ${platform}</div>` : ''}
                                            ${telemetryCategory ? `<div class="text-gray-600 dark:text-gray-400 mt-1">Telemetry: ${telemetryCategory}</div>` : ''}
                                            ${logsourceHint ? `<div class="text-gray-600 dark:text-gray-400 mt-1">Logsource: ${logsourceHint}</div>` : ''}
                                            ${sourceContext ? `<div class="text-gray-600 dark:text-gray-400 mt-1 italic">Context: ${sourceContext}</div>` : ''}
                                        </div>`;
                                    }).join('')}
                                </div>
                            </div>
                        </details>`);
                }
                
                // Capability skips
                if (capabilitySkips.length > 0) {
                    detailsSections.push(`<details class="mt-2 w-full">
                            <summary class="cursor-pointer text-xs !text-white dark:!text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: white !important;">View Capability Skips (${capabilitySkips.length})</summary>
                            <div class="mt-2 w-full bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs">
                                <div class="space-y-2 text-gray-900 dark:text-white">
                                    ${capabilitySkips.map(skip => {
                                        const extractor = skip.extractor || 'Unknown extractor';
                                        const reason = skip.reason || skip.reason_code || 'Skipped by capability routing';
                                        const supported = Array.isArray(skip.supported_platforms) ? skip.supported_platforms.join(', ') : 'Unknown';
                                        const detected = Array.isArray(skip.detected_platforms) ? skip.detected_platforms.join(', ') : 'Unknown';
                                        return `<div class="border-b border-gray-300 dark:border-gray-600 pb-2">
                                            <div><strong>${extractor}</strong></div>
                                            <div>Reason: ${reason}</div>
                                            <div>Supported platforms: ${supported}</div>
                                            <div>Detected platforms: ${detected}</div>
                                        </div>`;
                                    }).join('')}
                                </div>
                            </div>
                        </details>`);
                }

                // Summary
                if (summary && (summary.count !== undefined || summary.platforms_detected || summary.source_url)) {
                    detailsSections.push(`<details class="mt-2 w-full">
                            <summary class="cursor-pointer text-xs !text-white dark:!text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: white !important;">View Summary</summary>
                            <div class="mt-2 w-full bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs">
                                <div class="space-y-2 text-gray-900 dark:text-white">
                                    ${summary.count !== undefined ? `<div><strong>Count:</strong> ${summary.count}</div>` : ''}
                                    ${summary.source_url ? `<div><strong>Source URL:</strong> <a href="${summary.source_url}" target="_blank" class="text-blue-600 dark:text-blue-400 hover:underline">${summary.source_url}</a></div>` : ''}
                                    ${summary.platforms_detected && summary.platforms_detected.length > 0 ? `<div><strong>Platforms Detected:</strong> ${summary.platforms_detected.join(', ')}</div>` : ''}
                                </div>
                            </div>
                        </details>`);
                }
                
                // Discrete Huntables content (if available)
                if (exec.extraction_result.content && discreteHuntablesCount > 0) {
                    detailsSections.push(`<details class="mt-2 w-full">
                            <summary class="cursor-pointer text-xs !text-white dark:!text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: white !important;">View Discrete Huntables Content</summary>
                            <div class="mt-2 w-full max-h-48 overflow-y-auto bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs font-mono text-gray-900 dark:text-white whitespace-pre-wrap break-words">
                                ${exec.extraction_result.content}
                            </div>
                        </details>`);
                }
                
                // Raw LLM Response (if available)
                if (exec.extraction_result.raw_response) {
                    const rawResponse = String(exec.extraction_result.raw_response);
                    // COMMENTED OUT: Truncation control
                    // const truncatedResponse = rawResponse.length > 1000 ? rawResponse.substring(0, 1000) + '...' : rawResponse;
                    const truncatedResponse = rawResponse;
                    detailsSections.push(`<details class="mt-2 w-full">
                            <summary class="cursor-pointer text-xs !text-white dark:!text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: white !important;">View Raw LLM Response</summary>
                            <div class="mt-2 w-full max-h-96 overflow-y-auto bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs font-mono text-gray-900 dark:text-white whitespace-pre-wrap break-words">
                                ${rawResponse.replace(/</g, '&lt;').replace(/>/g, '&gt;')}
                            </div>
                        </details>`);
                }
                
                // Show filtered content that was sent to extraction agent
                const extractInputContentLength = exec.junk_filter_result?.filtered_length || exec.article_content?.length || 0;
                const extractInputDetails = exec.article_content && exec.article_content.length > 0 ? `<details class="mt-2 w-full" id="executionArticleDetails">
                    <summary class="cursor-pointer text-xs text-gray-700 dark:text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: var(--text-emphasis) !important;">View Filtered Content Sent to Extract Agents (${extractInputContentLength} chars)</summary>
                    <div id="executionArticleContent" class="mt-2 w-full max-h-96 overflow-y-auto bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs font-mono text-gray-900 dark:text-white whitespace-pre-wrap break-words">
                        ${String(exec.article_content).replace(/</g, '&lt;').replace(/>/g, '&gt;')}
                    </div>
                </details>` : '';
                
                // Get model used for extraction
                const extractModel = getModel('ExtractAgent');
                
                steps.push({
                    id: 'extraction',
                    shortName: 'Extraction',
                    status: discreteHuntablesCount > 0 ? 'pass' : 'warn',
                    warnReason: discreteHuntablesCount > 0 ? null : 'nothing extracted',
                    metric: discreteHuntablesCount + ' obs',
                    subSteps: null,
                    name: 'Step 3: Extract Agents',
                    input: `<div class="space-y-1">
                        <div>• Filtered article content (${extractInputContentLength} chars)</div>
                        <div>• Article title: "${exec.article_title || 'N/A'}"</div>
                        <div>• Article URL: ${exec.article_url || 'N/A'}</div>
                        <div>• ExtractAgent prompt from workflow config</div>
                        <div>• Model: <span class="font-mono text-xs">${extractModel}</span></div>
                    </div>`,
                    inputDetails: extractInputDetails,
                    output: `<div class="space-y-1 text-gray-700 dark:text-gray-300">
                        <div><strong>Discrete Huntables:</strong> ${discreteHuntablesCount}</div>
                        <div><strong>Observables:</strong> ${obsCount} items</div>
                        ${summary.platforms_detected && summary.platforms_detected.length > 0 ? `<div><strong>Platforms:</strong> ${summary.platforms_detected.join(', ')}</div>` : ''}
                        ${capabilitySkips.length > 0 ? `<div><strong>Capability Skips:</strong> ${capabilitySkips.length}</div>` : ''}
                    </div>`,
                    details: detailsSections.join('')
                });
                
                // Sub-Agents: Individual Extraction Agents (in workflow execution order)
                if (exec.extraction_result?.subresults) {
                    const subresults = exec.extraction_result.subresults || {};

                    // Sub-agents in workflow execution order
                    const subAgents = [
                        { key: 'cmdline', name: 'CmdlineExtract', display: 'Command Line Extraction', icon: '💻', order: 1 },
                        { key: 'process_lineage', name: 'ProcTreeExtract', display: 'Process Lineage Extraction', icon: '🌳', order: 2 },
                        { key: 'hunt_queries', name: 'HuntQueriesExtract', display: 'Hunt Queries Extraction', icon: '🔍', order: 3 },
                        { key: 'registry_artifacts', name: 'RegistryExtract', display: 'Registry Artifacts Extraction', icon: '🗝️', order: 4 },
                        { key: 'windows_services', name: 'ServicesExtract', display: 'Windows Services Extraction', icon: '⚙️', order: 5 },
                        { key: 'scheduled_tasks', name: 'ScheduledTasksExtract', display: 'Scheduled Tasks Extraction', icon: '\u{1F4C5}', order: 6 },
                        { key: 'network_indicators', name: 'NetworkIndicatorExtract', display: 'Network Indicators Extraction', icon: '\u{1F310}', order: 7 }
                    ];

                    const conversationLog = exec.error_log?.extract_agent?.conversation_log || [];
                    const subAgentDetails = subAgents.map(subAgent => {
                        const result = subresults[subAgent.key];
                        const skipRecord = capabilitySkips.find(skip => skip.extractor === subAgent.name);
                        const logEntry = conversationLog.find(e => e.agent === subAgent.name);
                        const attentionPreprocessor = logEntry?.attention_preprocessor;
                        // Ensure items is always an array - handle case where items is a string (e.g., process_lineage)
                        let items = [];
                        if (result?.items !== undefined && result?.items !== null) {
                            if (Array.isArray(result.items)) {
                                items = result.items;
                            } else {
                                // If items is not an array (string, object, etc.), set to empty array
                                items = [];
                            }
                        }
                        const count = result?.count || items.length || 0;
                        const raw = result?.raw || {};

                        const itemsHtml = items.length > 0 ? `<details class="mt-2">
                            <summary class="cursor-pointer text-xs text-gray-600 dark:text-gray-300 hover:text-gray-700 dark:hover:text-gray-200" style="color: var(--text-emphasis) !important;">View ${items.length} Items</summary>
                            <div class="mt-2 max-h-64 overflow-y-auto bg-gray-50 dark:bg-gray-900 p-3 rounded border border-gray-200 dark:border-gray-700 text-xs">
                                <div class="space-y-2">
                                    ${items.slice(0, 20).map((item, idx) => {
                                        const itemValue = typeof item === 'object' ? JSON.stringify(item, null, 2) : String(item);
                                        return `<div class="border-b border-gray-300 dark:border-gray-600 pb-2">
                                            <div class="font-semibold text-gray-600 dark:text-gray-300">${idx + 1}. Item</div>
                                            <div class="text-gray-600 dark:text-gray-300 break-all whitespace-pre-wrap">${itemValue.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</div>
                                        </div>`;
                                    }).join('')}
                                    ${items.length > 20 ? `<div class="text-gray-600 dark:text-gray-300">... and ${items.length - 20} more</div>` : ''}
                                </div>
                            </div>
                        </details>` : '';
                        
                        const rawHtml = raw && Object.keys(raw).length > 0 ? `<details class="mt-2">
                            <summary class="cursor-pointer text-xs text-gray-600 dark:text-gray-300 hover:text-gray-700 dark:hover:text-gray-200" style="color: var(--text-emphasis) !important;">View Raw Agent Response</summary>
                            <div class="mt-2 bg-gray-50 dark:bg-gray-900 p-3 rounded border border-gray-200 dark:border-gray-700 text-xs font-mono text-gray-600 dark:text-gray-300 whitespace-pre-wrap break-words">
                                ${JSON.stringify(raw, null, 2).replace(/</g, '&lt;').replace(/>/g, '&gt;')}
                            </div>
                        </details>` : '';
                        const skipHtml = skipRecord ? `<div class="mt-1 text-xs text-amber-300 dark:text-amber-300">
                                            <div>• Skipped: ${skipRecord.reason || skipRecord.reason_code || 'capability routing'}</div>
                                            ${Array.isArray(skipRecord.supported_platforms) ? `<div>• Supported platforms: ${skipRecord.supported_platforms.join(', ')}</div>` : ''}
                                            ${Array.isArray(skipRecord.detected_platforms) ? `<div>• Detected platforms: ${skipRecord.detected_platforms.join(', ')}</div>` : ''}
                                        </div>` : '';

                        const isProcessLineage = subAgent.key === 'process_lineage';
                        const subAgentStyle = 'style="color: var(--text-emphasis) !important;"';
                        return `<details class="mt-2 border border-cyan-200 dark:border-cyan-700 rounded-lg overflow-hidden">
                            <summary class="bg-cyan-50 dark:bg-cyan-900/30 px-4 py-3 cursor-pointer font-medium text-gray-400 dark:text-gray-300 hover:bg-cyan-100 dark:hover:bg-cyan-900/50 text-sm ${isProcessLineage ? 'process-lineage-extraction' : ''}" ${subAgentStyle}>
                                ${subAgent.icon} ${subAgent.display} <span class="text-white dark:text-white">(${count} ${count === 1 ? 'item' : 'items'})</span>
                            </summary>
                            <div class="card p-4 space-y-3">
                                <div>
                                    <strong class="text-gray-600 dark:text-gray-300 text-sm">Inputs:</strong>
                                    <div class="mt-1 text-xs text-gray-600 dark:text-gray-300">
                                        <div>• Filtered Content: ${extractInputContentLength} chars</div>
                                        <div>• Article Title: ${exec.article_title || 'N/A'}</div>
                                        <div>• Article URL: ${exec.article_url || 'N/A'}</div>
                                        <div>• Agent: ${subAgent.name}</div>
                                        ${exec.config_snapshot?.agent_models?.[`${subAgent.name}_model`] ? `<div>• Model: ${exec.config_snapshot.agent_models[`${subAgent.name}_model`]}</div>` : ''}
                                        ${attentionPreprocessor ? `<div>• 📌 Attention preprocessor: ${attentionPreprocessor.enabled ? (attentionPreprocessor.snippet_count ?? 0) + ' snippets surfaced' : 'disabled'}</div>` : ''}
                                    </div>
                                </div>
                                <div>
                                    <strong class="text-gray-600 dark:text-gray-300 text-sm">Outputs:</strong>
                                    ${skipRecord ? skipHtml : count > 0 ? `
                                        <div class="mt-1 text-xs text-gray-600 dark:text-gray-300">
                                            <div>• Items Extracted: <strong class="text-gray-600 dark:text-gray-300">${count}</strong></div>
                                        </div>
                                        ${itemsHtml}
                                        ${rawHtml}
                                    ` : '<span class="text-gray-600 dark:text-gray-300 text-xs">No items extracted</span>'}
                                </div>
                            </div>
                        </details>`;
                    }).join('');
                    
                    // Attach sub-agent results as nested subSteps on the extraction step
                    const extractionStep = steps.find(s => s.id === 'extraction');
                    if (extractionStep) {
                        extractionStep.subSteps = extractionStep.subSteps || [];
                        extractionStep.subSteps.push({
                            id: 'sub_agents',
                            shortName: 'Sub-Agents',
                            name: '🔬 Sub-Agents',
                            status: Object.values(subresults).some(r => (r?.count || r?.items?.length || 0) > 0) ? 'pass' : 'warn',
                            metric: Object.values(subresults).reduce((sum, r) => sum + (r?.count || r?.items?.length || 0), 0) + ' items',
                            output: `<div class="space-y-4">${subAgentDetails}</div>`,
                            input: `<div class="space-y-1 text-xs"><div>• ${Object.keys(subresults).length} sub-agents executed</div></div>`,
                            inputDetails: '',
                            details: ''
                        });
                    }
                    
                    // ExtractionSupervisorAgent: Aggregation
                    const supervisorDetails = `<div class="card p-4 space-y-3">
                        <div>
                            <strong class="text-gray-900 dark:text-white text-sm">Inputs:</strong>
                            <div class="mt-1 text-xs" style="color: var(--text-emphasis) !important;">
                                <div style="color: var(--text-emphasis) !important;">• Sub-Agent Results: ${Object.keys(subresults).length} sub-agents</div>
                                ${Object.entries(subresults).map(([key, data]) => {
                                    const count = data?.count || data?.items?.length || 0;
                                    const displayName = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                                    return `<div style="color: var(--text-emphasis) !important;">• ${displayName}: ${count} items</div>`;
                                }).join('')}
                            </div>
                        </div>
                        <div>
                            <strong class="text-gray-900 dark:text-white text-sm">Outputs:</strong>
                            <div class="mt-1 text-xs" style="color: var(--text-emphasis) !important;">
                                <div style="color: var(--text-emphasis) !important;">• Total Observables: <strong style="color: var(--text-emphasis) !important;">${discreteHuntablesCount}</strong></div>
                                <div style="color: var(--text-emphasis) !important;">• Aggregated from ${Object.keys(subresults).length} sub-agents</div>
                                ${summary.platforms_detected && summary.platforms_detected.length > 0 ? `<div style="color: var(--text-emphasis) !important;">• Platforms: ${summary.platforms_detected.join(', ')}</div>` : ''}
                            </div>
                            ${exec.extraction_result.content ? `<details class="mt-2">
                                <summary class="cursor-pointer text-xs !text-white dark:!text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: white !important;">View Aggregated Content Summary</summary>
                                <div class="mt-2 bg-gray-50 dark:bg-gray-900 p-3 rounded border border-gray-200 dark:border-gray-700 text-xs font-mono text-gray-900 dark:text-white whitespace-pre-wrap break-words">
                                    ${String(exec.extraction_result.content).substring(0, 2000).replace(/</g, '&lt;').replace(/>/g, '&gt;')}${exec.extraction_result.content.length > 2000 ? '...' : ''}
                                </div>
                            </details>` : ''}
                        </div>
                    </div>`;
                    
                    if (extractionStep) {
                        extractionStep.subSteps = extractionStep.subSteps || [];
                        extractionStep.subSteps.push({
                            id: 'supervisor',
                            shortName: 'Supervisor',
                            name: '🎯 Supervisor',
                            status: discreteHuntablesCount > 0 ? 'pass' : 'warn',
                            metric: discreteHuntablesCount + ' total',
                            output: supervisorDetails,
                            input: `<div class="space-y-1 text-xs"><div>• Aggregating results from ${Object.keys(subresults).length} sub-agents</div></div>`,
                            inputDetails: '',
                            details: ''
                        });
                    }
                }
            }
            
            // Step 4: Generate SIGMA
            const sigmaErrors = exec.error_log?.generate_sigma || exec.error_log?.sigma_generation;
            // Get conversation log from error_log even when there are no errors
            const conversationLog = sigmaErrors?.conversation_log || [];
            
            // Show Step 4 if we have sigma_rules (even if empty array) OR if we have error/conversation data
            if ((exec.sigma_rules !== null && exec.sigma_rules !== undefined) || sigmaErrors || conversationLog.length > 0) {
                const validationResults = sigmaErrors?.validation_results || [];
                const totalAttempts = sigmaErrors?.total_attempts || 0;
                const sigmaRulesCount = (exec.sigma_rules && Array.isArray(exec.sigma_rules)) ? exec.sigma_rules.length : 0;
                
                let errorDetails = '';
                if (sigmaRulesCount === 0 && sigmaErrors) {
                    errorDetails = `<div class="mt-2 p-2 bg-red-50 dark:bg-red-900/20 rounded border border-red-200 dark:border-red-800">
                        <div class="text-xs font-semibold text-red-800 dark:text-red-300 mb-1">Validation Errors:</div>
                        <div class="text-xs text-red-700 dark:text-red-400">
                            <div><strong>Total Attempts:</strong> ${totalAttempts}</div>
                            ${validationResults.length > 0 ? `
                                <details class="mt-1">
                                    <summary class="cursor-pointer text-xs !text-white dark:!text-white" style="color: white !important;">View ${validationResults.length} validation result(s)</summary>
                                    <div class="mt-1 space-y-1 font-mono text-xs text-gray-900 dark:text-white">
                                        ${validationResults.map((vr, idx) => `
                                            <div class="p-1 bg-gray-800 border border-gray-700 rounded">
                                                <div><strong>Attempt ${idx + 1}:</strong> ${vr.is_valid ? '✅ Valid' : '❌ Invalid'}</div>
                                                ${vr.errors && vr.errors.length > 0 ? `
                                                    <div class="ml-2 text-red-600 dark:text-red-400">
                                                        ${vr.errors.slice(0, 3).map(e => `• ${e}`).join('<br>')}
                                                        ${vr.errors.length > 3 ? `<br>... and ${vr.errors.length - 3} more errors` : ''}
                                                    </div>
                                                ` : ''}
                                            </div>
                                        `).join('')}
                                    </div>
                                </details>
                            ` : ''}
                            ${sigmaErrors.errors ? `<div class="mt-1 text-red-600 dark:text-red-400">${sigmaErrors.errors}</div>` : ''}
                        </div>
                    </div>`;
                }
                
                // Build conversation log HTML - show even when no errors if validation results exist
                let conversationHtml = '';
                // Show conversation log if it exists, OR show validation results summary even when no errors
                // Always show if validation results exist (even if conversation log is null)
                if (conversationLog && conversationLog.length > 0) {
                    // Detect format: per-rule (SigmaGenerationService) has rule_id; per-attempt (legacy) has messages
                    const isPerRuleFormat = conversationLog[0].rule_id !== undefined;

                    if (isPerRuleFormat) {
                        // Per-rule format: one entry per generated rule
                        const totalRepairs = conversationLog.reduce((sum, r) => sum + (r.repair_attempts || []).length, 0);
                        const repairSuffix = totalRepairs > 0 ? `, ${totalRepairs} repair attempt${totalRepairs !== 1 ? 's' : ''}` : '';
                        const ruleCardsHtml = conversationLog.map((entry, idx) => {
                            const ruleNum = idx + 1;
                            const isFailed = entry.final_status === 'failed';
                            const isRepaired = entry.final_status === 'repaired';
                            const statusIcon = isFailed ? '❌' : (isRepaired ? '🔧' : '✅');
                            const statusLabel = isFailed ? 'Failed' : (isRepaired ? 'Repaired' : 'Valid');
                            const statusColor = isFailed ? 'text-red-400' : (isRepaired ? 'text-amber-400' : 'text-emerald-400');
                            const borderColor = isFailed ? 'border-red-300 dark:border-red-700' : (isRepaired ? 'border-amber-300 dark:border-amber-700' : 'border-green-300 dark:border-green-700');
                            const phaseBadge = entry.generation_phase === 'expansion' ? '<span class="px-1 py-0.5 rounded text-xs bg-purple-600 text-white ml-1">expansion</span>' : '';

                            const val = entry.validation || {};
                            const valErrors = (val.errors || []).map(e => `<li class="text-red-400 text-xs">${String(e).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</li>`).join('');
                            const valWarnings = (val.warnings || []).map(w => `<li class="text-amber-400 text-xs">${String(w).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</li>`).join('');

                            const repairAttempts = entry.repair_attempts || [];
                            const repairHtml = repairAttempts.length > 0 ? `<details class="mb-1"><summary class="cursor-pointer text-xs text-amber-400 hover:text-amber-300 font-medium">🔧 Repair Attempts (${repairAttempts.length})</summary><div class="mt-2 space-y-2">${
                                repairAttempts.map((ra, raIdx) => {
                                    const raValid = ra.validation && ra.validation.is_valid;
                                    const raBorder = raValid ? 'border-green-700' : 'border-red-700';
                                    const raErrors = (ra.validation && ra.validation.errors || []).map(e => `<li class="text-red-400 text-xs">${String(e).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</li>`).join('');
                                    const raResp = ra.llm_response ? `<details class="mb-1"><summary class="cursor-pointer text-xs text-blue-400 hover:text-blue-300 font-medium">🤖 LLM Response</summary><pre class="mt-1 p-2 bg-gray-800 border border-gray-700 rounded text-xs text-gray-300 whitespace-pre-wrap break-words">${String(ra.llm_response).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</pre></details>` : '';
                                    const raErrHtml = raErrors ? `<div class="text-xs mt-1"><strong class="text-red-400">Errors:</strong><ul class="list-disc list-inside ml-2">${raErrors}</ul></div>` : '';
                                    const raErrMsg = ra.error ? `<div class="text-xs text-red-400 mt-1">Error: ${String(ra.error).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>` : '';
                                    return `<div class="p-2 bg-gray-900 border rounded ${raBorder}"><div class="text-xs font-semibold text-gray-300 mb-1">${raValid ? '✅' : '❌'} Repair Attempt ${ra.attempt || raIdx + 1}</div>${raResp}${raErrHtml}${raErrMsg}</div>`;
                                }).join('')
                            }</div></details>` : '';

                            return `<div class="p-3 bg-gray-800 border-2 rounded-lg ${borderColor}">
                                <div class="flex items-center mb-2"><span class="px-2 py-1 rounded text-xs font-semibold text-white bg-blue-600 mr-2">Rule ${ruleNum}</span>${phaseBadge}<span class="text-xs ${statusColor} font-semibold ml-2">${statusIcon} ${statusLabel}</span></div>
                                <div class="mb-2"><div class="text-xs font-semibold text-gray-700 dark:text-white mb-1">pySigma Validation:</div>
                                    <div class="p-2 bg-gray-700 rounded border ${borderColor}">
                                        <span class="text-xs ${val.is_valid ? 'text-emerald-400' : 'text-red-400'}">${val.is_valid ? '✅ Valid' : '❌ Invalid'}</span>
                                        ${valErrors ? `<div class="text-xs mt-1"><strong class="text-red-400">Errors:</strong><ul class="list-disc list-inside ml-2">${valErrors}</ul></div>` : ''}
                                        ${valWarnings ? `<div class="text-xs mt-1"><strong class="text-amber-400">Warnings:</strong><ul class="list-disc list-inside ml-2">${valWarnings}</ul></div>` : ''}
                                    </div>
                                </div>
                                ${repairHtml}
                            </div>`;
                        }).join('');

                        conversationHtml = `<div class="mt-3 border-t pt-3 border-gray-200 dark:border-gray-700">
                            <details class="w-full" open>
                                <summary class="cursor-pointer text-sm font-semibold text-gray-900 dark:text-white hover:text-gray-700 dark:hover:text-gray-100 mb-2 flex items-center justify-between">
                                    <span class="text-gray-900 dark:text-white"><svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.992 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182M2.985 19.644l3.181-3.182"/></svg> LLM ↔ pySigma Conversation Log (${conversationLog.length} rule${conversationLog.length !== 1 ? 's' : ''}${repairSuffix})</span>
                                    <button onclick="event.stopPropagation(); toggleLogFullscreen('log-${exec.id}', 'log-btn-${exec.id}')" id="log-btn-${exec.id}" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" title="Toggle log fullscreen">
                                        <svg id="log-fullscreen-icon-${exec.id}" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/></svg>
                                        <svg id="log-exit-fullscreen-icon-${exec.id}" class="w-4 h-4 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25"/></svg>
                                    </button>
                                </summary>
                                <div class="text-xs text-gray-600 dark:text-white mb-2 mt-2">Shows the iterative validation process between the LLM and pySigma validator</div>
                                <div id="log-${exec.id}" class="space-y-3 max-h-96 overflow-y-auto p-3 bg-gray-50 dark:bg-gray-900 rounded border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white">
                                    ${ruleCardsHtml}
                                </div>
                            </details>
                        </div>`;
                    } else {
                    // Per-attempt format (legacy): one entry per LLM call with messages/llm_response
                    conversationHtml = `<div class="mt-3 border-t pt-3 border-gray-200 dark:border-gray-700">
                        <details class="w-full" open>
                            <summary class="cursor-pointer text-sm font-semibold text-gray-900 dark:text-white hover:text-gray-700 dark:hover:text-gray-100 mb-2 flex items-center justify-between">
                                <span class="text-gray-900 dark:text-white"><svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.992 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182M2.985 19.644l3.181-3.182"/></svg> LLM ↔ pySigma Conversation Log (${conversationLog.length} attempt${conversationLog.length !== 1 ? 's' : ''})</span>
                                <button onclick="event.stopPropagation(); toggleLogFullscreen('log-${exec.id}', 'log-btn-${exec.id}')" id="log-btn-${exec.id}" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300" title="Toggle log fullscreen">
                                    <svg id="log-fullscreen-icon-${exec.id}" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/>
                                    </svg>
                                    <svg id="log-exit-fullscreen-icon-${exec.id}" class="w-4 h-4 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 9V4.5M9 9H4.5M9 9L3.75 3.75M9 15v4.5M9 15H4.5M9 15l-5.25 5.25M15 9h4.5M15 9V4.5M15 9l5.25-5.25M15 15h4.5M15 15v4.5m0-4.5l5.25 5.25"/>
                                    </svg>
                                </button>
                            </summary>
                            <div class="text-xs text-gray-600 dark:text-white mb-2 mt-2">Shows the iterative validation process between the LLM and pySigma validator</div>
                            <div id="log-${exec.id}" class="space-y-3 max-h-96 overflow-y-auto p-3 bg-gray-50 dark:bg-gray-900 rounded border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white">
                            ${conversationLog.map((entry, idx) => {
                                const attempt = entry.attempt || (idx + 1);
                                const attemptBadgeColor = idx === conversationLog.length - 1 ? 'bg-emerald-500' : 'bg-blue-500';
                                const attemptIcon = idx === conversationLog.length - 1 ? '✅' : '🔄';

                                // Format messages
                                const messages = entry.messages || [];
                                const messagesHtml = messages.map((msg, msgIdx) => {
                                    const role = msg.role || 'user';
                                    const content = String(msg.content || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                                    const roleIcon = role === 'system' ? '⚙️' : '👤';
                                    const roleColor = role === 'system' ? 'text-purple-700 dark:text-purple-400' : 'text-blue-700 dark:text-blue-400';
                                    const collapsibleId = `msg-${exec.id}-${idx}-${msgIdx}`;
                                    return `<div class="mb-2">
                                        <div class="flex items-center mb-1">
                                            <span class="mr-2">${roleIcon}</span>
                                            <span class="font-semibold ${roleColor} text-xs uppercase">${role}</span>
                                        </div>
                                        <div class="bg-gray-100 dark:bg-gray-800 p-2 rounded border border-gray-300 dark:border-gray-600">
                                            <div id="${collapsibleId}-preview" class="text-xs text-gray-700 dark:text-white">${content}</div>
                                        </div>
                                    </div>`;
                                }).join('');

                                // Format LLM response
                                const llmResponse = entry.llm_response || '';
                                const llmContent = String(llmResponse).replace(/</g, '&lt;').replace(/>/g, '&gt;');
                                const llmCollapsibleId = `llm-${exec.id}-${idx}`;

                                // Format validation results (API may return object or array)
                                const vRaw = entry.validation;
                                const validation = Array.isArray(vRaw) ? vRaw : (vRaw && typeof vRaw === 'object' && vRaw !== null ? Object.values(vRaw) : []);
                                const hasErrors = validation.some(v => !v.is_valid);
                                const validationIcon = hasErrors ? '❌' : '✅';
                                const validationColor = hasErrors ? 'text-red-700 dark:text-red-400' : 'text-green-700 dark:text-green-400';

                                const validationHtml = validation.map((v, vIdx) => {
                                    const errs = (v.errors || []).map(e => `<li class="text-red-700 dark:text-red-400 text-xs">${String(e).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</li>`).join('');
                                    const warns = (v.warnings || []).map(w => `<li class="text-yellow-700 dark:text-yellow-400 text-xs">${String(w).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</li>`).join('');
                                    return `<div class="mb-2 p-2 bg-gray-800 border border-gray-700 rounded border ${hasErrors ? 'border-red-300 dark:border-red-700' : 'border-green-300 dark:border-green-700'}">
                                        <div class="flex items-center mb-1">
                                            <span class="mr-2">${validationIcon}</span>
                                            <span class="font-semibold ${validationColor} text-xs">Rule ${v.rule_index || vIdx + 1}: ${v.is_valid ? 'Valid' : 'Invalid'}</span>
                                        </div>
                                        ${errs ? `<div class="text-xs mt-1"><strong class="text-red-700 dark:text-red-400">Errors:</strong><ul class="list-disc list-inside ml-2">${errs}</ul></div>` : ''}
                                        ${warns ? `<div class="text-xs mt-1"><strong class="text-yellow-700 dark:text-yellow-400">Warnings:</strong><ul class="list-disc list-inside ml-2">${warns}</ul></div>` : ''}
                                    </div>`;
                                }).join('');

                                return `<div class="p-3 card border-2 ${idx === conversationLog.length - 1 ? 'border-green-300 dark:border-green-700' : 'border-blue-300 dark:border-blue-700'}">
                                    <div class="flex items-center mb-2">
                                        <span class="px-2 py-1 rounded text-xs font-semibold text-white ${attemptBadgeColor} mr-2">${attemptIcon} Attempt ${attempt}</span>
                                        ${entry.all_valid ? '<span class="text-xs text-emerald-400 dark:text-green-400 font-semibold">All Rules Valid</span>' : '<span class="text-xs text-orange-600 dark:text-orange-400 font-semibold">Has Validation Errors</span>'}
                                    </div>
                                    <div class="mb-3">
                                        <div class="text-xs font-semibold text-gray-700 dark:text-white mb-1">Messages:</div>
                                        ${messagesHtml}
                                    </div>
                                    <div class="mb-3">
                                        <div class="text-xs font-semibold text-gray-700 dark:text-white mb-1">LLM Response:</div>
                                        <div class="bg-blue-50 dark:bg-blue-900/20 p-2 rounded border border-blue-200 dark:border-blue-800">
                                            <pre class="text-xs whitespace-pre-wrap text-gray-800 dark:text-white">${llmContent}</pre>
                                        </div>
                                    </div>
                                    <div>
                                        <div class="text-xs font-semibold text-gray-700 dark:text-white mb-1">Validation Results:</div>
                                        ${validationHtml || '<div class="text-xs text-gray-600 dark:text-white">No validation results</div>'}
                                    </div>
                                </div>`;
                            }).join('')}
                            </div>
                        </details>
                    </div>`;
                    }
                } else if (validationResults && validationResults.length > 0) {
                    // Show validation results summary when no conversation log but validation occurred
                    // Show this even when validation passed (sigmaErrors might be null but validationResults exist)
                    conversationHtml = `<div class="mt-3 border-t pt-3 border-gray-200 dark:border-gray-700">
                        <details class="w-full" open>
                            <summary class="cursor-pointer text-sm font-semibold text-gray-900 dark:text-white hover:text-gray-700 dark:hover:text-gray-100 mb-2 flex items-center justify-between">
                                <span class="text-gray-900 dark:text-white">🔄 pySigma Validation Results (${validationResults.length} attempt${validationResults.length !== 1 ? 's' : ''})</span>
                            </summary>
                            <div class="text-xs text-gray-600 dark:text-white mb-2 mt-2">Shows the validation process between the LLM and pySigma validator</div>
                            <div class="space-y-3 max-h-96 overflow-y-auto p-3 bg-gray-50 dark:bg-gray-900 rounded border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-white">
                                ${validationResults.map((vr, idx) => {
                                    const validationIcon = vr.is_valid ? '✅' : '❌';
                                    const validationColor = vr.is_valid ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400';
                                    const borderColor = vr.is_valid ? 'border-green-300 dark:border-green-700' : 'border-red-300 dark:border-red-700';
                                    const errs = (vr.errors || []).map(e => `<li class="text-red-700 dark:text-red-400 text-xs">${String(e).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</li>`).join('');
                                    const warns = (vr.warnings || []).map(w => `<li class="text-yellow-700 dark:text-yellow-400 text-xs">${String(w).replace(/</g,'&lt;').replace(/>/g,'&gt;')}</li>`).join('');
                                    return `<div class="p-3 card border-2 ${borderColor}">
                                        <div class="flex items-center mb-2">
                                            <span class="px-2 py-1 rounded text-xs font-semibold text-white ${vr.is_valid ? 'bg-emerald-500' : 'bg-red-500'} mr-2">${validationIcon} Attempt ${idx + 1}</span>
                                            <span class="font-semibold ${validationColor} text-xs">${vr.is_valid ? 'Valid' : 'Invalid'}</span>
                                        </div>
                                        ${errs ? `<div class="text-xs mt-2"><strong class="text-red-700 dark:text-red-400">Errors:</strong><ul class="list-disc list-inside ml-2">${errs}</ul></div>` : ''}
                                        ${warns ? `<div class="text-xs mt-2"><strong class="text-yellow-700 dark:text-yellow-400">Warnings:</strong><ul class="list-disc list-inside ml-2">${warns}</ul></div>` : ''}
                                    </div>`;
                                }).join('')}
                            </div>
                        </details>
                    </div>`;
                }
                
                const rulesDetails = exec.sigma_rules.length > 0 ? exec.sigma_rules.map((rule, idx) => {
                    const ruleTitle = rule.title || 'Untitled';
                    const ruleDescription = rule.description || '';
                    const ruleDetection = rule.detection || {};
                    const ruleLogsource = rule.logsource || {};
                    const ruleTags = rule.tags || [];
                    const ruleReferences = rule.references || [];
                    const ruleId = rule.id || '';
                    const ruleStatus = rule.status || '';
                    const ruleLevel = rule.level || '';
                    
                    return `
                    <details class="mt-3 w-full border border-gray-300 dark:border-gray-600 rounded-lg overflow-hidden" ${idx === 0 ? 'open' : ''}>
                        <summary class="cursor-pointer bg-gray-50 dark:bg-gray-900/30 px-4 py-3 font-semibold text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-900/50 text-sm" style="color: var(--text-emphasis) !important;">
                            Rule ${idx + 1}: ${ruleTitle}
                        </summary>
                        <div class="p-4 bg-gray-800 border border-gray-700 space-y-4">
                            ${ruleDescription ? `
                                <div>
                                    <strong class="text-gray-900 dark:text-white text-sm">Description:</strong>
                                    <p class="mt-1 text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap break-words">${ruleDescription.replace(/</g, '&lt;').replace(/>/g, '&gt;')}</p>
                                </div>
                            ` : ''}
                            
                            ${ruleId ? `
                                <div>
                                    <strong class="text-gray-900 dark:text-white text-sm">Rule ID:</strong>
                                    <span class="ml-2 text-sm text-gray-600 dark:text-gray-400 font-mono">${ruleId}</span>
                                </div>
                            ` : ''}
                            
                            ${ruleStatus || ruleLevel ? `
                                <div class="flex gap-4">
                                    ${ruleStatus ? `
                                        <div>
                                            <strong class="text-gray-900 dark:text-white text-sm">Status:</strong>
                                            <span class="ml-2 text-sm text-gray-600 dark:text-gray-400">${ruleStatus}</span>
                                        </div>
                                    ` : ''}
                                </div>
                            ` : ''}
                            
                            ${Object.keys(ruleLogsource).length > 0 ? `
                                <div>
                                    <strong class="text-gray-900 dark:text-white text-sm">Log Source:</strong>
                                    <pre class="mt-1 bg-gray-50 dark:bg-gray-900 p-3 rounded text-xs overflow-x-auto border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300">${JSON.stringify(ruleLogsource, null, 2).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
                                </div>
                            ` : ''}
                            
                            ${Object.keys(ruleDetection).length > 0 ? `
                                <div>
                                    <strong class="text-gray-900 dark:text-white text-sm">Detection Logic:</strong>
                                    <pre class="mt-1 bg-gray-50 dark:bg-gray-900 p-3 rounded text-xs overflow-x-auto border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300">${JSON.stringify(ruleDetection, null, 2).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
                                </div>
                            ` : ''}
                            
                            ${ruleTags.length > 0 ? `
                                <div>
                                    <strong class="text-gray-900 dark:text-white text-sm">Tags:</strong>
                                    <div class="mt-1 flex flex-wrap gap-2">
                                        ${ruleTags.map(tag => `<span class="px-2 py-1 bg-gray-100 dark:bg-gray-900/30 text-gray-700 dark:text-gray-300 rounded text-xs">${tag}</span>`).join('')}
                                    </div>
                                </div>
                            ` : ''}
                            
                            ${ruleReferences.length > 0 ? `
                                <div>
                                    <strong class="text-gray-900 dark:text-white text-sm">References:</strong>
                                    <ul class="mt-1 list-disc list-inside text-sm text-gray-600 dark:text-gray-400 space-y-1">
                                        ${ruleReferences.map(ref => `<li><a href="${ref}" target="_blank" class="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:underline break-all">${ref}</a></li>`).join('')}
                                    </ul>
                                </div>
                            ` : ''}
                            
                            <details class="mt-2">
                                <summary class="cursor-pointer text-xs text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200" style="color: var(--text-emphasis) !important;">
                                    View Full Rule JSON
                                </summary>
                                <pre class="mt-2 bg-gray-50 dark:bg-gray-900 p-3 rounded text-xs overflow-x-auto border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300">${JSON.stringify(rule, null, 2).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
                            </details>
                        </div>
                    </details>
                    `;
                }).join('') : '';
                const step3Details = (rulesDetails + conversationHtml).trim();
                
                // Show extracted content that was sent to SIGMA generation
                const extractContentForSigma = exec.extraction_result?.content || '';
                const extractContentDetails = extractContentForSigma ? `<details class="mt-2 w-full">
                    <summary class="cursor-pointer text-xs text-gray-700 dark:text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: var(--text-emphasis) !important;">View Extracted Content Sent to SIGMA Agent</summary>
                    <div class="mt-2 w-full max-h-96 overflow-y-auto bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs font-mono text-gray-900 dark:text-white whitespace-pre-wrap break-words">
                        ${extractContentForSigma.replace(/</g, '&lt;').replace(/>/g, '&gt;')}
                    </div>
                </details>` : '';
                
                // Get model used for SIGMA generation
                const sigmaModel = getModel('SigmaAgent');
                
                steps.push({
                    id: 'sigma',
                    shortName: 'SIGMA',
                    status: sigmaRulesCount > 0 ? 'pass' : (sigmaErrors ? 'error' : 'warn'),
                    warnReason: sigmaRulesCount === 0 && !sigmaErrors ? 'agent produced nothing' : null,
                    metric: sigmaRulesCount + (sigmaRulesCount === 1 ? ' rule' : ' rules'),
                    name: 'Step 4: Generate SIGMA',
                    input: `<div class="space-y-1" style="color: var(--text-emphasis) !important;">
                        <div style="color: var(--text-emphasis) !important;">• Extracted huntables: ${exec.extraction_result ? (exec.extraction_result.discrete_huntables_count || 0) : 0}</div>
                        <div style="color: var(--text-emphasis) !important;">• Observables: ${exec.extraction_result ? (exec.extraction_result.observables?.length || 0) : 0}</div>
                        <div style="color: var(--text-emphasis) !important;">• Article title: "${exec.article_title || 'N/A'}"</div>
                        <div style="color: var(--text-emphasis) !important;">• SigmaAgent prompt from workflow config</div>
                        <div style="color: var(--text-emphasis) !important;">• Model: <span class="font-mono text-xs" style="color: var(--text-emphasis) !important;">${sigmaModel}</span></div>
                    </div>`,
                    inputDetails: extractContentDetails,
                    output: `<div class="space-y-1 text-gray-700 dark:text-gray-300">
                        <div><strong>Rules Generated:</strong> ${exec.sigma_rules.length}</div>
                        ${exec.sigma_rules.length === 0 ? `<div class="text-orange-600 dark:text-orange-400">⚠️ No rules generated</div>${errorDetails}` : ''}
                        ${exec.sigma_rules.length > 0 ? `<div class="text-emerald-400 dark:text-green-400">✅ ${exec.sigma_rules.length} rule(s) generated successfully</div>` : ''}
                    </div>`,
                    details: step3Details
                });
            }
            
            // Step 5: Similarity Search
            if (exec.similarity_results !== null && exec.similarity_results !== undefined && Array.isArray(exec.similarity_results)) {
                const maxSim = exec.similarity_results.length > 0 ? exec.similarity_results.reduce((max, r) => Math.max(max, r.max_similarity || 0), 0) : 0;
                const similarityDetails = exec.similarity_results.length > 0 ? `<details class="mt-2 w-full" open>
                    <summary class="cursor-pointer text-xs text-gray-700 dark:text-white hover:text-gray-900 dark:hover:text-gray-100 font-medium" style="color: var(--text-emphasis) !important;">🔍 View Similarity Results (${exec.similarity_results.reduce((sum, r) => sum + (r.similar_rules?.length || 0), 0)} similar rules found)</summary>
                    <div class="mt-2 w-full max-h-96 overflow-y-auto bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs space-y-3">
                        ${exec.similarity_results.map((result, idx) => `
                            <div class="mb-3 p-3 bg-gray-800 border border-gray-700 rounded border border-gray-200 dark:border-gray-700">
                                <div class="mb-2">
                                    <div class="font-semibold text-gray-900 dark:text-white">Generated Rule ${idx + 1}: ${result.rule_title || 'Untitled'}</div>
                                    <div class="text-gray-600 dark:text-gray-400">Max Similarity: ${((result.max_similarity || 0) * 100).toFixed(1)}%</div>
                                    <div class="text-gray-600 dark:text-gray-400">Similar Rules Found: ${result.similar_rules?.length || 0}</div>
                                </div>
                                ${result.similar_rules && result.similar_rules.length > 0 ? `
                                    <div class="mt-2 space-y-2">
                                        ${result.similar_rules.map((similarRule, ruleIdx) => {
                                            const fromRepo = (similarRule.rule_id && String(similarRule.rule_id).startsWith('cust-')) || (similarRule.file_path && String(similarRule.file_path).startsWith('customer/'));
                                            const sourceLabel = fromRepo ? 'Your repo' : 'SigmaHQ';
                                            const sourceCls = fromRepo ? 'bg-amber-100 dark:bg-amber-900 text-amber-800 dark:text-amber-200' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300';
                                            return `
                                            <div class="border border-gray-300 dark:border-gray-600 rounded p-2 bg-gray-50 dark:bg-gray-900 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer transition-colors" 
                                                 onclick="showSimilarRuleDetails(${ruleIdx}, ${idx})" 
                                                 data-rule-data='${JSON.stringify(similarRule).replace(/'/g, "&#39;")}'>
                                                <div class="flex items-start justify-between">
                                                    <div class="flex-1">
                                                        <div class="flex items-center gap-2 flex-wrap">
                                                            <div class="font-medium text-blue-600 dark:text-blue-400 hover:underline">${similarRule.title || 'Untitled Rule'}</div>
                                                            <span class="text-xs px-2 py-0.5 rounded ${sourceCls}">${sourceLabel}</span>
                                                        </div>
                                                        ${similarRule.description ? `<div class="text-xs text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">${similarRule.description.substring(0, 150)}${similarRule.description.length > 150 ? '...' : ''}</div>` : ''}
                                                        <div class="flex flex-wrap gap-2 mt-2">
                                                            ${similarRule.rule_id ? `<span class="text-xs px-2 py-1 bg-gray-200 dark:bg-gray-700 rounded text-gray-700 dark:text-gray-300">ID: ${similarRule.rule_id}</span>` : ''}
                                                            ${similarRule.status ? `<span class="text-xs px-2 py-1 bg-green-100 dark:bg-green-900 rounded text-green-700 dark:text-green-300">${similarRule.status}</span>` : ''}
                                                        </div>
                                                    </div>
                                                    <div class="ml-3 text-right">
                                                        <div class="text-lg font-bold text-blue-600 dark:text-blue-400">${((similarRule.similarity || 0) * 100).toFixed(1)}%</div>
                                                        <div class="text-xs text-gray-500 dark:text-gray-400">similar</div>
                                                    </div>
                                                </div>
                                            </div>
                                        `; }).join('')}
                                    </div>
                                ` : `
                                    <div class="text-sm text-gray-500 dark:text-gray-400 italic mt-2">No similar rules found above threshold</div>
                                `}
                            </div>
                        `).join('')}
                    </div>
                </details>` : '';
                
                // Show SIGMA rules that were searched
                const sigmaRulesForSearch = exec.sigma_rules && exec.sigma_rules.length > 0 ? exec.sigma_rules.map((rule, idx) => 
                    `Rule ${idx + 1}: ${rule.title || 'Untitled'}` + (rule.description ? `\n${rule.description.substring(0, 200)}...` : '')
                ).join('\n\n') : '';
                const sigmaRulesInputDetails = sigmaRulesForSearch ? `<details class="mt-2 w-full">
                    <summary class="cursor-pointer text-xs text-gray-700 dark:text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: var(--text-emphasis) !important;">View SIGMA Rules Sent to Similarity Search</summary>
                    <div class="mt-2 w-full max-h-96 overflow-y-auto bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs font-mono text-gray-900 dark:text-white whitespace-pre-wrap break-words">
                        ${sigmaRulesForSearch.replace(/</g, '&lt;').replace(/>/g, '&gt;')}
                    </div>
                </details>` : '';
                
                const simThreshold = exec.config_snapshot?.similarity_threshold ?? 0.5;
                const simStatus = exec.similarity_results.length > 0
                    ? (maxSim < simThreshold ? 'pass' : 'warn')
                    : 'pass';
                const simWarnReason = simStatus === 'warn' ? 'above duplicate threshold' : null;
                steps.push({
                    id: 'similarity',
                    shortName: 'Similarity',
                    status: simStatus,
                    warnReason: simWarnReason,
                    metric: exec.similarity_results.length > 0 ? (maxSim * 100).toFixed(0) + '% max sim' : 'No matches',
                    name: 'Step 5: Similarity Search',
                    input: `<div class="space-y-1">
                        <div>• Generated SIGMA rules: ${exec.sigma_rules?.length || 0}</div>
                        <div>• Similarity threshold: ${(exec.config_snapshot?.similarity_threshold || 0.5) * 100}%</div>
                        <div>• Behavioral novelty assessment</div>
                    </div>`,
                    inputDetails: sigmaRulesInputDetails,
                    output: `<div class="space-y-1 text-gray-700 dark:text-gray-300">
                        <div><strong>Rules Searched:</strong> ${exec.similarity_results.length}</div>
                        <div><strong>Max Similarity:</strong> ${(maxSim * 100).toFixed(1)}%</div>
                        <div><strong>Threshold:</strong> ${(exec.config_snapshot?.similarity_threshold || 0.5) * 100}%</div>
                        <div><strong>Decision:</strong> ${maxSim >= (exec.config_snapshot?.similarity_threshold || 0.5) ? '⚠️ Similar rules found' : '✅ Low similarity'}</div>
                    </div>`,
                    details: similarityDetails
                });
            } else if (exec.sigma_rules && exec.sigma_rules.length === 0) {
                steps.push({
                    id: 'similarity',
                    shortName: 'Similarity',
                    status: 'skipped',
                    metric: 'No rules',
                    name: 'Step 5: Similarity Search',
                    input: '0 generated SIGMA rules',
                    output: '<div class="text-orange-600 dark:text-orange-400">⚠️ Skipped (no rules to search)</div>'
                });
            }
            
            // Step 6: Promote to Queue
            const queuedCount = exec.queued_rules_count || 0;
            const queuedRuleIds = exec.queued_rule_ids || [];
            const queueDetails = queuedCount > 0 ? `<details class="mt-2 w-full">
                <summary class="cursor-pointer text-xs text-gray-700 dark:text-white hover:text-gray-900 dark:hover:text-gray-100" style="color: var(--text-emphasis) !important;">View Queued Rules</summary>
                <div class="mt-2 w-full max-h-48 overflow-y-auto bg-gray-50 dark:bg-gray-900 rounded p-2 border text-xs">
                    <div class="text-gray-700 dark:text-gray-300 mb-2">
                        <a href="?jobId=${exec.id}#queue" class="font-semibold text-purple-600 dark:text-purple-400 cursor-pointer hover:underline hover:text-purple-700 dark:hover:text-purple-300 transition-colors">${queuedCount} rule(s) queued for review</a>
                    </div>
                    ${queuedRuleIds.length > 0 ? `
                        <div class="space-y-1 mt-2">
                            ${queuedRuleIds.map((ruleId, idx) => `
                                <div>
                                    <a href="/workflow#queue" 
                                       onclick="const e = arguments[0] || window.event; e.preventDefault(); e.stopPropagation(); highlightQueuedRule(${ruleId}); return false;" 
                                       class="text-purple-600 dark:text-purple-400 hover:underline cursor-pointer text-xs">
                                        📋 View Queued Rule #${ruleId}
                                    </a>
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            </details>` : '';
            
            // Determine why no rules were queued
            let queueMessage = '';
            if (exec.sigma_rules && exec.sigma_rules.length > 0) {
                if (queuedCount === 0) {
                    if (exec.similarity_results === null || exec.similarity_results === undefined) {
                        queueMessage = '<div class="text-orange-600 dark:text-orange-400">⚠️ No rules queued (similarity search did not run)</div>';
                    } else if (exec.similarity_results.length === 0) {
                        // Similarity search ran but found 0 matches - should have queued, but didn't
                        queueMessage = '<div class="text-orange-600 dark:text-orange-400">⚠️ No rules queued (similarity search found 0 matches but rule was not queued)</div>';
                    } else {
                        // Similarity search ran and found matches - check if all above threshold
                        const maxSim = exec.similarity_results.reduce((max, r) => Math.max(max, r.max_similarity || 0), 0);
                        if (maxSim >= (exec.config_snapshot?.similarity_threshold || 0.5)) {
                            queueMessage = '<div class="text-orange-600 dark:text-orange-400">⚠️ No rules queued (all above similarity threshold)</div>';
                        } else {
                            queueMessage = '<div class="text-orange-600 dark:text-orange-400">⚠️ No rules queued (unexpected - similarity below threshold but not queued)</div>';
                        }
                    }
                } else {
                    queueMessage = '<div class="text-emerald-400 dark:text-green-400">✅ Rules queued for review</div>';
                }
            } else {
                queueMessage = '<div class="text-orange-600 dark:text-orange-400">⚠️ No rules queued (no rules generated)</div>';
            }
            
            let queueWarnReason = null;
            if (queuedCount === 0) {
                if (!exec.sigma_rules || exec.sigma_rules.length === 0) {
                    queueWarnReason = 'no rules generated';
                } else if (exec.similarity_results === null || exec.similarity_results === undefined) {
                    queueWarnReason = 'similarity search did not run';
                } else {
                    const qMaxSim = exec.similarity_results.reduce((max, r) => Math.max(max, r.max_similarity || 0), 0);
                    if (qMaxSim >= (exec.config_snapshot?.similarity_threshold || 0.5)) {
                        queueWarnReason = 'filtered as duplicate';
                    } else {
                        queueWarnReason = 'not queued unexpectedly';
                    }
                }
            }
            steps.push({
                id: 'queue',
                shortName: 'Queue',
                status: queuedCount > 0 ? 'pass' : 'warn',
                warnReason: queueWarnReason,
                metric: queuedCount > 0 ? queuedCount + ' queued' : '0 queued',
                name: 'Step 6: Promote to Queue',
                input: `<div class="space-y-1">
                    <div>• Generated rules: ${exec.sigma_rules?.length || 0}</div>
                    <div>• Similarity results: ${exec.similarity_results !== null && exec.similarity_results !== undefined ? exec.similarity_results.length : 'N/A (did not run)'}</div>
                    <div>• Similarity threshold: ${(exec.config_snapshot?.similarity_threshold || 0.5) * 100}%</div>
                </div>`,
                output: exec.sigma_rules && exec.sigma_rules.length > 0 ? 
                    `<div class="space-y-1 text-gray-700 dark:text-gray-300">
                        <div><strong>Rules Queued:</strong> ${queuedCount}</div>
                        ${queueMessage}
                    </div>` : 
                    '<div class="text-orange-600 dark:text-orange-400">⚠️ No rules queued (no rules generated)</div>',
                details: queueDetails
            });
            
            let observablesData = { execution_id: exec.id, observables: Object.fromEntries(OBS_TYPE_ORDER.map(t => [t, []])) };
            try {
                const obsRes = await fetch(`/api/workflow/executions/${exec.id}/observables`);
                if (obsRes.ok) observablesData = await obsRes.json();
            } catch (e) { console.warn('Observables fetch failed', e); }
            window.__lastExecutionObservables = observablesData;
            const totalObs = OBS_TYPE_ORDER.reduce((sum, t) => sum + (observablesData.observables[t]?.length || 0), 0);
            function confidenceBadge(score) {
                if (score == null) return '<span class="text-[#dee2e8] text-xs">N/A</span>';
                const pct = Math.round(Number(score) * 100);
                const cls = pct >= 80 ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300' : pct >= 50 ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300' : 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300';
                return `<span class="px-2 py-0.5 rounded text-xs font-medium ${cls}" title="Confidence">${pct}% Confidence</span>`;
            }
            function traceabilitySection() {
                if (totalObs === 0) return `<div class="observable-traceability border-t pt-2 border-gray-700"><h4 class="font-bold mb-3 text-white">Observable Traceability</h4><p class="text-[#dee2e8] text-sm">Traceability unavailable (legacy execution or no observables).</p></div>`;
                let html = `<div class="observable-traceability border-t pt-2 border-gray-700"><h4 class="font-bold mb-3 text-white">Observable Traceability</h4><div class="space-y-2">`;
                for (const [typeKey, label] of Object.entries(typeLabels)) {
                    const list = observablesData.observables[typeKey] || [];
                    if (list.length === 0) continue;
                    const idPrefix = `obs-${exec.id}-${typeKey}`;
                    html += `<details class="border rounded-lg border-gray-700 bg-gray-900/50"><summary class="cursor-pointer px-3 py-2 text-sm font-medium text-[#dee2e8] hover:bg-gray-800">${label} (${list.length})</summary><div class="px-3 pb-3 space-y-2">`;
                    list.forEach((obs, idx) => {
                        const obsId = `${idPrefix}-${idx}`;
                        const val = typeof obs.observable_value === 'object' ? JSON.stringify(obs.observable_value) : String(obs.observable_value ?? '');
                        const hasTrace = obs.source_evidence != null || obs.extraction_justification != null;
                        const expandContent = !hasTrace ? `<p class="text-[#dee2e8] text-sm">Traceability unavailable</p>` : `
${ obs.source_evidence != null ? `<blockquote class="border-l-4 border-gray-600 pl-3 py-1 my-2 text-sm text-[#dee2e8] bg-gray-800 rounded">${escapeHtml(obs.source_evidence)}</blockquote>` : ''}
${ obs.extraction_justification != null ? `<p class="text-sm text-[#dee2e8]"><strong>Reasoning:</strong> ${escapeHtml(obs.extraction_justification)}</p>` : ''}
                            <p class="text-xs text-[#dee2e8]">${obs.subagent_name || ''} ${obs.model_version ? ' · ' + obs.model_version : ''} ${obs.extraction_timestamp ? ' · ' + obs.extraction_timestamp : ''}</p>
${ obs.source_evidence != null ? `<button type="button" class="mt-2 px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded jump-to-article-btn" data-type="${typeKey}" data-index="${idx}" title="Scroll to source paragraph in article">Jump to Article</button>` : ''}
                        `;
                        html += `<div class="border border-gray-700 rounded p-2 bg-gray-900"><details class="obs-item"><summary class="cursor-pointer flex items-center gap-2 flex-wrap"><code class="text-xs break-all text-[#dee2e8]">${escapeHtml(val)}</code> ${confidenceBadge(obs.confidence_score)}</summary><div class="mt-2 pt-2 border-t border-gray-700">${expandContent}</div></details></div>`;
                    });
                    html += `</div></details>`;
                }
                html += `</div></div>`;
                return html;
            }

            // Build execution header (article info, status, error — always shown above tabs)
            const headerHtml = `
                <div class="border-b pb-3 mb-4 border-gray-700">
                    <div class="text-gray-200"><strong>Execution ID:</strong> ${exec.id}</div>
                    <div class="text-gray-200"><strong>Article:</strong> <a href="/articles/${exec.article_id}" class="text-purple-400 hover:text-purple-300">${escapeHtml(exec.article_title || '')}</a></div>
                    <div class="text-gray-200"><strong>Status:</strong> ${getStatusBadge(exec.status)}</div>
                    ${exec.termination_reason ? `<div class="text-gray-200"><strong>Completion Reason:</strong> ${escapeHtml(describeTermination(exec.termination_reason, exec.termination_details))}</div>` : ''}
                    <div class="text-gray-200"><strong>Created:</strong> ${formatLocalDateTime(exec.created_at)}</div>
                    ${exec.completed_at ? `<div class="text-gray-200"><strong>Completed:</strong> ${formatLocalDateTime(exec.completed_at)}</div>` : ''}
                    ${exec.error_message ? `<div class="bg-red-900/20 p-3 rounded mt-2 border border-red-700"><strong class="text-red-300">Error:</strong> <span class="text-gray-100">${escapeHtml(exec.error_message)}</span></div>` : ''}
                </div>
            `;

            const tabbedHtml = steps.length > 0
                ? renderExecutionTabbed(steps, exec)
                : '<div class="text-gray-300 py-4">No step data available for this execution.</div>';

            const content = headerHtml + tabbedHtml;

            document.getElementById('executionDetailContent').innerHTML = content;
            if (typeof traceabilitySection === 'function') {
                const extractIdx = steps.findIndex(s => (s.name || s.shortName || '').toLowerCase().includes('extract'));
                if (extractIdx >= 0) {
                    const extractPanel = document.querySelector('#exec-panels [data-panel="' + extractIdx + '"]');
                    if (extractPanel) extractPanel.insertAdjacentHTML('beforeend', traceabilitySection());
                }
            }
            document.getElementById('executionModal').classList.remove('hidden');
            // Auto-fullscreen on open
            const modalContent = document.getElementById('executionModalContent');
            if (modalContent && !modalContent.classList.contains('modal-fullscreen')) {
                toggleModalFullscreen();
            }
            document.querySelectorAll('#executionDetailContent .jump-to-article-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    const typeKey = this.getAttribute('data-type');
                    const index = parseInt(this.getAttribute('data-index'), 10);
                    const obs = window.__lastExecutionObservables?.observables?.[typeKey]?.[index];
                    const evidence = obs?.source_evidence;
                    const el = document.getElementById('executionArticleContent');
                    const detailsEl = document.getElementById('executionArticleDetails');
                    if (!el || !evidence) { if (typeof showNotification === 'function') showNotification('Could not locate exact paragraph in article', 'warning'); return; }
                    if (detailsEl && !detailsEl.open) detailsEl.open = true;
                    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    const text = el.textContent || '';
                    const idx = text.indexOf(evidence.trim().slice(0, 200));
                    if (idx === -1) { if (typeof showNotification === 'function') showNotification('Could not locate exact paragraph in article', 'warning'); return; }
                    const before = text.slice(0, idx);
                    const matchLen = Math.min(evidence.length, text.length - idx);
                    const highlight = text.slice(idx, idx + matchLen);
                    const after = text.slice(idx + matchLen);
                    const span = document.createElement('span');
                    span.className = 'bg-yellow-300 dark:bg-yellow-600/50 rounded px-0.5';
                    span.textContent = highlight;
                    el.textContent = '';
                    el.appendChild(document.createTextNode(before));
                    el.appendChild(span);
                    el.appendChild(document.createTextNode(after));
                    setTimeout(() => { el.textContent = before + highlight + after; }, 3000);
                });
            });
        }
    } catch (error) {
        console.error('Error loading execution details:', error);
    }
}

async function downloadExecutionTraceBundle(executionId = null, slim = false) {
    const button = document.getElementById('downloadTraceBundleBtn');
    const targetExecutionId = executionId || button?.dataset.executionId;
    if (!targetExecutionId) {
        showNotification('No execution selected for trace download', 'error');
        return;
    }

    const originalHtml = button ? button.innerHTML : '';
    if (button) {
        button.disabled = true;
        button.setAttribute('aria-busy', 'true');
        button.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
            </svg>
            Downloading...
        `;
    }

    try {
        let url = `/api/workflow/executions/${targetExecutionId}/trace-bundle`;
        if (slim) {
            url += '?slim=true';
        }
        const response = await fetch(url);
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: response.statusText }));
            throw new Error(error.detail || `HTTP ${response.status}`);
        }

        const blob = await response.blob();
        const downloadUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        const suffix = slim ? '_slim' : '';
        a.download = `workflow_execution_trace_${targetExecutionId}${suffix}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(downloadUrl);
        showNotification(`Downloaded trace for execution ${targetExecutionId}`, 'success');
    } catch (error) {
        console.error('Error downloading execution trace bundle:', error);
        showNotification('Trace download failed: ' + error.message, 'error');
    } finally {
        if (button) {
            button.disabled = false;
            button.removeAttribute('aria-busy');
            button.innerHTML = originalHtml;
        }
    }
}

async function retryExecution(executionId, useLangGraphServer = false) {
    const mode = useLangGraphServer ? 'synchronously (wait for completion)' : 'asynchronously (background)';
    if (!await ModalManager.confirm(`Retry execution ${executionId}${mode ? ' ' + mode : ''}?`, { title: 'Retry Execution', confirmText: 'Retry', confirmClass: 'bg-purple-600 hover:bg-purple-700', cancelText: 'Cancel' })) return;
    
    try {
        const url = `/api/workflow/executions/${executionId}/retry?use_langgraph_server=${useLangGraphServer}`;
        const response = await fetch(url, { method: 'POST' });
        
        if (response.ok) {
            const result = await response.json();
            if (result.via_direct_execution) {
                showNotification('Retry completed. Execution finished synchronously.', 'success');
            } else {
                showNotification('Retry queued. Execution running in background.', 'success');
            }
            await loadExecutions();
        } else {
            const error = await response.json();
            const errorMsg = error.detail || 'Unknown error';
            showNotification('Error retrying execution: ' + errorMsg, 'error');
        }
    } catch (error) {
        console.error('Error retrying execution:', error);
        showNotification('Error retrying execution', 'error');
    }
}

function buildTraceUrl(info) {
    // Prefer the backend-selected trace URL; fall back to legacy session/search URLs.
    if (info.agent_chat_url) return info.agent_chat_url;
    if (info.session_url) return info.session_url;
    if (info.search_url) return info.search_url;
    return null;
}


async function debugInAgentChat(executionId) {
    try {
        // Get debug info (Langfuse trace URL)
        const response = await fetch(`/api/workflow/executions/${executionId}/debug-info`);
        if (response.ok) {
            const info = await response.json();
            const sessionUrl = buildTraceUrl(info);
            
            if (sessionUrl) {
                // Check if Langfuse is configured
                if (!info.uses_langfuse && info.instructions && info.instructions.includes('not configured')) {
                    // Show warning but still open trace URL
                    const proceed = await ModalManager.confirm(
                        'Langfuse keys are not configured. Trace results will only exist if the execution ran with Langfuse tracing enabled.\n\n' +
                        'Would you like to open the trace URL anyway?',
                        { title: 'Langfuse Not Configured', confirmText: 'Open URL', confirmClass: 'bg-blue-600 hover:bg-blue-700' }
                    );
                    if (!proceed) {
                        return;
                    }
                }
                
                // Log instructions if available
                if (info.instructions) {
                    console.log('Debug Instructions:', info.instructions);
                }
                
                // Show helpful message with search info
                let message = 'Opening Langfuse trace...\n\n';
                if (info.session_id) {
                    message += `If the trace is not found (404), search for:\n`;
                    message += `Session ID: ${info.session_id}\n`;
                    if (info.trace_id) {
                        message += `Trace ID: ${info.trace_id}\n`;
                    }
                    message += `\nUse the search/filter in Langfuse UI to find traces by session_id.`;
                }
                
                // Open Langfuse trace directly in new tab
                window.open(sessionUrl, '_blank');

                // Show message after a brief delay (so it doesn't block the window.open)
                setTimeout(() => {
                    if (info.session_id || info.trace_id) {
                        console.log(message);
                    }
                }, 500);
            } else {
                showNotification('Unable to generate trace URL. Please check Langfuse configuration.', 'error');
            }
        } else {
            const error = await response.json();
            showNotification('Error getting debug info: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error opening session:', error);
        showNotification('Error opening session. Please check your configuration.', 'error');
    }
}

function closeModal() {
    if (window.ModalManager) {
        window.ModalManager.close('executionModal');
    } else {
        document.getElementById('executionModal').classList.add('hidden');
    }
    // Reset fullscreen state when closing
    const modalContent = document.getElementById('executionModalContent');
    if (modalContent) {
        modalContent.classList.remove('modal-fullscreen');
        document.getElementById('fullscreenIcon').classList.remove('hidden');
        document.getElementById('exitFullscreenIcon').classList.add('hidden');
    }
    // Clear fullscreen stack
    window.fullscreenStack = [];
}

function toggleModalFullscreen() {
    const modalContent = document.getElementById('executionModalContent');
    const fullscreenIcon = document.getElementById('fullscreenIcon');
    const exitFullscreenIcon = document.getElementById('exitFullscreenIcon');
    
    if (!modalContent) return;
    
    if (modalContent.classList.contains('modal-fullscreen')) {
        // Exit fullscreen
        modalContent.classList.remove('modal-fullscreen');
        fullscreenIcon.classList.remove('hidden');
        exitFullscreenIcon.classList.add('hidden');
        // Remove from fullscreen stack
        window.fullscreenStack = window.fullscreenStack || [];
        window.fullscreenStack = window.fullscreenStack.filter(el => el !== 'modal');
    } else {
        // Enter fullscreen
        modalContent.classList.add('modal-fullscreen');
        fullscreenIcon.classList.add('hidden');
        exitFullscreenIcon.classList.remove('hidden');
        // Add to fullscreen stack
        window.fullscreenStack = window.fullscreenStack || [];
        window.fullscreenStack.push('modal');
    }
}

function switchExecTab(index) {
    // Update tab buttons — CSS handles styling via data-active/data-status attributes
    document.querySelectorAll('#exec-tab-strip button.exec-tab').forEach((btn, i) => {
        const isActive = i === index;
        btn.setAttribute('data-active', isActive ? 'true' : 'false');
        // Reset to base class — CSS attribute selectors handle the rest
        btn.className = 'exec-tab flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap border';
    });
    // Update panels
    document.querySelectorAll('#executionDetailContent .exec-panel').forEach((panel, i) => {
        panel.classList.toggle('hidden', i !== index);
    });
}

function renderSubTabs(subSteps) {
    if (!subSteps || subSteps.length === 0) return '';
    const tabButtons = subSteps.map((sub, i) => `
        <button class="exec-subtab exec-tab flex items-center gap-1 px-2 py-1 rounded text-xs font-medium whitespace-nowrap border"
                data-subtab="${i}" data-status="${sub.status}" data-active="${i === 0 ? 'true' : 'false'}"
                onclick="switchExecSubTab(this.closest('.exec-subtab-container'), ${i})">
            ${sub.shortName}${sub.metric ? `<span style="opacity:0.75;font-family:'JetBrains Mono',monospace;margin-left:4px;font-size:10px">${escapeHtml(String(sub.metric))}</span>` : ''}
        </button>
    `).join('');

    const panels = subSteps.map((sub, i) => `
        <div class="exec-subpanel ${i === 0 ? '' : 'hidden'}" data-subpanel="${i}">
            <div class="text-sm space-y-3 pt-3">
                <div style="font-family:'JetBrains Mono',monospace;font-size: 10px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-muted-slate);margin-bottom:4px">OUTPUT</div>
                ${sub.output || ''}
            </div>
        </div>
    `).join('');

    return `
        <div class="exec-subtab-container" style="margin-top:16px;border-top:1px solid var(--purple-border-15);padding-top:16px">
            <div class="flex gap-2 overflow-x-auto pb-2 mb-3">${tabButtons}</div>
            ${panels}
        </div>
    `;
}

function switchExecSubTab(container, index) {
    if (!container) return;
    // CSS handles styling via data-active/data-status attribute selectors
    container.querySelectorAll('button.exec-subtab').forEach((btn, i) => {
        const isActive = i === index;
        btn.setAttribute('data-active', isActive ? 'true' : 'false');
        btn.className = 'exec-subtab exec-tab flex items-center gap-1 px-2 py-1 rounded text-xs font-medium whitespace-nowrap border';
    });
    container.querySelectorAll('.exec-subpanel').forEach((panel, i) => {
        panel.classList.toggle('hidden', i !== index);
    });
}

function renderStepPanel(step) {
    const statusLabels = { pass: 'CONTINUED', stopped: 'TERMINATED', warn: 'WARNING', error: 'FAILED', skipped: 'SKIPPED' };
    const statusBadgeColors = {
        pass: 'bg-green-900/40 text-green-300 border-green-700',
        stopped: 'bg-red-900/40 text-red-300 border-red-700',
        warn: 'bg-amber-900/40 text-amber-300 border-amber-700',
        error: 'bg-red-900/40 text-red-300 border-red-700',
        skipped: 'bg-gray-900/40 text-gray-400 border-gray-600'
    };
    const badgeClass = statusBadgeColors[step.status] || statusBadgeColors.skipped;
    const label = statusLabels[step.status] || (step.status || '').toUpperCase();

    return `
        <div class="space-y-3">
            <div class="flex items-center justify-between flex-wrap gap-2">
                <h4>${step.name}</h4>
                <span class="px-2.5 py-1 rounded border text-xs font-semibold ${badgeClass}">${label}</span>
            </div>
            ${step.metric ? `<div style="font-family:'JetBrains Mono',monospace;font-size:18px;color:var(--text-primary);margin-bottom:4px">${step.metric}</div>` : ''}
            <details class="exec-inputs">
                <summary class="cursor-pointer select-none">
                    Inputs
                </summary>
                <div class="px-4 py-3 text-sm" style="color:var(--text-secondary);border-top:1px solid var(--purple-border-10)">
                    ${step.input || ''}
                    ${step.inputDetails || ''}
                </div>
            </details>
            <details open class="exec-output">
                <summary class="cursor-pointer select-none">
                    Output
                </summary>
                <div class="px-4 py-3 text-sm space-y-3" style="color:var(--text-secondary);border-top:1px solid var(--purple-border-10)">
                    ${step.output || ''}
                    ${step.details || ''}
                </div>
            </details>
            ${step.subSteps ? renderSubTabs(step.subSteps) : ''}
        </div>
    `;
}

function renderExecutionTabbed(steps, exec) {
    // exec is reserved for future use (e.g. rendering execution-level metadata alongside tabs)
    const tabButtons = steps.map((step, i) => {
        const isFirst = i === 0;
        const baseClass = 'exec-tab flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap border';
        return `<button class="${baseClass}"
                        data-tab="${i}" data-status="${step.status || 'skipped'}" data-active="${isFirst ? 'true' : 'false'}"
                        onclick="switchExecTab(${i})">
                    <span style="opacity:0.6;font-family:'JetBrains Mono',monospace;font-size:10px">${i + 1}</span>
                    <span>${step.shortName || step.name}</span>
                    ${step.metric ? `<span style="font-family:'JetBrains Mono',monospace;opacity:0.8;margin-left:4px;font-size:10px">${escapeHtml(String(step.metric))}</span>` : ''}
                    ${step.status === 'warn' && step.warnReason ? `<span style="opacity:0.75;font-size:10px;margin-left:2px">· ${escapeHtml(step.warnReason)}</span>` : ''}
                </button>`;
    }).join('');

    const panels = steps.map((step, i) => `
        <div class="exec-panel ${i === 0 ? '' : 'hidden'}" data-panel="${i}">
            ${renderStepPanel(step)}
        </div>
    `).join('');

    return `
        <div id="exec-tab-strip" class="sticky top-0 -mx-5 px-5 py-2 mb-4 z-10">
            <div class="flex gap-2 overflow-x-auto pb-1" style="scrollbar-width:none">
                ${tabButtons}
            </div>
        </div>
        <div id="exec-panels">
            ${panels}
        </div>
    `;
}

// COMMENTED OUT: Toggle collapsible content (for long prompts/responses)
// function toggleCollapse(elementId) {
//     const preview = document.getElementById(elementId + '-preview');
//     const full = document.getElementById(elementId + '-full');
//     if (preview && full) {
//         if (full.classList.contains('hidden')) {
//             preview.classList.add('hidden');
//             full.classList.remove('hidden');
//         } else {
//             preview.classList.remove('hidden');
//             full.classList.add('hidden');
//         }
//     }
// }

function toggleLogFullscreen(elementId, buttonId) {
    const logElement = document.getElementById(elementId);
    if (!logElement) return;
    
    const execId = elementId.replace('log-', '');
    const fullscreenIcon = document.getElementById(`log-fullscreen-icon-${execId}`);
    const exitFullscreenIcon = document.getElementById(`log-exit-fullscreen-icon-${execId}`);
    
    if (logElement.classList.contains('log-fullscreen')) {
        // Exit fullscreen
        logElement.classList.remove('log-fullscreen');
        if (fullscreenIcon) fullscreenIcon.classList.remove('hidden');
        if (exitFullscreenIcon) exitFullscreenIcon.classList.add('hidden');
        // Remove from fullscreen stack
        window.fullscreenStack = window.fullscreenStack || [];
        window.fullscreenStack = window.fullscreenStack.filter(el => el !== elementId);
    } else {
        // Enter fullscreen
        logElement.classList.add('log-fullscreen');
        if (fullscreenIcon) fullscreenIcon.classList.add('hidden');
        if (exitFullscreenIcon) exitFullscreenIcon.classList.remove('hidden');
        // Add to fullscreen stack
        window.fullscreenStack = window.fullscreenStack || [];
        window.fullscreenStack.push(elementId);
    }
}

// Trigger Workflow Modal Functions
function showTriggerWorkflowModal() {
    document.getElementById('triggerWorkflowModal').classList.remove('hidden');
    document.getElementById('triggerArticleId').value = '';
    document.getElementById('triggerWorkflowMessage').classList.add('hidden');
    
    // Focus input field after modal is visible
    setTimeout(() => {
        const input = document.getElementById('triggerArticleId');
        if (input) {
            input.focus();
            input.select();
        }
    }, 10);
}

function closeTriggerWorkflowModal() {
    if (window.ModalManager) {
        window.ModalManager.close('triggerWorkflowModal');
    } else {
        document.getElementById('triggerWorkflowModal').classList.add('hidden');
    }
    document.getElementById('triggerArticleId').value = '';
    document.getElementById('triggerWorkflowMessage').classList.add('hidden');
}

async function triggerWorkflow() {
    const articleId = document.getElementById('triggerArticleId').value;
    const messageDiv = document.getElementById('triggerWorkflowMessage');
    
    if (!articleId || parseInt(articleId) < 1) {
        messageDiv.className = 'q-modal-message';
        messageDiv.style.cssText = 'background:rgba(220,38,38,0.12);border:1px solid rgba(220,38,38,0.25);color:var(--badge-red-text)';
        messageDiv.textContent = 'Please enter a valid article ID';
        messageDiv.classList.remove('hidden');
        return;
    }

    try {
        messageDiv.className = 'q-modal-message';
        messageDiv.style.cssText = 'background:rgba(59,130,246,0.12);border:1px solid rgba(59,130,246,0.25);color:var(--badge-blue-text)';
        messageDiv.textContent = 'Triggering workflow...';
        messageDiv.classList.remove('hidden');

        // Always use Celery (fast, production mode) - no LangGraph server option
        const response = await fetch(`/api/workflow/articles/${articleId}/trigger?use_langgraph_server=false&force=true`, {
            method: 'POST'
        });

        if (response.ok) {
            const data = await response.json();
            messageDiv.className = 'q-modal-message';
            messageDiv.style.cssText = 'background:rgba(22,163,74,0.12);border:1px solid rgba(22,163,74,0.25);color:var(--badge-green-text)';
            messageDiv.innerHTML = `Workflow triggered — Execution <strong style="color:var(--text-primary)">#${data.execution_id}</strong> created. Refreshing...`;

            // Close modal after 2 seconds and refresh executions
            setTimeout(() => {
                closeTriggerWorkflowModal();
                loadExecutions();
            }, 2000);
        } else {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            messageDiv.className = 'q-modal-message';
            messageDiv.style.cssText = 'background:rgba(220,38,38,0.12);border:1px solid rgba(220,38,38,0.25);color:var(--badge-red-text)';
            messageDiv.textContent = `Error: ${errorData.detail || 'Failed to trigger workflow'}`;
        }
    } catch (error) {
        messageDiv.className = 'q-modal-message';
        messageDiv.style.cssText = 'background:rgba(220,38,38,0.12);border:1px solid rgba(220,38,38,0.25);color:var(--badge-red-text)';
        messageDiv.textContent = `Error: ${error.message}`;
    }
}


// Close modal when clicking outside
const executionModal = document.getElementById('executionModal');
if (executionModal) {
    executionModal.addEventListener('click', function(e) {
        if (e.target === this) {
            closeModal();
        }
    });
}

// Close modal with ESC key - handles nested fullscreen windows
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const executionModal = document.getElementById('executionModal');
        const triggerModal = document.getElementById('triggerWorkflowModal');
        
        // Check if execution modal is open
        if (executionModal && !executionModal.classList.contains('hidden')) {
            const modalContent = document.getElementById('executionModalContent');
            window.fullscreenStack = window.fullscreenStack || [];
            
            // First, check if log is fullscreen (most nested)
            if (window.fullscreenStack.length > 0) {
                const lastElementId = window.fullscreenStack[window.fullscreenStack.length - 1];
                
                if (lastElementId && lastElementId.startsWith('log-')) {
                    // Shrink log fullscreen
                    toggleLogFullscreen(lastElementId, null);
                    e.preventDefault();
                    return;
                }
            }
            
            // Check if modal itself is fullscreen
            if (modalContent && modalContent.classList.contains('modal-fullscreen')) {
                // Exit modal fullscreen, but don't close modal
                toggleModalFullscreen();
                e.preventDefault();
                return;
            }
            
            // If modal is not fullscreen, close it
            closeModal();
        } else if (triggerModal && !triggerModal.classList.contains('hidden')) {
            closeTriggerWorkflowModal();
        }
    }
});

function filterExecutions() {
    _execPage = 1;
    loadExecutions();
}

function changeExecutionPage(delta) {
    _execPage = Math.max(1, _execPage + delta);
    loadExecutions();
}

async function triggerStuckExecutions() {
    const btn = document.getElementById('triggerStuckBtn');
    const originalText = btn.textContent;
    
    if (!await ModalManager.confirm('Trigger all stuck pending executions? This will bypass Celery and run them directly.', { title: 'Trigger Stuck', confirmText: 'Trigger All', confirmClass: 'bg-orange-600 hover:bg-orange-700', cancelText: 'Cancel' })) {
        return;
    }
    
    btn.disabled = true;
    btn.textContent = '⏳ Processing...';
    
    try {
        const response = await fetch('/api/workflow/executions/trigger-stuck', { method: 'POST' });
        const data = await response.json();
        
        if (response.ok) {
            if (data.count === 0) {
                showNotification('No pending executions found.', 'success');
            } else {
                const message = `✅ Triggered ${data.count} execution(s)\n\n` +
                              `Successful: ${data.successful}\n` +
                              `Failed: ${data.failed}`;
                showNotification(message, 'info');
            }
            await loadExecutions();
        } else {
            showNotification('Error: ' + (data.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error triggering stuck executions:', error);
        showNotification('Error triggering stuck executions: ' + error.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

async function cleanupStaleExecutions() {
    if (!await ModalManager.confirm('Mark all running or pending executions older than 15 minutes as failed?', { title: 'Cleanup Stale', confirmText: 'Mark Failed', confirmClass: 'bg-orange-600 hover:bg-orange-700', cancelText: 'Cancel' })) {
        return;
    }
    
    try {
        const response = await fetch('/api/workflow/executions/cleanup-stale?max_age_hours=0.25', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            showNotification('Cleanup failed: ' + (errorData.detail || 'Unknown error'), 'error');
            return;
        }
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(result.message, 'success');
            refreshExecutions(); // Refresh the list
        } else {
            showNotification('Cleanup failed: ' + (result.message || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Cleanup error:', error);
        showNotification('Error cleaning up stale executions: ' + error.message, 'error');
    }
}

async function cancelAllRunningExecutions() {
    if (!await ModalManager.confirm('Cancel all running or pending executions? This will mark them as failed.', { title: 'Cancel All', confirmText: 'Cancel All', confirmClass: 'bg-red-600 hover:bg-red-700', cancelText: 'Cancel' })) {
        return;
    }
    
    try {
        const response = await fetch('/api/workflow/executions/cancel-all-running', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            showNotification('Cancel failed: ' + (errorData.detail || 'Unknown error'), 'error');
            return;
        }
        
        const result = await response.json();
        
        if (result.success) {
            showNotification(result.message, 'success');
            refreshExecutions(); // Refresh the list
        } else {
            showNotification('Cancel failed: ' + (result.message || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Cancel error:', error);
        showNotification('Error cancelling executions: ' + error.message, 'error');
    }
}

function refreshExecutions() {
    loadExecutions();
}
