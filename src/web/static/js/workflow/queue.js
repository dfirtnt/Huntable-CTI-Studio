// Workflow — SIGMA review queue module.
//
// Extracted verbatim from src/web/templates/workflow.html (formerly lines
// 10533-13643). Loaded as a classic script AFTER workflow.html's main inline
// block, which still declares the `queue` array it reads, and BEFORE the
// sigma-queue column-resize block that wraps `window.loadQueue`.
//
// Note the queue state declared here (`currentRuleId`, `isEditMode`,
// `pendingPreviewId`, `queuePage`, ...) is still read by code left inline —
// similar-rules, filterQueue, checkAndTriggerPreview — and by the
// `onclick="approveRule(currentRuleId)"` handlers in the rule modal markup.
// These stay global lexical bindings, so those references resolve unchanged.

// Queue Functions
let currentRuleId = null;
let isEditMode = false;
let isCreateMode = false; // true while authoring a brand-new "from scratch" draft in the rule modal
let currentEnrichedYaml = null; // Track current enriched state for iterative enrichment
let enrichIteration = 0; // Track number of enrichment iterations
let originalYaml = '';
let editedYaml = '';
let pendingPreviewId = null; // Track previewId from URL while data loads
let queuePage = 1;
let queueTotal = 0;
let queueLimit = 50;
let queueSelectedIds = new Set();

// ── Bulk selection helpers ───────────────────────────────────────────────────

function toggleQueueRow(id, checked) {
    if (checked) queueSelectedIds.add(id); else queueSelectedIds.delete(id);
    const row = document.getElementById('queue-row-' + id);
    if (row) row.classList.toggle('q-row-selected', checked);
    _syncQueueSelectAll();
    _updateQueueBulkBar();
}

function toggleAllQueueRows(checked) {
    _qSortedQueue().forEach(r => { if (checked) queueSelectedIds.add(r.id); else queueSelectedIds.delete(r.id); });
    renderQueue();
}

function _syncQueueSelectAll() {
    const cb = document.getElementById('queueSelectAll');
    if (!cb) return;
    const pageIds = _qSortedQueue().map(r => r.id);
    const allChecked = pageIds.length > 0 && pageIds.every(id => queueSelectedIds.has(id));
    const someChecked = pageIds.some(id => queueSelectedIds.has(id));
    cb.checked = allChecked;
    cb.indeterminate = !allChecked && someChecked;
}

function _updateQueueBulkBar() {
    const bar = document.getElementById('queueBulkBar');
    const counter = document.getElementById('queueBulkCount');
    if (!bar || !counter) return;
    const n = queueSelectedIds.size;
    bar.classList.toggle('hidden', n === 0);
    counter.textContent = n + ' selected';
}

function clearQueueSelection() {
    queueSelectedIds.clear();
    renderQueue();
}

async function bulkApprove() {
    const ids = [...queueSelectedIds];
    if (!ids.length) return;
    if (!await ModalManager.confirm('Approve ' + ids.length + ' rule(s)?', { title: 'Approve Rules', confirmText: 'Approve', confirmClass: 'bg-emerald-600 hover:bg-emerald-700', cancelText: 'Cancel' })) return;
    await _sendQueueBulkAction({ ids, action: 'approve' });
}

async function bulkReject() {
    const ids = [...queueSelectedIds];
    if (!ids.length) return;
    const notes = await ModalManager.prompt('Rejection reason for ' + ids.length + ' rule(s) (optional):', '', { title: 'Reject Rules', confirmText: 'Reject', confirmClass: 'bg-red-600 hover:bg-red-700', cancelText: 'Cancel', placeholder: 'Optional rejection reason' });
    if (notes === null) return;
    await _sendQueueBulkAction({ ids, action: 'reject', review_notes: notes || null });
}

async function bulkDelete() {
    const ids = [...queueSelectedIds];
    if (!ids.length) return;
    if (!await ModalManager.confirm('Permanently delete ' + ids.length + ' rule(s)? This cannot be undone.', { title: 'Delete Rules', confirmText: 'Delete', confirmClass: 'bg-red-600 hover:bg-red-700', cancelText: 'Cancel' })) return;
    await _sendQueueBulkAction({ ids, action: 'delete' });
}

async function _sendQueueBulkAction(payload) {
    try {
        const res = await fetch('/api/sigma-queue/bulk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            const result = await res.json();
            const label = payload.action === 'delete' ? 'Deleted' : payload.action === 'approve' ? 'Approved' : 'Rejected';
            showNotification(label + ' ' + result.updated + ' rule(s)', 'success');
            queueSelectedIds.clear();
            await loadQueue();
        } else {
            const err = await res.json().catch(() => ({}));
            showNotification('Bulk action failed: ' + (err.detail || 'Unknown error'), 'error');
        }
    } catch (e) {
        showNotification('Bulk action error: ' + e.message, 'error');
    }
}

async function deleteQueueRule(ruleId) {
    if (!await ModalManager.confirm('Delete this rule? This cannot be undone.', { title: 'Delete Rule', confirmText: 'Delete', confirmClass: 'bg-red-600 hover:bg-red-700', cancelText: 'Cancel' })) return;
    try {
        const res = await fetch('/api/sigma-queue/' + ruleId, { method: 'DELETE' });
        if (res.ok) {
            showNotification('Rule deleted', 'success');
            queueSelectedIds.delete(ruleId);
            await loadQueue();
        } else {
            const err = await res.json().catch(() => ({}));
            showNotification('Delete failed: ' + (err.detail || 'Unknown error'), 'error');
        }
    } catch (e) {
        showNotification('Delete error: ' + e.message, 'error');
    }
}

// ── End bulk selection ───────────────────────────────────────────────────────

function getQueueStatusBadge(status) {
    const known = ['pending', 'approved', 'rejected', 'submitted', 'needs_review'];
    const cls = known.includes(status) ? status : '';
    const label = status ? status.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) : 'Unknown';
    return `<span class="q-badge ${cls}">${label}</span>`;
}

function formatQueuePlatformLabel(platform) {
    const value = Array.isArray(platform) ? platform.find(Boolean) : platform;
    if (!value) return '';
    const normalized = String(value).trim().toLowerCase();
    const labels = {
        windows: 'Windows',
        linux: 'Linux',
        macos: 'macOS',
        unknown: 'Unknown',
        cross: 'Cross-platform',
        'cross-platform': 'Cross-platform',
    };
    return labels[normalized] || String(value).trim();
}

function getQueuePlatformBadge(metadata) {
    const label = formatQueuePlatformLabel(metadata?.platform);
    if (!label) return '';
    return `<span class="q-badge platform">${escapeHtml(label)}</span>`;
}

function getObservablesUsedCount(rule) {
    const list = rule?.rule_metadata?.observables_used;
    if (!Array.isArray(list) || list.length === 0) return 0;

    const unique = new Set();
    for (const idx of list) {
        if (Number.isInteger(idx) && idx >= 0) unique.add(idx);
    }
    return unique.size;
}

async function loadQueue() {
    try {
        const statusFilterEl = document.getElementById('queueStatusFilter');
        const statusFilter = statusFilterEl ? statusFilterEl.value : '';
        const offset = (queuePage - 1) * queueLimit;
        const params = new URLSearchParams({ limit: String(queueLimit), offset: String(offset) });
        if (statusFilter) params.set('status', statusFilter);

        // Deep-link job filter: ?jobId=<workflow execution id> narrows the queue
        // to only the rules produced by that job (e.g. from the executions tab's
        // "N rule(s) queued for review" link).
        const jobIdRaw = getURLParameter('jobId');
        let jobId = null;
        if (jobIdRaw && /^\d+$/.test(jobIdRaw)) {
            jobId = parseInt(jobIdRaw, 10);
            params.set('workflow_execution_id', String(jobId));
        } else if (jobIdRaw) {
            // Non-numeric jobId is not a valid job reference; drop it.
            removeURLParameter('jobId');
        }
        updateQueueJobFilterBar(jobId);
        const url = `/api/sigma-queue/list?${params.toString()}`;

        const response = await fetch(url);
        if (response.ok) {
            const data = await response.json();
            queue = data.items || data;   // API may return {items:[...]} or bare array
            queueTotal = data.total != null ? data.total : queue.length;
            if (data.limit != null) queueLimit = data.limit;
            renderQueue();
            updateQueueStats(data.status_counts || null);
            updateQueuePagination();
            // Check if we need to trigger preview from URL parameter
            checkAndTriggerPreview();
        } else {
            console.error('Failed to load queue:', response.status, response.statusText);
            const tbody = document.getElementById('queueTableBody');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="10" class="px-6 py-4 text-center text-red-500">Error loading queue</td></tr>';
            }
        }
    } catch (error) {
        console.error('Error loading queue:', error);
        const tbody = document.getElementById('queueTableBody');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="10" class="px-6 py-4 text-center text-red-500">Error: ' + error.message + '</td></tr>';
        }
    }
}

// --- Queue column sort state ---
let _qSortKey = null;
let _qSortAsc = true;

(function initQueueSortHeaders() {
    document.querySelectorAll('.q-sortable[data-sort-key]').forEach(th => {
        th.addEventListener('click', () => {
            const key = th.dataset.sortKey;
            if (_qSortKey === key) {
                _qSortAsc = !_qSortAsc;
            } else {
                _qSortKey = key;
                _qSortAsc = (key === 'article_title' || key === 'rule_title' || key === 'status');
            }
            renderQueue();
        });
    });
})();

function _qSortVal(rule, key) {
    switch (key) {
        case 'id': return rule.id;
        case 'article_title': return (rule.article_title || '').toLowerCase();
        case 'rule_title': return ((rule.rule_metadata || {}).title || '').toLowerCase();
        case 'obs_used': return getObservablesUsedCount(rule);
        case 'workflow_execution_id': return Number.isInteger(rule.workflow_execution_id) ? rule.workflow_execution_id : -1;
        case 'max_similarity': return typeof rule.max_similarity === 'number' ? rule.max_similarity : -1;
        case 'status': return rule.status || '';
        case 'created_at': return rule.created_at || '';
        default: return '';
    }
}

function _qSortedQueue() {
    if (!_qSortKey) return queue;
    return [...queue].sort((a, b) => {
        const va = _qSortVal(a, _qSortKey);
        const vb = _qSortVal(b, _qSortKey);
        let cmp;
        if (typeof va === 'number' && typeof vb === 'number') {
            cmp = va - vb;
        } else {
            cmp = String(va).localeCompare(String(vb), undefined, {sensitivity: 'base'});
        }
        return _qSortAsc ? cmp : -cmp;
    });
}

function _updateQSortIndicators() {
    document.querySelectorAll('.q-sortable[data-sort-key]').forEach(th => {
        const ind = th.querySelector('.q-sort-ind');
        if (!ind) return;
        ind.textContent = (th.dataset.sortKey === _qSortKey) ? (_qSortAsc ? ' \u25B2' : ' \u25BC') : '';
    });
}

