/**
 * Standardized Similarity Display Component
 * 
 * Provides consistent rendering of similarity search results across all pages.
 * Handles data normalization and supports multiple display modes.
 */

/**
 * Normalizes similarity data structure to a consistent format.
 * Handles both direct properties and nested similarity_breakdown.
 * 
 * @param {Object} match - Raw similarity match data
 * @returns {Object} Normalized similarity data
 */
function normalizeSimilarityData(match) {
    // Extract atom_jaccard (check both locations)
    const atomJaccard = match.atom_jaccard !== undefined 
        ? match.atom_jaccard 
        : (match.similarity_breakdown?.atom_jaccard || 0);
    
    // Extract logic_shape_similarity (check both locations)
    const logicShape = match.logic_shape_similarity !== undefined
        ? match.logic_shape_similarity
        : match.similarity_breakdown?.logic_shape_similarity;
    
    // Extract weighted similarity (may be called 'similarity')
    const similarity = match.similarity !== undefined ? match.similarity : 0;
    
    // Calculate novelty score if not provided
    const noveltyScore = match.novelty_score !== undefined 
        ? match.novelty_score 
        : (1.0 - similarity);
    
    // Get novelty label if provided, otherwise calculate
    let noveltyLabel = match.novelty_label;
    if (!noveltyLabel) {
        noveltyLabel = calculateNoveltyLabel(similarity, atomJaccard, logicShape);
    }
    
    const logicVal = (logicShape !== null && logicShape !== undefined) ? logicShape : 0;
    const weightedBeforePenalties = match.weighted_before_penalties !== undefined
        ? match.weighted_before_penalties
        : (0.70 * atomJaccard + 0.30 * logicVal);
    const servicePenalty = match.service_penalty !== undefined ? match.service_penalty : 0;
    const filterPenalty = match.filter_penalty !== undefined ? match.filter_penalty : 0;

    const similarityEngine = match.similarity_engine || 'legacy';
    const semanticDetails = match.semantic_details || null;
    const reasonFlags = Array.isArray(semanticDetails?.reason_flags) ? semanticDetails.reason_flags : [];

    // For deterministic engine, derive novelty label from similarity thresholds when not special-case
    let resolvedNoveltyLabel = noveltyLabel;
    if (similarityEngine === 'deterministic' && !reasonFlags.includes('canonical_class_mismatch') &&
        !reasonFlags.includes('unsupported_sigma_feature') && !reasonFlags.includes('dnf_expansion_limit')) {
        if (similarity >= 0.75) resolvedNoveltyLabel = 'DUPLICATE';
        else if (similarity >= 0.50) resolvedNoveltyLabel = 'SIMILAR';
        else resolvedNoveltyLabel = 'NOVEL';
    }

    return {
        similarity: similarity,
        atom_jaccard: atomJaccard,
        logic_shape_similarity: logicShape,
        novelty_label: resolvedNoveltyLabel,
        novelty_score: noveltyScore,
        similarity_breakdown: {
            atom_jaccard: atomJaccard,
            logic_shape_similarity: logicShape
        },
        weighted_before_penalties: weightedBeforePenalties,
        service_penalty: servicePenalty,
        filter_penalty: filterPenalty,
        similarity_engine: similarityEngine,
        semantic_details: semanticDetails,
        reason_flags: reasonFlags,
        shared_atoms: [...new Set(match.shared_atoms || [])],
        added_atoms: [...new Set(match.added_atoms || [])],
        removed_atoms: [...new Set(match.removed_atoms || [])],
        filter_differences: [...new Set(match.filter_differences || [])]
    };
}

/**
 * Calculates novelty label based on similarity metrics.
 * Uses the same logic as backend classification.
 * 
 * @param {number} similarity - Weighted similarity (0-1)
 * @param {number} atomJaccard - Atom Jaccard similarity (0-1)
 * @param {number|null} logicShape - Logic shape similarity (0-1) or null
 * @returns {string} Novelty label: DUPLICATE, SIMILAR, or NOVEL
 */
function calculateNoveltyLabel(similarity, atomJaccard, logicShape) {
    // DUPLICATE: atom_jaccard > 0.95 AND logic_similarity > 0.95
    if (atomJaccard > 0.95 && logicShape !== null && logicShape !== undefined && logicShape > 0.95) {
        return 'DUPLICATE';
    }
    // SIMILAR: atom_jaccard > 0.80
    if (atomJaccard > 0.80) {
        return 'SIMILAR';
    }
    // NOVEL: everything else
    return 'NOVEL';
}

