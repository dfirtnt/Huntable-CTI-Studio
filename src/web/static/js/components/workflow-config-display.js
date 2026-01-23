/**
 * Workflow Configuration Display Component
 * 
 * Provides standardized rendering of the current agentic workflow configuration
 * across different pages of the Huntable CTI Studio.
 */

/**
 * Parses a UTC timestamp string into a local Date object.
 * @param {string} timestamp - ISO timestamp
 * @returns {Date}
 */
function parseUTCDate(timestamp) {
    if (!timestamp) return new Date();
    // If timestamp doesn't have timezone info, assume it's UTC and append 'Z'
    let ts = timestamp;
    if (!ts.endsWith('Z') && !ts.match(/[+-]\d{2}:\d{2}$/)) {
        ts = ts + 'Z';
    }
    return new Date(ts);
}

/**
 * Orders agent models by workflow execution order and assigns indentation levels.
 * @param {Array} models - Array of model objects {agent, model, provider, enabled}
 * @returns {Array} Ordered and annotated models
 */
function orderModelsByWorkflow(models) {
    // Define workflow execution order with QA agents immediately after their corresponding agents
    const workflowOrder = [
        'Rank',
        'RankAgentQA',
        'Extract',
        'CmdlineExtract',
        'CmdLineQA',
        'ProcTreeExtract',
        'ProcTreeQA',
        'HuntQueriesExtract',
        'HuntQueriesQA',
        'SIGMA',
        'OS Fallback'
    ];
    
    // Define first-level sub-agents (indent level 1)
    const firstLevelSubAgents = new Set([
        'CmdlineExtract',
        'ProcTreeExtract',
        'HuntQueriesExtract',
        'RankAgentQA'
    ]);
    
    // Define second-level sub-agents (indent level 2) - QA agents under Extract
    const secondLevelSubAgents = new Set([
        'CmdLineQA',
        'ProcTreeQA',
        'HuntQueriesQA'
    ]);
    
    // Create a map for quick lookup
    const orderMap = new Map();
    workflowOrder.forEach((agent, index) => {
        orderMap.set(agent, index);
    });
    
    // Sort models by workflow order
    return [...models].sort((a, b) => {
        const orderA = orderMap.get(a.agent) ?? 999;
        const orderB = orderMap.get(b.agent) ?? 999;
        return orderA - orderB;
    }).map(model => {
        let indentLevel = 0;
        if (secondLevelSubAgents.has(model.agent)) {
            indentLevel = 2;
        } else if (firstLevelSubAgents.has(model.agent)) {
            indentLevel = 1;
        }
        return {
            ...model,
            indent: indentLevel > 0,
            indentLevel: indentLevel
        };
    });
}

/**
 * Renders the configuration display into a specified container.
 * 
 * @param {Object} currentConfig - The configuration object from /api/workflow/config
 * @param {Object} options - Rendering options
 * @param {string} options.containerId - Container ID (default: 'configDisplay')
 * @param {Array} options.uiModels - Optional models from UI state to override config
 * @param {boolean} options.showVersion - Whether to show version (default: true)
 * @param {boolean} options.showThresholds - Whether to show thresholds (default: true)
 * @param {string} options.extraHtml - Optional extra HTML to inject before models
 */