function renderQueue() {
    const tbody = document.getElementById('queueTableBody');
    if (!tbody) {
        console.error('queueTableBody element not found');
        return;
    }
    _updateQSortIndicators();
    
    if (queue.length === 0) {
        tbody.innerHTML = '<tr><td colspan="11" style="padding:24px;text-align:center;color:var(--text-muted-slate)">No queued rules found</td></tr>';
        // Check if we need to trigger preview from URL parameter even with empty queue
        checkAndTriggerPreview();
        return;
    }

    /* Pre-existing innerHTML pattern -- all values from own DB, not user input. */
    tbody.innerHTML = _qSortedQueue().map(rule => {
        const metadata = rule.rule_metadata || {};
        const title = metadata.title || 'Untitled Rule';
        const observablesUsedCount = getObservablesUsedCount(rule);
        const isSelected = queueSelectedIds.has(rule.id);
        const platformBadge = getQueuePlatformBadge(metadata);
        const rowClass = isSelected ? ' class="q-row-selected"' : '';
        const checked = isSelected ? ' checked' : '';
        const canActOn = (rule.status === 'pending' || rule.status === 'needs_review');
        const inlineActions = canActOn
            ? `<button onclick="approveRule(${rule.id})" class="q-action approve">Approve</button><button onclick="rejectRule(${rule.id})" class="q-action reject">Reject</button>`
            : '';
        const deleteIcon = `<svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0"/></svg>`;

        return `
            <tr id="queue-row-${rule.id}" data-status="${rule.status || ''}"${rowClass}>
                <td class="q-checkbox-cell"><input type="checkbox" class="q-row-checkbox"${checked} onchange="toggleQueueRow(${rule.id}, this.checked)"></td>
                <td class="q-status-indicator-cell" aria-hidden="true"></td>
                <td class="q-cell-id" style="padding-left:24px">${rule.id}</td>
                <td class="q-cell-article">
                    ${rule.article_id
                        ? `<a href="/articles/${rule.article_id}" title="${((rule.article_title || 'Article ' + rule.article_id) + '').replace(/"/g, '&quot;')}">${rule.article_title || 'Article ' + rule.article_id}</a>`
                        : `<span class="italic" style="color: var(--text-muted-slate)">Manual draft</span>`}
                </td>
                <td class="q-cell-title" title="${escapeHtml(title)}">
                    <span class="q-title-primary">${escapeHtml(title)}</span>
                    ${platformBadge}
                </td>
                <td class="q-cell-obs">${observablesUsedCount}</td>
                <td class="q-cell-job">
                    ${Number.isInteger(rule.workflow_execution_id) ? `<a href="#executions" onclick="switchTab('executions'); setTimeout(() => viewExecution(${rule.workflow_execution_id}), 100); return false;" title="Open workflow job ${rule.workflow_execution_id}">${rule.workflow_execution_id}</a>` : '-'}
                </td>
                <td class="q-cell-sim">
                    ${typeof rule.max_similarity === 'number' ? (rule.max_similarity * 100).toFixed(1) + '%' : '-'}
                </td>
                <td>${getQueueStatusBadge(rule.status)}</td>
                <td class="q-cell-date">${formatLocalDateTime(rule.created_at)}</td>
                <td><div class="q-actions-cell">
                    <button onclick="previewRule(${rule.id})" class="q-action preview">Preview</button>${inlineActions}<button onclick="deleteQueueRule(${rule.id})" class="q-action delete" title="Delete">${deleteIcon}</button>
                </div></td>
            </tr>
        `;
    }).join('');

    _syncQueueSelectAll();
    _updateQueueBulkBar();
    // Check if we need to trigger preview from URL parameter after rendering
    checkAndTriggerPreview();
}

function updateQueueStats(statusCounts) {
    const counts = statusCounts || {};
    const get = (k) => counts[k] != null ? counts[k] : (queue || []).filter(r => r.status === k).length;

    const pendingEl = document.getElementById('pendingCount');
    const approvedEl = document.getElementById('approvedCount');
    const rejectedEl = document.getElementById('rejectedCount');
    const submittedEl = document.getElementById('submittedCount');

    if (pendingEl) pendingEl.textContent = get('pending');
    if (approvedEl) approvedEl.textContent = get('approved');
    if (rejectedEl) rejectedEl.textContent = get('rejected');
    if (submittedEl) submittedEl.textContent = get('submitted');

    // Reflect active filter on stat cards
    const activeFilter = (document.getElementById('queueStatusFilter') || {}).value || '';
    document.querySelectorAll('#queueStats .q-stat-card').forEach(card => {
        const cardStatus = card.dataset.filterStatus || '';
        card.classList.toggle('q-stat-card--active', cardStatus === activeFilter && activeFilter !== '');
    });
}

function updateQueuePagination() {
    const bar = document.getElementById('queuePaginationBar');
    if (!bar) return;
    const start = queueTotal === 0 ? 0 : (queuePage - 1) * queueLimit + 1;
    const end = Math.min(queuePage * queueLimit, queueTotal);
    const totalPages = Math.max(1, Math.ceil(queueTotal / queueLimit));
    bar.innerHTML = `
        <span class="text-sm text-gray-600 dark:text-gray-400">Showing ${start}&ndash;${end} of ${queueTotal}</span>
        <div class="flex gap-2">
            <button type="button" onclick="goToQueuePage(${queuePage - 1})" ${queuePage <= 1 ? 'disabled' : ''} class="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed">Prev</button>
            <button type="button" onclick="goToQueuePage(${queuePage + 1})" ${queuePage >= totalPages ? 'disabled' : ''} class="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 disabled:opacity-50 disabled:cursor-not-allowed">Next</button>
        </div>
    `;
}

function goToQueuePage(pageNum) {
    const totalPages = Math.max(1, Math.ceil(queueTotal / queueLimit));
    if (pageNum < 1 || pageNum > totalPages) return;
    queuePage = pageNum;
    loadQueue();
}

// Show/hide the "viewing a single job" banner on the queue page. Called from
// loadQueue() so every reload (tab switch, refresh, pagination, status filter,
// auto-refresh) reflects the current ?jobId= param.
function updateQueueJobFilterBar(jobId) {
    const bar = document.getElementById('queueJobFilterBar');
    if (!bar) return;
    if (jobId === null) {
        bar.classList.add('hidden');
        return;
    }
    const idEl = document.getElementById('queueJobFilterId');
    if (idEl) idEl.textContent = String(jobId);
    bar.classList.remove('hidden');
}

// Clear the ?jobId= deep-link filter and reload the full queue.
function clearQueueJobFilter() {
    removeURLParameter('jobId');
    queuePage = 1;
    updateQueueJobFilterBar(null);
    loadQueue();
}

var cachedObservablesForRulePreview = null;

// --- Author a brand-new "from scratch" SIGMA rule ---------------------------

function ruleSkeletonYaml(author) {
    // Skeleton draft: title, description, author, status, logsource, detection.
    // Indented with 4 spaces to match standard Sigma YAML indentation conventions; the user edits this in place.
    return [
        'title: Place draft rule title here',
        'description: Place a short description of what this rule detects here',
        'status: experimental',
        'author: ' + author,
        'logsource:',
        '    product: windows',
        '    category: process_creation',
        'detection:',
        '    selection:',
        "        # Place your detection fields here, for example:",
        "        # Image|endswith: '\\\\example.exe'",
        "        # CommandLine|contains: 'suspicious-string'",
        '    condition: selection',
        ''
    ].join('\n');
}

async function createNewRule() {
    isCreateMode = true;
    isEditMode = false;
    currentRuleId = null;
    originalYaml = '';
    editedYaml = '';
    resetQualityReviewCard();

    // Default the author from Settings (sigmaAuthor) when available.
    let author = 'Huntable CTI Studio User';
    try {
        const r = await fetch('/api/settings');
        if (r.ok) {
            const d = await r.json();
            const s = d.settings || {};
            if (s.sigmaAuthor && String(s.sigmaAuthor).trim()) author = String(s.sigmaAuthor).trim();
        }
    } catch (e) { /* fall back to default author */ }

    pushModal('ruleModal', false);
    renderCreateRuleForm(author);
}

function renderCreateRuleForm(author) {
    const titleEl = document.getElementById('ruleModalTitle');
    if (titleEl) titleEl.textContent = 'Create New SIGMA Rule';

    const skeleton = ruleSkeletonYaml(author);
    document.getElementById('rulePreviewContent').innerHTML = `
        <div class="space-y-4 text-gray-600 dark:text-gray-300">
            <p class="text-sm italic text-gray-400">Place your draft rule here. Edit the skeleton below &mdash; fill in the title, description, author, status, log source, and detection &mdash; then save it to the queue.</p>
            <div>
                <h4 class="font-semibold mb-2">Rule YAML:</h4>
                <textarea id="createYamlEditor" class="w-full bg-gray-100 dark:bg-gray-900 p-4 rounded border border-gray-300 dark:border-gray-600 font-mono text-xs text-gray-600 dark:text-gray-300" rows="22" style="font-family: 'JetBrains Mono', monospace;">${escapeHtml(skeleton)}</textarea>
            </div>
            <div id="createRuleError" class="hidden p-3 bg-red-50 dark:bg-red-900 border border-red-200 dark:border-red-700 rounded text-sm text-red-700 dark:text-red-300"></div>
        </div>
    `;
    updateActionButtons();
    setTimeout(() => {
        const editor = document.getElementById('createYamlEditor');
        if (editor) editor.focus();
    }, 100);
}

async function saveNewRule() {
    const editor = document.getElementById('createYamlEditor');
    const errEl = document.getElementById('createRuleError');
    const showError = (msg) => {
        if (errEl) { errEl.textContent = msg; errEl.classList.remove('hidden'); }
    };
    if (!editor) return;

    const yamlText = editor.value.trim();
    if (!yamlText) {
        showError('Rule YAML cannot be empty.');
        return;
    }

    try {
        const response = await fetch('/api/sigma-queue/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rule_yaml: yamlText })
        });
        const data = await response.json().catch(() => ({}));
        if (response.ok && data.success) {
            isCreateMode = false;
            showNotification('Draft rule added to queue', 'success');
            // Refresh the queue so the saved row is available, then transition this
            // same modal into the standard Preview of the new rule. Validate / Enrich /
            // Similarity Search / Approve all act on a saved queue ID, so they only
            // become available once the draft has been persisted.
            queuePage = 1;
            const statusFilterEl = document.getElementById('queueStatusFilter');
            if (statusFilterEl && statusFilterEl.value) statusFilterEl.value = ''; // ensure the new pending row is visible
            await loadQueue();
            const saved = queue.find(r => r.id === data.queue_id);
            if (saved) {
                // In-place transition (modal already open): mirror previewRule() without re-pushing.
                currentRuleId = data.queue_id;
                isEditMode = false;
                originalYaml = saved.rule_yaml;
                editedYaml = saved.rule_yaml;
                const titleEl = document.getElementById('ruleModalTitle');
                if (titleEl) titleEl.textContent = 'SIGMA Rule Preview';
                updateURLParameter('previewId', data.queue_id);
                renderRulePreview(saved);
            } else {
                closeRuleModal();
            }
        } else {
            const msg = data.detail || 'Failed to add rule to queue';
            showError(typeof msg === 'string' ? msg : JSON.stringify(msg));
        }
    } catch (e) {
        showError('Network error: ' + e.message);
    }
}

// Validate / Enrich / Similarity Search all act on a saved queue ID. From the
// create modal, persist the draft first (which transitions the modal into the
// standard Preview), then run the requested action against the saved rule.
async function createThenRun(action) {
    await saveNewRule();
    if (isCreateMode || !currentRuleId) return; // save failed; error already shown in-modal
    if (action === 'validate') validateRule();
    else if (action === 'enrich') openEnrichModal();
    else if (action === 'similar') checkSimilarRulesForQueue();
}

async function previewRule(ruleId) {
    const rule = queue.find(r => r.id === ruleId);
    if (!rule) return;
    
    currentRuleId = ruleId;
    isEditMode = false;
    isCreateMode = false;
    originalYaml = rule.rule_yaml;
    editedYaml = rule.rule_yaml;
    const titleEl = document.getElementById('ruleModalTitle');
    if (titleEl) titleEl.textContent = 'SIGMA Rule Preview';
    resetQualityReviewCard();
    
    // Update URL with previewId parameter
    updateURLParameter('previewId', ruleId);
    
    pushModal('ruleModal', false); // Don't hide previous, rule modal is base level
    cachedObservablesForRulePreview = null;
    if (rule.workflow_execution_id) {
        try {
            const obsRes = await fetch(`/api/workflow/executions/${rule.workflow_execution_id}/observables`);
            if (obsRes.ok) cachedObservablesForRulePreview = await obsRes.json();
        } catch (e) { console.warn('Observables fetch failed', e); }
    }
    renderRulePreview(rule, cachedObservablesForRulePreview);
}

async function seedValidateAgentLabel() {
    const label = document.getElementById('validateAgentLabel');
    if (!label) return;
    let agentModels = (typeof currentConfig !== 'undefined' && currentConfig?.agent_models) ? currentConfig.agent_models : null;
    if (!agentModels) {
        try {
            const res = await fetch('/api/workflow/config');
            if (res.ok) {
                const cfg = await res.json();
                agentModels = cfg.agent_models || {};
            }
        } catch (e) {
            return;
        }
    }
    const provider = (agentModels['SigmaAgent_provider'] || getDefaultProvider()).toLowerCase();
    const model = (agentModels['SigmaAgent'] || '').trim();
    const display = model ? `${provider} / ${model}` : provider;
    label.textContent = display;
    label.title = `SigmaAgent provider: ${provider}, model: ${model || '(default)'}`;
}

function renderRulePreview(rule, observablesData) {
    observablesData = observablesData ?? cachedObservablesForRulePreview;
    const metadata = rule.rule_metadata || {};
    const similarityScores = rule.similarity_scores || [];
    const platformBadge = getQueuePlatformBadge(metadata);
    
    // Populate the Sigma agent label from workflow config (Validate always uses the workflow Sigma agent LLM)
    setTimeout(() => seedValidateAgentLabel(), 100);
    
    let similarRulesHtml = '';
    if (similarityScores.length > 0) {
        similarRulesHtml = `
            <div class="mt-4">
                <details class="border border-gray-600 rounded-lg">
                    <summary class="cursor-pointer px-3 py-2 font-semibold text-gray-300">Similar Existing Rules (${similarityScores.length})</summary>
                    <ul class="list-disc list-inside space-y-1 text-gray-600 dark:text-gray-300 px-3 pb-3 mt-2">
                        ${similarityScores.slice(0, 5).map(s => `
                            <li>${s.title || s.rule_id} (${(s.similarity * 100).toFixed(1)}% similar)</li>
                        `).join('')}
                    </ul>
                </details>
            </div>
        `;
    }
    
    const yamlSection = isEditMode ? `
        <div class="mt-4">
            <div class="flex justify-between items-center mb-2">
                <h4 class="font-semibold">Rule YAML:</h4>
                <button onclick="cancelEdit()" class="text-sm text-gray-400 hover:text-gray-200">
                    Cancel
                </button>
            </div>
            <textarea id="yamlEditor" class="w-full bg-gray-100 dark:bg-gray-900 p-4 rounded border border-gray-300 dark:border-gray-600 font-mono text-xs text-gray-600 dark:text-gray-300" rows="20" style="font-family: 'JetBrains Mono', monospace;">${escapeHtml(editedYaml)}</textarea>
        </div>
    ` : `
        <div class="mt-4">
            <div class="flex justify-between items-center mb-2">
                <h4 class="font-semibold">Rule YAML:</h4>
                <button onclick="enableEditMode()" class="text-sm text-blue-600 hover:text-blue-800 dark:text-blue-400">
                    ✏️ Edit
                </button>
            </div>
            <pre class="bg-gray-100 dark:bg-gray-900 p-4 rounded overflow-x-auto text-xs text-gray-600 dark:text-gray-300"><code id="ruleYamlCode">${escapeHtml(editedYaml)}</code></pre>
        </div>
    `;
    
    const content = `
        <div class="space-y-4 text-gray-600 dark:text-gray-300">
            <div><strong>Rule ID:</strong> ${rule.id}</div>
            ${platformBadge ? `<div><strong>Platform:</strong> ${platformBadge}</div>` : ''}
            <div><strong>Article:</strong> ${rule.article_id ? `<a href="/articles/${rule.article_id}" class="text-purple-600">${escapeHtml(rule.article_title || 'Article ' + rule.article_id)}</a>` : '<span class="italic" style="color: var(--text-muted-slate)">None (hand-authored draft)</span>'}</div>
            ${Number.isInteger(rule.workflow_execution_id) ? `<div><strong>Job:</strong> <a href="#executions" class="text-purple-600" onclick="closeModal(); switchTab('executions'); setTimeout(() => viewExecution(${rule.workflow_execution_id}), 100); return false;" title="Open workflow execution ${rule.workflow_execution_id}">Execution #${rule.workflow_execution_id}</a></div>` : ''}
            <div><strong>Max Similarity:</strong> ${typeof rule.max_similarity === 'number' ? (rule.max_similarity * 100).toFixed(1) + '%' : 'N/A'}</div>
            ${similarRulesHtml}
            ${observablesUsedSection(rule, observablesData)}
            ${yamlSection}
        </div>
    `;
    
    document.getElementById('rulePreviewContent').innerHTML = content;
    updateActionButtons();
}

function enableEditMode() {
    isEditMode = true;
    const rule = queue.find(r => r.id === currentRuleId);
    if (rule) {
        renderRulePreview(rule);
        setTimeout(() => {
            const editor = document.getElementById('yamlEditor');
            if (editor) {
                editor.focus();
            }
        }, 100);
    }
}

function cancelEdit() {
    isEditMode = false;
    editedYaml = originalYaml;
    const rule = queue.find(r => r.id === currentRuleId);
    if (rule) {
        renderRulePreview(rule);
    }
}

function saveYamlEdit() {
    const editor = document.getElementById('yamlEditor');
    if (!editor) return;
    
    editedYaml = editor.value;
    isEditMode = false;
    const rule = queue.find(r => r.id === currentRuleId);
    if (rule) {
        renderRulePreview(rule);
    }
}

/**
 * Returns the current rule YAML as shown/edited in the rule preview modal.
 * Use this before Validate, Enrich, or Similarity Search so actions use in-modal content.
 */
function getCurrentRuleYamlFromModal() {
    if (isEditMode) {
        const editor = document.getElementById('yamlEditor');
        return editor ? editor.value : editedYaml;
    }
    // View mode: prefer DOM content in case editedYaml is stale
    const codeEl = document.getElementById('ruleYamlCode');
    if (codeEl && codeEl.textContent && codeEl.textContent.trim()) {
        return codeEl.textContent;
    }
    return editedYaml;
}

function updateActionButtons() {
    const buttonContainer = document.getElementById('actionButtons');
    if (!buttonContainer) return;

    if (isCreateMode) {
        buttonContainer.innerHTML = `
            <button id="createSaveBtn" onclick="saveNewRule()" class="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-md">
                <svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg> Save to Queue
            </button>
            <button onclick="createThenRun('validate')" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md" title="Saves the draft to the queue, then validates it with the Sigma agent.">
                <svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5"/></svg> Validate Rule
            </button>
            <button onclick="createThenRun('enrich')" class="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md" title="Saves the draft to the queue, then opens AI enrichment.">
                <svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z"/></svg> Enrich
            </button>
            <button onclick="createThenRun('similar')" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md" title="Saves the draft to the queue, then searches for similar rules.">
                <svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/></svg> Similarity Search
            </button>
            <button onclick="closeRuleModal()" class="px-4 py-2 border border-gray-600 hover:bg-gray-800 text-gray-300 rounded-lg">
                Cancel
            </button>
        `;
        return;
    }

    if (isEditMode) {
        buttonContainer.innerHTML = `
            <button onclick="saveYamlEdit()" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md">
                💾 Save Changes
            </button>
            <button onclick="cancelEdit()" class="px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-md">
                Cancel Edit
            </button>
        `;
    } else {
        buttonContainer.innerHTML = `
            <button onclick="approveRule(currentRuleId)" class="px-4 py-2 btn-workflow text-white rounded-md">
                ✅ Approve
            </button>
            <button onclick="rejectRule(currentRuleId)" class="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-md">
                ❌ Reject
            </button>
            <button onclick="validateRule()" class="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md" title="Validate using the Sigma agent from the active workflow config (same LLM and API keys as in Workflow).">
                ✓ Validate Rule
            </button>
            <button onclick="openEnrichModal()" class="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-md">
                ✨ Enrich
            </button>
            <button onclick="checkSimilarRulesForQueue()" class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md">
                🔍 Similarity Search
            </button>
            <button onclick="closeRuleModal()" class="px-4 py-2 border border-gray-600 hover:bg-gray-800 text-gray-300 rounded-lg">
                Cancel
            </button>
        `;
    }
}

async function approveRule(ruleId) {
    if (!await ModalManager.confirm('Approve this rule for PR submission?', { title: 'Approve Rule', confirmText: 'Approve', confirmClass: 'bg-emerald-600 hover:bg-emerald-700', cancelText: 'Cancel' })) return;
    try {
        // Save any pending edits first
        if (isEditMode) {
            saveYamlEdit();
        }
        
        const payload = { status: 'approved' };
        // Include edited YAML if it differs from original
        if (editedYaml !== originalYaml) {
            payload.rule_yaml = editedYaml;
        }
        
        const response = await fetch(`/api/sigma-queue/${ruleId}/approve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            showNotification('Rule approved successfully', 'success');
            closeRuleModal();
            await loadQueue();
        } else {
            const error = await response.json();
            showNotification('Error approving rule: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error approving rule:', error);
        showNotification('Error approving rule', 'error');
    }
}