/**
 * Gets CSS classes for novelty label badge.
 * Deterministic engine: Duplicate=red, Similar=yellow, Novel=green. Legacy: current scheme.
 *
 * @param {string} noveltyLabel - Novelty label (DUPLICATE, SIMILAR, NOVEL)
 * @param {string} [similarityEngine] - 'deterministic' | 'legacy'
 * @returns {string} CSS class string
 */
function getNoveltyLabelClasses(noveltyLabel, similarityEngine) {
    if (similarityEngine === 'deterministic') {
        if (noveltyLabel === 'DUPLICATE') {
            return 'px-3 py-1 rounded text-sm font-semibold bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300';
        }
        if (noveltyLabel === 'SIMILAR') {
            return 'px-3 py-1 rounded text-sm font-semibold bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300';
        }
        return 'px-3 py-1 rounded text-sm font-semibold bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300';
    }
    if (noveltyLabel === 'DUPLICATE') {
        return 'px-3 py-1 rounded text-sm font-semibold bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300';
    }
    if (noveltyLabel === 'SIMILAR') {
        return 'px-3 py-1 rounded text-sm font-semibold bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300';
    }
    return 'px-3 py-1 rounded text-sm font-semibold bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300';
}

/**
 * Returns human-readable scoring mode label for semantic comparison (e.g. evaluator).
 *
 * @param {Object} semanticComparison - semantic_comparison object (may have similarity_engine)
 * @returns {string} "Deterministic (No LLM)" | "LLM / Embedding"
 */
function getScoringModeLabel(semanticComparison) {
    if (semanticComparison && semanticComparison.similarity_engine === 'deterministic') {
        return 'Deterministic (No LLM)';
    }
    return 'LLM / Embedding';
}

/**
 * Escapes HTML to prevent XSS.
 * 
 * @param {string} text - Text to escape
 * @returns {string} Escaped text
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Renders similarity display based on mode.
 * 
 * @param {Object} data - Similarity data (will be normalized)
 * @param {Object} options - Rendering options
 * @param {string} options.mode - Display mode: 'full', 'compact', or 'minimal'
 * @param {string} options.containerId - Optional container ID to render into (if provided, returns void)
 * @param {string} options.prefix - Optional prefix for element IDs (for multiple instances on same page)
 * @returns {string|void} HTML string if no containerId, void if rendering to container
 */