function renderWorkflowConfigDisplay(currentConfig, options = {}) {
    const containerId = options.containerId || 'configDisplay';
    const configDisplay = document.getElementById(containerId);
    if (!configDisplay || !currentConfig) return;
    
    let selectedModels = [];
    
    // Use UI models if provided, otherwise fallback to config
    if (options.uiModels && options.uiModels.length > 0) {
        const orderedModels = orderModelsByWorkflow(options.uiModels);
        selectedModels = orderedModels.map(m => {
            const enabled = m.enabled !== undefined ? m.enabled : true;
            const badgeClass = enabled 
                ? 'px-1.5 py-0.5 text-[10px] rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                : 'px-1.5 py-0.5 text-[10px] rounded-full bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
            const badgeText = enabled ? 'Enabled' : 'Disabled';
            return {
                text: `${m.agent}: ${m.model} (${m.provider})`,
                indentLevel: m.indentLevel || 0,
                badge: `<span class="${badgeClass} ml-1.5">${badgeText}</span>`
            };
        });
    } else if (currentConfig.agent_models) {
        // Build from saved config
        const agentModels = currentConfig.agent_models;
        const modelsList = [];
        const qaEnabled = currentConfig.qa_enabled || {};
        
        // Helper to add agent to list
        const addAgent = (agentId, displayName, indentLevel = 0, enabled = true) => {
            const model = agentModels[agentId] || agentModels[`${agentId}_model`];
            if (!model) return;
            
            const provider = agentModels[`${agentId}_provider`] || 'lmstudio';
            const badgeClass = enabled 
                ? 'px-1.5 py-0.5 text-[10px] rounded-full bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                : 'px-1.5 py-0.5 text-[10px] rounded-full bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
            const badgeText = enabled ? 'Enabled' : 'Disabled';
            
            modelsList.push({
                text: `${displayName}: ${model} (${provider})`,
                indentLevel: indentLevel,
                badge: `<span class="${badgeClass} ml-1.5">${badgeText}</span>`
            });
        };

        // 1. Rank Agent
        if (agentModels.RankAgent) {
            addAgent('RankAgent', 'Rank', 0, currentConfig.rank_agent_enabled !== false);
        }
        
        // 2. RankAgentQA
        if (agentModels.RankAgentQA) {
            addAgent('RankAgentQA', 'RankAgentQA', 1, qaEnabled['RankAgent'] || false);
        }
        
        // 3. Extract Agent (supervisor)
        if (agentModels.ExtractAgent) {
            addAgent('ExtractAgent', 'Extract', 0, true);
        }
        
        // 4. Extract Sub-agents
        const subAgentOrder = [
            { id: 'CmdlineExtract', name: 'CmdlineExtract', qa: 'CmdLineQA' },
            { id: 'ProcTreeExtract', name: 'ProcTreeExtract', qa: 'ProcTreeQA' },
            { id: 'HuntQueriesExtract', name: 'HuntQueriesExtract', qa: 'HuntQueriesQA' }
        ];
        
        // Get disabled state if available
        const disabled = window.disabledExtractAgents || new Set();
        
        subAgentOrder.forEach(agent => {
            const isEnabled = !disabled.has(agent.id);
            addAgent(agent.id, agent.name, 1, isEnabled);
            
            // Add QA for this sub-agent
            if (agentModels[agent.qa]) {
                addAgent(agent.qa, agent.qa, 2, qaEnabled[agent.id] || false);
            }
        });
        
        // 5. SIGMA Agent
        if (agentModels.SigmaAgent) {
            addAgent('SigmaAgent', 'SIGMA', 0, true);
        }
        
        // 6. OS Fallback
        if (agentModels.OSDetectionAgent_fallback) {
            addAgent('OSDetectionAgent_fallback', 'OS Fallback', 0, true);
        }
        
        selectedModels = modelsList;
    }
    
    const modelsHtml = selectedModels.length > 0 
        ? `<div class="mt-2"><strong>Selected Models:</strong><ul class="list-disc list-inside ml-2 mt-1">${selectedModels.map(m => {
            let indentClass = '';
            if (m.indentLevel === 2) indentClass = 'ml-12';
            else if (m.indentLevel === 1) indentClass = 'ml-6';
            return `<li class="text-xs ${indentClass}">${m.text}${m.badge || ''}</li>`;
        }).join('')}</ul></div>`
        : '';
    
    const updatedDate = currentConfig.updated_at 
        ? parseUTCDate(currentConfig.updated_at).toLocaleString() 
        : 'N/A';

    let html = '<div class="space-y-1 text-gray-700 dark:text-gray-300">';
    if (options.showVersion !== false) {
        html += `<p><strong class="text-gray-900 dark:text-gray-100">Version:</strong> ${currentConfig.version || 'N/A'}</p>`;
    }
    if (options.showThresholds !== false) {
        html += `
            <p><strong class="text-gray-900 dark:text-gray-100">Ranking Threshold:</strong> ${currentConfig.ranking_threshold || 'N/A'}</p>
            <p><strong class="text-gray-900 dark:text-gray-100">Junk Filter Threshold:</strong> ${currentConfig.junk_filter_threshold || 'N/A'}</p>
            <p><strong class="text-gray-900 dark:text-gray-100">Similarity Threshold:</strong> ${currentConfig.similarity_threshold || 'N/A'}</p>
        `;
    }
    html += `<p><strong class="text-gray-900 dark:text-gray-100">Updated:</strong> ${updatedDate}</p>`;
    if (options.extraHtml) {
        html += options.extraHtml;
    }
    html += modelsHtml;
    html += '</div>';
    
    configDisplay.innerHTML = html;
}

// Export functions for use in other scripts
if (typeof window !== 'undefined') {
    window.renderWorkflowConfigDisplay = renderWorkflowConfigDisplay;
    window.parseUTCDate = parseUTCDate;
    window.orderModelsByWorkflow = orderModelsByWorkflow;
}