async function rejectRule(ruleId) {
    const notes = await ModalManager.prompt('Rejection reason (optional):', '', { title: 'Reject Rule', confirmText: 'Reject', confirmClass: 'bg-red-600 hover:bg-red-700', cancelText: 'Cancel', placeholder: 'Optional rejection reason' });
    
    try {
        // Save any pending edits first
        if (isEditMode) {
            saveYamlEdit();
        }
        
        const payload = { review_notes: notes || null };
        // Include edited YAML if it differs from original
        if (editedYaml !== originalYaml) {
            payload.rule_yaml = editedYaml;
        }
        
        const response = await fetch(`/api/sigma-queue/${ruleId}/reject`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            showNotification('Rule rejected', 'info');
            closeRuleModal();
            await loadQueue();
        } else {
            const error = await response.json();
            showNotification('Error rejecting rule: ' + (error.detail || 'Unknown error'), 'error');
        }
    } catch (error) {
        console.error('Error rejecting rule:', error);
        showNotification('Error rejecting rule', 'error');
    }
}

async function submitPR() {
    const btn = document.getElementById('submitPRBtn');
    if (!btn) return;
    
    // Check if there are approved rules
    const approvedCount = parseInt(document.getElementById('approvedCount').textContent) || 0;
    if (approvedCount === 0) {
        showNotification('No approved rules to submit. Please approve rules first.', 'warning');
        return;
    }
    
    if (!await ModalManager.confirm(`Submit ${approvedCount} approved rule(s) as a GitHub PR?`, { title: 'Submit PR', confirmText: 'Submit', confirmClass: 'bg-purple-600 hover:bg-purple-700', cancelText: 'Cancel' })) {
        return;
    }
    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = '⏳ Submitting...';
    
    try {
        const response = await fetch('/api/sigma-queue/submit-pr', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const result = await response.json();
        
        if (result.success) {
            showNotification('PR created successfully. Rules: ' + result.rules_count, 'success');
            // Reload queue to show updated status
            await loadQueue();
        } else {
            let errorMsg = `❌ Failed to create PR: ${result.error || 'Unknown error'}`;
            if (result.branch) {
                errorMsg += `\n\nBranch created: ${result.branch}\nYou may need to create the PR manually.`;
            }
            showNotification(errorMsg, 'error');
        }
    } catch (error) {
        console.error('Error submitting PR:', error);
        showNotification('Error submitting PR: ' + error.message, 'error');
    } finally {
        // Restore button
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

function closeRuleModal() {
    if (window.ModalManager) {
        window.ModalManager.close('ruleModal');
    } else {
        document.getElementById('ruleModal').classList.add('hidden');
    }
    
    currentRuleId = null;
    isEditMode = false;
    isCreateMode = false;
    originalYaml = '';
    editedYaml = '';
    // Restore the default modal title (create mode swaps it out)
    const titleEl = document.getElementById('ruleModalTitle');
    if (titleEl) titleEl.textContent = 'SIGMA Rule Preview';
    resetQualityReviewCard();
    // Remove previewId from URL
    removeURLParameter('previewId');
    pendingPreviewId = null;
    // Clear validation results if any
    const validationResult = document.getElementById('validationResult');
    if (validationResult) {
        validationResult.remove();
    }
}

async function validateRule() {
    if (!currentRuleId) {
        showNotification('No rule selected', 'warning');
        return;
    }

    // Sync and persist current modal content so validation uses edits
    const currentYaml = getCurrentRuleYamlFromModal();
    const rule = queue.find(r => r.id === currentRuleId);
    if (rule && currentYaml !== rule.rule_yaml) {
        const putRes = await fetch(`/api/sigma-queue/${currentRuleId}/yaml`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rule_yaml: currentYaml })
        });
        if (putRes.ok) {
            rule.rule_yaml = currentYaml;
            editedYaml = currentYaml;
            originalYaml = currentYaml;
        }
    }

    // Show loading indicator
    const loadingMsg = document.createElement('div');
    loadingMsg.id = 'validationLoading';
    loadingMsg.className = 'fixed inset-0 bg-gray-600 bg-opacity-50 z-50 flex items-center justify-center';
    loadingMsg.innerHTML = `
        <div class="card p-6">
            <div class="text-center">
                <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto mb-4"></div>
                <p class="text-gray-700 dark:text-gray-300">Validating rule with workflow Sigma agent (LLM + pySIGMA)...</p>
                <p class="text-sm text-gray-500 dark:text-gray-400 mt-2">This may take up to 3 attempts</p>
            </div>
        </div>
    `;
    document.body.appendChild(loadingMsg);

    try {
        // Use same LLM as agent workflow (Sigma agent from workflow config; API keys server-side)
        const response = await fetch(`/api/sigma-queue/${currentRuleId}/validate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                use_workflow_sigma_agent: true,
                rule_yaml: currentYaml
            })
        });
        
        // Remove loading indicator
        const loadingEl = document.getElementById('validationLoading');
        if (loadingEl) loadingEl.remove();
        
        let data;
        try {
            data = await response.json();
        } catch (error) {
            console.error('Error parsing response:', error);
            const responseText = await response.text();
            throw new Error(`Server error: ${response.status} - ${responseText.substring(0, 200)}`);
        }
        
        // If response is not ok, still show modal with error info
        if (!response.ok) {
            data = {
                success: false,
                message: data.detail || data.message || `Validation failed with status ${response.status}`,
                attempts: 0,
                conversation_log: [],
                validation_results: [],
                errors: [data.detail || data.message || 'Unknown error'],
                provider: data.provider || 'workflow',
                model: data.model || 'Sigma agent'
            };
        }
        
        // Ensure conversation_log exists
        if (!data.conversation_log) {
            data.conversation_log = [];
        }
        if (!data.validation_results) {
            data.validation_results = [];
        }
        
        // Show conversation log modal (provider/model from response = workflow Sigma agent)
        showValidationConversationModal(data, data.provider || 'workflow', data.model || 'Sigma agent');
        
    } catch (error) {
        // Remove loading indicator
        const loadingEl = document.getElementById('validationLoading');
        if (loadingEl) loadingEl.remove();
        
        console.error('Error validating rule:', error);
        showNotification('Error validating rule: ' + error.message, 'error');
    }
}

async function showValidationConversationModal(data, provider, model) {
    // Remove any existing modal
    closeValidationConversationModal();
    
    // Clean up existing modal properly
    const existingModal = document.getElementById('validationConversationModal');
    if (existingModal) {
        if (window.ModalManager) {
            const stack = window.ModalManager.getStack();
            while (stack.includes('validationConversationModal')) {
                const index = stack.indexOf('validationConversationModal');
                stack.splice(index, 1);
            }
        }
        existingModal.remove();
        await new Promise(resolve => setTimeout(resolve, 10));
    }
    
    const modal = document.createElement('div');
    modal.id = 'validationConversationModal';
    modal.className = 'fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-[65]';
    
    document.body.appendChild(modal);
    
    // Ensure modal is visible
    modal.classList.remove('hidden');
    
    // Register with ModalManager
    if (window.ModalManager) {
        setTimeout(() => {
            const submitBtn = modal.querySelector('button[onclick*="applyValidatedRuleFromModal"]');
            window.ModalManager.register('validationConversationModal', {
                isDynamic: true,
                hasInput: false,
                submitButton: submitBtn
            });
            window.ModalManager.open('validationConversationModal', true);
            modal.classList.remove('hidden');
        }, 50);
    } else {
        // Fallback to old system
        pushModal('validationConversationModal', true);
    }
    
    const success = data.success || false;
    const validatedYaml = data.validated_yaml || '';
    const attempts = data.attempts || 0;
    const message = data.message || '';
    const conversationLog = data.conversation_log || [];
    const validationResults = data.validation_results || [];
    const errors = data.errors || [];
    
    // Build validation status display
    let validationStatusHtml = '';
    if (validationResults.length > 0) {
        validationStatusHtml = '<div class="mb-4 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">';
        validationStatusHtml += '<h4 class="font-medium text-gray-900 dark:text-white mb-2"><svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/></svg> Validation Results</h4>';
        
        validationResults.forEach((result, index) => {
            const statusIcon = result.is_valid ? '✅' : '❌';
            const statusColor = result.is_valid ? 'text-emerald-400 dark:text-green-400' : 'text-red-600 dark:text-red-400';
            const statusText = result.is_valid ? 'Valid' : 'Invalid';
            const ruleIndex = result.rule_index !== undefined ? result.rule_index : (index + 1);
            
            validationStatusHtml += `<div class="mb-2 p-2 border rounded ${result.is_valid ? 'border-green-200 dark:border-green-700 bg-green-50 dark:bg-green-900/20' : 'border-red-200 dark:border-red-700 bg-red-50 dark:bg-red-900/20'}">`;
            validationStatusHtml += `<div class="flex items-center mb-1">`;
            validationStatusHtml += `<span class="mr-2">${statusIcon}</span>`;
            validationStatusHtml += `<span class="font-medium ${statusColor}">Rule ${ruleIndex}: ${statusText}</span>`;
            validationStatusHtml += `</div>`;
            
            if (result.errors && result.errors.length > 0) {
                validationStatusHtml += `<div class="text-sm text-red-600 dark:text-red-400 mb-1">`;
                validationStatusHtml += `<strong>Errors:</strong><ul class="list-disc list-inside ml-2">`;
                result.errors.forEach(error => {
                    const escapedError = String(error).replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
                    validationStatusHtml += `<li>${escapedError}</li>`;
                });
                validationStatusHtml += `</ul></div>`;
            }
            
            if (result.warnings && result.warnings.length > 0) {
                validationStatusHtml += `<div class="text-sm text-amber-400 dark:text-yellow-400 mb-1">`;
                validationStatusHtml += `<strong>Warnings:</strong><ul class="list-disc list-inside ml-2">`;
                result.warnings.forEach(warning => {
                    const escapedWarning = String(warning).replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
                    validationStatusHtml += `<li>${escapedWarning}</li>`;
                });
                validationStatusHtml += `</ul></div>`;
            }
            
            validationStatusHtml += `</div>`;
        });
        
        validationStatusHtml += '</div>';
    }
    
    // Build error banner if failed
    let errorBannerHtml = '';
    if (!success) {
        const errorsHtml = errors.length > 0 
            ? `<ul class="mt-2 list-disc list-inside text-sm text-red-700 dark:text-red-300">${errors.map(err => `<li>${escapeHtml(String(err))}</li>`).join('')}</ul>`
            : '';
        errorBannerHtml = `
            <div class="mb-4 p-4 bg-red-50 dark:bg-red-900/20 border-2 border-red-300 dark:border-red-700 rounded-lg">
                <div class="flex items-start">
                    <span class="text-lg mr-3"><svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg></span>
                    <div class="flex-1">
                        <h4 class="font-bold text-red-900 dark:text-red-200 mb-2">Validation Failed</h4>
                        <p class="text-sm text-red-800 dark:text-red-300 mb-2">${escapeHtml(message)}</p>
                        ${errorsHtml}
                    </div>
                </div>
            </div>
        `;
    }
    
    modal.innerHTML = `
        <div class="relative top-10 mx-auto p-5 border w-11/12 max-w-6xl shadow-lg rounded-md bg-gray-800 border border-gray-700">
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-lg font-medium text-gray-900 dark:text-white"><svg class="w-5 h-5 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z"/></svg> Validation Results</h3>
                <button onclick="closeValidationConversationModal()" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
            
            <div class="mb-4 text-sm text-gray-600 dark:text-gray-400">
                <span class="font-medium">Provider:</span> ${provider.charAt(0).toUpperCase() + provider.slice(1)} | 
                <span class="font-medium">Model:</span> ${model} |
                <span class="font-medium">Attempts:</span> ${attempts}
            </div>
            
            ${errorBannerHtml}
            
            ${success ? `
            <div class="mb-4 p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-700 rounded-lg">
                <div class="flex items-start">
                    <div class="flex-shrink-0">
                        <svg class="h-5 w-5 text-green-400" fill="currentColor" viewBox="0 0 20 20">
                            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>
                        </svg>
                    </div>
                    <div class="ml-3 flex-1">
                        <h4 class="text-sm font-medium text-green-800 dark:text-green-200">
                            ✓ Validation Successful
                        </h4>
                        <p class="mt-1 text-sm text-green-700 dark:text-green-300">
                            ${escapeHtml(message)}
                        </p>
                        ${validatedYaml ? `
                        <div class="mt-3">
                            <h5 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Validated Rule:</h5>
                            <div class="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg max-h-96 overflow-y-auto">
                                <pre class="text-sm font-mono whitespace-pre-wrap text-gray-800 dark:text-gray-200">${escapeHtml(validatedYaml)}</pre>
                            </div>
                        </div>
                        ` : ''}
                    </div>
                </div>
            </div>
            ` : ''}
            
            ${validationStatusHtml}
            
            <div class="mt-4">
                <div class="flex items-center justify-between mb-2">
                    <h4 class="text-md font-medium text-gray-900 dark:text-white"><svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.992 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182M2.985 19.644l3.181-3.182"/></svg> LLM ↔ pySigma Conversation Log</h4>
                    <button id="toggleValidationConversation" class="text-sm text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 px-3 py-1 border border-blue-300 dark:border-blue-700 rounded hover:bg-blue-50 dark:hover:bg-blue-900/20">
                        Show Log
                    </button>
                </div>
                <div class="text-xs text-gray-600 dark:text-gray-400 mb-2">Shows the iterative pySigma semantic validation and Huntable policy checks</div>
                <div id="validationConversationContent" style="display: none;">
                    <div id="validationConversation" class="space-y-4 max-h-96 overflow-y-auto p-4 bg-gray-50 dark:bg-gray-900 rounded border">
                        <!-- Filled by script below -->
                    </div>
                </div>
            </div>
            
            <div class="mt-4 flex justify-between items-center">
                <div class="flex space-x-2">
                    ${success && validatedYaml ? `
                    <button onclick="applyValidatedRuleFromModal()" class="px-4 py-2 bg-emerald-600 hover:bg-green-700 text-white rounded-md">
                        ✅ Apply Validated Rule
                    </button>
                    ` : ''}
                </div>
                <button onclick="closeValidationConversationModal()" class="px-4 py-2 bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-md hover:bg-gray-400 dark:hover:bg-gray-500 transition-colors">
                    Close
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Store validated YAML for apply function
    if (success && validatedYaml) {
        window.validatedYaml = validatedYaml;
    }
    
    // Add toggle functionality for conversation log
    const toggleButton = document.getElementById('toggleValidationConversation');
    const conversationContent = document.getElementById('validationConversationContent');
    if (toggleButton && conversationContent) {
        toggleButton.addEventListener('click', function() {
            if (conversationContent.style.display === 'none') {
                conversationContent.style.display = 'block';
                toggleButton.textContent = 'Hide Log';
            } else {
                conversationContent.style.display = 'none';
                toggleButton.textContent = 'Show Log';
            }
        });
    }
    
    // Render conversation entries
    try {
        const convo = conversationLog || [];
        const container = document.getElementById('validationConversation');
        if (container) {
            if (!convo.length) {
                container.innerHTML = '<div class="text-sm text-gray-600 dark:text-gray-400 text-center py-4">⚠️ No conversation log available.</div>';
            } else {
                container.innerHTML = convo.map((entry, idx) => {
                    const attempt = entry.attempt || (idx + 1);
                    const attemptBadgeColor = idx === convo.length - 1 ? 'bg-emerald-500' : 'bg-blue-500';
                    const attemptIcon = idx === convo.length - 1 ? '✅' : '🔄';
                    
                    // Format the messages (system + user prompts)
                    const messages = entry.messages || [];
                    const messagesHtml = messages.map((msg, msgIdx) => {
                        const role = msg.role || 'user';
                        const content = String(msg.content || '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                        const roleIcon = role === 'system' ? '⚙️' : '👤';
                        const roleColor = role === 'system' ? 'text-purple-700 dark:text-purple-400' : 'text-blue-700 dark:text-blue-400';
                        const collapsibleId = 'val-msg-' + idx + '-' + msgIdx;
                        
                        return '<div class="mb-2">' +
                            '<div class="flex items-center mb-1">' +
                                '<span class="mr-2">' + roleIcon + '</span>' +
                                '<span class="font-semibold ' + roleColor + ' text-sm uppercase">' + role + '</span>' +
                            '</div>' +
                            '<div class="bg-gray-100 dark:bg-gray-800 p-2 rounded border border-gray-300 dark:border-gray-600">' +
                                '<div id="' + collapsibleId + '-preview" class="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap">' + content + '</div>' +
                            '</div>' +
                        '</div>';
                    }).join('');
                    
                    // Format LLM response
                    const llmResponse = entry.llm_response || '';
                    const llmContent = String(llmResponse).replace(/</g, '&lt;').replace(/>/g, '&gt;');
                    const llmCollapsibleId = 'val-llm-' + idx;
                    
                    // Format validation results (API may return object or array)
                    const vRaw = entry.validation;
                    const validation = Array.isArray(vRaw) ? vRaw : (vRaw && typeof vRaw === 'object' && vRaw !== null ? Object.values(vRaw) : []);
                    const hasErrors = validation.some(v => !v.is_valid);
                    const validationIcon = hasErrors ? '❌' : '✅';
                    const validationColor = hasErrors ? 'text-red-700 dark:text-red-400' : 'text-green-700 dark:text-green-400';
                    
                    const validationHtml = validation.map((v, vIdx) => {
                        const errs = (v.errors || []).map(e => '<li class="text-red-700 dark:text-red-400 text-xs">' + String(e).replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</li>').join('');
                        const warns = (v.warnings || []).map(w => '<li class="text-yellow-700 dark:text-yellow-400 text-xs">' + String(w).replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</li>').join('');
                        const statusBadge = v.is_valid 
                            ? '<span class="px-2 py-1 text-xs bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200 rounded">✅ VALID</span>'
                            : '<span class="px-2 py-1 text-xs bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 rounded">❌ INVALID</span>';
                        const borderClass = v.is_valid ? 'border-green-300 dark:border-green-700' : 'border-red-300 dark:border-red-700';
                        const errsHtml = errs ? '<div class="mt-2"><strong class="text-sm text-red-800 dark:text-red-300">Errors:</strong><ul class="list-disc ml-5 mt-1">' + errs + '</ul></div>' : '';
                        const warnsHtml = warns ? '<div class="mt-2"><strong class="text-sm text-yellow-800 dark:text-yellow-300">Warnings:</strong><ul class="list-disc ml-5 mt-1">' + warns + '</ul></div>' : '';
                        
                        return '<div class="mb-3 p-3 bg-gray-800 border border-gray-700 border ' + borderClass + ' rounded">' +
                            '<div class="flex items-center justify-between mb-2">' +
                                '<span class="font-semibold text-sm text-gray-900 dark:text-white">Rule #' + (vIdx + 1) + '</span>' +
                                statusBadge +
                            '</div>' +
                            errsHtml +
                            warnsHtml +
                        '</div>';
                    }).join('');
                    
                    if (entry.error) {
                        return '<div class="mb-4 p-3 border rounded bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-700">' +
                            '<div class="flex items-center mb-2">' +
                                '<span class="mr-2">❌</span>' +
                                '<span class="font-medium">Attempt ' + attempt + ' (Error)</span>' +
                            '</div>' +
                            '<div class="text-red-700 dark:text-red-300 text-sm">' + escapeHtml(entry.error) + '</div>' +
                        '</div>';
                    }
                    
                    return '<div class="mb-4 p-3 border rounded ' + (hasErrors ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-700' : 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-700') + '">' +
                        '<div class="flex items-center mb-2">' +
                            '<span class="mr-2">' + attemptIcon + '</span>' +
                            '<span class="font-medium text-gray-900 dark:text-white">Attempt ' + attempt + ':</span>' +
                        '</div>' +
                        '<div class="space-y-3">' +
                            '<div class="border-l-4 border-blue-500 dark:border-blue-400 pl-3">' +
                                '<div class="font-semibold text-sm text-gray-700 dark:text-gray-300 mb-2">📝 Prompts Sent to LLM</div>' +
                                messagesHtml +
                            '</div>' +
                            '<div class="border-l-4 border-purple-500 dark:border-purple-400 pl-3">' +
                                '<div class="flex items-center mb-2">' +
                                    '<span class="mr-2"><svg class=\"w-4 h-4 inline\" fill=\"none\" stroke=\"currentColor\" viewBox=\"0 0 24 24\" stroke-width=\"2\"><path stroke-linecap=\"round\" stroke-linejoin=\"round\" d=\"M8.25 3v1.5M4.5 8.25H3M21 8.25h-1.5M4.5 12H3M21 12h-1.5M4.5 15.75H3M21 15.75h-1.5M8.25 19.5V21M12 3v1.5M12 19.5V21M15.75 3v1.5M15.75 19.5V21M6.75 7.5h10.5v9H6.75v-9z\"/></svg></span>' +
                                    '<span class="font-semibold text-sm text-gray-700 dark:text-gray-300">LLM Response</span>' +
                                '</div>' +
                                '<div class="bg-purple-50 dark:bg-purple-900/20 p-3 rounded border border-purple-200 dark:border-purple-700">' +
                                    '<div id="' + llmCollapsibleId + '-preview" class="text-xs text-gray-700 dark:text-gray-300 whitespace-pre-wrap">' + llmContent + '</div>' +
                                '</div>' +
                            '</div>' +
                            '<div class="border-l-4 ' + (hasErrors ? 'border-red-500 dark:border-red-400' : 'border-green-500 dark:border-green-400') + ' pl-3">' +
                                '<div class="flex items-center mb-2">' +
                                    '<span class="mr-2">' + validationIcon + '</span>' +
                                    '<span class="font-semibold text-sm ' + validationColor + '">pySigma Validation</span>' +
                                '</div>' +
                                '<div class="space-y-2">' +
                                    validationHtml +
                                '</div>' +
                            '</div>' +
                        '</div>' +
                    '</div>';
                }).join('');
            }
        }
    } catch (e) {
        console.error('Failed to render validation conversation', e);
        const container = document.getElementById('validationConversation');
        if (container) {
            container.innerHTML = '<div class="text-sm text-red-600 dark:text-red-400">Error rendering conversation log. Check console for details.</div>';
        }
    }
}

function closeValidationConversationModal() {
    if (window.ModalManager) {
        window.ModalManager.close('validationConversationModal');
    } else {
        const modal = document.getElementById('validationConversationModal');
        if (modal) {
            modal.remove();
        }
    }
}

async function applyValidatedRuleFromModal() {
    if (!window.validatedYaml) {
        showNotification('No validated rule to apply', 'warning');
        return;
    }
    
    if (!await ModalManager.confirm('Apply the validated rule? This will update the rule YAML.', { title: 'Apply Rule', confirmText: 'Apply', confirmClass: 'bg-purple-600 hover:bg-purple-700', cancelText: 'Cancel' })) return;
    
    try {
        const response = await fetch(`/api/sigma-queue/${currentRuleId}/yaml`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rule_yaml: window.validatedYaml })
        });
        
        if (response.ok) {
            // Update the rule in the queue array
            const rule = queue.find(r => r.id === currentRuleId);
            if (rule) {
                rule.rule_yaml = window.validatedYaml;
                editedYaml = window.validatedYaml;
                originalYaml = window.validatedYaml;
                isEditMode = false;
                
                // Re-render the rule preview with updated YAML
                renderRulePreview(rule);
            }
            
            // Close validation modal
            closeValidationConversationModal();
            
            // Clear validated YAML
            window.validatedYaml = null;
            
            // Reload queue in background
            loadQueue().catch(err => console.error('Error reloading queue:', err));
            
            showNotification('Validated rule applied successfully', 'success');
        } else {
            showNotification('Error applying validated rule', 'error');
        }
    } catch (error) {
        console.error('Error applying validated rule:', error);
        showNotification('Error applying validated rule', 'error');
    }
}

async function applyValidatedRule() {
    if (!window.validatedYaml) {
        showNotification('No validated rule to apply', 'warning');
        return;
    }
    
    if (!await ModalManager.confirm('Apply the validated rule? This will update the rule YAML.', { title: 'Apply Rule', confirmText: 'Apply', confirmClass: 'bg-purple-600 hover:bg-purple-700', cancelText: 'Cancel' })) return;
    
    try {
        const response = await fetch(`/api/sigma-queue/${currentRuleId}/yaml`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rule_yaml: window.validatedYaml })
        });
        
        if (response.ok) {
            // Update the rule in the queue array
            const rule = queue.find(r => r.id === currentRuleId);
            if (rule) {
                rule.rule_yaml = window.validatedYaml;
                editedYaml = window.validatedYaml;
                originalYaml = window.validatedYaml;
                isEditMode = false;
                
                // Re-render the rule preview with updated YAML
                renderRulePreview(rule);
            }
            
            // Remove validation result
            const validationResult = document.getElementById('validationResult');
            if (validationResult) {
                validationResult.remove();
            }
            
            // Clear validated YAML
            window.validatedYaml = null;
            
            // Reload queue in background
            loadQueue().catch(err => console.error('Error reloading queue:', err));
            
            showNotification('Validated rule applied successfully', 'success');
        } else {
            showNotification('Error applying validated rule', 'error');
        }
    } catch (error) {
        console.error('Error applying validated rule:', error);
        showNotification('Error applying validated rule', 'error');
    }
}