function renderSimilarityDisplay(data, options = {}) {
    const mode = options.mode || 'full';
    const prefix = options.prefix || '';
    const containerId = options.containerId;
    const ruleALabel = options.ruleALabel || 'Rule A';
    const ruleBLabel = options.ruleBLabel || 'Rule B';
    const includeExplainability = options.includeExplainability !== false; // Default true for full mode, can be enabled for compact
    
    // Normalize data
    const normalized = normalizeSimilarityData(data);
    
    const similarity = normalized.similarity;
    const similarityPercent = (similarity * 100).toFixed(1);
    const noveltyLabel = normalized.novelty_label;
    const noveltyScore = (normalized.novelty_score * 100).toFixed(1);
    const atomJaccard = normalized.atom_jaccard;
    const atomJaccardPercent = (atomJaccard * 100).toFixed(1);
    const logicShape = normalized.logic_shape_similarity;
    const logicShapePercent = logicShape !== null && logicShape !== undefined 
        ? (logicShape * 100).toFixed(1) + '%'
        : 'N/A';
    const hasLogicShape = logicShape !== null && logicShape !== undefined;

    const engine = normalized.similarity_engine || 'legacy';
    const reasonFlags = normalized.reason_flags || [];
    const canonicalMismatch = reasonFlags.includes('canonical_class_mismatch');
    const unsupportedOrDnf = reasonFlags.includes('unsupported_sigma_feature') || reasonFlags.includes('dnf_expansion_limit');
    const showNumericScore = !canonicalMismatch && !unsupportedOrDnf;
    const engineBadge = engine === 'deterministic'
        ? '<span class="px-2 py-0.5 rounded text-xs font-medium bg-slate-200 dark:bg-slate-600 text-slate-700 dark:text-slate-200">Deterministic Semantic Engine</span>'
        : '<span class="px-2 py-0.5 rounded text-xs font-medium bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-200">Legacy Heuristic Engine</span>';
    const jaccardVal = engine === 'deterministic' && normalized.semantic_details && normalized.semantic_details.jaccard != null
        ? normalized.semantic_details.jaccard
        : atomJaccard;
    const jaccardZeroDeterministic = engine === 'deterministic' && showNumericScore && jaccardVal === 0;
    let scoreDisplay = showNumericScore ? `${similarityPercent}%` : '';
    if (canonicalMismatch) scoreDisplay = 'Not Comparable (Different Telemetry Class)';
    else if (unsupportedOrDnf) scoreDisplay = 'Deterministic engine skipped (unsupported rule type)';
    else if (jaccardZeroDeterministic) scoreDisplay = 'No Shared Behavioral Atoms';
    const scoreClass = showNumericScore ? 'text-3xl font-bold text-blue-600 dark:text-blue-400' : 'text-lg font-semibold text-gray-500 dark:text-gray-400';
    
    let html = '';
    
    if (mode === 'full') {
        // Full mode: Progress bar, large similarity %, engine badge, novelty label, full breakdown, explainability
        html = `
            <!-- Overall Similarity & Novelty Classification -->
            <div class="mb-6">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-lg font-semibold text-gray-700 dark:text-gray-300">${engine === 'deterministic' ? 'Behavioral Similarity' : 'Weighted Similarity'}</span>
                    <div class="flex items-center space-x-4 flex-wrap gap-y-1">
                        <span id="${prefix}overallSimilarity" class="${scoreClass}" ${jaccardZeroDeterministic ? `title="Similarity: ${similarityPercent}% | Jaccard: 0% | Containment: ${normalized.semantic_details && normalized.semantic_details.containment_factor != null ? (normalized.semantic_details.containment_factor * 100).toFixed(1) : '—'}% | Filter penalty: ${normalized.semantic_details && normalized.semantic_details.filter_penalty != null ? (normalized.semantic_details.filter_penalty * 100).toFixed(1) : '0'}%"` : ''}>${escapeHtml(scoreDisplay)}</span>
                        <span id="${prefix}engineBadge">${engineBadge}</span>
                        <span id="${prefix}noveltyLabel" class="${getNoveltyLabelClasses(noveltyLabel, engine)}">${noveltyLabel}</span>
                    </div>
                </div>
                ${showNumericScore ? `
                <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4 mb-4">
                    <div id="${prefix}similarityBar" class="bg-blue-600 h-4 rounded-full transition-all duration-500" style="width: ${similarityPercent}%"></div>
                </div>
                ` : ''}
                ${engine !== 'deterministic' ? `
                <div class="text-sm text-gray-600 dark:text-gray-400">
                    <span>Novelty Score: </span>
                    <span id="${prefix}noveltyScore" class="font-semibold">${noveltyScore}%</span>
                </div>
                ` : ''}
                ${unsupportedOrDnf && normalized.similarity !== undefined ? `<div class="text-xs text-gray-500 dark:text-gray-400 mt-1">Fallback score (legacy): ${(normalized.similarity * 100).toFixed(1)}%</div>` : ''}
            </div>

            ${engine !== 'deterministic' ? `
            <!-- Behavioral Similarity Breakdown (Legacy engine only) -->
            <div class="mb-6">
                <h4 class="text-md font-semibold text-gray-700 dark:text-gray-300 mb-3">🔍 Behavioral Similarity Breakdown</h4>
                <div class="bg-blue-50 dark:bg-blue-900 border border-blue-200 dark:border-blue-700 rounded-lg p-4">
                    <div class="grid grid-cols-1 gap-2 text-sm">
                        <div class="flex justify-between">
                            <span class="text-gray-700 dark:text-gray-300">Atom Jaccard <span class="text-gray-500">(weight: 70%)</span>:</span>
                            <span id="${prefix}atomJaccard" class="font-medium text-blue-700 dark:text-blue-300">${atomJaccardPercent}%</span>
                        </div>
                        <div class="flex justify-between">
                            <span class="text-gray-700 dark:text-gray-300">Logic Shape <span class="text-gray-500">(weight: 30%)</span>:</span>
                            <span id="${prefix}logicShape" class="font-medium text-blue-700 dark:text-blue-300 ${!hasLogicShape ? 'italic text-gray-500 dark:text-gray-400' : ''}">${logicShapePercent}</span>
                        </div>
                        ${!hasLogicShape ? `
                        <div id="${prefix}logicShapeNA" class="text-xs text-gray-500 dark:text-gray-400 italic">
                            N/A - Logic shape not computed when all atoms are identical (proven event equivalence)
                        </div>
                        ` : `<div id="${prefix}logicShapeNA" class="hidden text-xs text-gray-500 dark:text-gray-400 italic"></div>`}
                        <div class="pt-2 border-t border-blue-200 dark:border-blue-700 flex justify-between">
                            <span class="text-gray-700 dark:text-gray-300 font-semibold">Weighted Total:</span>
                            <span id="${prefix}weightedTotal" class="font-medium text-blue-700 dark:text-blue-300">${similarityPercent}%</span>
                        </div>
                    </div>
                </div>
            </div>
            ` : ''}
            ${engine === 'deterministic' && normalized.semantic_details && !canonicalMismatch && !unsupportedOrDnf ? (() => {
                const sd = normalized.semantic_details;
                const j = (sd.jaccard != null ? (sd.jaccard * 100).toFixed(1) : '—') + '%';
                const c = sd.containment_factor != null ? (sd.containment_factor * 100).toFixed(1) + '%' : '—';
                const fp = sd.filter_penalty != null ? (sd.filter_penalty * 100).toFixed(1) + '%' : '—';
                const sa = sd.surface_score_a != null ? sd.surface_score_a.toFixed(2) : '—';
                const sb = sd.surface_score_b != null ? sd.surface_score_b.toFixed(2) : '—';
                const oa = sd.overlap_ratio_a != null ? (sd.overlap_ratio_a * 100).toFixed(1) + '%' : '—';
                const ob = sd.overlap_ratio_b != null ? (sd.overlap_ratio_b * 100).toFixed(1) + '%' : '—';
                const cc = escapeHtml(sd.canonical_class || '—');
                const rf = Array.isArray(sd.reason_flags) ? sd.reason_flags.join(', ') : '—';
                return `
            <!-- Semantic Breakdown (Deterministic Engine) - primary breakdown when deterministic -->
            <div class="mb-6">
                <details class="bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg" open>
                    <summary class="px-4 py-3 cursor-pointer text-md font-semibold text-gray-700 dark:text-gray-300 flex items-center gap-2">
                        🔍 Behavioral Similarity (Jaccard × Containment − Filter)
                        <span class="inline-flex items-center justify-center w-4 h-4 rounded-full bg-slate-300 dark:bg-slate-600 text-slate-600 dark:text-slate-300 text-xs cursor-help" title="Similarity = (Jaccard × Containment) − Filter Penalty">ℹ</span>
                    </summary>
                    <div class="px-4 pb-4 grid grid-cols-1 gap-2 text-sm">
                        <div class="flex justify-between"><span class="text-gray-600 dark:text-gray-400">Canonical class</span><span class="font-mono text-gray-800 dark:text-slate-100">${cc}</span></div>
                        ${sd.surface_score_a != null && sd.surface_score_b != null ? `
                        <div class="flex justify-between"><span class="text-gray-600 dark:text-gray-400">Surface (Current)</span><span class="text-gray-800 dark:text-slate-100">${sd.surface_score_a} branches</span></div>
                        <div class="flex justify-between"><span class="text-gray-600 dark:text-gray-400">Surface (Candidate)</span><span class="text-gray-800 dark:text-slate-100">${sd.surface_score_b} branches</span></div>
                        ` : ''}
                        <div class="flex justify-between"><span class="text-gray-600 dark:text-gray-400">Jaccard</span><span class="text-gray-800 dark:text-slate-100">${j}</span></div>
                        <div class="flex justify-between"><span class="text-gray-600 dark:text-gray-400">Containment factor</span><span class="text-gray-800 dark:text-slate-100">${c}</span></div>
                        <div class="flex justify-between"><span class="text-gray-600 dark:text-gray-400">Filter penalty</span><span class="text-gray-800 dark:text-slate-100">${fp}</span></div>
                        <div class="flex justify-between"><span class="text-gray-600 dark:text-gray-400">Overlap ratio A/B</span><span class="text-gray-800 dark:text-slate-100">${oa} / ${ob}</span></div>
                        ${rf !== '—' ? `<div class="flex justify-between"><span class="text-gray-600 dark:text-gray-400">Reason flags</span><span class="text-xs font-mono text-gray-800 dark:text-slate-100">${escapeHtml(rf)}</span></div>` : ''}
                    </div>
                </details>
            </div>`;
            })() : ''}

            <!-- Explainability -->
            <div id="${prefix}explainabilitySection" class="mb-6 ${normalized.shared_atoms.length > 0 || normalized.added_atoms.length > 0 || normalized.removed_atoms.length > 0 || normalized.filter_differences.length > 0 ? '' : 'hidden'}">
                <h4 class="text-md font-semibold text-gray-700 dark:text-gray-300 mb-3">📊 Explainability</h4>
                <div class="space-y-4">
                    ${normalized.shared_atoms.length > 0 ? `
                    <div id="${prefix}sharedAtomsSection">
                        <h5 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Shared Atoms:</h5>
                        <div id="${prefix}sharedAtoms" class="bg-green-50 dark:bg-green-900 border border-green-200 dark:border-green-700 rounded p-3 text-xs font-mono text-gray-900 dark:text-green-50">${escapeHtml(normalized.shared_atoms.join('\n'))}</div>
                    </div>
                    ` : `<div id="${prefix}sharedAtomsSection" class="hidden"></div>`}
                    ${normalized.removed_atoms.length > 0 ? `
                    <div id="${prefix}addedAtomsSection">
                        <h5 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Atoms in ${ruleALabel} (not in ${ruleBLabel}):</h5>
                        <div id="${prefix}addedAtoms" class="bg-yellow-50 dark:bg-yellow-900 border border-yellow-200 dark:border-yellow-700 rounded p-3 text-xs font-mono text-gray-900 dark:text-yellow-50">${escapeHtml(normalized.removed_atoms.join('\n'))}</div>
                    </div>
                    ` : `<div id="${prefix}addedAtomsSection" class="hidden"></div>`}
                    ${normalized.added_atoms.length > 0 ? `
                    <div id="${prefix}removedAtomsSection">
                        <h5 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Atoms in ${ruleBLabel} (not in ${ruleALabel}):</h5>
                        <div id="${prefix}removedAtoms" class="bg-orange-50 dark:bg-orange-900 border border-orange-200 dark:border-orange-700 rounded p-3 text-xs font-mono text-gray-900 dark:text-amber-50">${escapeHtml(normalized.added_atoms.join('\n'))}</div>
                    </div>
                    ` : `<div id="${prefix}removedAtomsSection" class="hidden"></div>`}
                    ${normalized.filter_differences.length > 0 ? `
                    <div id="${prefix}filterDifferencesSection">
                        <h5 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Filter Differences (NOT logic):</h5>
                        <div id="${prefix}filterDifferences" class="bg-purple-50 dark:bg-purple-900 border border-purple-200 dark:border-purple-700 rounded p-3 text-xs font-mono text-gray-900 dark:text-purple-50">${escapeHtml(normalized.filter_differences.join('\n'))}</div>
                    </div>
                    ` : `<div id="${prefix}filterDifferencesSection" class="hidden"></div>`}
                </div>
            </div>
        `;
    } else if (mode === 'compact') {
        // Compact mode: Engine badge, similarity %, breakdown grid, optionally semantic breakdown (deterministic), explainability
        const compactEngineBadge = engine === 'deterministic'
            ? '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-slate-200 dark:bg-slate-600 text-slate-700 dark:text-slate-200 mb-2">Deterministic Semantic Engine</span>'
            : '<span class="inline-block px-2 py-0.5 rounded text-xs font-medium bg-gray-200 dark:bg-gray-600 text-gray-700 dark:text-gray-200 mb-2">Legacy Heuristic Engine</span>';
        const showCompactDeterministic = engine === 'deterministic' && normalized.semantic_details && !canonicalMismatch && !unsupportedOrDnf;
        const compactDeterministicBlock = showCompactDeterministic ? (() => {
            const sd = normalized.semantic_details;
            const j = (sd.jaccard != null ? (sd.jaccard * 100).toFixed(1) : '—') + '%';
            const c = sd.containment_factor != null ? (sd.containment_factor * 100).toFixed(1) + '%' : '—';
            const cc = escapeHtml(sd.canonical_class || '—');
            const compactScoreDisplay = jaccardZeroDeterministic ? 'No Shared Behavioral Atoms' : similarityPercent + '%';
            const compactScoreTitle = jaccardZeroDeterministic ? `Similarity: ${similarityPercent}% | Jaccard: 0% | Containment: ${c} | Filter penalty: ${sd.filter_penalty != null ? (sd.filter_penalty * 100).toFixed(1) + '%' : '0%'}` : 'Similarity = (Jaccard × Containment) − Filter Penalty';
            const surfaceRows = sd.surface_score_a != null && sd.surface_score_b != null ? `
                    <span class="text-gray-600 dark:text-gray-400">Surface (Current)</span><span class="text-gray-800 dark:text-slate-100">${sd.surface_score_a} branches</span>
                    <span class="text-gray-600 dark:text-gray-400">Surface (Candidate)</span><span class="text-gray-800 dark:text-slate-100">${sd.surface_score_b} branches</span>
                ` : '';
            return `
            <div class="p-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded text-xs">
                <div class="font-bold text-slate-900 dark:text-slate-100 mb-2 flex items-center gap-1">
                    🔍 Behavioral Similarity
                    <span class="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-slate-300 dark:bg-slate-600 text-slate-600 dark:text-slate-300 text-[10px] cursor-help" title="Similarity = (Jaccard × Containment) − Filter Penalty">ℹ</span>
                </div>
                <div class="grid grid-cols-2 gap-1">
                    <span class="text-gray-600 dark:text-gray-400">Similarity</span><span class="font-medium text-blue-700 dark:text-blue-300" title="${escapeHtml(compactScoreTitle)}">${escapeHtml(compactScoreDisplay)}</span>
                    <span class="text-gray-600 dark:text-gray-400">Canonical class</span><span class="font-mono text-gray-800 dark:text-slate-100">${cc}</span>
                    ${surfaceRows}
                    <span class="text-gray-600 dark:text-gray-400">Jaccard</span><span class="text-gray-800 dark:text-slate-100">${j}</span>
                    <span class="text-gray-600 dark:text-gray-400">Containment</span><span class="text-gray-800 dark:text-slate-100">${c}</span>
                </div>
            </div>`;
        })() : '';
        const compactDeterministicFallback = engine === 'deterministic' && !showCompactDeterministic ? `
            <div class="p-2 bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded text-xs">
                <span class="font-semibold">Similarity: </span>
                <span class="font-medium ${showNumericScore ? 'text-blue-700 dark:text-blue-300' : 'text-gray-500 dark:text-gray-400'}">${escapeHtml(scoreDisplay)}</span>
            </div>` : '';
        const compactLegacyBlock = engine !== 'deterministic' ? `
            <div class="p-2 bg-blue-50 dark:bg-blue-900 border border-blue-200 dark:border-blue-700 rounded">
                <div class="text-xs font-bold text-blue-900 dark:text-blue-100 mb-2">🔍 Behavioral Similarity Breakdown:</div>
                <div class="grid grid-cols-2 gap-1 text-xs">
                    <div class="flex justify-between">
                        <span class="text-gray-700 dark:text-gray-300">Atom Jaccard <span class="text-gray-500">(weight: 70%)</span>:</span>
                        <span class="font-medium text-blue-700 dark:text-blue-300">${atomJaccardPercent}%</span>
                    </div>
                    <div class="flex justify-between">
                        <span class="text-gray-700 dark:text-gray-300">Logic Shape <span class="text-gray-500">(weight: 30%)</span>:</span>
                        <span class="font-medium text-blue-700 dark:text-blue-300">${logicShapePercent}</span>
                    </div>
                    <div class="col-span-2 pt-1 border-t border-blue-200 dark:border-blue-700 flex justify-between">
                        <span class="text-gray-700 dark:text-gray-300 font-semibold">Weighted Total:</span>
                        <span class="font-medium text-blue-700 dark:text-blue-300">${similarityPercent}%</span>
                    </div>
                </div>
            </div>` : '';
        const explainabilityHtml = includeExplainability && (normalized.shared_atoms.length > 0 || normalized.added_atoms.length > 0 || normalized.removed_atoms.length > 0 || normalized.filter_differences.length > 0) ? `
            <div class="mt-3 p-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded">
                <div class="text-xs font-bold text-gray-900 dark:text-gray-100 mb-2">📊 Explainability:</div>
                <div class="space-y-2 text-xs">
                    ${normalized.shared_atoms.length > 0 ? `
                        <div>
                            <div class="font-medium text-gray-700 dark:text-gray-300 mb-1">Shared Atoms:</div>
                            <div class="bg-green-50 dark:bg-green-900 border border-green-200 dark:border-green-700 rounded p-2 font-mono text-gray-900 dark:text-green-50 whitespace-pre-wrap">${escapeHtml(normalized.shared_atoms.join('\n'))}</div>
                        </div>
                    ` : ''}
                    ${normalized.removed_atoms.length > 0 ? `
                        <div>
                            <div class="font-medium text-gray-700 dark:text-gray-300 mb-1">Atoms in ${ruleALabel} (not in ${ruleBLabel}):</div>
                            <div class="bg-yellow-50 dark:bg-yellow-900 border border-yellow-200 dark:border-yellow-700 rounded p-2 font-mono text-gray-900 dark:text-yellow-50 whitespace-pre-wrap">${escapeHtml(normalized.removed_atoms.join('\n'))}</div>
                        </div>
                    ` : ''}
                    ${normalized.added_atoms.length > 0 ? `
                        <div>
                            <div class="font-medium text-gray-700 dark:text-gray-300 mb-1">Atoms in ${ruleBLabel} (not in ${ruleALabel}):</div>
                            <div class="bg-orange-50 dark:bg-orange-900 border border-orange-200 dark:border-orange-700 rounded p-2 font-mono text-gray-900 dark:text-amber-50 whitespace-pre-wrap">${escapeHtml(normalized.added_atoms.join('\n'))}</div>
                        </div>
                    ` : ''}
                    ${normalized.filter_differences.length > 0 ? `
                        <div>
                            <div class="font-medium text-gray-700 dark:text-gray-300 mb-1">Filter Differences (NOT logic):</div>
                            <div class="bg-purple-50 dark:bg-purple-900 border border-purple-200 dark:border-purple-700 rounded p-2 font-mono text-gray-900 dark:text-purple-50 whitespace-pre-wrap">${escapeHtml(normalized.filter_differences.join('\n'))}</div>
                        </div>
                    ` : ''}
                </div>
            </div>
        ` : '';
        
        html = `
            <div class="mt-3">
                <div class="mb-2">${compactEngineBadge}</div>
                ${compactDeterministicBlock || compactDeterministicFallback || compactLegacyBlock}
                ${explainabilityHtml}
            </div>
        `;
    } else {
        // Minimal mode: Just similarity % and label
        const minScoreText = canonicalMismatch ? 'Not comparable' : (unsupportedOrDnf ? 'Skipped (unsupported)' : similarityPercent + '%');
        const minScoreClass = showNumericScore ? 'text-blue-600 dark:text-blue-400' : 'text-gray-500 dark:text-gray-400';
        html = `
            <div class="text-sm">
                <span class="font-semibold">Similarity: </span>
                <span class="${minScoreClass}">${escapeHtml(minScoreText)}</span>
                <span class="${getNoveltyLabelClasses(noveltyLabel, engine)} ml-2">${noveltyLabel}</span>
            </div>
        `;
    }
    
    // If containerId provided, render into DOM
    if (containerId) {
        const container = document.getElementById(containerId);
        if (container) {
            container.innerHTML = html;
            // Update progress bar width if in full mode
            if (mode === 'full') {
                const bar = document.getElementById(`${prefix}similarityBar`);
                if (bar) {
                    bar.style.width = `${similarityPercent}%`;
                }
            }
            return;
        }
    }
    
    return html;
}

