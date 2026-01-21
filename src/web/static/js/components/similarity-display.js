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
    
    return {
        similarity: similarity,
        atom_jaccard: atomJaccard,
        logic_shape_similarity: logicShape,
        novelty_label: noveltyLabel,
        novelty_score: noveltyScore,
        similarity_breakdown: {
            atom_jaccard: atomJaccard,
            logic_shape_similarity: logicShape
        },
        // Preserve explainability data if present
        shared_atoms: match.shared_atoms || [],
        added_atoms: match.added_atoms || [],
        removed_atoms: match.removed_atoms || [],
        filter_differences: match.filter_differences || []
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
 * 
 * @param {string} noveltyLabel - Novelty label (DUPLICATE, SIMILAR, NOVEL)
 * @returns {string} CSS class string
 */
function getNoveltyLabelClasses(noveltyLabel) {
    if (noveltyLabel === 'DUPLICATE') {
        return 'px-3 py-1 rounded text-sm font-semibold bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300';
    } else if (noveltyLabel === 'SIMILAR') {
        return 'px-3 py-1 rounded text-sm font-semibold bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300';
    } else {
        return 'px-3 py-1 rounded text-sm font-semibold bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300';
    }
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
    
    let html = '';
    
    if (mode === 'full') {
        // Full mode: Progress bar, large similarity %, novelty label, full breakdown, explainability
        html = `
            <!-- Overall Similarity & Novelty Classification -->
            <div class="mb-6">
                <div class="flex items-center justify-between mb-2">
                    <span class="text-lg font-semibold text-gray-700 dark:text-gray-300">Weighted Similarity</span>
                    <div class="flex items-center space-x-4">
                        <span id="${prefix}overallSimilarity" class="text-3xl font-bold text-blue-600 dark:text-blue-400">${similarityPercent}%</span>
                        <span id="${prefix}noveltyLabel" class="${getNoveltyLabelClasses(noveltyLabel)}">${noveltyLabel}</span>
                    </div>
                </div>
                <div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-4 mb-4">
                    <div id="${prefix}similarityBar" class="bg-blue-600 h-4 rounded-full transition-all duration-500" style="width: ${similarityPercent}%"></div>
                </div>
                <div class="text-sm text-gray-600 dark:text-gray-400">
                    <span>Novelty Score: </span>
                    <span id="${prefix}noveltyScore" class="font-semibold">${noveltyScore}%</span>
                </div>
            </div>

            <!-- Behavioral Similarity Breakdown -->
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

            <!-- Explainability -->
            <div id="${prefix}explainabilitySection" class="mb-6 ${normalized.shared_atoms.length > 0 || normalized.added_atoms.length > 0 || normalized.removed_atoms.length > 0 || normalized.filter_differences.length > 0 ? '' : 'hidden'}">
                <h4 class="text-md font-semibold text-gray-700 dark:text-gray-300 mb-3">📊 Explainability</h4>
                <div class="space-y-4">
                    ${normalized.shared_atoms.length > 0 ? `
                    <div id="${prefix}sharedAtomsSection">
                        <h5 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Shared Atoms:</h5>
                        <div id="${prefix}sharedAtoms" class="bg-green-50 dark:bg-green-900 border border-green-200 dark:border-green-700 rounded p-3 text-xs font-mono text-gray-900 dark:text-gray-100">${escapeHtml(normalized.shared_atoms.join('\n'))}</div>
                    </div>
                    ` : `<div id="${prefix}sharedAtomsSection" class="hidden"></div>`}
                    ${normalized.removed_atoms.length > 0 ? `
                    <div id="${prefix}addedAtomsSection">
                        <h5 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Atoms in ${ruleALabel} (not in ${ruleBLabel}):</h5>
                        <div id="${prefix}addedAtoms" class="bg-yellow-50 dark:bg-yellow-900 border border-yellow-200 dark:border-yellow-700 rounded p-3 text-xs font-mono text-gray-900 dark:text-gray-100">${escapeHtml(normalized.removed_atoms.join('\n'))}</div>
                    </div>
                    ` : `<div id="${prefix}addedAtomsSection" class="hidden"></div>`}
                    ${normalized.added_atoms.length > 0 ? `
                    <div id="${prefix}removedAtomsSection">
                        <h5 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Atoms in ${ruleBLabel} (not in ${ruleALabel}):</h5>
                        <div id="${prefix}removedAtoms" class="bg-orange-50 dark:bg-orange-900 border border-orange-200 dark:border-orange-700 rounded p-3 text-xs font-mono text-gray-900 dark:text-gray-100">${escapeHtml(normalized.added_atoms.join('\n'))}</div>
                    </div>
                    ` : `<div id="${prefix}removedAtomsSection" class="hidden"></div>`}
                    ${normalized.filter_differences.length > 0 ? `
                    <div id="${prefix}filterDifferencesSection">
                        <h5 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Filter Differences (NOT logic):</h5>
                        <div id="${prefix}filterDifferences" class="bg-purple-50 dark:bg-purple-900 border border-purple-200 dark:border-purple-700 rounded p-3 text-xs font-mono text-gray-900 dark:text-gray-100">${escapeHtml(normalized.filter_differences.join('\n'))}</div>
                    </div>
                    ` : `<div id="${prefix}filterDifferencesSection" class="hidden"></div>`}
                </div>
            </div>
        `;
    } else if (mode === 'compact') {
        // Compact mode: Similarity %, breakdown grid, optionally explainability
        const explainabilityHtml = includeExplainability && (normalized.shared_atoms.length > 0 || normalized.added_atoms.length > 0 || normalized.removed_atoms.length > 0 || normalized.filter_differences.length > 0) ? `
            <div class="mt-3 p-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded">
                <div class="text-xs font-bold text-gray-900 dark:text-gray-100 mb-2">📊 Explainability:</div>
                <div class="space-y-2 text-xs">
                    ${normalized.shared_atoms.length > 0 ? `
                        <div>
                            <div class="font-medium text-gray-700 dark:text-gray-300 mb-1">Shared Atoms:</div>
                            <div class="bg-green-50 dark:bg-green-900 border border-green-200 dark:border-green-700 rounded p-2 font-mono text-gray-900 dark:text-gray-100 whitespace-pre-wrap">${escapeHtml(normalized.shared_atoms.join('\n'))}</div>
                        </div>
                    ` : ''}
                    ${normalized.removed_atoms.length > 0 ? `
                        <div>
                            <div class="font-medium text-gray-700 dark:text-gray-300 mb-1">Atoms in ${ruleALabel} (not in ${ruleBLabel}):</div>
                            <div class="bg-yellow-50 dark:bg-yellow-900 border border-yellow-200 dark:border-yellow-700 rounded p-2 font-mono text-gray-900 dark:text-gray-100 whitespace-pre-wrap">${escapeHtml(normalized.removed_atoms.join('\n'))}</div>
                        </div>
                    ` : ''}
                    ${normalized.added_atoms.length > 0 ? `
                        <div>
                            <div class="font-medium text-gray-700 dark:text-gray-300 mb-1">Atoms in ${ruleBLabel} (not in ${ruleALabel}):</div>
                            <div class="bg-orange-50 dark:bg-orange-900 border border-orange-200 dark:border-orange-700 rounded p-2 font-mono text-gray-900 dark:text-gray-100 whitespace-pre-wrap">${escapeHtml(normalized.added_atoms.join('\n'))}</div>
                        </div>
                    ` : ''}
                    ${normalized.filter_differences.length > 0 ? `
                        <div>
                            <div class="font-medium text-gray-700 dark:text-gray-300 mb-1">Filter Differences (NOT logic):</div>
                            <div class="bg-purple-50 dark:bg-purple-900 border border-purple-200 dark:border-purple-700 rounded p-2 font-mono text-gray-900 dark:text-gray-100 whitespace-pre-wrap">${escapeHtml(normalized.filter_differences.join('\n'))}</div>
                        </div>
                    ` : ''}
                </div>
            </div>
        ` : '';
        
        html = `
            <div class="mt-3 p-2 bg-blue-50 dark:bg-blue-900 border border-blue-200 dark:border-blue-700 rounded">
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
            </div>
            ${explainabilityHtml}
        `;
    } else {
        // Minimal mode: Just similarity % and label
        html = `
            <div class="text-sm">
                <span class="font-semibold">Similarity: </span>
                <span class="text-blue-600 dark:text-blue-400">${similarityPercent}%</span>
                <span class="${getNoveltyLabelClasses(noveltyLabel)} ml-2">${noveltyLabel}</span>
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
        labelEl.className = getNoveltyLabelClasses(noveltyLabel);
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
    
    // Update weighted total
    const totalEl = document.getElementById(getId('weightedTotal'));
    if (totalEl) totalEl.textContent = `${similarityPercent}%`;
    
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
        escapeHtml
    };
}