function resetQualityReviewCard() {
    // Quality review card removed; keep stub in case preview logic still calls it.
}

let enrichmentPresetRestoredThisSession = false;

async function loadEnrichProviderModelCatalog() {
    // Use the already-loaded commercialModelCatalog (populated at page load by
    // loadEnabledProviders) so the enrich modal always shows the same model list
    // as every other picker on the page — no separate fetch needed.
    populateEnrichProviderDropdown();

    // Derive the default provider from the enabledProviders map (same source the
    // rest of the workflow UI uses).
    let defaultProvider = null;
    if (enabledProviders.lmstudio) {
        defaultProvider = 'lmstudio';
    } else if (enabledProviders.openai && commercialModelCatalog.openai) {
        defaultProvider = 'openai';
    } else if (enabledProviders.anthropic && commercialModelCatalog.anthropic) {
        defaultProvider = 'anthropic';
    }

    if (defaultProvider) {
        const providerSelect = document.getElementById('enrichProviderSelect');
        if (providerSelect) {
            providerSelect.value = defaultProvider;
            await populateEnrichModelDropdown(defaultProvider);
        }
    }
}

function populateEnrichProviderDropdown() {
    const providerSelect = document.getElementById('enrichProviderSelect');
    if (!providerSelect) return;

    providerSelect.innerHTML = '<option value="">Select provider...</option>';

    const providers = ['lmstudio', 'openai', 'anthropic'];
    providers.forEach(provider => {
        if (provider === 'lmstudio') {
            const option = document.createElement('option');
            option.value = provider;
            option.textContent = 'LMStudio';
            providerSelect.appendChild(option);
        } else if (commercialModelCatalog[provider] && commercialModelCatalog[provider].length > 0) {
            const option = document.createElement('option');
            option.value = provider;
            option.textContent = provider.charAt(0).toUpperCase() + provider.slice(1);
            providerSelect.appendChild(option);
        }
    });

    // Add event listener for provider change
    providerSelect.addEventListener('change', async function() {
        await populateEnrichModelDropdown(this.value);
    });
}

async function populateEnrichModelDropdown(provider) {
    const modelSelect = document.getElementById('enrichModelSelect');
    if (!modelSelect) return;
    
    modelSelect.innerHTML = '<option value="">Select model...</option>';
    
    if (provider === 'lmstudio') {
        // Load LMStudio models from API
        try {
            const response = await fetch('/api/lmstudio-models');
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.models && data.models.length > 0) {
                    data.models.forEach(model => {
                        const option = document.createElement('option');
                        option.value = model;
                        option.textContent = model;
                        modelSelect.appendChild(option);
                    });
                    // Select first model by default
                    if (data.models.length > 0) {
                        modelSelect.value = data.models[0];
                    }
                } else {
                    const option = document.createElement('option');
                    option.value = '';
                    option.textContent = 'No LMStudio models available';
                    option.disabled = true;
                    modelSelect.appendChild(option);
                }
            } else {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'Failed to load LMStudio models';
                option.disabled = true;
                modelSelect.appendChild(option);
            }
        } catch (error) {
            console.error('Error loading LMStudio models:', error);
            const option = document.createElement('option');
            option.value = '';
            option.textContent = 'Error loading models';
            option.disabled = true;
            modelSelect.appendChild(option);
        }
    } else if (provider && commercialModelCatalog[provider]) {
        const models = getCommercialProviderModels(provider) || commercialModelCatalog[provider];
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model;
            option.textContent = model;
            modelSelect.appendChild(option);
        });
        if (models.length > 0) {
            modelSelect.value = models[0];
        }
    }
}