/**
 * Updates existing DOM elements with similarity data (for backward compatibility).
 * Useful when you have pre-existing HTML structure and just want to update values.
 * 
 * @param {Object} data - Similarity data (will be normalized)
 * @param {Object} options - Update options
 * @param {string} options.prefix - Prefix for element IDs
 */
function updateSimilarityDisplay(data, options = {}) {
    const prefix = options.prefix || '';
    const normalized = normalizeSimilarityData(data);
    
    // Helper to build element ID with proper camelCase handling
    const getId = (name) => {
        if (!prefix) return name;
        // Capitalize first letter of element name when prefix is present
        return prefix + name.charAt(0).toUpperCase() + name.slice(1);
    };
    
    // Debug: Log what we're looking for
    if (typeof console !== 'undefined' && console.log) {
        console.log('updateSimilarityDisplay called with prefix:', prefix);
        console.log('Normalized data:', normalized);
        console.log('Looking for element:', getId('overallSimilarity'));
    }
    
    const similarity = normalized.similarity || 0;
    const similarityPercent = (similarity * 100).toFixed(1);
    const noveltyLabel = normalized.novelty_label || 'NOVEL';
    const noveltyScore = (normalized.novelty_score || 0) * 100;
    const noveltyScorePercent = noveltyScore.toFixed(1);
    const atomJaccard = normalized.atom_jaccard || 0;
    const atomJaccardPercent = (atomJaccard * 100).toFixed(1);
    const logicShape = normalized.logic_shape_similarity;
    const hasLogicShape = logicShape !== null && logicShape !== undefined;
    
    // Update overall similarity
    const overallEl = document.getElementById(getId('overallSimilarity'));
    if (overallEl) overallEl.textContent = `${similarityPercent}%`;
    
    // Update similarity bar
    const barEl = document.getElementById(getId('similarityBar'));
    if (barEl) barEl.style.width = `${similarityPercent}%`;
    
    // Update novelty label
    const labelEl = document.getElementById(getId('noveltyLabel'));
    if (labelEl) {
        labelEl.textContent = noveltyLabel;
        labelEl.className = getNoveltyLabelClasses(noveltyLabel, normalized.similarity_engine);
    }
    
    // Update novelty score
    const scoreEl = document.getElementById(getId('noveltyScore'));
    if (scoreEl) scoreEl.textContent = `${noveltyScorePercent}%`;
    
    // Update atom jaccard
    const atomEl = document.getElementById(getId('atomJaccard'));
    if (atomEl) atomEl.textContent = `${atomJaccardPercent}%`;
    
    // Update logic shape
    const logicEl = document.getElementById(getId('logicShape'));
    const logicNAEl = document.getElementById(getId('logicShapeNA'));
    if (logicEl) {
        if (hasLogicShape) {
            logicEl.textContent = `${(logicShape * 100).toFixed(1)}%`;
            logicEl.classList.remove('italic', 'text-gray-500', 'dark:text-gray-400');
            if (logicNAEl) logicNAEl.classList.add('hidden');
        } else {
            logicEl.textContent = 'N/A';
            logicEl.classList.add('italic', 'text-gray-500', 'dark:text-gray-400');
            if (logicNAEl) logicNAEl.classList.remove('hidden');
        }
    }
    
    // Update weighted total: show formula result (70%×atom + 30%×logic); if penalties exist, show "X% − Y% penalties = Z%"
    const totalEl = document.getElementById(getId('weightedTotal'));
    if (totalEl) {
        const weightedSubtotal = normalized.weighted_before_penalties ?? (0.70 * atomJaccard + 0.30 * (logicShape != null ? logicShape : 0));
        const weightedSubtotalPercent = (weightedSubtotal * 100).toFixed(1);
        const totalPenalty = (normalized.service_penalty || 0) + (normalized.filter_penalty || 0);
        if (totalPenalty > 0) {
            const penaltiesPercent = (totalPenalty * 100).toFixed(1);
            totalEl.textContent = `${weightedSubtotalPercent}% − ${penaltiesPercent}% penalties = ${similarityPercent}%`;
        } else {
            totalEl.textContent = `${weightedSubtotalPercent}%`;
        }
    }
    
    // Update explainability sections
    if (normalized.shared_atoms && normalized.shared_atoms.length > 0) {
        const sharedSection = document.getElementById(getId('sharedAtomsSection'));
        const sharedContent = document.getElementById(getId('sharedAtoms'));
        if (sharedSection) sharedSection.classList.remove('hidden');
        if (sharedContent) sharedContent.textContent = normalized.shared_atoms.join('\n');
    } else {
        const sharedSection = document.getElementById(getId('sharedAtomsSection'));
        if (sharedSection) sharedSection.classList.add('hidden');
    }
    
    if (normalized.removed_atoms && normalized.removed_atoms.length > 0) {
        const addedSection = document.getElementById(getId('addedAtomsSection'));
        const addedContent = document.getElementById(getId('addedAtoms'));
        if (addedSection) addedSection.classList.remove('hidden');
        if (addedContent) addedContent.textContent = normalized.removed_atoms.join('\n');
    } else {
        const addedSection = document.getElementById(getId('addedAtomsSection'));
        if (addedSection) addedSection.classList.add('hidden');
    }
    
    if (normalized.added_atoms && normalized.added_atoms.length > 0) {
        const removedSection = document.getElementById(getId('removedAtomsSection'));
        const removedContent = document.getElementById(getId('removedAtoms'));
        if (removedSection) removedSection.classList.remove('hidden');
        if (removedContent) removedContent.textContent = normalized.added_atoms.join('\n');
    } else {
        const removedSection = document.getElementById(getId('removedAtomsSection'));
        if (removedSection) removedSection.classList.add('hidden');
    }
    
    if (normalized.filter_differences && normalized.filter_differences.length > 0) {
        const filterSection = document.getElementById(getId('filterDifferencesSection'));
        const filterContent = document.getElementById(getId('filterDifferences'));
        if (filterSection) filterSection.classList.remove('hidden');
        if (filterContent) filterContent.textContent = normalized.filter_differences.join('\n');
    } else {
        const filterSection = document.getElementById(getId('filterDifferencesSection'));
        if (filterSection) filterSection.classList.add('hidden');
    }
    
    // Show explainability section if any content exists
    const explainSection = document.getElementById(getId('explainabilitySection'));
    if (explainSection) {
        const hasContent = (normalized.shared_atoms && normalized.shared_atoms.length > 0) ||
                          (normalized.added_atoms && normalized.added_atoms.length > 0) ||
                          (normalized.removed_atoms && normalized.removed_atoms.length > 0) ||
                          (normalized.filter_differences && normalized.filter_differences.length > 0);
        if (hasContent) {
            explainSection.classList.remove('hidden');
        } else {
            explainSection.classList.add('hidden');
        }
    }
}

// Export functions for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        normalizeSimilarityData,
        calculateNoveltyLabel,
        renderSimilarityDisplay,
        updateSimilarityDisplay,
        getNoveltyLabelClasses,
        getScoringModeLabel,
        escapeHtml
    };
}
