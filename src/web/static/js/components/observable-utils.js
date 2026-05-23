/**
 * Observable utility functions shared across workflow.html,
 * workflow_executions.html, and sigma_queue.html.
 *
 * OBS_TYPE_ORDER MUST stay in sync with AGENT_NAMES_SUB in
 * src/config/workflow_config_schema.py — verified by
 * TestCanonicalObservableOrderContract in
 * tests/unit/test_observable_traceability_regressions.py.
 */

const OBS_TYPE_ORDER = ['cmdline', 'process_lineage', 'hunt_queries', 'registry_artifacts', 'windows_services', 'scheduled_tasks'];

function filterObservablesForRule(rule, observablesData) {
    if (!observablesData?.observables) return observablesData;
    var indices = (rule.rule_metadata && rule.rule_metadata.observables_used) || null;
    const emptyObs = Object.fromEntries(OBS_TYPE_ORDER.map(t => [t, []]));
    if (!indices || !Array.isArray(indices) || indices.length === 0) return { observables: emptyObs };
    var flat = [].concat(...OBS_TYPE_ORDER.map(t => observablesData.observables[t] || []));
    var keep = {};
    indices.forEach(function(i) { if (i >= 0 && i < flat.length) keep[i] = true; });
    var offset = 0;
    var result = {};
    OBS_TYPE_ORDER.forEach(function(t) {
        var bucket = observablesData.observables[t] || [];
        result[t] = bucket.filter(function(_, idx) { return keep[offset + idx]; });
        offset += bucket.length;
    });
    return { observables: result };
}

const typeLabels = { cmdline: 'Command-line', process_lineage: 'Process Tree', hunt_queries: 'Hunt Queries', registry_artifacts: 'Registry Artifacts', windows_services: 'Windows Services', scheduled_tasks: 'Scheduled Tasks' };

// All observable values inserted into HTML are escaped with .replace(/</g,'&lt;') before use.
function observablesUsedSection(rule, observablesData) {
    const filtered = filterObservablesForRule(rule, observablesData);
    if (!filtered || !filtered.observables) return '';
    const obs = filtered.observables;
    const total = OBS_TYPE_ORDER.reduce((sum, t) => sum + (obs[t]?.length || 0), 0);
    if (total === 0) return '<div class="mt-4"><details open class="border border-gray-600 rounded-lg"><summary class="cursor-pointer px-3 py-2 font-semibold text-gray-300">Observables Used</summary><p class="px-3 pb-3 text-gray-400 text-sm">No observables for this execution.</p></details></div>';
    function confidenceBadge(score) {
        if (score == null) return '<span class="text-gray-500 text-xs">N/A</span>';
        const pct = Math.round(Number(score) * 100);
        const cls = pct >= 80 ? 'bg-green-900/40 text-green-300' : pct >= 50 ? 'bg-yellow-900/40 text-yellow-300' : 'bg-red-900/40 text-red-300';
        return `<span class="px-2 py-0.5 rounded text-xs font-medium ${cls}">${pct}%</span>`;
    }
    let html = '<div class="mt-4"><details open class="border border-gray-600 rounded-lg"><summary class="cursor-pointer px-3 py-2 font-semibold text-gray-300">Observables Used (' + total + ')</summary><div class="px-3 pb-3 space-y-2">';
    for (const [typeKey, label] of Object.entries(typeLabels)) {
        const list = obs[typeKey] || [];
        if (list.length === 0) continue;
        html += `<details open class="border border-gray-600 rounded p-2 bg-gray-900/50"><summary class="cursor-pointer text-sm font-medium text-gray-200">${label} (${list.length})</summary><div class="mt-2 space-y-2">`;
        list.forEach((ob, idx) => {
            const val = typeof ob.observable_value === 'object' ? JSON.stringify(ob.observable_value) : String(ob.observable_value ?? '');
            const safeVal = val.replace(/</g, '&lt;').replace(/>/g, '&gt;');
            const hasTrace = ob.source_evidence != null || ob.extraction_justification != null;
            const infoId = 'obs-info-' + rule.id + '-' + typeKey + '-' + idx;
            html += `<div class="flex items-center gap-2 flex-wrap border-b border-gray-700 pb-2"><code class="text-xs break-all text-gray-300">${safeVal}</code> ${confidenceBadge(ob.confidence_score)}`;
            if (hasTrace) html += ` <button type="button" class="text-xs text-blue-400 hover:text-blue-300 cursor-pointer" onclick="showObservableInfoModal('${infoId}')" title="Show justification and source">ⓘ</button>`;
            html += '</div>';
            if (hasTrace) {
                const modalContent = `<div class="space-y-2 text-left text-sm"><div><strong class="text-gray-300">Value:</strong><pre class="mt-1 p-2 bg-gray-900 rounded text-xs text-gray-300 break-all">${safeVal}</pre></div>${ob.extraction_justification != null ? `<div><strong class="text-gray-300">Reasoning:</strong><p class="mt-1 text-gray-400">${String(ob.extraction_justification).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</p></div>` : ''}${ob.source_evidence != null ? `<div><strong class="text-gray-300">Source evidence:</strong><blockquote class="mt-1 p-2 border-l-4 border-gray-600 bg-gray-900 rounded text-gray-400 text-xs">${String(ob.source_evidence).replace(/</g, '&lt;').replace(/>/g, '&gt;')}</blockquote></div>` : ''}</div>`;
                html += `<div id="${infoId}" class="hidden obs-info-content">${modalContent}</div>`;
            }
        });
        html += '</div></details>';
    }
    html += '</div></details></div>';
    return html;
}

// Content is sourced from hidden divs populated by our own rendering code,
// where all observable values are already HTML-escaped via .replace(/<, >).
function showObservableInfoModal(contentId) {
    const el = document.getElementById(contentId);
    if (!el) return;
    const inner = el.innerHTML;
    const modal = document.createElement('div');
    modal.id = 'observableInfoModal';
    modal.className = 'fixed inset-0 bg-black/70 flex items-center justify-center z-[60]';
    modal.innerHTML = '<div class="bg-gray-800 border border-gray-600 rounded-lg p-4 max-w-lg max-h-[80vh] overflow-y-auto shadow-xl"><div class="flex justify-end mb-2"><button type="button" class="text-gray-400 hover:text-white" onclick="document.getElementById(\'observableInfoModal\').remove()">X</button></div><div class="observable-info-body"></div></div>';
    modal.querySelector('.observable-info-body').innerHTML = inner;
    modal.querySelector('button').onclick = () => modal.remove();
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
    document.body.appendChild(modal);
}