// Track if preview modal was open when opening enrich modal
// previewModalWasOpen removed - using modal stack instead

async function openEnrichModal() {
    const rule = queue.find(r => r.id === currentRuleId);
    if (!rule) return;
    
    // Ensure rule modal is registered and tracked if it's open
    const ruleModal = document.getElementById('ruleModal');
    const modalStack = window.ModalManager ? window.ModalManager.getStack() : [];
    
    if (ruleModal && !ruleModal.classList.contains('hidden')) {
        // Ensure rule modal is registered and in stack
        if (window.ModalManager && !modalStack.includes('ruleModal')) {
            window.ModalManager.register('ruleModal', { isDynamic: false });
            // Modal is already visible, ensure it's tracked in stack
            // Call open with hidePrevious=false to add to stack without hiding anything
            window.ModalManager.open('ruleModal', false);
        }
    } else if (currentRuleId && window.ModalManager) {
        // Rule modal should be open but isn't - ensure it's registered
        if (!modalStack.includes('ruleModal')) {
            window.ModalManager.register('ruleModal', { isDynamic: false });
        }
    }
    
    // Push to modal stack (will hide previous modal, which should be ruleModal)
    pushModal('enrichModal', true);
    
    // Reset state
    currentEnrichedYaml = null;
    enrichIteration = 0;
    
    // Set original rule YAML from current modal content (including unsaved edits)
    document.getElementById('enrichOriginalRule').value = getCurrentRuleYamlFromModal();
    
    // Try to load latest saved prompt version
    let defaultSystemPrompt = `SYSTEM (GPT-5*) — Modular SIGMA Rule Validator/Polisher (7 Toggles)

You are a SIGMA rule "validation + minimal-polish" agent. Your job is to ensure a provided draft SIGMA rule is:
- syntactically valid YAML and structurally valid Sigma,
- strongly supported by provided evidence (URL and/or article content),
- minimally changed (preserve effective detection),
- enriched with metadata (id, references, author, title specificity, false positives guidance) based on enabled directives.

You MUST follow the 7 directives below as independent modules. Each directive has an enable/disable toggle.
If a directive is disabled, do not perform it and do not mention it.

CRITICAL BEHAVIOR
- Evidence grounding: If article_content is present, it is the authoritative evidence source. If only a URL is present, you may use it only as a reference string, not as evidence.
- No invention: Do not invent behaviors, paths, arguments, IOCs, registry keys, parent/child relations, or product-specific fields not supported by evidence.
- Minimal changes: Avoid substantive detection changes. Only adjust detection logic if required for fidelity to evidence or to fix invalid Sigma structure.
- Output must be deterministic, machine-consumable, and follow the Output Contract.
- Do not include chain-of-thought. Provide results only.

──────────────────────────────────────────────────────────────────────────────
INPUTS (from application)
- toggles: JSON object, keys d1..d7 with boolean values
- author_value: string (application-provided; e.g., "Huntable")
- url: string or null
- article_content: string or null
- draft_sigma_yaml: string (the draft minimal Sigma rule)

──────────────────────────────────────────────────────────────────────────────
OUTPUT CONTRACT (MUST FOLLOW)
Return ONLY a single JSON object with this schema:

{
  "status": "pass" | "needs_revision" | "fail",
  "summary": "short human-readable summary",
  "actions_taken": ["..."],
  "issues": [
    {
      "directive": "d1|d2|d3|d4|d5|d6|d7",
      "severity": "low|medium|high",
      "type": "syntax|schema|evidence|metadata|style|logic",
      "message": "..."
    }
  ],
  "updated_sigma_yaml": "YAML string or empty if fail",
  "diff_notes": ["bullet-like short notes describing changes made (no long prose)"],
  "suggested_followups": ["optional next steps if needs_revision/fail"]
}

- If status="fail": updated_sigma_yaml MUST be "" and issues MUST explain why.
- If status="needs_revision": updated_sigma_yaml should be best-effort corrected; include followups.
- If status="pass": updated_sigma_yaml must contain the final polished rule.

──────────────────────────────────────────────────────────────────────────────
DIRECTIVE MODULES (7 MODULAR DIRECTIVES)

[d1] ID: validate/generate an ID (random number in SIGMA format)
Toggle: toggles.d1
Rules:
- If rule has "id": validate it is a UUID (preferred) OR a Sigma-compatible unique identifier used by your org.
- If missing or invalid: generate a UUID v4 and set rule field: id: <uuidv4>
- Do NOT regenerate a valid existing id.
- Record action in actions_taken and diff_notes.

[d2] Evidence fidelity: validate article content strongly supports rule logic
Toggle: toggles.d2
Rules:
- If article_content is provided: every detection component (selections, keywords, field constraints, condition logic) must be supported explicitly by text.
- If something is not supported:
  - Prefer REMOVAL or NARROWING to restore fidelity (minimal changes).
  - If removal breaks the rule beyond usefulness, set status="needs_revision" and explain what evidence is missing.
- If only url is provided (article_content null/empty): you cannot validate evidence; set status="needs_revision" unless draft rule already states it is generic and does not claim article-specific behaviors. In all cases, do not "assume" evidence from URL alone.
- Evidence test standard: "Would a reader find the same executable/arguments/paths/registry keys/fields plainly stated in article_content?"
- Record any unsupported elements as issues with severity medium/high.

[d3] References: ensure/add the URL as reference
Toggle: toggles.d3
Rules:
- If url provided:
  - Ensure it is present under: references:
      - <url>
  - If references field missing, add it.
  - If references exists but url missing, append it (dedupe).
- If url not provided: do nothing.
- Do NOT add any other references unless explicitly provided by input.
- Record action in actions_taken and diff_notes.

[d4] Preserve detection: avoid substantive changes to effective detection
Toggle: toggles.d4
Rules:
- This is a global guardrail applied during all edits:
  - No broadening conditions.
  - No adding new selections/keywords/fields.
  - Only allowed changes:
    (a) syntax fixes that do not change meaning,
    (b) field normalization that preserves equivalence,
    (c) removal/narrowing of unsupported logic for evidence fidelity,
    (d) small structural fixes required by Sigma tooling (e.g., proper condition formatting).
- If any change could alter detection materially, you must:
  - minimize it,
  - document it clearly in diff_notes,
  - and justify it as "required for fidelity or validity."
- If preserving detection conflicts with evidence fidelity, evidence fidelity wins (but keep smallest narrowing).

[d5] Author: add author field/value provided by the application
Toggle: toggles.d5
Rules:
- Ensure top-level field exists: author: <author_value>
- If author exists but differs:
  - Append rather than overwrite if it looks like multiple authors are allowed in your ecosystem; otherwise set to author_value and record a low/medium issue.
  - Default behavior: if author is a string, convert to "Existing Author; <author_value>" only if you are confident this is acceptable YAML for your consumers; otherwise overwrite and note.
- Record action in actions_taken and diff_notes.

[d6] Title: improve title to be more unique and specific to use-case
Toggle: toggles.d6
Rules:
- Make title specific without inventing:
  - Include the key behavior + key tool/executable + unique technique context (e.g., "via rundll32 loading image file" only if supported).
  - Avoid vague titles like "Suspicious PowerShell."
  - Keep it concise (ideally <= 12 words).
- Must be faithful to evidence (or to the existing rule's stated scope if article_content missing).
- Do not add IOCs or actor names unless explicitly in article_content or in the draft rule already.
- Record action in actions_taken and diff_notes.

[d7] False positives: evaluate and propose/improve false positive guidance
Toggle: toggles.d7
Rules:
- If falsepositives field missing, add it as a YAML list if you can provide reasonable, non-speculative guidance.
- If article_content provides legitimate-use context, incorporate it.
- If evidence is thin, keep false positive guidance conservative and generic (e.g., "Administrative tooling may trigger") and mark as low severity note.
- Do not claim specific benign software unless explicitly supported by article_content or the existing rule.
- Record action in actions_taken and diff_notes.

──────────────────────────────────────────────────────────────────────────────
PROCESS (MANDATORY EXECUTION ORDER)
1) Parse draft_sigma_yaml as YAML. If invalid, try to minimally fix YAML formatting. If impossible: fail.
2) Validate Sigma-required fields minimally (title, logsource, detection). If missing, set needs_revision and minimally scaffold ONLY if the draft indicates intended structure; otherwise fail.
3) Apply enabled directives in order d1 → d7, while enforcing d4 guardrail if enabled.
4) Re-validate final YAML is well-formed and preserves intent.
5) Produce JSON output per contract.

──────────────────────────────────────────────────────────────────────────────
STYLE AND FORMATTING RULES (SIGMA YAML)
- Use standard Sigma field names: title, id, status, description, references, author, date, logsource, detection, falsepositives, level, tags.
- Keep YAML clean:
  - references as list
  - falsepositives as list
  - detection selections as mappings
  - condition as string
- Do not add unrelated metadata.
- Preserve existing indentation and ordering where possible; otherwise prefer common Sigma ordering:
  title, id, status, description, references, author, date, tags, logsource, detection, falsepositives, level

END SYSTEM PROMPT`;
    
    let defaultUserInstruction = 'Improve and enrich this SIGMA rule with better detection logic, more comprehensive conditions, and proper metadata.';
    
    // Try to load latest saved prompt version
    try {
        const response = await fetch('/api/sigma-queue/prompt/latest');
        const data = await response.json();
        
        if (data.success && data.system_prompt) {
            // Load saved version
            document.getElementById('enrichSystemPrompt').value = data.system_prompt;
            document.getElementById('enrichInstruction').value = data.user_instruction || defaultUserInstruction;
        } else {
            // Use defaults if no saved version exists
            document.getElementById('enrichSystemPrompt').value = defaultSystemPrompt;
            document.getElementById('enrichInstruction').value = defaultUserInstruction;
        }
    } catch (error) {
        console.error('Error loading latest prompt version:', error);
        // Fall back to defaults on error
        document.getElementById('enrichSystemPrompt').value = defaultSystemPrompt;
        document.getElementById('enrichInstruction').value = defaultUserInstruction;
    }
    _syncEnrichDisplay();
    _enrichSPViewMode();
    // A fresh open starts from the latest saved prompt, not a named preset.
    _wireEnrichDriftListeners();
    enrichLoadedPreset = null;
    _captureEnrichBaseline();
    updateEnrichPresetState();
    const _vr = document.getElementById('enrichValidateResult');
    if (_vr) { _vr.style.display = 'none'; _vr.textContent = ''; }

    document.getElementById('enrichResult').classList.add('hidden');
    document.getElementById('enrichOriginalSection')?.classList.remove('hidden');
    document.getElementById('enrichError').classList.add('hidden');
    document.getElementById('applyEnrichBtn').classList.add('hidden');
    document.getElementById('enrichFurtherBtn').classList.add('hidden');
    document.getElementById('enrichBtn').classList.remove('hidden');
    document.getElementById('enrichLoading').classList.add('hidden');
    
    // Reset comparison view
    document.getElementById('enrichComparisonView').classList.add('hidden');
    document.getElementById('enrichedRuleYaml').classList.remove('hidden');
    document.getElementById('enrichDiffView').classList.add('hidden');
    document.getElementById('toggleViewBtn').textContent = '📊 Show Comparison';
    
    // Safely reset labels if they exist
    const leftLabel = document.getElementById('enrichLeftLabel');
    const rightLabel = document.getElementById('enrichRightLabel');
    const iterationInfo = document.getElementById('enrichIterationInfo');
    if (leftLabel) leftLabel.textContent = 'Original Rule';
    if (rightLabel) rightLabel.textContent = 'Enriched Rule';
    if (iterationInfo) iterationInfo.textContent = '';
    
    // Reset raw response section
    const rawResponseContent = document.getElementById('rawResponseContent');
    const rawResponseToggle = document.getElementById('rawResponseToggle');
    const rawResponseCaret = document.getElementById('rawResponseCaret');
    if (rawResponseContent) rawResponseContent.classList.add('hidden');
    if (rawResponseToggle) rawResponseToggle.setAttribute('aria-expanded', 'false');
    if (rawResponseCaret) rawResponseCaret.textContent = '▼';
    const rawResponseText = document.getElementById('rawResponseText');
    if (rawResponseText) rawResponseText.innerHTML = '';
    
    // Load provider/model catalog and populate dropdowns, then restore last preset if any
    await loadEnrichProviderModelCatalog();
    await restoreLastEnrichmentPreset();
}

function _collectEnrichSPIssues(sp) {
    const issues = [];
    if (!sp || !sp.trim()) {
        issues.push({ level: 'error', msg: 'System prompt is empty. An empty prompt disables the output contract entirely.' });
        return issues;
    }
    if (!sp.includes('updated_sigma_yaml')) {
        issues.push({ level: 'error', msg: 'Missing "updated_sigma_yaml" reference. Absence causes HTTP 400 on every pass/needs_revision response.' });
    }
    const lower = sp.toLowerCase();
    if (!lower.includes('json')) {
        issues.push({ level: 'warn', msg: 'No JSON mandate found. LLM may return markdown/YAML, silently falling back to legacy path with no structured metadata.' });
    }
    if (!lower.includes('status')) {
        issues.push({ level: 'warn', msg: 'Missing "status" field reference. Without status, the parser falls to legacy path and all issue/summary data is lost.' });
    }
    if (!lower.includes('pass') && !lower.includes('needs_revision') && !lower.includes('fail')) {
        issues.push({ level: 'warn', msg: 'No status values enumerated (pass/needs_revision/fail). LLM may use non-standard values the parser will not recognize.' });
    }
    if (sp.trim().length < 40) {
        issues.push({ level: 'warn', msg: 'System prompt is very short (under 40 characters). Likely incomplete and does not convey sufficient behavioral constraints.' });
    }
    return issues;
}

function validateEnrichSystemPrompt() {
    const sp = document.getElementById('enrichSystemPrompt').value;
    const resultDiv = document.getElementById('enrichValidateResult');
    const issues = _collectEnrichSPIssues(sp);
    _renderValidateResult(resultDiv, issues);
}

function _syncEnrichDisplay() {
    const ta = document.getElementById('enrichSystemPrompt');
    const div = document.getElementById('enrichSystemPromptDisplay');
    if (div && ta) div.textContent = ta.value;
}

function _enrichSPViewMode() {
    const ta = document.getElementById('enrichSystemPrompt');
    ta.setAttribute('readonly', '');
    ta.classList.add('hidden');
    document.getElementById('enrichSystemPromptDisplay').classList.remove('hidden');
    document.getElementById('enrichSPExpandBtn').classList.remove('hidden');
    document.getElementById('enrichSPEditBtn').classList.remove('hidden');
    document.getElementById('enrichSPHistoryBtn').classList.remove('hidden');
    document.getElementById('enrichSPCancelBtn').classList.add('hidden');
    document.getElementById('enrichSPSaveBtn').classList.add('hidden');
}

function _enrichSPEditMode() {
    const ta = document.getElementById('enrichSystemPrompt');
    ta.removeAttribute('readonly');
    ta.classList.remove('hidden');
    document.getElementById('enrichSystemPromptDisplay').classList.add('hidden');
    document.getElementById('enrichSPExpandBtn').classList.add('hidden');
    document.getElementById('enrichSPEditBtn').classList.add('hidden');
    document.getElementById('enrichSPHistoryBtn').classList.add('hidden');
    document.getElementById('enrichSPCancelBtn').classList.remove('hidden');
    document.getElementById('enrichSPSaveBtn').classList.remove('hidden');
}

function editEnrichSystemPrompt() {
    _enrichSPEditMode();
    document.getElementById('enrichSystemPrompt').focus();
}

async function cancelEnrichSystemPrompt() {
    try {
        const response = await fetch('/api/sigma-queue/prompt/latest');
        const data = await response.json();
        if (data.success && data.system_prompt) {
            document.getElementById('enrichSystemPrompt').value = data.system_prompt;
        }
    } catch (e) { /* keep current value on network error */ }
    _syncEnrichDisplay();
    _enrichSPViewMode();
    updateEnrichPresetState();
}

async function saveEnrichSystemPromptEdit() {
    const sp = document.getElementById('enrichSystemPrompt').value;
    const issues = _collectEnrichSPIssues(sp);
    const errors = issues.filter(i => i.level === 'error');
    if (errors.length > 0) {
        _renderValidateResult(document.getElementById('enrichValidateResult'), issues);
        return;
    }
    _enrichSPViewMode();
    _syncEnrichDisplay();
    await saveEnrichmentPrompt();
}

// Bespoke overlay (outside ModalManager): close on Escape regardless of focus
// location. An inline onkeydown on the div only fires while focus is inside the
// overlay; a document-level listener mirrors how ModalManager handles Escape.
function _enrichExpEscHandler(e) {
    if (e.key === 'Escape') {
        closeEnrichExpanded();
    }
}

function openEnrichExpanded() {
    const ta = document.getElementById('enrichSystemPrompt');
    const expTA = document.getElementById('enrich-exp-system');
    expTA.value = ta.value;
    expTA.readOnly = true;
    document.getElementById('enrich-exp-edit-btn').style.display = '';
    document.getElementById('enrich-exp-save-btn').style.display = 'none';
    document.getElementById('enrich-exp-mode-badge').textContent = 'Read-only';
    const len = expTA.value.length;
    document.getElementById('enrich-exp-charcount').textContent = len + ' chars';
    expTA.oninput = () => {
        document.getElementById('enrich-exp-charcount').textContent = expTA.value.length + ' chars';
    };
    document.getElementById('enrich-exp-validate-result').style.display = 'none';
    document.getElementById('enrichModal').classList.add('hidden');
    const overlay = document.getElementById('enrich-expanded-overlay');
    overlay.classList.add('visible');
    overlay.focus();
    document.removeEventListener('keydown', _enrichExpEscHandler);
    document.addEventListener('keydown', _enrichExpEscHandler);
}

function editEnrichExpanded() {
    const expTA = document.getElementById('enrich-exp-system');
    expTA.readOnly = false;
    expTA.focus();
    document.getElementById('enrich-exp-edit-btn').style.display = 'none';
    document.getElementById('enrich-exp-save-btn').style.display = '';
    document.getElementById('enrich-exp-mode-badge').textContent = 'Editing';
}

function validateEnrichExpandedPrompt() {
    const sp = document.getElementById('enrich-exp-system').value;
    const resultDiv = document.getElementById('enrich-exp-validate-result');
    const issues = _collectEnrichSPIssues(sp);
    _renderValidateResult(resultDiv, issues);
}

async function saveEnrichExpanded() {
    const sp = document.getElementById('enrich-exp-system').value;
    const issues = _collectEnrichSPIssues(sp);
    const errors = issues.filter(i => i.level === 'error');
    if (errors.length > 0) {
        _renderValidateResult(document.getElementById('enrich-exp-validate-result'), issues);
        return;
    }
    document.getElementById('enrichSystemPrompt').value = sp;
    _syncEnrichDisplay();
    updateEnrichPresetState();
    closeEnrichExpanded();
    await saveEnrichmentPrompt();
}

function closeEnrichExpanded() {
    document.removeEventListener('keydown', _enrichExpEscHandler);
    document.getElementById('enrich-expanded-overlay').classList.remove('visible');
    document.getElementById('enrichModal').classList.remove('hidden');
}

function closeEnrichModal() {
    if (window.ModalManager) {
        window.ModalManager.close('enrichModal');
    } else {
        const enrichModal = document.getElementById('enrichModal');
        if (enrichModal) {
            enrichModal.classList.add('hidden');
        }
    }
}

async function saveEnrichmentPrompt() {
    const systemPrompt = document.getElementById('enrichSystemPrompt').value.trim();
    const userInstruction = document.getElementById('enrichInstruction').value.trim();
    
    if (!systemPrompt) {
        showNotification('System prompt cannot be empty', 'error');
        return;
    }
    
    // Prompt for optional change description
    const changeDescription = await ModalManager.prompt('Enter a description for this version (optional):', '', { title: 'Save Prompt', confirmText: 'Save', placeholder: 'Optional description' }) || null;
    
    try {
        const response = await fetch('/api/sigma-queue/prompt/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                system_prompt: systemPrompt,
                user_instruction: userInstruction || null,
                change_description: changeDescription
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Failed to save prompt');
        }
        
        showNotification('Prompt saved as version ' + data.version, 'success');
    } catch (error) {
        console.error('Error saving prompt:', error);
        showNotification('Error saving prompt: ' + error.message, 'error');
    }
}

async function showSigmaPromptHistory() {
    try {
        const response = await fetch('/api/sigma-queue/prompt/history?limit=50');
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Failed to load history');
        }
        
        // Push to modal stack
        pushModal('promptHistoryModal', true);
        
        const historyList = document.getElementById('promptHistoryList');
        historyList.innerHTML = '';
        
        if (data.history.length === 0) {
            const empty = document.createElement('p');
            empty.className = 'text-gray-500 dark:text-gray-400 text-center py-4';
            empty.textContent = 'No saved versions yet.';
            historyList.appendChild(empty);
        } else {
            data.history.forEach(version => {
                const item = document.createElement('div');
                item.className = 'border border-gray-300 dark:border-gray-600 rounded-md p-3 bg-gray-50 dark:bg-gray-900';

                const dateStr = new Date(version.created_at).toLocaleString();

                // header row
                const header = document.createElement('div');
                header.className = 'flex items-center justify-between mb-2';

                const meta = document.createElement('div');
                const versionSpan = document.createElement('span');
                versionSpan.className = 'font-semibold text-gray-900 dark:text-white mr-2';
                versionSpan.textContent = 'Version ' + version.version;
                const dateSpan = document.createElement('span');
                dateSpan.className = 'text-xs text-gray-500 dark:text-gray-400';
                dateSpan.textContent = dateStr;
                meta.appendChild(versionSpan);
                meta.appendChild(dateSpan);

                const loadBtn = document.createElement('button');
                loadBtn.className = 'px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-md';
                loadBtn.textContent = 'Rollback';
                loadBtn.addEventListener('click', () => loadPromptVersion(version.id));

                header.appendChild(meta);
                header.appendChild(loadBtn);
                item.appendChild(header);

                // optional description
                if (version.change_description) {
                    const desc = document.createElement('p');
                    desc.className = 'text-xs text-gray-500 dark:text-gray-400 mb-2 italic';
                    desc.textContent = version.change_description;
                    item.appendChild(desc);
                }

                // actual prompt text
                const pre = document.createElement('pre');
                pre.className = 'text-xs font-mono text-gray-800 dark:text-gray-200 bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded p-2 max-h-48 overflow-y-auto whitespace-pre-wrap break-words';
                pre.textContent = version.system_prompt;
                item.appendChild(pre);

                historyList.appendChild(item);
            });
        }
    } catch (error) {
        console.error('Error loading history:', error);
        showNotification('Error loading history: ' + error.message, 'error');
    }
}

// closePromptHistoryModal already defined above

async function loadPromptVersion(versionId) {
    try {
        const response = await fetch(`/api/sigma-queue/prompt/load/${versionId}`);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Failed to load prompt version');
        }
        
        // Load the prompt into the textareas
        document.getElementById('enrichSystemPrompt').value = data.system_prompt;
        if (data.user_instruction) {
            document.getElementById('enrichInstruction').value = data.user_instruction;
        }
        _syncEnrichDisplay();
        _enrichSPViewMode();

        // Close history modal
        closePromptHistoryModal();
        
        showNotification('Prompt version loaded', 'success');
    } catch (error) {
        console.error('Error loading prompt version:', error);
        showNotification('Error loading prompt version: ' + error.message, 'error');
    }
}

// --- Enrich preset active-config state tracking ---
// Mirrors the "what's active / what's saved / what's drifted" model used by the
// agent-config prompt editors. enrichLoadedPreset is the preset currently loaded
// into the modal (null = none); enrichBaseline is the config snapshot it was
// loaded/saved at, so edits made on top of a preset surface as "modified".
let enrichLoadedPreset = null;   // { id, name } or null
let enrichBaseline = null;       // { provider, model, systemPrompt, userInstruction }
let _enrichDriftWired = false;

function _enrichCurrentConfig() {
    return {
        provider: document.getElementById('enrichProviderSelect')?.value || '',
        model: document.getElementById('enrichModelSelect')?.value || '',
        systemPrompt: (document.getElementById('enrichSystemPrompt')?.value || '').trim(),
        userInstruction: (document.getElementById('enrichInstruction')?.value || '').trim(),
    };
}

function _captureEnrichBaseline() {
    enrichBaseline = _enrichCurrentConfig();
}

function _enrichConfigDrifted() {
    if (!enrichBaseline) return false;
    const cur = _enrichCurrentConfig();
    return cur.provider !== enrichBaseline.provider
        || cur.model !== enrichBaseline.model
        || cur.systemPrompt !== enrichBaseline.systemPrompt
        || cur.userInstruction !== enrichBaseline.userInstruction;
}

function updateEnrichPresetState() {
    const el = document.getElementById('enrichPresetState');
    if (!el) return;
    const base = 'font-medium px-2 py-0.5 rounded';
    if (!enrichLoadedPreset) {
        el.textContent = 'Unsaved config';
        el.className = base + ' bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300';
    } else if (_enrichConfigDrifted()) {
        el.textContent = `Preset: ${enrichLoadedPreset.name} · modified`;
        el.className = base + ' bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300';
    } else {
        el.textContent = `Preset: ${enrichLoadedPreset.name} · clean`;
        el.className = base + ' bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300';
    }
}

function _wireEnrichDriftListeners() {
    if (_enrichDriftWired) return;
    ['enrichProviderSelect', 'enrichModelSelect'].forEach(id => {
        document.getElementById(id)?.addEventListener('change', updateEnrichPresetState);
    });
    ['enrichInstruction', 'enrichSystemPrompt'].forEach(id => {
        document.getElementById(id)?.addEventListener('input', updateEnrichPresetState);
    });
    _enrichDriftWired = true;
}

async function saveEnrichmentPreset() {
    const provider = document.getElementById('enrichProviderSelect').value;
    const model = document.getElementById('enrichModelSelect').value;
    const systemPrompt = document.getElementById('enrichSystemPrompt').value.trim();
    const userInstruction = document.getElementById('enrichInstruction').value.trim();

    if (!provider || !model) {
        showNotification('Please select both a provider and model', 'error');
        return;
    }

    if (!systemPrompt) {
        showNotification('System prompt cannot be empty', 'error');
        return;
    }

    // Prompt for preset name and description. When a preset is already loaded,
    // default to its name so the save updates it in place (the backend upserts
    // by name); clearing the name and entering a new one saves-as-new.
    const name = await ModalManager.prompt('Enter a name for this preset:', enrichLoadedPreset ? enrichLoadedPreset.name : '', { title: 'Save Preset', confirmText: 'Save', placeholder: 'Preset name' });
    if (!name || !name.trim()) {
        return; // User cancelled
    }

    const description = await ModalManager.prompt('Enter a description (optional):', '', { title: 'Description', confirmText: 'Save', placeholder: 'Optional description' }) || null;
    
    try {
        const response = await fetch('/api/sigma-queue/preset/save', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                name: name.trim(),
                description: description,
                provider: provider,
                model: model,
                system_prompt: systemPrompt,
                user_instruction: userInstruction || null
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Failed to save preset');
        }
        
        // The just-saved config is now the clean baseline for this preset.
        enrichLoadedPreset = { id: data.id, name: name.trim() };
        _captureEnrichBaseline();
        updateEnrichPresetState();

        showNotification('Preset "' + name + '" ' + data.message, 'success');
    } catch (error) {
        console.error('Error saving preset:', error);
        showNotification('Error saving preset: ' + error.message, 'error');
    }
}

async function showPresetList() {
    try {
        const response = await fetch('/api/sigma-queue/preset/list');
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Failed to load presets');
        }
        
        // Push to modal stack
        pushModal('presetListModal', true);
        
        const presetList = document.getElementById('presetList');
        presetList.innerHTML = '';
        
        if (data.presets.length === 0) {
            presetList.innerHTML = '<p class="text-gray-500 dark:text-gray-400 text-center py-4">No presets saved yet.</p>';
        } else {
            data.presets.forEach(preset => {
                const item = document.createElement('div');
                item.className = 'border border-gray-300 dark:border-gray-600 rounded-md p-3 bg-gray-50 dark:bg-gray-900';
                
                const date = new Date(preset.updated_at);
                const dateStr = date.toLocaleString();
                
                item.innerHTML = `
                    <div class="flex items-start justify-between">
                        <div class="flex-1">
                            <div class="flex items-center space-x-2 mb-2">
                                <span class="font-semibold text-gray-900 dark:text-white">${escapeHtml(preset.name)}</span>
                                <span class="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded">${escapeHtml(preset.provider)}</span>
                                <span class="text-xs px-2 py-1 bg-purple-100 dark:bg-purple-900 text-purple-800 dark:text-purple-200 rounded">${escapeHtml(preset.model)}</span>
                            </div>
                            ${preset.description ? `<p class="text-sm text-gray-600 dark:text-gray-400 mb-2">${escapeHtml(preset.description)}</p>` : ''}
                            <div class="text-xs text-gray-500 dark:text-gray-400">
                                Updated: ${dateStr}
                            </div>
                        </div>
                        <div class="flex space-x-2 ml-4">
                            <button onclick="loadPresetById(${preset.id})" class="px-3 py-1 text-xs bg-blue-600 hover:bg-blue-700 text-white rounded-md">
                                Load
                            </button>
                            <button onclick="deletePreset(${preset.id}, '${escapeHtml(preset.name)}')" class="px-3 py-1 text-xs bg-red-600 hover:bg-red-700 text-white rounded-md">
                                Delete
                            </button>
                        </div>
                    </div>
                `;
                
                presetList.appendChild(item);
            });
        }
    } catch (error) {
        console.error('Error loading presets:', error);
        const errorMessage = error instanceof Error ? error.message : 
                           (typeof error === 'string' ? error : 
                           (error?.message || JSON.stringify(error) || 'Unknown error'));
        showNotification('Error loading presets: ' + errorMessage, 'error');
    }
}

function closePresetListModal() {
    if (window.ModalManager) {
        window.ModalManager.close('presetListModal');
    } else {
        popModal();
    }
}

async function loadPresetById(presetId, opts = {}) {
    const { silent = false } = opts;
    try {
        // Ensure presetId is an integer
        const id = parseInt(presetId, 10);
        if (isNaN(id)) {
            throw new Error(`Invalid preset ID: ${presetId}`);
        }
        
        const response = await fetch(`/api/sigma-queue/preset/${id}`);
        
        let data;
        try {
            data = await response.json();
        } catch (jsonError) {
            // If response is not JSON, use status text
            throw new Error(`Server error (${response.status}): ${response.statusText || 'Failed to load preset'}`);
        }
        
        if (!response.ok) {
            const errorMsg = extractErrorMessage(data, `Failed to load preset (${response.status})`);
            throw new Error(errorMsg);
        }
        
        // Load the preset into the form
        document.getElementById('enrichProviderSelect').value = data.provider;
        await populateEnrichModelDropdown(data.provider);

        const modelSelect = document.getElementById('enrichModelSelect');
        modelSelect.value = data.model;
        if (data.model && modelSelect.value !== data.model) {
            console.warn(`loadPresetById: model "${data.model}" not found in catalog for provider "${data.provider}"`);
        }
        
        document.getElementById('enrichSystemPrompt').value = data.system_prompt;
        if (data.user_instruction) {
            document.getElementById('enrichInstruction').value = data.user_instruction;
        } else {
            document.getElementById('enrichInstruction').value = '';
        }
        // The textarea is the source of truth but is hidden in view mode; the
        // visible #enrichSystemPromptDisplay div must be refreshed or the preset's
        // system prompt stays invisible (and an Edit->Cancel would discard it).
        _syncEnrichDisplay();
        _enrichSPViewMode();

        // Record the loaded preset + its config snapshot so later edits read as drift.
        enrichLoadedPreset = { id, name: data.name };
        _captureEnrichBaseline();
        updateEnrichPresetState();

        localStorage.setItem('enrichmentLastPresetId', String(id));

        if (!silent) {
            closePresetListModal();
            showNotification('Preset "' + data.name + '" loaded', 'success');
        }
    } catch (error) {
        console.error('Error loading preset:', error);
        if (silent) throw error;
        const errorMessage = error instanceof Error ? error.message : 
                           (typeof error === 'string' ? error : 
                           (error?.message || JSON.stringify(error) || 'Unknown error'));
        showNotification('Error loading preset: ' + errorMessage, 'error');
    }
}

async function deletePreset(presetId, presetName) {
    if (!await ModalManager.confirm(`Are you sure you want to delete preset "${presetName}"?`, { title: 'Delete Preset', confirmText: 'Delete', confirmClass: 'bg-red-600 hover:bg-red-700' })) {
        return;
    }
    
    try {
        // Ensure presetId is an integer
        const id = parseInt(presetId, 10);
        if (isNaN(id)) {
            throw new Error(`Invalid preset ID: ${presetId}`);
        }
        
        const response = await fetch(`/api/sigma-queue/preset/${id}`, {
            method: 'DELETE'
        });
        
        let data;
        try {
            data = await response.json();
        } catch (jsonError) {
            throw new Error(`Server error (${response.status}): ${response.statusText || 'Failed to delete preset'}`);
        }
        
        if (!response.ok) {
            const errorMsg = extractErrorMessage(data, `Failed to delete preset (${response.status})`);
            throw new Error(errorMsg);
        }
        
        if (localStorage.getItem('enrichmentLastPresetId') === String(id)) {
            localStorage.removeItem('enrichmentLastPresetId');
        }
        
        // Reload preset list
        await showPresetList();
        
        showNotification('Preset "' + presetName + '" deleted', 'success');
    } catch (error) {
        console.error('Error deleting preset:', error);
        const errorMessage = error instanceof Error ? error.message : 
                           (typeof error === 'string' ? error : 
                           (error?.message || JSON.stringify(error) || 'Unknown error'));
        showNotification('Error deleting preset: ' + errorMessage, 'error');
    }
}

async function restoreLastEnrichmentPreset() {
    if (enrichmentPresetRestoredThisSession) return;
    const raw = localStorage.getItem('enrichmentLastPresetId');
    if (!raw) return;
    const id = parseInt(raw, 10);
    if (isNaN(id)) {
        localStorage.removeItem('enrichmentLastPresetId');
        return;
    }
    if (!document.getElementById('enrichProviderSelect')) return;
    try {
        await loadPresetById(id, { silent: true });
        enrichmentPresetRestoredThisSession = true;
    } catch (e) {
        localStorage.removeItem('enrichmentLastPresetId');
    }
}

// escapeHtml now lives in /static/js/utils.js (loaded from base.html).

async function generateEnrichmentDiff(originalYaml, enrichedYaml) {
    const diffView = document.getElementById('enrichDiffView');
    const diffError = document.getElementById('enrichDiffError');
    const diffContent = document.getElementById('enrichDiffContent');
    
    if (!diffView) {
        console.warn('Diff view element not found');
        return;
    }
    
    function showDiffError(html) {
        diffView.classList.remove('hidden');
        if (diffError) {
            diffError.innerHTML = html;
            diffError.classList.remove('hidden');
        }
        if (diffContent) diffContent.classList.add('hidden');
    }
    
    function hideDiffError() {
        if (diffError) {
            diffError.innerHTML = '';
            diffError.classList.add('hidden');
        }
        if (diffContent) diffContent.classList.remove('hidden');
    }
    
    // Basic validation - check if rules are not empty
    if (!originalYaml || !originalYaml.trim()) {
        showDiffError(`<div class="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
            <div class="flex items-center">
                <span class="text-amber-400 dark:text-yellow-400 font-semibold mr-2"><svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg> Warning:</span>
                <span class="text-yellow-800 dark:text-yellow-200">Original rule is empty. Cannot compare.</span>
            </div>
        </div>`);
        return;
    }
    
    if (!enrichedYaml || !enrichedYaml.trim()) {
        showDiffError(`<div class="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
            <div class="flex items-center">
                <span class="text-amber-400 dark:text-yellow-400 font-semibold mr-2"><svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg> Warning:</span>
                <span class="text-yellow-800 dark:text-yellow-200">Enriched rule is empty. Cannot compare.</span>
            </div>
        </div>`);
        return;
    }
    
    hideDiffError();
    diffView.classList.remove('hidden');
    const overallSimilarityEl = document.getElementById('enrichOverallSimilarity');
    const noveltyLabelEl = document.getElementById('enrichNoveltyLabel');
    const similarityBarEl = document.getElementById('enrichSimilarityBar');
    
    if (overallSimilarityEl) overallSimilarityEl.textContent = '...';
    if (noveltyLabelEl) noveltyLabelEl.textContent = '';
    if (similarityBarEl) similarityBarEl.style.width = '0%';
    
    try {
        // Call the sigma-ab-test compare endpoint
        const response = await fetch('/api/sigma-ab-test/compare', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                rule_a: originalYaml,
                rule_b: enrichedYaml
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            // Extract detailed error message
            let errorMsg = 'Failed to compare rules';
            if (data.detail) {
                errorMsg = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
            } else if (data.error) {
                errorMsg = data.error;
            } else if (data.message) {
                errorMsg = data.message;
            }
            throw new Error(errorMsg);
        }
        
        if (!data.success) {
            throw new Error(data.error || data.detail || 'Comparison returned unsuccessful result');
        }
        
        // Ensure diffView is visible and structure is preserved
        diffView.classList.remove('hidden');
        
        // Verify the HTML structure exists before updating
        const testEl = document.getElementById('enrichOverallSimilarity');
        if (!testEl) {
            console.error('enrichDiffView structure missing - elements not found');
            throw new Error('Comparison view structure not found in DOM');
        }
        
        // Display results using standardized similarity display component
        updateSimilarityDisplay(data, { prefix: 'enrich' });
        
    } catch (error) {
        console.error('Error generating enrichment diff:', error);
        const errorMsg = error.message || 'Failed to compare rules';
        const isValidationError = errorMsg.includes('validation') || errorMsg.includes('Invalid YAML') || errorMsg.includes('Rule') || errorMsg.includes('validation');
        const errorHtml = `<div class="card-elevated p-6">
            <h3 class="text-xl font-semibold text-gray-900 dark:text-white mb-4">Comparison Error</h3>
            <div class="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                <div class="flex items-start">
                    <span class="text-red-600 dark:text-red-400 font-semibold mr-2 mt-1">❌</span>
                    <div class="flex-1">
                        <div class="text-red-800 dark:text-red-200 font-semibold mb-2">${isValidationError ? 'Validation Error' : 'Comparison Failed'}</div>
                        <div class="text-red-700 dark:text-red-300 text-sm whitespace-pre-wrap">${escapeHtml(errorMsg)}</div>
                        ${isValidationError ? '<div class="text-red-600 dark:text-red-400 text-xs mt-2 italic">Tip: The enriched output may include prose before the YAML. Comparison extracts the YAML block when possible.</div>' : ''}
                    </div>
                </div>
            </div>
        </div>`;
        showDiffError(errorHtml);
    }
}

async function enrichRule() {
    // Disable immediately to prevent double-click; re-enable on any early return.
    const enrichBtn = document.getElementById('enrichBtn');
    enrichBtn.disabled = true;
    enrichBtn.textContent = 'Enriching...';
    enrichBtn.classList.add('opacity-75', 'cursor-not-allowed');

    const rule = queue.find(r => r.id === currentRuleId);
    if (!rule) {
        enrichBtn.disabled = false;
        enrichBtn.textContent = 'Enrich Rule';
        enrichBtn.classList.remove('opacity-75', 'cursor-not-allowed');
        return;
    }

    // Get selected provider and model
    const providerSelect = document.getElementById('enrichProviderSelect');
    const modelSelect = document.getElementById('enrichModelSelect');
    const selectedProvider = providerSelect ? providerSelect.value : '';
    const selectedModel = modelSelect ? modelSelect.value : '';

    if (!selectedProvider || !selectedModel) {
        document.getElementById('enrichError').textContent = 'Please select both a provider and model.';
        document.getElementById('enrichError').classList.remove('hidden');
        enrichBtn.disabled = false;
        enrichBtn.textContent = 'Enrich Rule';
        enrichBtn.classList.remove('opacity-75', 'cursor-not-allowed');
        return;
    }

    // Get API key from server-side settings (not needed for LMStudio)
    let apiKey = null;
    if (selectedProvider !== 'lmstudio') {
        try {
            const response = await fetch('/api/settings');
            if (response.ok) {
                const data = await response.json();
                const settings = data.settings || {};

                // Get API key based on selected provider
                if (selectedProvider === 'openai') {
                    apiKey = settings.WORKFLOW_OPENAI_API_KEY || settings.OPENAI_API_KEY;
                } else if (selectedProvider === 'anthropic') {
                    apiKey = settings.WORKFLOW_ANTHROPIC_API_KEY || settings.ANTHROPIC_API_KEY;
                }
            }
        } catch (error) {
            console.warn('Could not fetch API key from settings API:', error);
        }

        if (!apiKey || !apiKey.trim()) {
            const providerName = selectedProvider.charAt(0).toUpperCase() + selectedProvider.slice(1);
            document.getElementById('enrichError').textContent = `Please configure your ${providerName} API key in Settings first.`;
            document.getElementById('enrichError').classList.remove('hidden');
            console.error('API key not found for provider:', selectedProvider);
            enrichBtn.disabled = false;
            enrichBtn.textContent = 'Enrich Rule';
            enrichBtn.classList.remove('opacity-75', 'cursor-not-allowed');
            return;
        }

        // Trim API key to remove any whitespace
        apiKey = apiKey.trim();
    }

    const instruction = 'Validate and minimally enrich this SIGMA rule per the enabled directives. Preserve detection logic. Return the JSON output contract only.';
    const systemPrompt = document.getElementById('enrichSystemPrompt').value.trim();

    // Show loading, hide error and result (button already disabled above)
    
    document.getElementById('enrichLoading').classList.remove('hidden');
    document.getElementById('enrichError').classList.add('hidden');
    document.getElementById('enrichResult').classList.add('hidden');
    
    try {
        // Determine which header to use based on provider (LMStudio doesn't need API key)
        const headers = {
            'Content-Type': 'application/json'
        };
        if (selectedProvider !== 'lmstudio' && apiKey) {
            const headerKey = selectedProvider === 'openai' ? 'X-OpenAI-API-Key' :
                             selectedProvider === 'anthropic' ? 'X-Anthropic-API-Key' :
                             'X-OpenAI-API-Key';
            headers[headerKey] = apiKey;
        }
        
        const includeArticleContent = document.getElementById('includeArticleContent').checked;
        
        const requestBody = {
            instruction: instruction || undefined,
            system_prompt: systemPrompt || undefined,
            provider: selectedProvider,
            model: selectedModel,
            include_article_content: includeArticleContent,
            current_rule_yaml: document.getElementById('enrichOriginalRule').value
        };
        
        console.log('Sending enrich request:', {
            url: `/api/sigma-queue/${currentRuleId}/enrich`,
            provider: selectedProvider,
            model: selectedModel,
            hasApiKey: !!apiKey
        });
        
        const response = await fetch(`/api/sigma-queue/${currentRuleId}/enrich`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(requestBody)
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            // Show error message from server
            const errorMsg = data.detail || data.message || `Error: ${response.status} ${response.statusText}`;
            document.getElementById('enrichError').textContent = errorMsg;
            document.getElementById('enrichError').classList.remove('hidden');
            console.error('Enrichment failed:', errorMsg, data);
            return;
        }
        
        if (data.success) {
            const enrichedYaml = data.enriched_yaml;
            const rawResponse = data.raw_response || enrichedYaml;
            enrichIteration++;
            
            // Determine what to compare against (before updating currentEnrichedYaml)
            const previousYaml = currentEnrichedYaml || document.getElementById('enrichOriginalRule').value;
            const isIterative = currentEnrichedYaml !== null;
            
            console.log('Enrichment successful, showing comparison view', { iteration: enrichIteration, isIterative });
            
            // Get all elements first
            const enrichResult = document.getElementById('enrichResult');
            const comparisonView = document.getElementById('enrichComparisonView');
            const textarea = document.getElementById('enrichedRuleYaml');
            const toggleBtn = document.getElementById('toggleViewBtn');
            const originalComparison = document.getElementById('enrichOriginalComparison');
            const enrichedComparison = document.getElementById('enrichedComparison');
            const applyBtn = document.getElementById('applyEnrichBtn');
            const enrichBtn = document.getElementById('enrichBtn');
            const enrichFurtherBtn = document.getElementById('enrichFurtherBtn');
            const leftLabel = document.getElementById('enrichLeftLabel');
            const rightLabel = document.getElementById('enrichRightLabel');
            const iterationInfo = document.getElementById('enrichIterationInfo');
            const rawResponseText = document.getElementById('rawResponseText');
            
            if (!enrichResult || !comparisonView || !textarea || !toggleBtn) {
                console.error('Missing elements for comparison view');
                showNotification('Could not display comparison view. Please check console.', 'error');
                return;
            }
            
            // Update current enriched state
            currentEnrichedYaml = enrichedYaml;
            
            // Set enriched rule in textarea
            textarea.value = enrichedYaml;
            
            setRawLLMResponse(rawResponse);
            
            // Update labels and info based on iteration
            if (isIterative) {
                leftLabel.textContent = `Previous (Iteration ${enrichIteration - 1})`;
                rightLabel.textContent = `Enriched (Iteration ${enrichIteration})`;
                iterationInfo.textContent = `🔄 Iterative enrichment - This is iteration #${enrichIteration}. Building on previous enrichment.`;
            } else {
                leftLabel.textContent = 'Original Rule';
                rightLabel.textContent = 'Enriched Rule';
                iterationInfo.textContent = '';
            }
            
            // Populate comparison view
            originalComparison.textContent = previousYaml;
            enrichedComparison.textContent = enrichedYaml;
            
            // Generate and display A/B diff automatically
            await generateEnrichmentDiff(previousYaml, enrichedYaml);
            
            // Show result section first
            enrichResult.classList.remove('hidden');
            // The original rule now lives inside the comparison view, so hide the
            // standalone input block to avoid showing it twice.
            document.getElementById('enrichOriginalSection')?.classList.add('hidden');

            // Force a reflow to ensure DOM is updated
            enrichResult.offsetHeight;
            
            // Show comparison view by default
            comparisonView.classList.remove('hidden');
            textarea.classList.add('hidden');
            toggleBtn.textContent = '📝 Show Editor';
            
            // Scroll comparison view into view if needed
            setTimeout(() => {
                comparisonView.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 100);
            
            // Show buttons
            applyBtn.classList.remove('hidden');
            enrichBtn.classList.add('hidden');
            enrichFurtherBtn.classList.remove('hidden'); // Show "Enrich Further" button
            
            console.log('Comparison view should now be visible');
        } else {
            document.getElementById('enrichError').textContent = data.detail || 'Error enriching rule';
            document.getElementById('enrichError').classList.remove('hidden');
        }
    } catch (error) {
        console.error('Error enriching rule:', error);
        document.getElementById('enrichError').textContent = 'Network error: ' + error.message;
        document.getElementById('enrichError').classList.remove('hidden');
    } finally {
        document.getElementById('enrichLoading').classList.add('hidden');
        const enrichBtn = document.getElementById('enrichBtn');
        enrichBtn.disabled = false;
        enrichBtn.innerHTML = '✨ Enrich Rule';
        enrichBtn.classList.remove('opacity-75', 'cursor-not-allowed');
    }
}

async function applyEnrichedRule() {
    const enrichedYaml = document.getElementById('enrichedRuleYaml').value;
    if (!enrichedYaml.trim()) {
        showNotification('No enriched rule to apply', 'warning');
        return;
    }
    
    if (!await ModalManager.confirm('Apply the enriched rule? This will update the rule YAML.', { title: 'Apply Enriched Rule', confirmText: 'Apply', confirmClass: 'bg-purple-600 hover:bg-purple-700' })) return;
    
    try {
        const response = await fetch(`/api/sigma-queue/${currentRuleId}/yaml`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rule_yaml: enrichedYaml })
        });
        
        if (response.ok) {
            // Close only the enrich modal
            closeEnrichModal();
            
            // Update the rule in the queue array
            const rule = queue.find(r => r.id === currentRuleId);
            if (rule) {
                rule.rule_yaml = enrichedYaml;
                // Update editedYaml and originalYaml to reflect the change
                editedYaml = enrichedYaml;
                originalYaml = enrichedYaml;
                isEditMode = false;
                
                // Re-render the rule preview with updated YAML
                renderRulePreview(rule);
            }
            
            // Reload queue in background to sync with server
            loadQueue().catch(err => console.error('Error reloading queue:', err));
        } else {
            showNotification('Error applying enriched rule', 'error');
        }
    } catch (error) {
        console.error('Error applying enriched rule:', error);
        showNotification('Error applying enriched rule', 'error');
    }
}

// Close enrich modal when clicking outside
const enrichModal = document.getElementById('enrichModal');
if (enrichModal) {
    enrichModal.addEventListener('click', function(e) {
        if (e.target === this) {
            closeEnrichModal();
        }
    });
}

// Enrich modal escape handling is now done by the unified escape handler below

async function enrichRuleFurther() {
    // Use the current enriched rule as the base for further enrichment
    if (!currentEnrichedYaml) {
        showNotification('No enriched rule to build upon. Please enrich the rule first.', 'warning');
        return;
    }
    
    // Get selected provider and model
    const providerSelect = document.getElementById('enrichProviderSelect');
    const modelSelect = document.getElementById('enrichModelSelect');
    const selectedProvider = providerSelect ? providerSelect.value : '';
    const selectedModel = modelSelect ? modelSelect.value : '';
    
    if (!selectedProvider || !selectedModel) {
        document.getElementById('enrichError').textContent = 'Please select both a provider and model.';
        document.getElementById('enrichError').classList.remove('hidden');
        return;
    }
    
    // Get API key from server-side settings (not needed for LMStudio)
    let apiKey = null;
    if (selectedProvider !== 'lmstudio') {
        try {
            const response = await fetch('/api/settings');
            if (response.ok) {
                const data = await response.json();
                const settings = data.settings || {};
                
                // Get API key based on selected provider
                if (selectedProvider === 'openai') {
                    apiKey = settings.WORKFLOW_OPENAI_API_KEY || settings.OPENAI_API_KEY;
                } else if (selectedProvider === 'anthropic') {
                    apiKey = settings.WORKFLOW_ANTHROPIC_API_KEY || settings.ANTHROPIC_API_KEY;
                }
            }
        } catch (error) {
            console.warn('Could not fetch API key from settings API:', error);
        }
        
        if (!apiKey || !apiKey.trim()) {
            const providerName = selectedProvider.charAt(0).toUpperCase() + selectedProvider.slice(1);
            document.getElementById('enrichError').textContent = `Please configure your ${providerName} API key in Settings first.`;
            document.getElementById('enrichError').classList.remove('hidden');
            return;
        }
        
        // Trim API key
        apiKey = apiKey.trim();
    }
    
    // Prompt for new instruction
    const newInstruction = await ModalManager.prompt('Enter additional enrichment instructions (or leave empty for default):\n\nThis will enrich the already-enriched rule further.', '', { title: 'Enrich Rule', confirmText: 'Enrich', placeholder: 'Additional instructions' });
    
    if (newInstruction === null) return; // User cancelled
    
    const systemPrompt = document.getElementById('enrichSystemPrompt').value.trim();
    const includeArticleContent = document.getElementById('includeArticleContent').checked;
    
    // Show loading
    const enrichFurtherBtn = document.getElementById('enrichFurtherBtn');
    enrichFurtherBtn.disabled = true;
    enrichFurtherBtn.innerHTML = '<span class="inline-block animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></span>Enriching Further...';
    enrichFurtherBtn.classList.add('opacity-75', 'cursor-not-allowed');
    
    document.getElementById('enrichLoading').classList.remove('hidden');
    document.getElementById('enrichError').classList.add('hidden');
    
    try {
        // Determine which header to use based on provider (LMStudio doesn't need API key)
        const headers = {
            'Content-Type': 'application/json'
        };
        if (selectedProvider !== 'lmstudio' && apiKey) {
            const headerKey = selectedProvider === 'openai' ? 'X-OpenAI-API-Key' :
                             selectedProvider === 'anthropic' ? 'X-Anthropic-API-Key' :
                             'X-OpenAI-API-Key';
            headers[headerKey] = apiKey;
        }
        
        const response = await fetch(`/api/sigma-queue/${currentRuleId}/enrich`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({
                instruction: newInstruction.trim() || undefined,
                system_prompt: systemPrompt || undefined,
                provider: selectedProvider,
                model: selectedModel,
                current_rule_yaml: currentEnrichedYaml,  // Pass current enriched YAML
                include_article_content: includeArticleContent
            })
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            // Show error message from server
            const errorMsg = data.detail || data.message || `Error: ${response.status} ${response.statusText}`;
            document.getElementById('enrichError').textContent = errorMsg;
            document.getElementById('enrichError').classList.remove('hidden');
            console.error('Enrichment failed:', errorMsg, data);
            return;
        }
        
        if (data.success) {
            const enrichedYaml = data.enriched_yaml;
            const rawResponse = data.raw_response || enrichedYaml;
            enrichIteration++;
            
            // Get previous version for comparison
            const previousYaml = currentEnrichedYaml;
            
            // Get all elements
            const enrichResult = document.getElementById('enrichResult');
            const comparisonView = document.getElementById('enrichComparisonView');
            const textarea = document.getElementById('enrichedRuleYaml');
            const toggleBtn = document.getElementById('toggleViewBtn');
            const originalComparison = document.getElementById('enrichOriginalComparison');
            const enrichedComparison = document.getElementById('enrichedComparison');
            const leftLabel = document.getElementById('enrichLeftLabel');
            const rightLabel = document.getElementById('enrichRightLabel');
            const iterationInfo = document.getElementById('enrichIterationInfo');
            const rawResponseText = document.getElementById('rawResponseText');
            
            // Update current enriched state
            currentEnrichedYaml = enrichedYaml;
            
            // Set enriched rule in textarea
            textarea.value = enrichedYaml;
            
            setRawLLMResponse(rawResponse);
            
            // Update labels for iterative enrichment
            leftLabel.textContent = `Previous (Iteration ${enrichIteration - 1})`;
            rightLabel.textContent = `Enriched (Iteration ${enrichIteration})`;
            iterationInfo.textContent = `🔄 Iterative enrichment - This is iteration #${enrichIteration}. Building on previous enrichment.`;
            
            // Populate comparison view
            originalComparison.textContent = previousYaml;
            enrichedComparison.textContent = enrichedYaml;
            
            // Generate and display A/B diff automatically
            await generateEnrichmentDiff(previousYaml, enrichedYaml);
            
            // Ensure views are visible
            enrichResult.classList.remove('hidden');
            comparisonView.classList.remove('hidden');
            textarea.classList.add('hidden');
            toggleBtn.textContent = '📝 Show Editor';
            
            // Scroll into view
            setTimeout(() => {
                comparisonView.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 100);
            
        } else {
            document.getElementById('enrichError').textContent = data.detail || 'Error enriching rule further';
            document.getElementById('enrichError').classList.remove('hidden');
        }
    } catch (error) {
        console.error('Error enriching rule further:', error);
        document.getElementById('enrichError').textContent = 'Network error: ' + error.message;
        document.getElementById('enrichError').classList.remove('hidden');
    } finally {
        document.getElementById('enrichLoading').classList.add('hidden');
        enrichFurtherBtn.disabled = false;
        enrichFurtherBtn.innerHTML = '🔄 Enrich Further';
        enrichFurtherBtn.classList.remove('opacity-75', 'cursor-not-allowed');
    }
}

function toggleEnrichView() {
    const comparisonView = document.getElementById('enrichComparisonView');
    const toggleBtn = document.getElementById('toggleViewBtn');
    const textarea = document.getElementById('enrichedRuleYaml');
    
    if (!comparisonView || !toggleBtn || !textarea) {
        console.error('Toggle enrich view: elements not found');
        return;
    }
    
    if (comparisonView.classList.contains('hidden')) {
        comparisonView.classList.remove('hidden');
        textarea.classList.add('hidden');
        toggleBtn.textContent = '📝 Show Editor';
    } else {
        comparisonView.classList.add('hidden');
        textarea.classList.remove('hidden');
        toggleBtn.textContent = '📊 Show Comparison';
    }
}

function toggleRawResponse() {
    const content = document.getElementById('rawResponseContent');
    const toggle = document.getElementById('rawResponseToggle');
    const caret = document.getElementById('rawResponseCaret');
    
    if (!content || !toggle) {
        console.error('Toggle raw response: elements not found');
        return;
    }
    
    const isHidden = content.classList.contains('hidden');
    if (isHidden) {
        content.classList.remove('hidden');
        toggle.setAttribute('aria-expanded', 'true');
        if (caret) caret.textContent = '▲';
    } else {
        content.classList.add('hidden');
        toggle.setAttribute('aria-expanded', 'false');
        if (caret) caret.textContent = '▼';
    }
}

function normalizeRawLLMList(value) {
    if (Array.isArray(value)) return value;
    if (value === null || value === undefined || value === '') return [];
    return [value];
}

function formatRawLLMValue(value) {
    if (typeof value === 'string') return value;
    return JSON.stringify(value, null, 2);
}

function rawLLMListHtml(items) {
    const normalized = normalizeRawLLMList(items);
    if (!normalized.length) {
        return '<p class="text-xs text-gray-500 dark:text-gray-400 italic">None reported.</p>';
    }
    return `<ul class="list-disc list-inside space-y-1 text-sm text-gray-800 dark:text-gray-200">${normalized.map(item => `<li>${escapeHtml(formatRawLLMValue(item))}</li>`).join('')}</ul>`;
}

function rawLLMFieldHtml(label, value) {
    if (value === null || value === undefined || value === '') return '';
    return `
        <div>
            <h5 class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">${escapeHtml(label)}</h5>
            <div class="text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap">${escapeHtml(formatRawLLMValue(value))}</div>
        </div>
    `;
}

function formatRawLLMResponse(rawResponse) {
    const rawText = String(rawResponse || '').trim();
    if (!rawText) {
        return '<p class="text-sm text-gray-500 dark:text-gray-400 italic">No raw response returned.</p>';
    }

    let parsed;
    try {
        parsed = JSON.parse(rawText);
    } catch (_) {
        return `<pre class="font-mono whitespace-pre-wrap overflow-x-auto text-xs text-gray-900 dark:text-gray-100">${escapeHtml(rawText)}</pre>`;
    }

    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
        return `<pre class="font-mono whitespace-pre-wrap overflow-x-auto text-xs text-gray-900 dark:text-gray-100">${escapeHtml(JSON.stringify(parsed, null, 2))}</pre>`;
    }

    const knownFields = new Set(['status', 'summary', 'actions_taken', 'issues', 'updated_sigma_yaml']);
    const extraFields = Object.keys(parsed).filter(key => !knownFields.has(key));
    const status = parsed.status ? String(parsed.status) : 'unknown';
    const yaml = parsed.updated_sigma_yaml ? String(parsed.updated_sigma_yaml) : '';

    return `
        <div class="space-y-4">
            <div class="flex items-center gap-2">
                <h4 class="text-sm font-semibold text-gray-900 dark:text-gray-100">LLM Response</h4>
                <span class="inline-flex items-center rounded border border-gray-300 dark:border-gray-600 px-2 py-0.5 text-xs font-medium tracking-wide text-gray-700 dark:text-gray-300">${escapeHtml(status.toUpperCase())}</span>
            </div>
            ${rawLLMFieldHtml('Summary', parsed.summary)}
            <div>
                <h5 class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">Actions Taken</h5>
                ${rawLLMListHtml(parsed.actions_taken)}
            </div>
            <div>
                <h5 class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">Issues</h5>
                ${rawLLMListHtml(parsed.issues)}
            </div>
            ${yaml ? `
                <div>
                    <h5 class="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-1">Updated Sigma YAML</h5>
                    <pre class="font-mono whitespace-pre-wrap overflow-x-auto text-xs bg-white dark:bg-gray-950 border border-gray-200 dark:border-gray-700 rounded p-3 text-gray-900 dark:text-gray-100">${escapeHtml(yaml)}</pre>
                </div>
            ` : ''}
            ${extraFields.map(key => rawLLMFieldHtml(key.replace(/_/g, ' '), parsed[key])).join('')}
        </div>
    `;
}

function setRawLLMResponse(rawResponse) {
    const rawResponseText = document.getElementById('rawResponseText');
    if (rawResponseText) {
        rawResponseText.innerHTML = formatRawLLMResponse(rawResponse);
    }
}

// Close modal when clicking outside
const ruleModal = document.getElementById('ruleModal');
if (ruleModal) {
    ruleModal.addEventListener('click', function(e) {
        if (e.target === this) {
            closeRuleModal();
        }
    });
}
